import type { Job, ToolEvent } from "./types";

/**
 * 진행률 추정. 검증은 모델이 도구를 얼마나 쓸지 미리 알 수 없는 열린 작업이라
 * 정확한 %는 없다. 대신 두 신호를 합쳐 "보수적이지만 계속 움직이는" 값을 만든다.
 *  - 이벤트 기반: 상태(queued→running→postprocessing) + 도구 호출 로그에서 단계 감지
 *  - 시간 기반: 경과 시간에 따라 천천히 올라가는 바닥값(모델이 길게 생각하는 동안에도 멈춰 보이지 않게)
 * 완료 전에는 92%를 넘지 않고, 화면에서는 뒤로 가지 않도록 최대값을 유지한다.
 */
export interface ProgressEstimate {
  pct: number;                 // 0–100
  stage: string;               // 지금 하는 일 (사람이 읽는 문장)
  elapsedSec: number;          // 작업 생성 후 경과
  remainingSec: number | null; // 대략적 예상. 확신이 낮을 땐 null
  idleSec: number | null;      // 마지막 진행 기록 후 경과
}

const RUNNING_CAP = 92;

function isExtract(e: ToolEvent) { return e.tool === "bash" && e.detail.includes("extract_text"); }
function isPython(e: ToolEvent) { return e.tool === "python" || e.tool === "code_execution"; }
function isRecalc(e: ToolEvent) { return isPython(e) || (e.tool === "bash" && (e.detail.includes("python") || e.detail.includes("korean_number_parser"))); }
function isExternal(e: ToolEvent) { return e.tool === "web_search" || e.tool === "web_fetch" || e.tool === "law_api" || e.tool === "law_api_result"; }
function isExport(e: ToolEvent) {
  const d = e.detail;
  return d.includes("OUTPUT_DIR") || ((e.tool === "editor" || e.tool === "bash" || isPython(e)) && (d.includes("result.json") || d.includes("report.md")));
}

function eventPct(job: Job): number {
  const ev = job.progress || [];
  if (ev.length === 0) return 10;
  let pct = 12; // 스킬 읽기 등 첫 도구 호출
  let started = -1;
  ev.forEach((e, i) => {
    if (isExtract(e)) pct = Math.max(pct, 20);
    if (started < 0 && (isRecalc(e) || isExternal(e))) started = i;
  });
  if (started >= 0) {
    const n = ev.length - started; // 본격 검증 이후 도구 호출 수
    pct = Math.max(pct, 28 + 55 * (1 - Math.exp(-n / 14)));
  }
  if (ev.some(isExport)) pct = Math.max(pct, 88);
  return pct;
}

function timePct(elapsedSec: number): number {
  // 1분 23% · 3분 42% · 5분 55% · 10분 72% · 상한 82%
  return 10 + 72 * (1 - Math.exp(-elapsedSec / 300));
}

function stageText(job: Job, idleSec: number | null): string {
  switch (job.status) {
    case "queued": return "대기 중 — 앞선 검증이 끝나면 시작합니다";
    case "uploading": return "문서를 검증 컨테이너로 올리는 중";
    case "postprocessing": return "결과 정리 중 — 판정 규칙 적용, 보고서 저장";
    case "done": return "완료";
    case "failed": return "중단됨";
  }
  const last = job.progress?.[job.progress.length - 1];
  let s: string;
  if (!last) s = "검증 준비 중 — 스킬과 문서를 읽습니다";
  else if (isExtract(last)) s = "문서에서 텍스트를 추출하는 중";
  else if (isExport(last)) s = "보고서 작성 중 — 거의 끝났습니다";
  else if (last.tool === "web_search") s = "외부 사실 확인 중 — 웹 검색";
  else if (last.tool === "web_fetch") s = "출처 원문과 대조하는 중";
  else if (last.tool === "law_api" || last.tool === "law_api_result") s = "국가법령정보센터에서 조문 확인 중";
  else if (isRecalc(last)) s = "수치를 Python으로 다시 계산하는 중";
  else if (last.tool === "editor" && (last.detail.includes("SKILL") || last.detail.includes("references/"))) s = "검증 절차(스킬)를 읽는 중";
  else if (last.tool === "editor") s = "작업 파일 정리 중";
  else s = "검증 진행 중";
  if (idleSec !== null && idleSec >= 45) s += " · 모델이 결과를 분석하고 있습니다";
  return s;
}

export function estimateProgress(job: Job, nowMs: number): ProgressEstimate {
  const created = Date.parse(job.created_at);
  const elapsedSec = Number.isNaN(created) ? 0 : Math.max(0, Math.floor((nowMs - created) / 1000));
  const lastAt = job.progress?.length ? Date.parse(job.progress[job.progress.length - 1].at) : Date.parse(job.updated_at);
  const idleSec = Number.isNaN(lastAt) ? null : Math.max(0, Math.floor((nowMs - lastAt) / 1000));

  let pct: number;
  switch (job.status) {
    case "queued": pct = 2; break;
    case "uploading": pct = 6; break;
    case "running": pct = Math.min(RUNNING_CAP, Math.max(eventPct(job), timePct(elapsedSec))); break;
    case "postprocessing": pct = Math.min(97, 93 + Math.floor((idleSec ?? 0) / 10)); break;
    case "done": pct = 100; break;
    default: pct = Math.min(RUNNING_CAP, Math.max(eventPct(job), timePct(elapsedSec)));
  }
  pct = Math.round(pct);

  let remainingSec: number | null = null;
  if (job.status === "running" && pct >= 15 && pct < RUNNING_CAP && elapsedSec >= 30) {
    remainingSec = Math.round(elapsedSec * (100 - pct) / pct);
  } else if (job.status === "postprocessing") {
    remainingSec = 20;
  }

  return { pct, stage: stageText(job, idleSec), elapsedSec, remainingSec, idleSec };
}

export function fmtDuration(sec: number): string {
  const m = Math.floor(sec / 60), s = sec % 60;
  return m > 0 ? `${m}분 ${String(s).padStart(2, "0")}초` : `${s}초`;
}

export function fmtRemaining(sec: number): string {
  if (sec < 60) return "1분 이내";
  const m = Math.ceil(sec / 60);
  return `약 ${m}분`;
}
