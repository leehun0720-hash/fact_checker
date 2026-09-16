#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
korean_number_parser.py — 한국어 문서 숫자 전수 추출·정규화 도구

문서 검증 1단계(주장 인벤토리)에서 실행한다. 문서의 모든 숫자 표현을 찾아
표준 값으로 정규화하고 줄 번호·문맥과 함께 출력한다. 눈으로 훑을 때 생기는
누락을 막고, 검산·내부 정합성 대조의 입력 자료를 만든다.

사용법:
    python korean_number_parser.py <파일경로>          # 표 출력
    python korean_number_parser.py <파일경로> --json   # JSON 출력

지원: 1,234 / 45.2% / 3.5%p / 500만원 / 3억 5,000만원 / 1조 2,345억 / 120만 명
주의: 날짜(2026-08-01), 시각, 전화번호, 영문 단위(M/B)는 일반 숫자로 잡히므로
      문맥(CONTEXT)을 보고 사람이 걸러낸다. '제3조' 같은 법령 조문 번호는
      자동으로 [조문] 태그가 붙는다.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

MAG = {"조": 10**12, "억": 10**8, "만": 10**4, "천": 10**3}

NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
CHAIN = rf"(?:(?:{NUM})\s*[조억만천]\s*)+(?:{NUM})?|(?:{NUM})"
SUFFIX = r"%p|퍼센트포인트|%|퍼센트|원|달러|명|건|개|년|월|일|회|배|시간|평|㎡|호|항"
PATTERN = re.compile(rf"(?P<chain>{CHAIN})\s*(?P<suffix>(?:{SUFFIX})?)")

TOKEN = re.compile(rf"({NUM})\s*([조억만천])?")


def parse_chain(chain: str) -> float:
    """'3억 5,000만' 같은 연쇄 표현을 하나의 수치로 환산한다."""
    total = 0.0
    for m in TOKEN.finditer(chain):
        num = float(m.group(1).replace(",", ""))
        mag = m.group(2)
        total += num * MAG[mag] if mag else num
    return total


def classify(value, suffix, before_text):
    """단위 분류. 연도·조문 등 '수량이 아닌 숫자'를 구분해 검산 대상에서 제외할 수 있게 한다."""
    if re.search(r"제\s*$", before_text):
        return "조문(법령)"
    if suffix in ("%", "퍼센트"):
        return "%"
    if suffix in ("%p", "퍼센트포인트"):
        return "%p"
    if suffix == "년" and 1900 <= value <= 2100:
        return "연도"
    if suffix == "원":
        return "원"
    if suffix == "달러":
        return "달러"
    return suffix or "(단위없음)"


def fmt(value: float) -> str:
    """정규화 값을 읽기 좋게 표시한다 (원화는 억/만 병기)."""
    if value == int(value):
        base = f"{int(value):,}"
    else:
        base = f"{value:,.4f}".rstrip("0").rstrip(".")
    if value >= 10**8:
        return f"{base} ({value/10**8:,.4g}억)"
    if value >= 10**4:
        return f"{base} ({value/10**4:,.4g}만)"
    return base


def extract(text: str):
    results = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if re.match(r"\s*<!--.*-->\s*$", line):
            continue  # extract_text.py가 넣은 페이지·표 위치 표식은 숫자가 아니다
        for m in PATTERN.finditer(line):
            chain = m.group("chain")
            if not chain or not chain.strip():
                continue
            suffix = m.group("suffix") or ""
            value = parse_chain(chain)
            before = line[max(0, m.start() - 12): m.start()]
            unit = classify(value, suffix, before)
            if unit == "조문(법령)":
                # '제3조'의 3은 조 단위 환산 대상이 아니다
                head = re.match(NUM, chain.strip())
                value = float(head.group(0).replace(",", "")) if head else value
            ctx_s = max(0, m.start() - 22)
            ctx_e = min(len(line), m.end() + 22)
            results.append({
                "line": lineno,
                "raw": (chain + suffix).strip(),
                "value": value,
                "unit": unit,
                "context": ("…" if ctx_s > 0 else "") + line[ctx_s:ctx_e].strip()
                           + ("…" if ctx_e < len(line) else ""),
            })
    return results


def duplicates(results):
    """같은 값이 여러 곳에 등장하는 그룹 — 내부 정합성 대조의 출발점."""
    groups = defaultdict(list)
    for r in results:
        if r["unit"] in ("연도", "조문(법령)"):
            continue
        groups[(r["value"], r["unit"])].append(r)
    return {k: v for k, v in groups.items() if len(v) >= 2}


def main():
    ap = argparse.ArgumentParser(description="한국어 문서 숫자 추출·정규화")
    ap.add_argument("file", help="대상 텍스트/마크다운 파일")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = ap.parse_args()

    path = Path(args.file)
    if not path.exists():
        sys.exit(f"파일을 찾을 수 없습니다: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    results = extract(text)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print(f"# 숫자 추출 결과 — {path.name} (총 {len(results)}건)\n")
    print(f"{'줄':>4} | {'원문 표기':<16} | {'정규화 값':<26} | {'단위':<8} | 문맥")
    print("-" * 100)
    for r in results:
        print(f"{r['line']:>4} | {r['raw']:<16} | {fmt(r['value']):<26} | {r['unit']:<8} | {r['context']}")

    dups = duplicates(results)
    if dups:
        print(f"\n# 동일 값 다중 표기 그룹 ({len(dups)}개) — 내부 정합성 대조 후보")
        for (value, unit), items in sorted(dups.items(), key=lambda x: -x[0][0]):
            lines = ", ".join(f"{i['line']}줄({i['raw']})" for i in items)
            print(f"  값 {fmt(value)} [{unit}] × {len(items)}회 → {lines}")
    print("\n※ 연도·조문·날짜성 숫자는 검산 대상에서 제외하고, 문맥을 확인해 수동으로 걸러낼 것.")


if __name__ == "__main__":
    main()
