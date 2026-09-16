"""인증·조직.

- 비밀번호: hashlib.scrypt (표준 라이브러리) + 무작위 salt, 상수시간 비교
- 세션: 무작위 토큰을 발급하고 DB에는 SHA-256 해시만 저장. Authorization: Bearer <token>
- 조직: 사용자는 정확히 한 조직에 속한다. 역할은 owner / member
- 초대: owner가 만든 코드로 가입. 자가 가입(ALLOW_SELF_SIGNUP=1)은 새 조직을 만든다
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException

from .config import settings
from .db import connect

SESSION_DAYS = 30
INVITE_DAYS = 7
_SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _after(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat(timespec="seconds")


# ---------- 비밀번호 ----------

def hash_password(pw: str) -> str:
    if len(pw) < 8:
        raise ValueError("비밀번호는 8자 이상이어야 합니다.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pw.encode("utf-8"), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, salt_hex, digest_hex = stored.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(pw.encode("utf-8"), salt=bytes.fromhex(salt_hex), **_SCRYPT)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def _norm_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "이메일 형식이 올바르지 않습니다.")
    return email


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9가-힣]+", "-", name.strip().lower()).strip("-") or "org"
    return f"{base[:40]}-{secrets.token_hex(2)}"


# ---------- 로그인 시도 제한 (프로세스 메모리) ----------

_attempts: dict[str, list[float]] = {}
_attempts_lock = threading.Lock()
MAX_ATTEMPTS, WINDOW_SEC = 5, 300


def _throttle(email: str) -> None:
    now = time.time()
    with _attempts_lock:
        hits = [t for t in _attempts.get(email, []) if now - t < WINDOW_SEC]
        _attempts[email] = hits
        if len(hits) >= MAX_ATTEMPTS:
            raise HTTPException(429, "로그인 시도가 너무 많습니다. 5분 뒤에 다시 시도하세요.")


def _record_failure(email: str) -> None:
    with _attempts_lock:
        _attempts.setdefault(email, []).append(time.time())


# ---------- 모델 ----------

@dataclass
class AuthUser:
    id: str
    email: str
    name: Optional[str]
    role: str
    org_id: str
    org_name: str
    org_slug: str
    monthly_job_limit: int


def _row_to_user(row) -> AuthUser:
    return AuthUser(id=row["id"], email=row["email"], name=row["name"], role=row["role"], org_id=row["org_id"],
                    org_name=row["org_name"], org_slug=row["org_slug"], monthly_job_limit=row["monthly_job_limit"])


USER_SQL = """
SELECT u.id, u.email, u.name, u.role, u.org_id, o.name AS org_name, o.slug AS org_slug, o.monthly_job_limit
FROM users u JOIN orgs o ON o.id = u.org_id
WHERE {where} AND u.is_active = 1 AND o.is_active = 1
"""


# ---------- 조직·사용자 생성 ----------

def create_org(name: str, monthly_job_limit: int = 100) -> dict:
    name = (name or "").strip()
    if not name:
        raise HTTPException(400, "조직 이름이 필요합니다.")
    org = {"id": uuid.uuid4().hex[:12], "name": name, "slug": _slugify(name), "created_at": _now(),
           "monthly_job_limit": monthly_job_limit}
    with connect() as con:
        con.execute("INSERT INTO orgs(id, name, slug, created_at, monthly_job_limit) VALUES(:id,:name,:slug,:created_at,:monthly_job_limit)", org)
    return org


def create_user(org_id: str, email: str, password: str, name: str | None, role: str = "member") -> AuthUser:
    email = _norm_email(email)
    try:
        pw_hash = hash_password(password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    uid = uuid.uuid4().hex[:12]
    with connect() as con:
        if con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(409, "이미 가입된 이메일입니다.")
        con.execute("INSERT INTO users(id, org_id, email, name, password_hash, role, created_at) VALUES(?,?,?,?,?,?,?)",
                    (uid, org_id, email, (name or "").strip() or None, pw_hash, role, _now()))
        row = con.execute(USER_SQL.format(where="u.id = ?"), (uid,)).fetchone()
    return _row_to_user(row)


# ---------- 세션 ----------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def login(email: str, password: str) -> tuple[str, AuthUser]:
    email = _norm_email(email)
    _throttle(email)
    with connect() as con:
        row = con.execute("SELECT password_hash FROM users WHERE email = ? AND is_active = 1", (email,)).fetchone()
        ok = bool(row) and verify_password(password, row["password_hash"])
        if not ok:
            _record_failure(email)
            raise HTTPException(401, "이메일 또는 비밀번호가 맞지 않습니다.")
        user_row = con.execute(USER_SQL.format(where="u.email = ?"), (email,)).fetchone()
        if not user_row:
            raise HTTPException(403, "비활성화된 조직입니다.")
        token = secrets.token_urlsafe(32)
        con.execute("INSERT INTO sessions(token_hash, user_id, created_at, expires_at, last_seen_at) VALUES(?,?,?,?,?)",
                    (_token_hash(token), user_row["id"], _now(), _after(SESSION_DAYS), _now()))
    return token, _row_to_user(user_row)


def logout(token: str) -> None:
    with connect() as con:
        con.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def user_from_token(token: str) -> Optional[AuthUser]:
    with connect() as con:
        s = con.execute("SELECT user_id, expires_at FROM sessions WHERE token_hash = ?", (_token_hash(token),)).fetchone()
        if not s or s["expires_at"] < _now():
            return None
        row = con.execute(USER_SQL.format(where="u.id = ?"), (s["user_id"],)).fetchone()
        if not row:
            return None
        con.execute("UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?", (_now(), _token_hash(token)))
    return _row_to_user(row)


# ---------- 초대 ----------

def create_invite(org_id: str, created_by: str, role: str = "member") -> dict:
    if role not in ("member", "owner"):
        raise HTTPException(400, "역할은 member 또는 owner입니다.")
    inv = {"code": secrets.token_urlsafe(9), "org_id": org_id, "role": role, "created_by": created_by,
           "created_at": _now(), "expires_at": _after(INVITE_DAYS)}
    with connect() as con:
        con.execute("INSERT INTO invites(code, org_id, role, created_by, created_at, expires_at) VALUES(:code,:org_id,:role,:created_by,:created_at,:expires_at)", inv)
    return inv


def accept_invite(code: str, email: str, password: str, name: str | None) -> AuthUser:
    with connect() as con:
        inv = con.execute("SELECT * FROM invites WHERE code = ?", ((code or "").strip(),)).fetchone()
    if not inv or inv["used_at"] or inv["expires_at"] < _now():
        raise HTTPException(400, "초대 코드가 유효하지 않거나 만료되었습니다.")
    user = create_user(inv["org_id"], email, password, name, role=inv["role"])
    with connect() as con:
        con.execute("UPDATE invites SET used_by = ?, used_at = ? WHERE code = ?", (user.id, _now(), inv["code"]))
    return user


def list_members(org_id: str) -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT id, email, name, role, created_at, is_active FROM users WHERE org_id = ? ORDER BY created_at", (org_id,)).fetchall()
    return [dict(r) for r in rows]


def list_open_invites(org_id: str) -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT code, role, created_at, expires_at FROM invites WHERE org_id = ? AND used_at IS NULL AND expires_at > ? ORDER BY created_at DESC",
                           (org_id, _now())).fetchall()
    return [dict(r) for r in rows]


def set_member_active(org_id: str, user_id: str, active: bool) -> None:
    with connect() as con:
        con.execute("UPDATE users SET is_active = ? WHERE id = ? AND org_id = ?", (1 if active else 0, user_id, org_id))
        if not active:
            con.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def jobs_this_month(org_id: str) -> int:
    start = datetime.now().astimezone().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
    with connect() as con:
        return con.execute("SELECT COUNT(*) FROM jobs WHERE org_id = ? AND created_at >= ?", (org_id, start)).fetchone()[0]


# ---------- FastAPI 의존성 ----------

def current_user(authorization: Optional[str] = Header(default=None)) -> AuthUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "로그인이 필요합니다.")
    user = user_from_token(authorization.split(" ", 1)[1].strip())
    if not user:
        raise HTTPException(401, "세션이 만료되었습니다. 다시 로그인하세요.")
    return user


def require_owner(user: AuthUser = Depends(current_user)) -> AuthUser:
    if user.role != "owner":
        raise HTTPException(403, "조직 관리자만 할 수 있습니다.")
    return user


def bearer_token(authorization: Optional[str] = Header(default=None)) -> str:
    return authorization.split(" ", 1)[1].strip() if authorization and " " in authorization else ""
