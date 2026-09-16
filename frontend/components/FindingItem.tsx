import { SEVERITY_LABEL, VERDICT_LABEL, type Finding } from "@/lib/types";

const EVIDENCE_LABEL: Record<string, string> = {
  recalc: "재계산", search: "웹 검색", fetch: "원문 대조", law_api: "법령 오픈API", internal_compare: "문서 내 대조",
  user_required: "내부 자료 필요", none: "없음",
};
const FLAG_TEXT: Record<string, string> = {
  downgraded_no_evidence: "모델은 '오류'로 판정했지만 재현 가능한 근거가 없어 '의심'으로 낮췼습니다.",
  confirmed_without_evidence: "'확인됨'인데 근거 서술이 비어 있습니다. 판정을 그대로 믿지 마세요.",
  severity_defaulted: "심각도가 비어 있어 '중대'로 두었습니다.",
};

export default function FindingItem({ f }: { f: Finding }) {
  const ev = f.evidence || { type: "none", detail: "", sources: [] };
  const hasDetail = Boolean(ev.detail || ev.formula || (ev.sources && ev.sources.length) || f.fix || f.user_action);
  return (
    <article className={`finding ${f.verdict}`} id={f.id}>
      <div className="finding-head">
        <span className={`tag ${f.verdict}`}>{VERDICT_LABEL[f.verdict]}</span>
        {f.severity && <span className={`tag sev ${f.verdict}`}>{SEVERITY_LABEL[f.severity]}</span>}
        <span>{f.category}</span>
        {f.location && <span>{f.location}</span>}
        <span style={{ marginLeft: "auto" }}>{f.id}</span>
      </div>
      {f.quote && <blockquote>“{f.quote}”</blockquote>}
      {f.issue && <p className="issue">{f.issue}</p>}

      {hasDetail && (
        <details open={f.verdict === "error"}>
          <summary>근거와 수정안</summary>
          <dl className="detail-grid">
            <dt>근거</dt>
            <dd>
              <span className="muted">{EVIDENCE_LABEL[ev.type] ?? ev.type}</span>
              {ev.detail && <div>{ev.detail}</div>}
              {ev.formula && <pre><code>{ev.formula}</code></pre>}
              {ev.sources?.length > 0 && (
                <ul className="sources small">
                  {ev.sources.map((s, i) => (
                    <li key={i}>
                      {s.url ? <a href={s.url} target="_blank" rel="noreferrer">{s.title || s.url}</a> : (s.title || "출처 미상")}
                      {s.published && <span className="muted"> ({s.published})</span>}
                    </li>
                  ))}
                </ul>
              )}
            </dd>
            {f.fix && (<><dt>수정안</dt><dd>{f.fix}</dd></>)}
            {f.user_action && (<><dt>확인 요청</dt><dd>{f.user_action}</dd></>)}
          </dl>
        </details>
      )}

      {f.flags?.length > 0 && (
        <div className="flags">{f.flags.map((fl) => FLAG_TEXT[fl] ?? fl).join(" ")}</div>
      )}
    </article>
  );
}
