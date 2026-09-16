"""검증 보고서 PDF — result.normalized.json → HTML → Chromium(Playwright) → PDF.

기존 문서 제작 방식(HTML → Chromium, Pretendard)을 따른다. 보고서 본문은 모델이 쓴 report.md가 아니라
후처리된 result(강등·재계산 반영)를 기준으로 그린다. 화면과 PDF가 같은 판정을 말하게 하기 위해서다.
"""
from __future__ import annotations

import html
from datetime import datetime

from .schema import Finding, Job, VerificationResult

VERDICT = {"error": "오류 확인", "suspect": "의심", "unverifiable": "검증 불가", "confirmed": "확인됨"}
SEVERITY = {"critical": "치명", "major": "중대", "minor": "경미"}
GRADE_TITLE = {"A": "그대로 사용 가능", "B": "지적 항목 수정 후 사용 가능",
               "C": "주요 수정 후 재검토 필요", "D": "전면 재작성 권고"}
EVIDENCE = {"recalc": "재계산", "search": "웹 검색", "fetch": "원문 대조", "law_api": "법령 오픈API",
            "internal_compare": "문서 내 대조", "user_required": "내부 자료 필요", "none": "없음"}
FLAG = {"downgraded_no_evidence": "근거 없음 → 의심으로 강등", "confirmed_without_evidence": "근거 서술 없음",
        "severity_defaulted": "심각도 기본값 적용"}

CSS = """
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css");
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
:root { --ink:#1c2430; --muted:#5b6673; --line:#d3dae1; --error:#b42318; --suspect:#b54708; --unv:#5b6673; --ok:#067647; --primary:#1f3a5f; }
* { box-sizing: border-box; }
body { font-family: "Pretendard Variable", Pretendard, "Apple SD Gothic Neo", "Malgun Gothic", "Noto Sans KR", sans-serif;
       color: var(--ink); font-size: 10.5pt; line-height: 1.55; margin: 0; font-feature-settings: "tnum" 1; }
h1 { font-size: 20pt; margin: 0 0 4mm; letter-spacing: -0.01em; }
h2 { font-size: 13pt; margin: 9mm 0 3mm; padding-bottom: 1.5mm; border-bottom: 1px solid var(--ink); break-after: avoid; }
h3 { font-size: 11pt; margin: 5mm 0 2mm; break-after: avoid; }
p { margin: 0 0 2mm; }
.muted { color: var(--muted); }
.small { font-size: 9pt; }
.head { display: grid; grid-template-columns: 30mm 1fr; gap: 7mm; align-items: start; margin-bottom: 4mm; }
.stamp { width: 30mm; height: 30mm; border: 0.8mm solid var(--ink); border-radius: 1.5mm; display: grid; place-items: center;
         font-size: 22pt; font-weight: 800; position: relative; }
.stamp small { position: absolute; bottom: 1.6mm; left: 0; right: 0; text-align: center; font-size: 7pt; font-weight: 600; color: var(--muted); }
.stamp.A { color: var(--ok); border-color: var(--ok); } .stamp.B { color: var(--primary); border-color: var(--primary); }
.stamp.C { color: var(--suspect); border-color: var(--suspect); } .stamp.D { color: var(--error); border-color: var(--error); }
.gtitle { font-size: 14pt; font-weight: 700; }
table { width: 100%; border-collapse: collapse; font-size: 9.5pt; }
th, td { text-align: left; padding: 1.6mm 2mm; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; border-bottom: 1px solid var(--ink); }
td.num { white-space: nowrap; }
.meta td:first-child { color: var(--muted); width: 28mm; }
.counts { display: flex; gap: 8mm; margin-top: 3mm; font-size: 10pt; }
.counts b { margin-left: 1mm; }
.c-error { color: var(--error); } .c-suspect { color: var(--suspect); } .c-unv { color: var(--unv); } .c-ok { color: var(--ok); }
.flag { display: inline-block; margin-top: 2.5mm; padding: 1mm 2.5mm; border: 1px solid var(--suspect); color: var(--suspect); border-radius: 1mm; font-size: 9pt; font-weight: 600; }
.finding { border-left: 1.2mm solid var(--unv); padding: 2mm 0 2mm 4mm; margin: 0 0 4mm; break-inside: avoid; }
.finding.error { border-left-color: var(--error); } .finding.suspect { border-left-color: var(--suspect); } .finding.confirmed { border-left-color: var(--ok); }
.fhead { font-size: 9pt; color: var(--muted); display: flex; gap: 3mm; flex-wrap: wrap; }
.tag { font-weight: 700; padding: 0 1.5mm; border-radius: 0.8mm; }
.tag.error { color: var(--error); background: #fbeae8; } .tag.suspect { color: var(--suspect); background: #fbefe3; }
.tag.unverifiable { color: var(--unv); background: #eceff2; } .tag.confirmed { color: var(--ok); background: #e6f4ec; }
.tag.sev { border: 1px solid currentColor; background: transparent; }
blockquote { margin: 1.5mm 0; padding: 1.5mm 3mm; border-left: 0.5mm solid var(--line); background: #f6f8fa; }
dl { display: grid; grid-template-columns: 16mm 1fr; gap: 0.8mm 3mm; margin: 1.5mm 0 0; font-size: 9.5pt; }
dt { color: var(--muted); } dd { margin: 0; }
code { font-family: ui-monospace, Menlo, Consolas, "D2Coding", monospace; font-size: 8.8pt; }
ol.recs { margin: 0; padding-left: 5mm; } ol.recs li { margin-bottom: 1.2mm; }
.foot { margin-top: 10mm; padding-top: 2mm; border-top: 1px solid var(--line); font-size: 8.5pt; color: var(--muted); }
"""


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _finding_html(f: Finding) -> str:
    ev = f.evidence
    sev = f'<span class="tag sev {f.verdict}">{SEVERITY.get(f.severity or "", "")}</span>' if f.severity else ""
    srcs = "".join(
        f"<li>{_e(s.title or s.url)}{' — ' + _e(s.url) if s.url and s.title else ''}{' (' + _e(s.published) + ')' if s.published else ''}</li>"
        for s in ev.sources) if ev.sources else ""
    rows = [f'<dt>근거</dt><dd><span class="muted">{_e(EVIDENCE.get(ev.type, ev.type))}</span> {_e(ev.detail)}'
            f'{"<br><code>" + _e(ev.formula) + "</code>" if ev.formula else ""}'
            f'{"<ul class=\"small\" style=\"margin:1mm 0 0;padding-left:4mm\">" + srcs + "</ul>" if srcs else ""}</dd>']
    if f.fix:
        rows.append(f"<dt>수정안</dt><dd>{_e(f.fix)}</dd>")
    if f.user_action:
        rows.append(f"<dt>확인 요청</dt><dd>{_e(f.user_action)}</dd>")
    flags = f'<div class="small" style="color:var(--suspect);margin-top:1mm">{_e(" / ".join(FLAG.get(x, x) for x in f.flags))}</div>' if f.flags else ""
    return f"""
<div class="finding {f.verdict}">
  <div class="fhead"><span class="tag {f.verdict}">{VERDICT[f.verdict]}</span>{sev}<span>{_e(f.category)}</span><span>{_e(f.location)}</span><span style="margin-left:auto">{_e(f.id)}</span></div>
  {f'<blockquote>“{_e(f.quote)}”</blockquote>' if f.quote else ''}
  {f'<p>{_e(f.issue)}</p>' if f.issue else ''}
  <dl>{''.join(rows)}</dl>{flags}
</div>"""


