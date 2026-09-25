"""
RPG Maker 번역 병합기 v5 (Verified Merger)

- line_index 로 번역 줄과 매핑을 1:1 연결 (페이지 내 순번에 의존하지 않음)
- 적용 전 원본 값이 original_key 로 시작하는지 대조 → 다르면 적용하지 않음
- 번역문의 제어문자 목록(모양·개수·순서)이 원본과 다르면 적용하지 않음
- 파일명·플러그인 메타데이터(note) 등 보호 경로는 적용하지 않음
- 원본 폴더는 건드리지 않고 출력 폴더에 복사본을 만들어 적용
- 건너뛴 항목은 merge_report.jsonl 에 사유와 함께 기록
"""
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "02_translate"))
from text_codec import tokens_of  # noqa: E402

PATH_TOKEN_RE = re.compile(r'\.([^.\[\]]+)|\[(\d+)\]')

# 번역하면 게임이 깨질 수 있는 키 (extractor.PROTECTED_KEYS 와 동일 + 최종 방어)
PROTECTED_KEYS = {
    "note", "faceName", "characterName", "battlerName", "tilesetNames",
    "title1Name", "title2Name", "parallaxName", "battleback1Name", "battleback2Name",
    "animation1Name", "animation2Name", "effectName", "locale",
    "bgm", "bgs", "me", "se", "sounds", "titleBgm", "battleBgm",
    "victoryMe", "defeatMe", "gameoverMe", "boat", "ship", "airship",
}
RISKY_CODES = {355, 655, 356, 357, 324, 108, 408, 118}


def parse_json_path(path: str) -> List[Any]:
    """'$.events[1].pages[0].list[5].parameters[0]' -> ['events', 1, 'pages', 0, ...]"""
    if not path.startswith("$"):
        raise ValueError(f"잘못된 경로: {path}")
    rest = path[1:]
    parts: List[Any] = []
    pos = 0
    while pos < len(rest):
        m = PATH_TOKEN_RE.match(rest, pos)
        if not m:
            raise ValueError(f"경로 해석 실패: {path}")
        parts.append(m.group(1) if m.group(1) is not None else int(m.group(2)))
        pos = m.end()
    if not parts:
        raise ValueError(f"빈 경로: {path}")
    return parts


def is_protected(mapping: Dict[str, Any]) -> bool:
    parts = parse_json_path(mapping["json_path"])
    keys = {p for p in parts if isinstance(p, str)}
    if keys & PROTECTED_KEYS:
        return True
    # 재귀 추출(code 0)로 잡힌 이벤트 명령 파라미터는 스크립트일 수 있음
    if mapping.get("command_code", 0) == 0 and "list" in keys and "parameters" in keys:
        return True
    return False


def is_risky(mapping: Dict[str, Any]) -> bool:
    if "type" in mapping:
        return str(mapping["type"]).startswith("risky_")
    return mapping.get("command_code", 0) in RISKY_CODES


