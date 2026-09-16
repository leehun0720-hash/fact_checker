"""MOCK_VERIFIER=1 일 때 쓰는 샘플 결과. 프론트 개발·데모용이며 실제 검증이 아니다."""
from __future__ import annotations

import time

from .schema import Job, ToolEvent, Usage
from .verifier import RunOutcome

SAMPLE_RESULT = {
    "schema_version": "1.0",
    "document": {"name": "", "pages": 12, "chars": 18400, "as_of": "2026-06", "scope": "전체", "extraction": "ok"},
    "summary": {
        "grade": "C",
        "needs_evidence_flag": False,
        "text": "예산 표의 합계와 성장률 서술에서 재계산으로 확인된 오류가 있고, 인용된 통계 하나는 출처 기관 자료에서 찾을 수 없었습니다. 사업 배경과 법적 근거 서술은 확인되었습니다.",
        "counts": {},
    },
    "findings": [
        {"id": "F01", "verdict": "error", "severity": "critical", "category": "계산", "location": "4쪽 '예산 계획' 표",
         "quote": "합계 2.7억원", "issue": "항목 합계가 총계와 다릅니다.",
         "evidence": {"type": "recalc", "detail": "인건비 1.2억 + 장비 0.8억 + 운영 0.5억 = 2.5억원 (Python 실행)", "formula": "1.2e8 + 0.8e8 + 0.5e8 = 2.5e8", "sources": []},
         "fix": "합계 2.5억원 — 또는 누락 항목(0.2억원) 확인 후 추가", "user_action": None},
        {"id": "F02", "verdict": "error", "severity": "major", "category": "계산", "location": "6쪽 2문단",
         "quote": "3년간 100억에서 160억으로 성장해 연평균 20% 성장", "issue": "CAGR과 단순평균을 혼동했습니다.",
         "evidence": {"type": "recalc", "detail": "(160/100)^(1/3) − 1 = 16.96%", "formula": "(160/100)**(1/3)-1", "sources": []},
         "fix": "연평균 약 17% 성장(CAGR)", "user_action": None},
        {"id": "F03", "verdict": "error", "severity": "minor", "category": "정합", "location": "2쪽 요약 ↔ 7쪽 본문",
         "quote": "참여 기관 12개 / 참여 기관 13개", "issue": "같은 값이 두 곳에서 다르게 적혀 있습니다.",
         "evidence": {"type": "internal_compare", "detail": "요약 12개, 본문 표 13개 (문서 내 대조)", "formula": None, "sources": []},
         "fix": "본문 표 기준 13개로 통일 (표가 원자료이면)", "user_action": None},
        {"id": "F04", "verdict": "suspect", "severity": "major", "category": "출처", "location": "3쪽 1문단",
         "quote": "중소벤처기업부 2025년 조사에 따르면 중소기업의 73.4%가 AI를 도입했다",
         "issue": "출처 기관 공식 자료에서 해당 수치를 확인할 수 없습니다.",
         "evidence": {"type": "search", "detail": "중기부 2025년 실태조사 보도자료·통계 페이지 3건 확인. 73.4% 수치 미발견. 유사 조사(중기중앙회 2025)는 28.7%.", "formula": None,
                      "sources": [{"title": "중소벤처기업부 보도자료 목록", "url": "https://www.mss.go.kr", "published": None}]},
         "fix": None, "user_action": "원출처(보고서명·쪽수) 확보 또는 문장 삭제"},
        {"id": "F05", "verdict": "unverifiable", "severity": None, "category": "사실", "location": "9쪽 표",
         "quote": "당사 기존 계약 단가 500만원", "issue": "회사 내부 정보로 웹 검증 대상이 아닙니다.",
         "evidence": {"type": "user_required", "detail": "내부 계약서 대조 필요", "formula": None, "sources": []},
         "fix": None, "user_action": "계약서 단가 조항 대조"},
        {"id": "F06", "verdict": "error", "severity": "major", "category": "법령", "location": "5쪽",
         "quote": "지능정보화 기본법 제14조(지능정보사회 시행계획)",
         "issue": "조문 번호와 제목이 맞지 않습니다. 현행 제14조의 제목은 '공공지능정보화의 추진'입니다.",
         "evidence": {"type": "law_api", "detail": "국가법령정보센터 오픈API lawService(lawjosub) 조회: 법령ID 000028 제14조 = '공공지능정보화의 추진', 조문 시행일 2026-01-22. '시행계획'은 제7조(지능정보사회 시행계획).", "formula": None,
                      "sources": [{"title": "지능정보화 기본법 제14조 — 국가법령정보센터", "url": "https://www.law.go.kr", "published": "2026-01-22"}]},
         "fix": "지능정보화 기본법 제7조(지능정보사회 시행계획)", "user_action": None},
    ],
    "recalculations": [
        {"location": "4쪽 표", "doc_value": "2.7억", "recalc_value": "2.5억", "match": False, "formula": "1.2e8 + 0.8e8 + 0.5e8", "estimated": False},
        {"location": "6쪽", "doc_value": "20%", "recalc_value": "16.96%", "match": False, "formula": "(160/100)**(1/3)-1", "estimated": True},
        {"location": "8쪽 표", "doc_value": "5,000만", "recalc_value": "5,000만", "match": True, "formula": "5_000_000 * 10", "estimated": False},
    ],
    "recommendations": [
        "우선순위 1 — 4쪽 예산 표 합계 수정(누락 항목 여부 확인)",
        "우선순위 2 — 73.4% 통계의 원출처 확보, 없으면 삭제",
        "우선순위 3 — 내부 계약 단가는 계약서 대조 후 확정",
    ],
    "stats": {"python_runs": 4, "web_searches": 6, "web_fetches": 1},
    "limits": ["회사 내부 계약 조건·미공개 매출은 웹으로 검증할 수 없어 사용자 확인 목록에 올렸습니다."],
}

