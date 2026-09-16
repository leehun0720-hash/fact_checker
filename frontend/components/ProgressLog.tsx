import type { Job } from "@/lib/types";
import { STATUS_LABEL } from "@/lib/types";

const TOOL_LABEL: Record<string, string> = {
  web_search: "웹 검색", web_fetch: "원문 확인", bash: "실행", editor: "파일", law_api: "법령 API", download_error: "다운로드 실패",
};

export default function ProgressLog({ job }: { job: Job }) {
  const c = job.counters || {};
  const events = job.progress.slice(-30).reverse();
  return (
    <section className="progress" aria-live="polite">
      <div className="progress-title">
        <span className="pulse" aria-hidden />
        <h2>{STATUS_LABEL[job.status]}</h2>
        <span className="muted small">{job.filename}</span>
      </div>
      <p className="muted small" style={{ marginTop: 6 }}>
        문서 길이에 따라 몇 분 걸립니다. 이 페이지를 닫아도 검증은 계속되며, 최근 작업 목록에서 다시 열 수 있습니다.
      </p>
      <div className="counters">
        <span>Python 실행 {c.python ?? 0}</span>
        <span>웹 검색 {c.web_search ?? 0}</span>
        <span>원문 확인 {c.web_fetch ?? 0}</span>
        <span>파일 작업 {c.editor ?? 0}</span>
        {c.law_api ? <span>법령 API {c.law_api}</span> : null}
      </div>
      {events.length > 0 && (
        <ul className="log">
          {events.map((e, i) => (
            <li key={`${e.at}-${i}`}>
              <span className="tool">{TOOL_LABEL[e.tool] ?? e.tool}</span>
              <span className={`detail ${e.tool === "web_search" ? "text" : ""}`}>{e.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
