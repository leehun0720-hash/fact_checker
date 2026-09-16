import type { Job } from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000").replace(/\/$/, "");
const SESSION_KEY = "dfc_session";

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(SESSION_KEY) || "";
}
export function setToken(t: string) { window.localStorage.setItem(SESSION_KEY, t); }
export function clearToken() { window.localStorage.removeItem(SESSION_KEY); }

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { ...authHeaders(), ...(init.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try { const j = await res.json(); if (j?.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

function json<T>(path: string, body: unknown, method = "POST"): Promise<T> {
  return request<T>(path, { method, body: JSON.stringify(body), headers: { "Content-Type": "application/json" } });
}

// ---------- 인증 ----------
export interface OrgSummary { id: string; name: string; slug: string; monthly_job_limit: number; jobs_this_month: number }
export interface Me {
  id: string; email: string; name?: string | null; role: "owner" | "member";
  org: OrgSummary;
}
export interface AuthResponse { token: string; user: Me }

export const login = (email: string, password: string) => json<AuthResponse>("/api/auth/login", { email, password });
export const register = (org_name: string, email: string, password: string, name?: string) =>
  json<AuthResponse>("/api/auth/register", { org_name, email, password, name });
export const join = (code: string, email: string, password: string, name?: string) =>
  json<AuthResponse>("/api/auth/join", { code, email, password, name });
export const me = () => request<Me>("/api/auth/me");
export const logout = () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
export const health = () => request<{ ok: boolean; mock: boolean; law_api: boolean; self_signup: boolean }>("/api/health");

// ---------- 조직 ----------
export interface Member { id: string; email: string; name?: string | null; role: string; created_at: string; is_active: number }
export interface Invite { code: string; role: string; created_at: string; expires_at: string }
export interface OrgInfo extends OrgSummary { members: Member[]; invites: Invite[] }
export const getOrg = () => request<OrgInfo>("/api/org");
export const createInvite = (role: "member" | "owner") => json<Invite>("/api/org/invites", { role });
export const setMemberActive = (id: string, active: boolean) =>
  request<{ ok: boolean }>(`/api/org/members/${id}/${active ? "activate" : "deactivate"}`, { method: "POST" });

// ---------- 작업 ----------
export interface CreateJobInput {
  file: File; as_of?: string; scope: string; notes?: string; want_corrected: boolean; extra_files: File[];
}
export async function createJob(input: CreateJobInput): Promise<{ id: string }> {
  const fd = new FormData();
  fd.append("file", input.file);
  fd.append("scope", input.scope);
  if (input.as_of) fd.append("as_of", input.as_of);
  if (input.notes) fd.append("notes", input.notes);
  fd.append("want_corrected", String(input.want_corrected));
  for (const f of input.extra_files) fd.append("extra_files", f);
  return request("/api/jobs", { method: "POST", body: fd });
}
export const getJob = (id: string) => request<Job>(`/api/jobs/${id}`);
export const listJobs = () => request<Job[]>(`/api/jobs`);

/** 다운로드는 인증 헤더가 필요하므로 fetch → blob → 저장 */
export async function download(path: string, filename: string) {
  const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
  if (!res.ok) {
    let msg = "다운로드에 실패했습니다.";
    try { const j = await res.json(); if (j?.detail) msg = j.detail; } catch {}
    throw new ApiError(res.status, msg);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
export function formatTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** 추정 비용 표기. 소액은 센트 단위까지. */
export function formatCost(usd?: number | null) {
  if (usd === undefined || usd === null) return "";
  if (usd < 0.01) return "$0.01 미만";
  return `$${usd.toFixed(2)}`;
}