class VerifiedMerger:
    def __init__(self, include_risky: bool = False):
        self.include_risky = include_risky
        self.mappings: List[Dict[str, Any]] = []
        self.translations: Dict[int, Dict[str, Any]] = {}
        self.report: List[Dict[str, Any]] = []
        self.stats: Counter = Counter()

    def load_mappings(self, mapping_path: Path):
        with open(mapping_path, 'r', encoding='utf-8') as f:
            self.mappings = json.load(f)["mappings"]
        for i, m in enumerate(self.mappings):
            if m["line_index"] != i:
                raise ValueError(f"mapping.json 의 line_index 가 연속적이지 않습니다 (위치 {i})")
        print(f"매핑 {len(self.mappings)}개 로드")

    def load_translations(self, path: Path):
        """번역 JSONL 로드. line_index 가 없으면(구버전 추출물) 매핑 순서로 복원"""
        items = [json.loads(l) for l in open(path, encoding='utf-8') if l.strip()]
        if not items:
            return

        if all("line_index" in it for it in items):
            indexed = [(it["line_index"], it) for it in items]
        else:
            risky_file = str(items[0].get("type", "")).startswith("risky_")
            candidates = [m["line_index"] for m in self.mappings if is_risky(m) == risky_file]
            if len(candidates) != len(items):
                raise ValueError(
                    f"{path.name}: 줄 수({len(items)})가 매핑({len(candidates)})과 다릅니다. "
                    "번역 파일이 잘렸거나 다른 추출 결과입니다."
                )
            indexed = list(zip(candidates, items))

        for idx, it in indexed:
            m = self.mappings[idx]
            if it.get("page_id") != m["page_id"]:
                raise ValueError(
                    f"{path.name}: line_index {idx} 의 page_id 가 매핑과 다릅니다 "
                    f"({it.get('page_id')} != {m['page_id']}). 줄 정렬이 어긋났습니다."
                )
            self.translations[idx] = it
        print(f"{path.name}: 번역 {len(indexed)}줄 로드")

    def _skip(self, m: Dict[str, Any], reason: str, **extra):
        self.stats[reason] += 1
        self.report.append({"line_index": m["line_index"], "source_file": m["source_file"],
                            "json_path": m["json_path"], "reason": reason, **extra})

    def _apply_one(self, data: Any, m: Dict[str, Any], new_text: str) -> bool:
        parts = parse_json_path(m["json_path"])
        try:
            parent = data
            for p in parts[:-1]:
                parent = parent[p]
            current = parent[parts[-1]]
        except (KeyError, IndexError, TypeError):
            self._skip(m, "경로 없음")
            return False

        if not isinstance(current, str):
            self._skip(m, "원본 값이 문자열 아님")
            return False
        if not current.startswith(m.get("original_key", "")):
            self._skip(m, "원문 불일치", expected=m.get("original_key"), actual=current[:20])
            return False
        if current == new_text:
            self.stats["변경 없음"] += 1
            return False
        if tokens_of(current) != tokens_of(new_text):
            self._skip(m, "제어문자 불일치", original=current, translated=new_text)
            return False

        parent[parts[-1]] = new_text
        return True

    def merge(self, data_dir: Path, output_dir: Path, report_path: Path = BASE_DIR / "output/merge_report.jsonl"):
        data_dir, output_dir = data_dir.resolve(), output_dir.resolve()
        if data_dir == output_dir:
            raise ValueError("출력 폴더는 원본 폴더와 달라야 합니다 (원본 보호)")

        # 파일별로 적용할 항목 모으기
        per_file: Dict[str, List[Dict[str, Any]]] = {}
        for m in self.mappings:
            t = self.translations.get(m["line_index"])
            if t is None:
                continue
            if is_risky(m) and not self.include_risky:
                self.stats["risky 제외"] += 1
                continue
            if is_protected(m):
                self._skip(m, "보호 경로")
                continue
            per_file.setdefault(m["source_file"], []).append(m)

        print(f"원본 복사: {data_dir} -> {output_dir}")
        shutil.copytree(data_dir, output_dir, dirs_exist_ok=True)

        applied = 0
        for filename, maps in per_file.items():
            src = data_dir / filename
            if not src.exists():
                for m in maps:
                    self._skip(m, "파일 없음")
                continue
            with open(src, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)

            changed = 0
            for m in maps:
                if self._apply_one(data, m, self.translations[m["line_index"]].get("text", "")):
                    changed += 1

            if changed:
                with open(output_dir / filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
            applied += changed
            print(f"  {filename}: {changed}/{len(maps)} 적용")

        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            for row in self.report:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        print(f"\n병합 완료: {applied}줄 적용")
        for reason, n in self.stats.most_common():
            print(f"  - {reason}: {n}")
        print(f"건너뛴 항목 상세: {report_path}")
        return applied


def main():
    import argparse
    parser = argparse.ArgumentParser(description="RPG Maker Verified Merger v5")
    parser.add_argument('--data-dir', required=True, type=Path, help='원본 게임 data 폴더 (수정하지 않음)')
    parser.add_argument('--output-dir', required=True, type=Path, help='번역이 적용된 data 폴더를 만들 위치')
    parser.add_argument('--mapping', type=Path, default=BASE_DIR / "output/mapping.json")
    parser.add_argument('--translations', type=Path, nargs='+',
                        default=[BASE_DIR / "output/translated_texts.txt"],
                        help='번역 JSONL 파일 (risky 번역본이 있으면 함께 지정)')
    parser.add_argument('--report', type=Path, default=BASE_DIR / "output/merge_report.jsonl",
                        help='건너뛴 항목 기록 파일')
    parser.add_argument('--include-risky', action='store_true', help='risky(스크립트·주석 등) 번역도 적용')
    args = parser.parse_args()

    merger = VerifiedMerger(include_risky=args.include_risky)
    merger.load_mappings(args.mapping)
    for path in args.translations:
        merger.load_translations(path)
    merger.merge(args.data_dir, args.output_dir, args.report)


if __name__ == "__main__":
    main()
