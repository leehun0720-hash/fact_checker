"use client";
import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { ApiError, clearToken, getToken, health, join, login, logout, me, register, setToken, type Me } from "@/lib/api";

interface AuthCtx { user: Me; refresh: () => Promise<void>; signOut: () => Promise<void> }
const Ctx = createContext<AuthCtx | null>(null);
export function useAuth(): AuthCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth는 AppFrame 안에서만 쓸 수 있습니다.");
  return c;
}

/** 헤더 + 로그인 게이트. 세션이 있으면 사용자 정보를 불러오고, 없으면 로그인/가입 화면을 보여준다. */
export default function AppFrame({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);

  const refresh = useCallback(async () => {
    if (!getToken()) { setUser(null); setChecked(true); return; }
    try { setUser(await me()); }
    catch (e) { if (e instanceof ApiError && e.status === 401) clearToken(); setUser(null); }
    finally { setChecked(true); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const signOut = useCallback(async () => {
    try { await logout(); } catch {}
    clearToken(); setUser(null);
  }, []);

  return (
    <div className="shell">
      <header className="topbar">
        <Link href="/" className="brand">문서 검증<small>TEN AI Doc Fact Checker</small></Link>
        {user && (
          <nav>
            <Link href="/">새 검증</Link>
            <Link href="/#recent">최근 작업</Link>
            <Link href="/org">{user.org.name}</Link>
            <button className="linkbtn" onClick={signOut}>로그아웃</button>
          </nav>
        )}
      </header>
      {!checked ? null : user
        ? <Ctx.Provider value={{ user, refresh, signOut }}>{children}</Ctx.Provider>
        : <AuthScreen onDone={(u) => { setUser(u); }} />}
    </div>
  );
}

type Mode = "login" | "join" | "register";

function AuthScreen({ onDone }: { onDone: (u: Me) => void }) {
  const [mode, setMode] = useState<Mode>("login");
  const [selfSignup, setSelfSignup] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [orgName, setOrgName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { health().then((h) => setSelfSignup(h.self_signup)).catch(() => {}); }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try {
      const res = mode === "login" ? await login(email, password)
        : mode === "join" ? await join(code, email, password, name || undefined)
        : await register(orgName, email, password, name || undefined);
      setToken(res.token); onDone(res.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "요청에 실패했습니다."); setBusy(false);
    }
  }

  const titles: Record<Mode, string> = { login: "로그인", join: "초대 코드로 가입", register: "새 조직 만들기" };
  return (
    <section className="gate stack" style={{ ["--gap" as string]: "16px" }}>
      <h1>{titles[mode]}</h1>
      <p className="muted small">
        {mode === "login" && "조직 계정으로 로그인하세요. 검증 기록은 같은 조직 안에서만 공유됩니다."}
        {mode === "join" && "조직 관리자에게 받은 초대 코드와 함께 계정을 만듭니다."}
        {mode === "register" && "새 조직과 관리자 계정을 함께 만듭니다. 팀원은 나중에 초대 코드로 합류합니다."}
      </p>
      <form className="stack" style={{ ["--gap" as string]: "12px" }} onSubmit={submit}>
        {mode === "join" && (
          <div className="field"><label htmlFor="code">초대 코드</label>
            <input id="code" className="input" value={code} onChange={(e) => setCode(e.target.value)} required autoComplete="off" /></div>
        )}
        {mode === "register" && (
          <div className="field"><label htmlFor="org">조직 이름</label>
            <input id="org" className="input" value={orgName} onChange={(e) => setOrgName(e.target.value)} required /></div>
        )}
        {mode !== "login" && (
          <div className="field"><label htmlFor="name">이름 (선택)</label>
            <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
        )}
        <div className="field"><label htmlFor="email">이메일</label>
          <input id="email" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="username" /></div>
        <div className="field"><label htmlFor="pw">비밀번호{mode !== "login" && <span className="muted"> (8자 이상)</span>}</label>
          <input id="pw" className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={mode === "login" ? 1 : 8}
            autoComplete={mode === "login" ? "current-password" : "new-password"} /></div>
        {error && <div className="alert error" role="alert">{error}</div>}
        <div><button className="btn" type="submit" disabled={busy}>{busy ? "확인 중" : titles[mode]}</button></div>
      </form>
      <div className="small muted" style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        {mode !== "login" && <button className="linkbtn" onClick={() => { setMode("login"); setError(null); }}>이미 계정이 있음</button>}
        {mode !== "join" && <button className="linkbtn" onClick={() => { setMode("join"); setError(null); }}>초대 코드로 가입</button>}
        {mode !== "register" && selfSignup && <button className="linkbtn" onClick={() => { setMode("register"); setError(null); }}>새 조직 만들기</button>}
      </div>
    </section>
  );
}
