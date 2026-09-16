"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "@/components/AppFrame";
import StatusBadge from "@/components/StatusBadge";
import { ApiError, createJob, formatBytes, formatCost, formatTime, listJobs } from "@/lib/api";
import type { Job } from "@/lib/types";

const ACCEPT = ".pdf,.docx,.hwpx,.md,.txt";
const SCOPES = ["전체", "숫자·계산만", "출처·인용만", "법령만"];

export default function HomePage() {
  return (
    <>
      <UploadForm />
      <hr className="hr" />
      <RecentJobs />
    </>
  );
}

function UploadForm() {
  const router = useRouter();
  const { user } = useAuth();
  const quotaLeft = user.org.monthly_job_limit - user.org.jobs_this_month;
  const [file, setFile] = useState<File | null>(null);
  const [extra, setExtra] = useState<File[]>([]);
  const [asOf, setAsOf] = useState("");
  const [scope, setScope] = useState(SCOPES[0]);
  const [notes, setNotes] = useState("");
  const [corrected, setCorrected] = useState(false);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const { id } = await createJob({ file, as_of: asOf || undefined, scope, notes: notes || undefined, want_corrected: corrected, extra_files: extra });
      router.push(`/jobs/${id}`);
    } catch (err) {
      const msg = err instanceof ApiError && err.status === 401
        ? "세션이 만료되었습니다. 새로 고침 후 다시 로그인하세요."
        : (err as Error).message;
      setError(msg); setBusy(false);
    }
  }

  return (
    <section className="stack" style={{ ["--gap" as string]: "28px" }}>
      <div className="measure stack" style={{ ["--gap" as string]: "8px" }}>
        <h1>문서를 올리면 수치·출처·법령·내부 정합성을 검증합니다</h1>
        <p className="muted">
          모든 계산은 Python으로 다시 실행하고, 외부 사실은 실시간 검색으로 확인합니다. 근거를 붙일 수 없는 지적은 '오류'가 아니라 '의심'으로 표시됩니다.
        </p>
      </div>

      <form className="form stack" style={{ ["--gap" as string]: "20px" }} onSubmit={submit}>
        <label
          className={`drop ${over ? "is-over" : ""} ${file ? "has-file" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={onDrop}
        >
          <input ref={inputRef} type="file" accept={ACCEPT} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          {file ? (
            <div>
              <div className="name">{file.name}</div>
              <div className="meta">{formatBytes(file.size)} — 다른 파일을 놓거나 눌러서 바꿀 수 있습니다</div>
            </div>
          ) : (
            <div>
              <div className="name">검증할 문서를 여기에 놓거나 눌러서 선택</div>
              <div className="meta">PDF, Word(.docx), 한글(.hwpx), 마크다운, 텍스트 — 20MB까지</div>
            </div>
          )}
        </label>

        <div className="row">
          <div className="field">
            <label htmlFor="asof">문서 기준 시점</label>
            <input id="asof" className="input" value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="예: 2026-06 (비우면 문서에서 파악)" />
            <span className="hint">이 시점 이후 바뀐 수치는 오류가 아니라 '업데이트 권장'으로 구분됩니다.</span>
          </div>
          <div className="field">
            <label htmlFor="scope">검증 범위</label>
            <select id="scope" className="select" value={scope} onChange={(e) => setScope(e.target.value)}>
              {SCOPES.map((s) => <option key={s}>{s}</option>)}
            </select>
            <span className="hint">범위 밖에서 치명적 오류가 보이면 별도로 알립니다.</span>
          </div>
        </div>

        <div className="field">
          <label htmlFor="notes">메모 (선택)</label>
          <textarea id="notes" className="textarea" value={notes} onChange={(e) => setNotes(e.target.value)}
            placeholder="예: 3장 예산 표를 중점적으로. '당사'는 주식회사 텐에이아이." />
        </div>

        <div className="field">
          <label htmlFor="extra">내부 근거자료 (선택)</label>
          <input id="extra" className="input" type="file" multiple accept={ACCEPT + ",.xlsx,.csv"}
            onChange={(e) => setExtra(Array.from(e.target.files ?? []))} />
          <span className="hint">
            계약서·내부 통계처럼 웹에 없는 사실을 대조할 자료. 없으면 해당 주장은 '검증 불가(내부 자료 필요)'로 분류됩니다.
            {extra.length > 0 && ` — ${extra.length}개 선택`}
          </span>
        </div>

        <label className="check">
          <input type="checkbox" checked={corrected} onChange={(e) => setCorrected(e.target.checked)} />
          <span>교정본도 만들기 <span className="muted small">— 원문 문체를 유지하고 수정 부분만 표시합니다. 시간이 더 걸립니다.</span></span>
        </label>

        {error && <div className="alert error" role="alert">{error}</div>}

        <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
          <button className="btn" type="submit" disabled={!file || busy || quotaLeft <= 0}>{busy ? "올리는 중" : "검증 시작"}</button>
          <span className="muted small">{quotaLeft > 0 ? `이번 달 남은 검증 ${quotaLeft}건` : "이번 달 검증 한도를 모두 썼습니다"}</span>
        </div>
      </form>
    </section>
  );
}

function RecentJobs() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    listJobs().then(setJobs).catch((e) => setError((e as Error).message));
  }, []);
  return (
    <section id="recent" className="stack">
      <h2>최근 작업</h2>
      {error && <div className="alert error">{error}</div>}
      {jobs && jobs.length === 0 && <div className="empty">아직 검증한 문서가 없습니다. 위에서 첫 문서를 올려 보세요.</div>}
      {jobs && jobs.length > 0 && (
        <div className="list">
          {jobs.map((j) => (
            <Link key={j.id} href={`/jobs/${j.id}`} className="list-row">
              <div>
                <div className="list-name">{j.filename}</div>
                <div className="list-sub">{j.options.scope}{j.options.as_of ? ` / 기준 ${j.options.as_of}` : ""} / {formatBytes(j.size_bytes)}{j.user_email ? ` / ${j.user_email}` : ""}{j.usage?.cost_usd ? ` / 약 ${formatCost(j.usage.cost_usd)}` : ""}</div>
              </div>
              <span className="list-time list-sub">{formatTime(j.created_at)}</span>
              <StatusBadge status={j.status} />
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