SAMPLE_REPORT = """# 문서 검증 보고서 (샘플)

| 항목 | 내용 |
|---|---|
| 검증 대상 | 샘플 문서 |
| 신뢰도 등급 | C — 주요 수정 후 재검토 필요 |

이 보고서는 MOCK_VERIFIER=1 상태에서 생성된 샘플입니다. 실제 검증 결과가 아닙니다.
"""


def run_mock(job: Job, on_progress) -> RunOutcome:
    steps = [
        ("editor", "view /skills/doc-fact-checker/SKILL.md"),
        ("bash", "python /skills/doc-fact-checker/scripts/extract_text.py input.pdf --out /tmp/work/document.md"),
        ("bash", "python /skills/doc-fact-checker/scripts/korean_number_parser.py /tmp/work/document.md --json"),
        ("bash", "python -c 'print(1.2e8 + 0.8e8 + 0.5e8)'"),
        ("web_search", "중소벤처기업부 2025 중소기업 AI 도입 실태조사"),
        ("law_api", 'law_search {"query": "지능정보화 기본법"}'),
        ("law_api", 'law_article {"law_id": "000028", "article": "14"}'),
        ("bash", 'cp /tmp/work/result.json /tmp/work/report.md "$OUTPUT_DIR/" && ls "$OUTPUT_DIR"'),
    ]
    job.status = "running"
    job.model = "mock"
    for tool, detail in steps:
        time.sleep(0.6)
        job.progress.append(ToolEvent(at=Job.now(), tool=tool, detail=detail))
        job.counters[tool] = job.counters.get(tool, 0) + 1
        on_progress(job)
    raw = dict(SAMPLE_RESULT)
    raw["document"] = {**SAMPLE_RESULT["document"], "name": job.filename,
                       "as_of": job.options.as_of or SAMPLE_RESULT["document"]["as_of"], "scope": job.options.scope}
    return RunOutcome(raw_result=raw, files={"report.md": SAMPLE_REPORT.encode("utf-8")},
                      events=list(job.progress), usage=Usage(rounds=1), final_text="")
