export type Verdict = "error" | "suspect" | "unverifiable" | "confirmed";
export type Severity = "critical" | "major" | "minor";
export type Grade = "A" | "B" | "C" | "D";
export type JobStatus = "queued" | "uploading" | "running" | "postprocessing" | "done" | "failed";

export interface Source { title?: string | null; url?: string | null; published?: string | null }
export interface Evidence { type: string; detail: string; formula?: string | null; sources: Source[] }
export interface Finding {
  id: string;
  verdict: Verdict;
  severity: Severity | null;
  category: string;
  location: string;
  quote: string;
  issue: string;
  evidence: Evidence;
  fix?: string | null;
  user_action?: string | null;
  flags: string[];
}
export interface Recalculation {
  location: string; doc_value: string; recalc_value: string; match: boolean | null; formula: string; estimated: boolean;
}
export interface Counts { error: number; suspect: number; unverifiable: number; confirmed: number }
export interface VerificationResult {
  document: { name: string; pages?: number | null; chars?: number | null; as_of?: string | null; scope?: string | null; extraction: string };
  summary: {
    grade: Grade; needs_evidence_flag: boolean; text: string; counts: Counts;
    severity_counts: Record<string, number>; critical_suspects: number; model_grade?: string | null;
  };
  findings: Finding[];
  recalculations: Recalculation[];
  recommendations: string[];
  stats: { python_runs: number; web_searches: number; web_fetches: number };
  limits: string[];
}
export interface ToolEvent { at: string; tool: string; detail: string }
export interface Job {
  id: string; org_id?: string; user_id?: string; user_email?: string; created_at: string; updated_at: string; status: JobStatus;
  filename: string; size_bytes: number; extra_files: string[];
  options: { as_of?: string | null; scope: string; notes?: string | null; want_corrected: boolean };
  progress: ToolEvent[]; counters: Record<string, number>;
  usage: { input_tokens: number; cache_read_input_tokens?: number; cache_creation_input_tokens?: number; output_tokens: number;
           web_search_requests: number; web_fetch_requests: number; rounds: number; cost_usd?: number };
  error?: string | null; result?: VerificationResult | null;
  has_report: boolean; has_corrected: boolean; model?: string | null;
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  error: "오류 확인", suspect: "의심", unverifiable: "검증 불가", confirmed: "확인됨",
};
export const SEVERITY_LABEL: Record<Severity, string> = { critical: "치명", major: "중대", minor: "경미" };
export const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "대기", uploading: "업로드 중", running: "검증 중", postprocessing: "정리 중", done: "완료", failed: "실패",
};
export const GRADE_TITLE: Record<Grade, string> = {
  A: "그대로 사용 가능", B: "지적 항목 수정 후 사용 가능", C: "주요 수정 후 재검토 필요", D: "전면 재작성 권고",
};
