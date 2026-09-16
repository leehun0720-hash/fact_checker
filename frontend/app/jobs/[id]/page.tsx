"use client";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import StatusBadge from "@/components/StatusBadge";
import GradeStamp from "@/components/GradeStamp";
import ProgressLog from "@/components/ProgressLog";
import FindingItem from "@/components/FindingItem";
import { download, formatBytes, formatTime, getJob } from "@/lib/api";
import { GRADE_TITLE, VERDICT_LABEL, type Job, type Verdict, type VerificationResult } from "@/lib/types";

const ACTIVE = new Set(["queued", "uploading", "running", "postprocessing"]);
type Filter = "all" | Verdict;
type Tab = "findings" | "recalc" | "recs" | "log";

export default function JobPage() {
  return <JobView />;
}

function JobView() {
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const j = await getJob(id);
        if (!alive) return;
        setJob(j); setError(null);
        if (ACTIVE.has(j.status)) timer = setTimeout(tick, 3000);
      } catch (e) {
        if (!alive) return;
        setError((e as Error).message);
        timer = setTimeout(tick, 8000);
      }
    };
    tick();
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [id]);

  if (error && !job) return <div className="alert error">{error}</div>;
  if (!job) return <p className="muted">불러오는 중</p>;

  return (
    <div className="stack" style={{ ["--gap" as string]: "24px" }}>
      <header className="stack" style={{ ["--gap" as string]: "8px" }}>
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
          <h1 style={{ overflowWrap: "anywhere" }}>{job.filename}</h1>
          <StatusBadge status={job.status} />
        </div>
        <div className="meta-line">
          <span>{formatBytes(job.size_bytes)}</span>
          <span>범위 {job.options.scope}</span>
          {job.options.as_of && <span>기준 시점 {job.options.as_of}</span>}
          {job.extra_files.length > 0 && <span>근거자료 {job.extra_files.length}개</span>}
          <span>시작 {formatTime(job.created_at)}</span>
          {job.user_email && <span>요청 {job.user_email}</span>}
          {job.model && <span>모델 {job.model}</span>}
        </div>
        {job.options.notes && <p className="muted small">메모: {job.options.notes}</p>}
      </header>

      {ACTIVE.has(job.status) && <ProgressLog job={job} />}

      {job.status === "failed" && (
        <div className="alert error" role="alert">
          <b>검증이 완료되지 않았습니다.</b>
          <div className="small" style={{ marginTop: 6 }}>{job.error}</div>
          <div className="small muted" style={{ marginTop: 6 }}>같은 문서를 다시 올리면 새 작업으로 실행됩니다. 반복되면 파일 형식(스캔 PDF 여부)과 서버 로그를 확인하세요.</div>
        </div>
      )}

      {job.status === "done" && job.result && <Report job={job} r={job.result} />}
    </div>
  );
}

