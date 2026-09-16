from app.postprocess import extract_json_block, postprocess


def test_downgrade_error_without_evidence_and_recompute_grade():
    raw = {
        "summary": {"grade": "A", "counts": {"error": 9}},
        "findings": [
            {"id": "F1", "verdict": "오류 확인", "severity": "치명", "category": "계산",
             "quote": "x", "evidence": {"type": "none", "detail": ""}},
            {"id": "F2", "verdict": "error", "severity": "major", "category": "fact",
             "quote": "y", "evidence": {"type": "search", "detail": "출처 대조 결과 다름"}},
            {"id": "F3", "verdict": "confirmed", "severity": "minor", "category": "법령",
             "quote": "z", "evidence": {"type": "fetch", "detail": "조문 일치"}},
            {"verdict": "검증 불가", "category": "사실", "quote": "w", "evidence": {"type": "user_required", "detail": "내부 자료"}},
        ],
    }
    r = postprocess(raw)
    by_id = {f.id: f for f in r.findings}
    assert by_id["F1"].verdict == "suspect" and "downgraded_no_evidence" in by_id["F1"].flags
    assert by_id["F2"].verdict == "error" and by_id["F2"].category == "사실"
    assert by_id["F3"].severity is None
    assert by_id["F04"].verdict == "unverifiable"
    assert r.summary.counts.model_dump() == {"error": 1, "suspect": 1, "unverifiable": 1, "confirmed": 1}
    assert r.summary.grade == "B"           # 중대 1건 → B (모델의 A 무시)
    assert r.summary.model_grade == "A"
    assert r.summary.critical_suspects == 1
    assert [f.verdict for f in r.findings] == ["error", "suspect", "unverifiable", "confirmed"]


def test_grade_rules():
    def mk(sev, n):
        return [{"verdict": "error", "severity": sev, "quote": "q", "evidence": {"type": "recalc", "detail": "d"}} for _ in range(n)]
    assert postprocess({"findings": mk("major", 3)}).summary.grade == "C"
    assert postprocess({"findings": mk("critical", 1)}).summary.grade == "C"
    assert postprocess({"findings": mk("minor", 5)}).summary.grade == "A"
    assert postprocess({"summary": {"grade": "D"}, "findings": []}).summary.grade == "D"


def test_needs_evidence_flag():
    fs = [{"verdict": "unverifiable", "quote": "q", "evidence": {"type": "user_required", "detail": "x"}}] * 2 \
       + [{"verdict": "confirmed", "quote": "q", "evidence": {"type": "search", "detail": "x"}}] * 3
    assert postprocess({"findings": fs}).summary.needs_evidence_flag is True


def test_extract_json_block():
    text = "요약입니다.\n<result_json>\n{\"findings\": [], \"summary\": {\"grade\": \"A\"}}\n</result_json>"
    assert extract_json_block(text)["summary"]["grade"] == "A"
    assert extract_json_block("```json\n{\"findings\": []}\n```")["findings"] == []
    assert extract_json_block("no json here") is None
