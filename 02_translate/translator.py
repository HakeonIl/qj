"""
RPG Maker 번역기 v3 (토큰 최소화)

LLM에게는 제어문자를 뺀 순수 문장만, 중복 없이, 짧은 `ID|화자|원문` 형식으로 보낸다.
- 제어문자: text_codec 이 떼어냈다가 코드로 복원 (LLM이 태그를 망가뜨릴 수 없음)
- 중복 제거: 같은 문장은 한 번만 번역
- 고정 번역: glossary 의 고정_번역과 정확히 일치하면 LLM 호출 없이 치환
- 줄 단위 검증: 실패한 줄만 모아서 재요청 (배치 전체 재시도 X)
- 캐시: 번역된 문장은 cache 파일에 저장 → 중단 후 재실행 시 이어서 진행
"""
import os
import json
import re
import asyncio
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional

import aiohttp

from text_codec import encode, decode, validate, Encoded

BASE_DIR = Path(__file__).resolve().parent.parent
LINE_RE = re.compile(r'^\s*(\d+)\s*\|(.*)$')


class Unit:
    """LLM에 보낼 번역 단위 (중복 제거된 문장 하나)"""
    def __init__(self, uid: int, enc: Encoded, speaker: str):
        self.uid = uid
        self.enc = enc
        self.speaker = speaker
        self.result: Optional[str] = None
        self.last_error = ''