function Report({ job, r }: { job: Job; r: VerificationResult }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [tab, setTab] = useState<Tab>("findings");
  const [pdfBusy, setPdfBusy] = useState(false);
  const [dlError, setDlError] = useState<string | null>(null);
  const c = r.summary.counts;
  const sev = r.summary.severity_counts || {};

  const shown = useMemo(
    () => (filter === "all" ? r.findings : r.findings.filter((f) => f.verdict === filter)),
    [r.findings, filter],
  );

  return (
    <>
      <section className="report-head">
        <GradeStamp grade={r.summary.grade} />
        <div>
          <div className="grade-title">{GRADE_TITLE[r.summary.grade]}</div>
          <p style={{ marginTop: 8, maxWidth: "68ch" }}>{r.summary.text}</p>
          <div className="counts">
            <span className="k-error">오류 확인<b>{c.error}</b></span>
            <span className="k-suspect">의심<b>{c.suspect}</b></span>
            <span className="k-unverifiable">검증 불가<b>{c.unverifiable}</b></span>
            <span className="k-confirmed">확인됨<b>{c.confirmed}</b></span>
          </div>
          {c.error > 0 && (
            <div className="muted small" style={{ marginTop: 6 }}>
              오류 중 치명 {sev.critical ?? 0}, 중대 {sev.major ?? 0}, 경미 {sev.minor ?? 0}
              {r.summary.critical_suspects > 0 && ` / 치명 가능성이 있는 의심 항목 ${r.summary.critical_suspects}건`}
            </div>
          )}
          {r.summary.needs_evidence_flag && (
            <div className="flag">근거 보강 필요 — 검증하지 못한 주장이 30%를 넘습니다. 등급과 별개로, 이 문서는 아직 신뢰할 수 있는 문서가 아닙니다.</div>
          )}
          {r.summary.model_grade && r.summary.model_grade !== r.summary.grade && (
            <div className="muted small" style={{ marginTop: 8 }}>
              모델이 제시한 등급은 {r.summary.model_grade}이지만 오류 건수 규칙에 따라 {r.summary.grade}로 다시 산정했습니다.
            </div>
          )}
        </div>
      </section>

      <div className="meta-line">
        <span>{r.document.pages ? `${r.document.pages}쪽` : ""}{r.document.chars ? ` ${r.document.chars.toLocaleString()}자` : ""}</span>
        <span>Python 재계산 {r.stats.python_runs}건</span>
        <span>웹 검색 {job.usage.web_search_requests || r.stats.web_searches}회</span>
        <span>원문 대조 {job.usage.web_fetch_requests || r.stats.web_fetches}건</span>
        {job.counters?.law_api ? <span>법령 오픈API {job.counters.law_api}회</span> : null}
        {r.document.extraction !== "ok" && <span style={{ color: "var(--suspect)" }}>텍스트 추출 {r.document.extraction === "partial" ? "일부 실패 (스캔 페이지 가능성)" : "실패"}</span>}
      </div>

      <div className="downloads">
        <button className="btn small" disabled={pdfBusy} onClick={async () => { setPdfBusy(true); setDlError(null); try { await download(`/api/jobs/${job.id}/report.pdf`, `검증보고서_${job.filename}.pdf`); } catch (e) { setDlError((e as Error).message); } finally { setPdfBusy(false); } }}>{pdfBusy ? "PDF 만드는 중" : "보고서 (PDF)"}</button>
        {job.has_report && <button className="btn secondary small" onClick={() => download(`/api/jobs/${job.id}/report.md`, `검증보고서_${job.filename}.md`)}>보고서 (Markdown)</button>}
        <button className="btn secondary small" onClick={() => download(`/api/jobs/${job.id}/result.json`, `검증결과_${job.filename}.json`)}>결과 데이터 (JSON)</button>
        {job.has_corrected && <button className="btn secondary small" onClick={() => download(`/api/jobs/${job.id}/corrected.md`, `교정본_${job.filename}.md`)}>교정본</button>}
        <button className="btn secondary small" onClick={() => download(`/api/jobs/${job.id}/log.json`, `검증로그_${job.id}.json`)}>실행 기록 (JSON)</button>
      </div>
      {dlError && <div className="alert error small">{dlError}</div>}

      <div className="tabs" role="tablist">
        {([["findings", `지적 항목 ${r.findings.length}`], ["recalc", `검산표 ${r.recalculations.length}`], ["recs", "권장 조치"], ["log", "실행 기록"]] as [Tab, string][]).map(([k, label]) => (
          <button key={k} role="tab" className="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{label}</button>
        ))}
      </div>

      {tab === "findings" && (
        <section className="stack">
          <div className="filters" role="group" aria-label="판정으로 걸러보기">
            <button className="chip" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>전체 {r.findings.length}</button>
            {(["error", "suspect", "unverifiable", "confirmed"] as Verdict[]).map((v) => (
              <button key={v} className="chip" aria-pressed={filter === v} onClick={() => setFilter(v)}>{VERDICT_LABEL[v]} {c[v]}</button>
            ))}
          </div>
          {shown.length === 0
            ? <div className="empty">이 판정에 해당하는 항목이 없습니다.</div>
            : <div className="findings">{shown.map((f) => <FindingItem key={f.id} f={f} />)}</div>}
          {r.limits?.length > 0 && (
            <div className="alert info small">
              <b>검증 한계</b>
              <ul style={{ margin: "6px 0 0", paddingLeft: "1.2em" }}>{r.limits.map((l, i) => <li key={i}>{l}</li>)}</ul>
            </div>
          )}
        </section>
      )}

      {tab === "recalc" && (
        r.recalculations.length === 0 ? <div className="empty">재계산한 수치가 없습니다.</div> : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>위치</th><th>문서 값</th><th>재계산 값</th><th>일치</th><th>계산식</th></tr></thead>
              <tbody>
                {r.recalculations.map((x, i) => (
                  <tr key={i}>
                    <td>{x.location}</td>
                    <td className="num">{x.doc_value}</td>
                    <td className="num">{x.recalc_value}</td>
                    <td>{x.match === null ? "—" : x.match ? <span className="match-ok">일치</span> : <span className="match-no">불일치</span>}</td>
                    <td><code>{x.formula}</code>{x.estimated && <span className="muted small"> (수식 추정)</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {tab === "recs" && (
        r.recommendations.length === 0 ? <div className="empty">권장 조치가 없습니다.</div> :
          <ol className="recs">{r.recommendations.map((x, i) => <li key={i}>{x}</li>)}</ol>
      )}

      {tab === "log" && <RunLog job={job} />}
    </>
  );
}

function RunLog({ job }: { job: Job }) {
  const u = job.usage;
  const LABEL: Record<string, string> = { web_search: "웹 검색", web_fetch: "원문 확인", bash: "실행", editor: "파일", law_api: "법령 API", law_api_result: "법령 결과" };
  return (
    <section className="stack">
      <div className="meta-line">
        <span>입력 토큰 {u.input_tokens.toLocaleString()}</span>
        <span>출력 토큰 {u.output_tokens.toLocaleString()}</span>
        <span>이어가기 {u.rounds}회</span>
      </div>
      <p className="muted small">화면에는 최근 60개 동작만 남습니다. 전체 기록은 위의 '실행 기록 (JSON)'으로 받으세요.</p>
      <ul className="log">
        {job.progress.map((e, i) => (
          <li key={i}>
            <span className="tool">{LABEL[e.tool] ?? e.tool}</span>
            <span className={`detail ${e.tool === "web_search" ? "text" : ""}`}>{e.detail}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
