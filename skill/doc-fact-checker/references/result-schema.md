# result.json 스키마 — 앱 연동용 구조화 결과

보고서(`report.md`)와 같은 내용을 기계가 읽을 수 있게 담는다. 앱은 이 파일만 읽으므로, 보고서에 있는 판정이 여기 빠지면 사용자에게 보이지 않는다.

## 규칙

- `findings`에는 검증한 **모든** 주장을 넣는다. 확인됨(`confirmed`)도 넣는다. 확인됨에도 근거를 남겨야 보고서 자체가 검증 가능해진다.
- `verdict`가 `error`인 항목은 `evidence.type`이 `none`일 수 없고 `evidence.detail`이 비어 있을 수 없다. 근거 없는 오류 판정은 앱이 자동으로 `suspect`로 강등한다.
- `quote`는 원문을 **그대로** 옮긴다. 요지로 바꿔 쓰지 않는다.
- `severity`는 `error`·`suspect`에만 붙인다. `unverifiable`·`confirmed`는 `null`.
- 숫자 검산은 `recalculations`에 계산식과 함께 전부 기록한다. 역산으로 추정한 계산식은 `estimated: true`.
- `summary.counts`와 `summary.grade`는 앱이 `findings`로부터 다시 계산해 대조한다. 어긋나면 앱의 계산이 우선한다.
- 문자열은 모두 한국어. 키는 아래와 정확히 같게 쓴다. 추가 키는 무시된다.

## 스키마

```json
{
  "schema_version": "1.0",
  "document": {
    "name": "파일명",
    "pages": 12,
    "chars": 34000,
    "as_of": "문서 기준 시점 (예: 2026-06, 미상이면 null)",
    "scope": "전체 | 숫자만 | 법령만 | 사용자가 지정한 범위 설명",
    "extraction": "ok | partial | failed"
  },
  "summary": {
    "grade": "A | B | C | D",
    "needs_evidence_flag": false,
    "text": "2~3문장 요약: 무엇이 문제이고 무엇이 건전한지",
    "counts": { "error": 0, "suspect": 0, "unverifiable": 0, "confirmed": 0 }
  },
  "findings": [
    {
      "id": "F01",
      "verdict": "error | suspect | unverifiable | confirmed",
      "severity": "critical | major | minor | null",
      "category": "계산 | 정합 | 사실 | 출처 | 법령 | 의견",
      "location": "4쪽 '예산 계획' 표",
      "quote": "원문 그대로",
      "issue": "무엇이 어떻게 문제인지 한두 문장",
      "evidence": {
        "type": "recalc | search | fetch | law_api | internal_compare | user_required | none",
        "detail": "재계산 결과, 검색된 출처의 해당 내용, 원문 대조 결과 등 재현 가능한 서술",
        "formula": "Python으로 실행한 계산식 (계산일 때만, 아니면 null)",
        "sources": [ { "title": "출처 제목", "url": "https://...", "published": "2025-03 (모르면 null)" } ]
      },
      "fix": "수정안 문장 (없으면 null)",
      "user_action": "사용자 확인이 필요한 경우 무엇을 확인해야 하는지 (없으면 null)"
    }
  ],
  "recalculations": [
    {
      "location": "4쪽 표",
      "doc_value": "2.7억",
      "recalc_value": "2.5억",
      "match": false,
      "formula": "1.2e8 + 0.8e8 + 0.5e8",
      "estimated": false
    }
  ],
  "recommendations": [ "우선순위 1 — ...", "우선순위 2 — ..." ],
  "stats": { "python_runs": 0, "web_searches": 0, "web_fetches": 0 },
  "limits": [ "검증하지 못한 영역이나 한계 (예: 내부 계약 조건은 웹 검증 불가)" ]
}
```

## 등급 산정 기준 (앱이 재계산)

| 등급 | 기준 |
|---|---|
| A | 치명 0, 중대 0 (경미만 소수) |
| B | 치명 0, 중대 1~2 |
| C | 치명 1 이상 또는 중대 3 이상 |
| D | 핵심 논거가 검증 실패 — 모델 판단. 모델이 D를 주면 앱도 D를 유지한다 |

`unverifiable`이 전체 findings의 30%를 넘으면 `needs_evidence_flag`를 `true`로 둔다.