def render_html(job: Job, r: VerificationResult, generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now().astimezone()
    c, s = r.summary.counts, r.summary.severity_counts or {}
    errors = [f for f in r.findings if f.verdict == "error"]
    suspects = [f for f in r.findings if f.verdict == "suspect"]
    unv = [f for f in r.findings if f.verdict == "unverifiable"]
    confirmed = [f for f in r.findings if f.verdict == "confirmed"]

    def table(fs: list[Finding]) -> str:
        if not fs:
            return '<p class="muted">해당 없음</p>'
        body = "".join(
            f"<tr><td>{_e(f.id)}</td><td>{_e(f.location)}</td><td>“{_e(f.quote)}”</td><td>{VERDICT[f.verdict]}</td>"
            f"<td>{_e(f.issue or f.evidence.detail)}</td><td>{_e(f.user_action or f.fix or '')}</td></tr>" for f in fs)
        return f"<table><thead><tr><th>#</th><th>위치</th><th>원문</th><th>분류</th><th>사유</th><th>권장 조치</th></tr></thead><tbody>{body}</tbody></table>"

    recalc = "".join(
        f"<tr><td>{_e(x.location)}</td><td class=num>{_e(x.doc_value)}</td><td class=num>{_e(x.recalc_value)}</td>"
        f"<td class='{'c-ok' if x.match else 'c-error'}'><b>{'—' if x.match is None else ('일치' if x.match else '불일치')}</b></td>"
        f"<td><code>{_e(x.formula)}</code>{' <span class=muted>(추정)</span>' if x.estimated else ''}</td></tr>"
        for x in r.recalculations) or "<tr><td colspan=5 class=muted>재계산한 수치 없음</td></tr>"

    means = f"Python 재계산 {r.stats.python_runs}건, 웹 검색 {job.usage.web_search_requests or r.stats.web_searches}회, 원문 대조 {job.usage.web_fetch_requests or r.stats.web_fetches}건"
    if job.counters.get("law_api"):
        means += f", 법령 오픈API {job.counters['law_api']}회"

    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>문서 검증 보고서 — {_e(r.document.name or job.filename)}</title><style>{CSS}</style></head>
<body>
<h1>문서 검증 보고서</h1>
<div class="head">
  <div class="stamp {r.summary.grade}">{r.summary.grade}<small>신뢰도</small></div>
  <div>
    <div class="gtitle">{GRADE_TITLE.get(r.summary.grade, '')}</div>
    <p>{_e(r.summary.text)}</p>
    <div class="counts"><span class="c-error">오류 확인<b>{c.error}</b></span><span class="c-suspect">의심<b>{c.suspect}</b></span><span class="c-unv">검증 불가<b>{c.unverifiable}</b></span><span class="c-ok">확인됨<b>{c.confirmed}</b></span></div>
    {f'<div class="small muted">오류 중 치명 {s.get("critical", 0)}, 중대 {s.get("major", 0)}, 경미 {s.get("minor", 0)}</div>' if c.error else ''}
    {'<div class="flag">근거 보강 필요 — 검증하지 못한 주장이 30%를 넘습니다</div>' if r.summary.needs_evidence_flag else ''}
  </div>
</div>
<table class="meta">
  <tr><td>검증 대상</td><td>{_e(r.document.name or job.filename)}{f' ({r.document.pages}쪽' + (f', {r.document.chars:,}자' if r.document.chars else '') + ')' if r.document.pages else ''}</td></tr>
  <tr><td>검증 일자</td><td>{generated_at:%Y-%m-%d}</td></tr>
  <tr><td>문서 기준 시점</td><td>{_e(r.document.as_of or job.options.as_of or '문서에서 파악하지 못함')}</td></tr>
  <tr><td>검증 범위</td><td>{_e(r.document.scope or job.options.scope)}</td></tr>
  <tr><td>사용 수단</td><td>{_e(means)}</td></tr>
  {f'<tr><td>내부 근거자료</td><td>{_e(", ".join(job.extra_files))}</td></tr>' if job.extra_files else ''}
</table>

<h2>1. 오류 목록 (심각도순)</h2>
{''.join(_finding_html(f) for f in errors) or '<p class="muted">재현 가능한 근거로 확인된 오류가 없습니다.</p>'}

<h2>2. 의심 항목</h2>
{''.join(_finding_html(f) for f in suspects) or '<p class="muted">해당 없음</p>'}

<h2>3. 검증 불가 항목 (사용자 확인 필요)</h2>
{table(unv)}

<h2>4. 수치 검산표</h2>
<table><thead><tr><th>위치</th><th>문서 값</th><th>재계산 값</th><th>일치</th><th>계산식</th></tr></thead><tbody>{recalc}</tbody></table>

<h2>5. 확인된 주장</h2>
{''.join(_finding_html(f) for f in confirmed) or '<p class="muted">해당 없음</p>'}

<h2>6. 권장 조치</h2>
{('<ol class="recs">' + ''.join(f'<li>{_e(x)}</li>' for x in r.recommendations) + '</ol>') if r.recommendations else '<p class="muted">없음</p>'}

{('<h2>7. 검증 한계</h2><ul class=small>' + ''.join(f'<li>{_e(x)}</li>' for x in r.limits) + '</ul>') if r.limits else ''}

<div class="foot">TEN AI Doc Fact Checker · 작업 {_e(job.id)} · 모델 {_e(job.model or '')} · 생성 {generated_at:%Y-%m-%d %H:%M}<br>
'오류 확인'은 재현 가능한 근거(재계산·출처 원문·법령 원문)가 있는 항목에만 붙습니다. 근거가 없는 지적은 '의심'으로 표시됩니다.</div>
</body></html>"""


def html_to_pdf(doc: str) -> bytes:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PDF 생성에는 playwright가 필요합니다: pip install playwright && playwright install chromium") from exc
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(doc, wait_until="networkidle")  # 폰트 CDN 로드 대기
            return page.pdf(format="A4", print_background=True, prefer_css_page_size=True,
                            display_header_footer=True,
                            header_template="<span></span>",
                            footer_template='<div style="width:100%;font-size:8px;color:#5b6673;padding:0 16mm;display:flex;justify-content:space-between;">'
                                            '<span>문서 검증 보고서</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
        finally:
            browser.close()
