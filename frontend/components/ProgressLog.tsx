"use client";
import { useEffect, useRef, useState } from "react";
import type { Job } from "@/lib/types";
import { STATUS_LABEL } from "@/lib/types";
import { estimateProgress, fmtDuration, fmtRemaining } from "@/lib/progress";

const TOOL_LABEL: Record<string, string> = {
  web_search: "웹 검색", web_fetch: "원문 확인", bash: "실행", editor: "파일", law_api: "법령 API", download_error: "다운로드 실패",
};

/** 1초마다 갱신되는 현재 시각 — 경과 시간 표시용 */
function useNow(intervalMs = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export default function ProgressLog({ job }: { job: Job }) {
  const now = useNow();
  const est = estimateProgress(job, now);

  // 추정치는 신호에 따라 흔들릴 수 있으니 화면의 %는 뒤로 가지 않게 최대값을 유지
  const maxRef = useRef<{ id: string; pct: number }>({ id: job.id, pct: 0 });
  if (maxRef.current.id !== job.id) maxRef.current = { id: job.id, pct: 0 };
  maxRef.current.pct = Math.max(maxRef.current.pct, est.pct);
  const pct = maxRef.current.pct;

  const c = job.counters || {};
  const events = job.progress.slice(-30).reverse();
  return (
    <section className="progress" aria-live="polite">
      <div className="progress-title">
        <span className="pulse" aria-hidden />
        <h2>{STATUS_LABEL[job.status]}</h2>
        <span className="muted small">{job.filename}</span>
      </div>

      <div className="bar-wrap">
        <div className="bar-head">
          <span className="bar-pct">{pct}%</span>
          <span className="bar-stage">{est.stage}</span>
        </div>
        <div className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label="검증 진행률">
          <span className="bar-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="bar-meta">
          <span>경과 <b>{fmtDuration(est.elapsedSec)}</b></span>
          {est.remainingSec !== null && <span>남은 시간 <b>{fmtRemaining(est.remainingSec)}</b> <span className="muted">(예상)</span></span>}
          {est.idleSec !== null && est.idleSec >= 20 && <span className="muted">마지막 활동 {fmtDuration(est.idleSec)} 전</span>}
        </div>
      </div>

      <p className="muted small" style={{ marginTop: 10 }}>
        진행률은 도구 호출 기록과 경과 시간으로 추정한 값입니다. 문서 길이와 검색량에 따라 실제 소요 시간은 달라집니다. 이 페이지를 닫아도 검증은 계속되며, 최근 작업 목록에서 다시 열 수 있습니다.
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
