"""Claude API 요금표 — 검증 한 건의 비용을 usage로 계산한다.

출처: https://platform.claude.com/docs/en/about-claude/pricing (2026-09 확인)
단위: USD / 100만 토큰. 웹 검색은 회당 $0.01, 웹 fetch·코드 실행(검색과 함께 쓰면)은 무료.
모델이 표에 없으면 Opus 5 요금으로 계산한다(보수적).
"""
from __future__ import annotations

from .schema import Usage

# model → (기본 입력, 캐시 읽기, 캐시 쓰기(5분), 출력)
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5": (5.00, 0.50, 6.25, 25.00),
    "claude-opus-4-8": (5.00, 0.50, 6.25, 25.00),
    "claude-sonnet-5": (2.00, 0.20, 2.50, 10.00),
    "claude-haiku-4-5": (1.00, 0.10, 1.25, 5.00),
}
WEB_SEARCH_USD = 0.01  # $10 / 1,000회


def estimate_cost_usd(model: str | None, u: Usage) -> float:
    p = PRICES.get(model or "", PRICES["claude-opus-5"])
    base, cache_read, cache_write, out = p
    tokens = (u.input_tokens * base + u.cache_read_input_tokens * cache_read
              + u.cache_creation_input_tokens * cache_write + u.output_tokens * out) / 1_000_000
    return round(tokens + u.web_search_requests * WEB_SEARCH_USD, 4)
