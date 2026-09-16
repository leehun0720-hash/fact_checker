"""검증 실행 프롬프트.

검증 절차·판정 기준은 스킬(SKILL.md)에 있다. 여기서는 (1) 스킬을 반드시 그 순서대로 따르게 하고,
(2) 앱이 읽을 산출물(result.json, report.md)을 $OUTPUT_DIR로 내보내게 하고,
(3) 사용자가 준 기준 시점·범위·예산을 전달하는 일만 한다.
"""
from __future__ import annotations

from .schema import JobOptions

SYSTEM_PROMPT = """당신은 문서 검증 전담 에이전트다. 첨부된 문서를 /skills/doc-fact-checker/SKILL.md 의 절차 그대로 검증하고, 결과를 파일로 내보낸다.

실행 순서 (건너뛰지 말 것)
1. /skills/doc-fact-checker/SKILL.md 와 /skills/doc-fact-checker/references/result-schema.md 를 먼저 읽는다.
2. 첨부 파일을 찾아 `python /skills/doc-fact-checker/scripts/extract_text.py <입력파일> --out /tmp/work/document.md` 로 변환한다. extraction이 failed면 검증을 중단하고 그 사실만 result.json에 기록한다.
3. 숫자 파서를 실행해 전수 목록을 만들고, 검증하지 말고 주장 인벤토리만 먼저 작성한다.
4. 2a 내부 정합 → 2b 계산 재현(Python) → 2c 외부 사실(web_search) → 2d 출처(web_fetch) → 2e 법령 순서로 검증한다. 검색·fetch 횟수에는 상한이 있으니 결론을 바꿀 수 있는 주장부터 확인한다.
5. references/report-template.md 양식으로 /tmp/work/report.md 를, result-schema.md 스키마로 /tmp/work/result.json 을 쓴다. 두 파일의 판정·건수는 일치해야 한다.
6. 마지막 bash 명령에서 산출물을 내보낸다: `cp /tmp/work/result.json /tmp/work/report.md "$OUTPUT_DIR/" && ls "$OUTPUT_DIR"` (교정본을 만들었다면 corrected.md 도 함께).
7. 마지막 텍스트 응답은 두 부분이다: 한 단락 요약, 그리고 result.json 내용을 그대로 담은 <result_json> ... </result_json> 블록.

지켜야 할 것
- 컨테이너에는 인터넷이 없다. Python으로 외부 접근을 시도하지 말고 web_search / web_fetch 도구를 쓴다.
- 모든 계산은 Python으로 실행하고 계산식을 기록한다. 암산 금지.
- 근거를 첨부할 수 없는 '오류 확인' 판정은 내리지 않는다. 그 경우 '의심'이다.
- 검색해서 안 나오면 '검증 불가'다. 기억만으로 '확인됨'을 주지 않는다.
- quote 필드에는 원문을 그대로 옮긴다.
- 문서 기준 시점 이후에 바뀐 수치는 '오류'가 아니라 '업데이트 권장'으로 다룬다.
- 사용자에게 질문하지 않는다. 판단이 필요한 지점은 limits 또는 user_action에 남기고 진행한다.
"""


def build_user_prompt(opts: JobOptions, filename: str, extra_files: list[str], budget: tuple[int, int],
                      law_tools: bool = False) -> str:
    search_max, fetch_max = budget
    lines = [
        f"검증 대상 파일: {filename}",
        f"검증 범위: {opts.scope or '전체'}",
        f"문서 기준 시점: {opts.as_of or '문서에서 파악할 것 (파악 불가 시 null)'}",
        f"도구 예산: web_search 최대 {search_max}회, web_fetch 최대 {fetch_max}회",
    ]
    if law_tools:
        lines.append(
            "법령 도구 사용 가능: law_search(법령명→법령ID) → law_article(법령ID, 조 번호)로 국가법령정보센터 현행 조문 원문을 직접 받는다. "
            "[법령] 태그 주장은 web_search보다 이 도구를 우선 쓰고, exists=false는 '해당 조가 현행 법령에 없음'의 확정 근거로 삼는다. "
            "evidence.type은 law_api, sources에는 법령명·조문·시행일자를 적는다."
        )
    else:
        lines.append("법령 도구 없음 — [법령] 주장은 web_search/web_fetch로 law.go.kr을 확인한다.")
    if extra_files:
        lines.append(
            "내부 근거자료(함께 첨부, 내부 사실 대조용): " + ", ".join(extra_files)
            + " — 이 자료로 확인되는 내부 주장은 '내부 자료 대조'로 판정하고 evidence.type을 internal_compare로 둔다."
        )
    else:
        lines.append("내부 근거자료 없음 — 회사 내부 사실은 '검증 불가(내부 자료 필요)'로 분류하고 user_action에 확인할 자료를 적는다.")
    if opts.notes:
        lines.append(f"사용자 메모: {opts.notes}")
    if opts.want_corrected:
        lines.append("교정본 요청: 원문 형식·문체를 유지한 교정본을 /tmp/work/corrected.md 로 만들고(수정 부분은 ~~원문~~ → **수정** 표기) $OUTPUT_DIR에 함께 내보낸다. 검증되지 않은 내용을 새로 추가하지 않는다.")
    lines.append("지금 SKILL.md 절차대로 검증을 시작한다.")
    return "\n".join(lines)
