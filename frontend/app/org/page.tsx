"use client";
import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/components/AppFrame";
import { createInvite, formatTime, getOrg, setMemberActive, type Invite, type OrgInfo } from "@/lib/api";

export default function OrgPage() {
  const { user, refresh } = useAuth();
  const [org, setOrg] = useState<OrgInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newInvite, setNewInvite] = useState<Invite | null>(null);
  const isOwner = user.role === "owner";

  const load = useCallback(() => getOrg().then(setOrg).catch((e) => setError((e as Error).message)), []);
  useEffect(() => { load(); }, [load]);

  async function invite(role: "member" | "owner") {
    setError(null);
    try { setNewInvite(await createInvite(role)); await load(); }
    catch (e) { setError((e as Error).message); }
  }
  async function toggle(id: string, active: boolean) {
    setError(null);
    try { await setMemberActive(id, active); await load(); await refresh(); }
    catch (e) { setError((e as Error).message); }
  }

  if (error && !org) return <div className="alert error">{error}</div>;
  if (!org) return <p className="muted">불러오는 중</p>;

  const pct = Math.min(100, Math.round((org.jobs_this_month / Math.max(1, org.monthly_job_limit)) * 100));
  return (
    <div className="stack" style={{ ["--gap" as string]: "28px" }}>
      <header className="stack" style={{ ["--gap" as string]: "6px" }}>
        <h1>{org.name}</h1>
        <p className="muted">이 조직의 검증 기록은 구성원끼리만 공유됩니다. 다른 조직에서는 볼 수 없습니다.</p>
      </header>

      <section className="stack" style={{ ["--gap" as string]: "8px" }}>
        <h2>이번 달 사용량</h2>
        <p><b>{org.jobs_this_month}</b> / {org.monthly_job_limit}건 <span className="muted small">({pct}%)</span></p>
        <div className="meter" aria-hidden><span style={{ width: `${pct}%` }} /></div>
        <p className="muted small">한도에 이르면 새 검증을 시작할 수 없습니다. 한도 조정은 운영자에게 요청하세요.</p>
      </section>

      {error && <div className="alert error">{error}</div>}

      <section className="stack">
        <h2>구성원 {org.members.length}</h2>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>이메일</th><th>이름</th><th>역할</th><th>가입</th>{isOwner && <th></th>}</tr></thead>
            <tbody>
              {org.members.map((m) => (
                <tr key={m.id} style={{ opacity: m.is_active ? 1 : 0.55 }}>
                  <td>{m.email}{m.id === user.id && <span className="muted small"> (나)</span>}</td>
                  <td>{m.name || "—"}</td>
                  <td>{m.role === "owner" ? "관리자" : "구성원"}{!m.is_active && <span className="muted small"> · 비활성</span>}</td>
                  <td className="muted small">{formatTime(m.created_at)}</td>
                  {isOwner && (
                    <td style={{ textAlign: "right" }}>
                      {m.id !== user.id && (
                        <button className="btn secondary small" onClick={() => toggle(m.id, !m.is_active)}>
                          {m.is_active ? "비활성화" : "다시 활성화"}
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {isOwner && (
        <section className="stack">
          <h2>초대</h2>
          <p className="muted small">초대 코드는 7일 동안, 한 번만 쓸 수 있습니다. 코드를 받은 사람은 로그인 화면의 '초대 코드로 가입'에서 계정을 만듭니다.</p>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn small" onClick={() => invite("member")}>구성원 초대 코드 만들기</button>
            <button className="btn secondary small" onClick={() => invite("owner")}>관리자 초대 코드 만들기</button>
          </div>
          {newInvite && (
            <div className="alert info">
              새 초대 코드 <code style={{ fontSize: "1.05em", userSelect: "all" }}>{newInvite.code}</code>
              <span className="muted small"> — {newInvite.role === "owner" ? "관리자" : "구성원"} 권한, {formatTime(newInvite.expires_at)}까지</span>
            </div>
          )}
          {org.invites.length > 0 && (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>미사용 코드</th><th>권한</th><th>만료</th></tr></thead>
                <tbody>{org.invites.map((i) => (
                  <tr key={i.code}><td><code style={{ userSelect: "all" }}>{i.code}</code></td><td>{i.role === "owner" ? "관리자" : "구성원"}</td><td className="muted small">{formatTime(i.expires_at)}</td></tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
