"""
RPG Maker 제어문자 코덱
LLM에게는 제어문자를 뺀 '순수 문장'만 보내고, 번역 후 코드로 원위치에 복원한다.

- 앞/뒤에 붙은 태그 (\\F[...], \\AA[N], \\FFF[...] 등): 떼어냈다가 그대로 다시 붙임 → LLM은 아예 못 봄
- 문장 중간의 대기 코드 (\\| \\! \\. \\^): 제거 후 번역문의 비슷한 위치(구두점 기준)에 다시 삽입 → LLM은 아예 못 봄
- 문장 중간의 의미 있는 태그 (\\V[n], \\C[n], \\N[n] 등): {1}, {2} 자리표시자로 치환 → 번역 후 검증·복원
- 줄바꿈: <br> 로 치환 (한 줄 한 항목 형식을 유지하기 위해)
"""
import re
from dataclasses import dataclass, field
from typing import List, Tuple

TAG_RE = re.compile(
    r'\\[A-Za-z]+\[[^\]]*\]'    # \C[1], \F[warau], \AA[N]
    r'|\\[A-Za-z]+<[^>]*>'      # 플러그인식 \X<...>
    r'|\\[{}!.|^<>$\\]'         # \! \. \| \^ \{ \} \\ 등
    r'|\\[A-Za-z]+'             # \G 등 인자 없는 코드
)
# 본문 중간에서 보존해야 하는 것: 제어문자 + 시스템 메시지 인자(%1 등)
TOKEN_RE = re.compile(TAG_RE.pattern + r'|%\d+')
# 루비 표기 {漢字|よみ} → 번역에는 읽기가 필요 없으므로 본문만 남김
RUBY_RE = re.compile(r'\{([^{}|]+)\|[^{}]*\}')
WAIT_CODES = {'\\|', '\\!', '\\.', '\\^'}
PLACEHOLDER_RE = re.compile(r'\{(\d+)\}')
BR = '<br>'

# 대기 코드를 다시 꽂을 때 선호하는 위치 (이 문자 바로 뒤)
_BREAK_CHARS = set('、。，,.!！?？…‥♥♡～~」』）)')
_KANA_RE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\uFF66-\uFF9F]')


@dataclass
class Encoded:
    prefix: str                 # 앞에 붙은 태그 묶음
    core: str                   # LLM에 보낼 문장
    suffix: str                 # 뒤에 붙은 태그 묶음
    placeholders: List[str] = field(default_factory=list)          # {n} -> 원래 태그
    waits: List[Tuple[float, str]] = field(default_factory=list)   # (상대 위치, 대기 코드)

    @property
    def needs_llm(self) -> bool:
        return bool(_KANA_RE.search(self.core) or re.search(r'[\u4E00-\u9FFF]', self.core))


def _split_edges(text: str) -> Tuple[str, str, str]:
    """앞/뒤 태그 묶음과 가운데 본문을 분리"""
    pos = 0
    while True:
        m = TAG_RE.match(text, pos)
        if m:
            pos = m.end()
        elif pos < len(text) and text[pos] in ' \u3000':
            pos += 1
        else:
            break
    prefix, rest = text[:pos], text[pos:]

    end = len(rest)
    while end > 0:
        tail = rest[:end]
        if tail[-1] in ' \u3000':
            end -= 1
            continue
        found = None
        for m in TAG_RE.finditer(tail):
            if m.end() == end:
                found = m
        if found:
            end = found.start()
        else:
            break
    return prefix, rest[:end], rest[end:]


def encode(text: str) -> Encoded:
    prefix, body, suffix = _split_edges(text)
    body = RUBY_RE.sub(r'\1', body)

    core_parts: List[str] = []
    placeholders: List[str] = []
    waits: List[Tuple[int, str]] = []
    core_len = 0
    last = 0
    for m in TOKEN_RE.finditer(body):
        chunk = body[last:m.start()]
        core_parts.append(chunk)
        core_len += len(chunk)
        tag = m.group(0)
        if tag in WAIT_CODES:
            waits.append((core_len, tag))
        else:
            placeholders.append(tag)
            ph = '{%d}' % len(placeholders)
            core_parts.append(ph)
            core_len += len(ph)
        last = m.end()
    core_parts.append(body[last:])
    core = ''.join(core_parts)
    total = max(len(core), 1)

    return Encoded(
        prefix=prefix,
        core=core.replace('\n', BR),
        suffix=suffix,
        placeholders=placeholders,
        waits=[(p / total, tag) for p, tag in waits],
    )


class DecodeError(ValueError):
    pass


def _wait_position(text: str, rel: float) -> int:
    """상대 위치 근처에서 구두점 바로 뒤를 찾는다. 없으면 비율 위치."""
    target = round(rel * len(text))
    best, best_dist = target, None
    for i, ch in enumerate(text):
        if ch in _BREAK_CHARS:
            cand = i + 1
            # 연속 구두점(…… 등)은 끝까지 넘어간다
            while cand < len(text) and text[cand] in _BREAK_CHARS:
                cand += 1
            dist = abs(cand - target)
            if best_dist is None or dist < best_dist:
                best, best_dist = cand, dist
    if best_dist is not None and best_dist <= max(4, len(text) // 4):
        return best
    return min(max(target, 0), len(text))


def validate(enc: Encoded, translated: str) -> str:
    """번역문 검증. 문제가 있으면 사유 문자열, 없으면 빈 문자열"""
    found = PLACEHOLDER_RE.findall(translated)
    expected = [str(i + 1) for i in range(len(enc.placeholders))]
    if sorted(found) != expected:
        return f'자리표시자 불일치 (원문 {expected}, 번역 {found})'
    if translated.count(BR) != enc.core.count(BR):
        return f'줄바꿈 개수 불일치 (원문 {enc.core.count(BR)}, 번역 {translated.count(BR)})'
    if enc.needs_llm and _KANA_RE.search(translated):
        return '번역문에 일본어(가나)가 남아 있음'
    return ''


def decode(enc: Encoded, translated: str, check: bool = True) -> str:
    reason = validate(enc, translated) if check else ''
    if reason:
        raise DecodeError(reason)

    text = translated.replace(BR, '\n')

    # 대기 코드는 자리표시자 복원 전에 꽂는다 (태그 길이가 위치 계산을 흐리지 않도록)
    for rel, tag in sorted(enc.waits, key=lambda w: w[0], reverse=True):
        pos = _wait_position(text, rel)
        text = text[:pos] + tag + text[pos:]

    text = PLACEHOLDER_RE.sub(lambda m: enc.placeholders[int(m.group(1)) - 1], text)
    return enc.prefix + text + enc.suffix