class Translator:
    def __init__(self, config_path: Path = BASE_DIR / "config/config.json", base_path: Path = BASE_DIR):
        self.base_path = Path(base_path)
        self.config = self._load_json(Path(config_path))
        self.settings = self.config.get("translation_settings", {})
        self.fixed, glossary_text = self._load_glossary()
        self.system_prompt = self._build_system_prompt(glossary_text)
        self.client_session: Optional[aiohttp.ClientSession] = None
        self.semaphore = asyncio.Semaphore(self.settings.get("max_concurrent", 8))
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}

    @staticmethod
    def _load_json(path: Path, default=None):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            if default is not None:
                return default
            raise

    def _load_glossary(self):
        glossary = self._load_json(self.base_path / "config/glossary.json", {})
        fixed = dict(glossary.get("고정_번역", {})) if isinstance(glossary, dict) else {}
        for k in (glossary.get("번역_안함", []) if isinstance(glossary, dict) else []):
            fixed[k] = k
        return fixed, "\n".join(f"{k} = {v}" for k, v in fixed.items()) or "(없음)"

    def _build_system_prompt(self, glossary_text: str) -> str:
        # 말투 설정은 캐릭터당 한 줄로 압축. 매 요청 동일한 앞부분이라 API의 프롬프트 캐시에 걸린다.
        patterns = self._load_json(self.base_path / "config/character_speech_patterns.json", {})
        speech_lines = []
        for name, info in patterns.get("characters", {}).items():
            ko = self.fixed.get(name, name)
            tone = info.get("prompt_summary") or info.get("default_speaking_tone", "")
            speech_lines.append(f"- {name}({ko}): {tone}")
        template = (self.base_path / "02_translate/prompt_compact.md").read_text(encoding='utf-8')
        # str.format 은 {1} 자리표시자와 충돌하므로 replace 사용
        return (template.replace("{glossary_text}", glossary_text)
                        .replace("{speech_text}", "\n".join(speech_lines) or "(없음)"))

    # ---------- LLM 호출 ----------

    async def _get_client_session(self) -> aiohttp.ClientSession:
        if self.client_session is None or self.client_session.closed:
            self.client_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300))
        return self.client_session

    async def close(self):
        if self.client_session:
            await self.client_session.close()

    async def _call_llm(self, user_prompt: str) -> str:
        model_key = self.config.get("translator_model", "deepseek")
        model_config = self.config["models"][model_key]
        api_key = model_config.get("api_key") or os.environ.get(f"{model_key.upper()}_API_KEY", "")
        endpoint = model_config["endpoint"].rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"

        payload = {
            "model": model_config["model_name"],
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.settings.get("temperature", 0.3),
            "stream": False,
        }
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

        session = await self._get_client_session()
        async with self.semaphore:
            async with session.post(endpoint, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"API Error {resp.status}: {await resp.text()}")
                data = await resp.json()
        usage = data.get("usage") or {}
        self.usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
        self.usage["completion_tokens"] += usage.get("completion_tokens", 0)
        self.usage["requests"] += 1
        return data["choices"][0]["message"]["content"]

    # ---------- 배치 번역 ----------

    @staticmethod
    def build_user_prompt(units: List[Unit]) -> str:
        return "\n".join(f"{u.uid}|{u.speaker}|{u.enc.core}" for u in units)

    @staticmethod
    def parse_response(text: str) -> Dict[int, str]:
        out: Dict[int, str] = {}
        for line in text.splitlines():
            m = LINE_RE.match(line.strip().strip('`'))
            if m:
                out.setdefault(int(m.group(1)), m.group(2).strip())
        return out

    async def translate_units(self, units: List[Unit]):
        """배치를 번역하고, 검증에 통과한 줄은 확정. 실패한 줄은 남겨둔다."""
        try:
            parsed = self.parse_response(await self._call_llm(self.build_user_prompt(units)))
        except Exception as e:
            for u in units:
                u.last_error = f"요청 실패: {e}"
            return
        for u in units:
            if u.uid not in parsed:
                u.last_error = "응답에 해당 ID 없음"
                continue
            reason = validate(u.enc, parsed[u.uid])
            if reason:
                u.last_error = reason
            else:
                u.result = parsed[u.uid]

    async def translate_all(self, units: List[Unit], batch_size: int, max_retries: int,
                            on_progress=None):
        pending = units
        for attempt in range(max_retries + 1):
            if not pending:
                break
            # 재시도는 작은 배치로 → 모델이 헷갈릴 여지를 줄임
            size = batch_size if attempt == 0 else max(5, batch_size // (2 ** attempt))
            batches = [pending[i:i + size] for i in range(0, len(pending), size)]
            print(f"[{attempt + 1}회차] {len(pending)}문장 / {len(batches)}배치 (배치당 {size})")

            async def run(batch):
                await self.translate_units(batch)
                if on_progress:
                    on_progress(batch)

            await asyncio.gather(*(run(b) for b in batches))
            pending = [u for u in pending if u.result is None]

        return pending

    # ---------- 파일 처리 ----------

    async def process_file(self, input_file: Path, output_file: Path, batch_size: int, max_retries: int):
        lines = [json.loads(l) for l in open(input_file, encoding='utf-8') if l.strip()]
        cache_path = output_file.with_suffix(".cache.json")
        cache: Dict[str, str] = self._load_json(cache_path, {})

        encs = [encode(item.get("text", "")) for item in lines]
        units_by_core: Dict[str, Unit] = {}
        for item, enc in zip(lines, encs):
            core = enc.core
            if not enc.needs_llm or core in self.fixed or core in cache or core in units_by_core:
                continue
            units_by_core[core] = Unit(len(units_by_core) + 1, enc, item.get("speaker") or "")
        units = list(units_by_core.values())

        src_chars = sum(len(item.get("text", "")) for item in lines)
        send_chars = sum(len(u.enc.core) for u in units)
        print(f"입력 {len(lines)}줄 ({src_chars:,}자) → LLM 전송 {len(units)}문장 ({send_chars:,}자), "
              f"캐시 {len(cache)}문장 재사용")

        def save_cache(batch):
            for u in batch:
                if u.result is not None:
                    cache[u.enc.core] = u.result
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
            tmp.replace(cache_path)

        failed = await self.translate_all(units, batch_size, max_retries, on_progress=save_cache)

        # 원래 줄 순서대로 복원
        failed_log = []
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            for item, enc in zip(lines, encs):
                new_item = dict(item)
                core = enc.core
                translated = self.fixed.get(core, cache.get(core))
                if enc.needs_llm and translated is None:
                    failed_log.append({**item, "error": units_by_core[core].last_error})
                elif enc.needs_llm:
                    new_item["text"] = decode(enc, translated)
                f.write(json.dumps(new_item, ensure_ascii=False) + "\n")

        failed_path = output_file.with_name(output_file.stem + ".failed.jsonl")
        with open(failed_path, 'w', encoding='utf-8') as f:
            for row in failed_log:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        print(f"완료: {output_file} / 실패 {len(failed)}문장 ({len(failed_log)}줄, 원문 유지) → {failed_path}")
        print(f"토큰 사용량: {self.usage}")


async def main():
    parser = argparse.ArgumentParser(description="RPG Maker Translator (token-minimized)")
    parser.add_argument("--input-file", type=Path, default=BASE_DIR / "output/japanese_texts.txt")
    parser.add_argument("--output-file", type=Path, default=BASE_DIR / "output/translated_texts.txt")
    parser.add_argument("--batch-size", type=int, default=60, help="요청 1회당 문장 수")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="API 호출 없이 전송될 프롬프트만 출력")
    args = parser.parse_args()

    translator = Translator()
    if args.dry_run:
        lines = [json.loads(l) for l in open(args.input_file, encoding='utf-8') if l.strip()][:args.batch_size]
        units = [Unit(i + 1, encode(x["text"]), x.get("speaker") or "") for i, x in enumerate(lines)]
        units = [u for u in units if u.enc.needs_llm]
        print("=== system ===\n" + translator.system_prompt)
        print("=== user ===\n" + Translator.build_user_prompt(units))
        return

    try:
        await translator.process_file(args.input_file, args.output_file, args.batch_size, args.max_retries)
    finally:
        await translator.close()


if __name__ == "__main__":
    asyncio.run(main())
