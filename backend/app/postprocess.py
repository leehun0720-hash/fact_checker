"""모델 출력 후처리 — 스킬의 '검증자 6원칙' 중 코드로 강제할 수 있는 것을 강제한다.

- 근거 없는 '오류 확인'은 '의심'으로 강등 (원칙 2)
- 판정 건수와 등급은 findings에서 다시 계산 (모델 자기보고를 믿지 않음)
- 확인됨·검증 불가에는 심각도를 붙이지 않음
- 심각도순 정렬
"""
from __future__ import annotations

import json
import re
from typing import Any

from .schema import Finding, VerificationResult

VERDICT_ALIASES = {
    "error": "error", "오류": "error", "오류 확인": "error", "❌": "error", "false": "error",
    "suspect": "suspect", "의심": "suspect", "⚠️": "suspect", "doubtful": "suspect",
    "unverifiable": "unverifiable", "검증 불가": "unverifiable", "검증불가": "unverifiable", "❓": "unverifiable", "unknown": "unverifiable",
    "confirmed": "confirmed", "확인됨": "confirmed", "확인": "confirmed", "✅": "confirmed", "true": "confirmed",
}
SEVERITY_ALIASES = {
    "critical": "critical", "치명": "critical", "🔴": "critical", "high": "critical",
    "major": "major", "중대": "major", "🟠": "major", "medium": "major",
    "minor": "minor", "경미": "minor", "🟡": "minor", "low": "minor",
}
CATEGORY_ALIASES = {
    "계산": "계산", "calc": "계산", "calculation": "계산",
    "정합": "정합", "consistency": "정합", "내부정합": "정합",
    "사실": "사실", "fact": "사실",
    "출처": "출처", "source": "출처", "citation": "출처",
    "법령": "법령", "law": "법령", "legal": "법령",
    "의견": "의견", "opinion": "의견",
}
VERDICT_ORDER = {"error": 0, "suspect": 1, "unverifiable": 2, "confirmed": 3}
SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, None: 3}
NO_EVIDENCE_TYPES = {"", "none", "null", "n/a", "없음"}


def _norm(value: Any, table: dict[str, str], default: str | None) -> str | None:
    if value is None:
        return default
    key = str(value).strip()
    for k, v in table.items():
        if key.lower() == k.lower() or key.startswith(k):
            return v
    return default


def extract_json_block(text: str) -> dict | None:
    """최종 텍스트 응답의 <result_json> 블록(또는 ```json 펜스)에서 JSON을 꺼낸다. 파일 전달이 실패했을 때의 대체 경로."""
    m = re.search(r"<result_json>\s*(.*?)\s*</result_json>", text, re.S)
    candidates = [m.group(1)] if m else []
    candidates += re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    for c in candidates:
        try:
            data = json.loads(c)
            if isinstance(data, dict) and "findings" in data:
                return data
        except json.JSONDecodeError:
            continue
    return None


def normalize_finding(f: Finding, idx: int) -> Finding:
    f.id = f.id or f"F{idx:02d}"
    f.verdict = _norm(f.verdict, VERDICT_ALIASES, "unverifiable")
    f.severity = _norm(f.severity, SEVERITY_ALIASES, None)
    f.category = _norm(f.category, CATEGORY_ALIASES, "사실")

    ev_type = (f.evidence.type or "").strip().lower()
    has_evidence = ev_type not in NO_EVIDENCE_TYPES and bool((f.evidence.detail or "").strip())

    if f.verdict == "error" and not has_evidence:
        f.verdict = "suspect"
        f.flags.append("downgraded_no_evidence")
    if f.verdict == "confirmed" and not has_evidence:
        # 근거 없는 '확인됨'도 위험하다 (원칙 4). 판정은 두되 표시한다.
        f.flags.append("confirmed_without_evidence")

    if f.verdict in ("unverifiable", "confirmed"):
        f.severity = None
    elif f.severity is None:
        f.severity = "major"
        f.flags.append("severity_defaulted")
    return f


def compute_grade(findings: list[Finding], model_grade: str | None) -> str:
    critical = sum(1 for f in findings if f.verdict == "error" and f.severity == "critical")
    major = sum(1 for f in findings if f.verdict == "error" and f.severity == "major")
    if str(model_grade).strip().upper() == "D":
        return "D"  # '핵심 논거 검증 실패'는 모델 판단을 존중
    if critical >= 1 or major >= 3:
        return "C"
    if major >= 1:
        return "B"
    return "A"


def postprocess(raw: dict) -> VerificationResult:
    result = VerificationResult.model_validate(raw)
    result.findings = [normalize_finding(f, i + 1) for i, f in enumerate(result.findings)]
    result.findings.sort(key=lambda f: (VERDICT_ORDER[f.verdict], SEVERITY_ORDER[f.severity]))

    counts = result.summary.counts
    counts.error = sum(1 for f in result.findings if f.verdict == "error")
    counts.suspect = sum(1 for f in result.findings if f.verdict == "suspect")
    counts.unverifiable = sum(1 for f in result.findings if f.verdict == "unverifiable")
    counts.confirmed = sum(1 for f in result.findings if f.verdict == "confirmed")

    sev: dict[str, int] = {"critical": 0, "major": 0, "minor": 0}
    for f in result.findings:
        if f.verdict == "error" and f.severity:
            sev[f.severity] += 1
    result.summary.severity_counts = sev
    result.summary.critical_suspects = sum(
        1 for f in result.findings if f.verdict == "suspect" and f.severity == "critical"
    )
    result.summary.model_grade = (result.summary.grade or None)
    result.summary.grade = compute_grade(result.findings, result.summary.model_grade)

    total = len(result.findings)
    result.summary.needs_evidence_flag = bool(total and counts.unverifiable / total > 0.30)
    return result
