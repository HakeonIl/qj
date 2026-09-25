"""
RPG Maker 제어문자 코덱
LLM에게는 제어문자를 뺀 '순수 문장'만 보내고, 번역 후 코드로 원위치에 복원한다.

- 앞/뒤에 붙은 태그 (\\F[...], \\AA[N], \\FFF[...] 등): 떼어냈다가 원본 문자열 그대로 다시 붙임 → LLM은 아예 못 봄
- 문장 중간의 태그 (\\| \\! \\V[n] \\C[n] %1 등): {1}, {2} 자리표시자로 치환 → 번역 후 원본 문자열로 복원
- 줄바꿈: <br> 로 치환 (한 줄 한 항목 형식을 유지하기 위해)

태그 문자열은 LLM 응답에서 절대 가져오지 않는다. 복원 후에는 태그 목록(모양·개수·순서)이
원문과 완전히 같은지 다시 확인하고, 다르면 DecodeError 로 거부한다.
"""
import re
from dataclasses import dataclass, field
from typing import List

TAG_RE = re.compile(
    r'\\[A-Za-z]+\[[^\]]*\]'    # \C[1], \F[warau], \AA[N]
    r'|\\[A-Za-z]+<[^>]*>'      # 플러그인식 \X<...>
    r'|\\[{}!.|^<>$\\]'         # \! \. \| \^ \{ \} \\ 등
    r'|\\[A-Za-z]+'             # \G 등 인자 없는 코드
)
# 본문 중간에서 보존해야 하는 것: 제어문자 + 시스템 메시지 인자(%1 등)
# + 원문에 원래 있던 {숫자} (자리표시자와 헷갈리지 않도록 이것도 자리표시자로 감쌈)
TOKEN_RE = re.compile(TAG_RE.pattern + r'|%\d+|\{\d+\}')
# 루비 표기 {漢字|よみ} → 번역에는 읽기가 필요 없으므로 본문만 남김
RUBY_RE = re.compile(r'\{([^{}|]+)\|[^{}]*\}')
PLACEHOLDER_RE = re.compile(r'\{(\d+)\}')
BR = '<br>'

_KANA_RE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\uFF66-\uFF9F]')


@dataclass
class Encoded:
    original: str               # 원문 (최종 검증용)
    prefix: str                 # 앞에 붙은 태그 묶음
    core: str                   # LLM에 보낼 문장
    suffix: str                 # 뒤에 붙은 태그 묶음
    placeholders: List[str] = field(default_factory=list)   # {n} -> 원래 태그

    @property
    def needs_llm(self) -> bool:
        return bool(_KANA_RE.search(self.core) or re.search(r'[\u4E00-\u9FFF]', self.core))


def tokens_of(text: str) -> List[str]:
    """문자열 안의 제어문자·인자 목록 (순서 포함)"""
    return TOKEN_RE.findall(text)


def _split_edges(text: str):
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

    placeholders: List[str] = []

    def to_placeholder(m):
        placeholders.append(m.group(0))
        return '{%d}' % len(placeholders)

    core = TOKEN_RE.sub(to_placeholder, body)
    return Encoded(
        original=text,
        prefix=prefix,
        core=core.replace('\n', BR),
        suffix=suffix,
        placeholders=placeholders,
    )


class DecodeError(ValueError):
    pass


def validate(enc: Encoded, translated: str) -> str:
    """LLM 번역문 검증. 문제가 있으면 사유 문자열, 없으면 빈 문자열"""
    found = PLACEHOLDER_RE.findall(translated)
    expected = [str(i + 1) for i in range(len(enc.placeholders))]
    if found != expected:
        return f'자리표시자 불일치/순서 변경 (원문 {expected}, 번역 {found})'
    if '\\' in translated:
        return '번역문에 역슬래시(\\) 포함 — 새 제어문자가 생길 수 있음'
    if re.search(r'%\d', translated):
        return '번역문에 %숫자 포함'
    if translated.count(BR) != enc.core.count(BR):
        return f'줄바꿈 개수 불일치 (원문 {enc.core.count(BR)}, 번역 {translated.count(BR)})'
    if enc.needs_llm and _KANA_RE.search(translated):
        return '번역문에 일본어(가나)가 남아 있음'
    return ''


def decode(enc: Encoded, translated: str, check: bool = True) -> str:
    reason = validate(enc, translated) if check else ''
    if reason:
        raise DecodeError(reason)

    body = translated.replace(BR, '\n')
    body = PLACEHOLDER_RE.sub(lambda m: enc.placeholders[int(m.group(1)) - 1], body)
    result = enc.prefix + body + enc.suffix

    # 최종 안전장치: 태그 모양·개수·순서가 원문과 완전히 같아야 한다
    if tokens_of(result) != tokens_of(enc.original):
        raise DecodeError(f'태그 불일치 (원문 {tokens_of(enc.original)}, 결과 {tokens_of(result)})')
    return result
