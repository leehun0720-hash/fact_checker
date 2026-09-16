"""SQLite 저장소 — 조직·사용자·세션·초대·작업.

내부용→고객 제공으로 넘어가는 단계의 최소 구성이다. 연결은 호출마다 열고 닫아 스레드 안전을 확보하고,
WAL 모드로 읽기·쓰기 경합을 줄인다. 작업(job) 본문은 JSON으로 저장하고 목록·권한 확인용 컬럼만 따로 둔다.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .config import settings

_init_lock = threading.Lock()
_initialized = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS orgs (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL,
  created_at TEXT NOT NULL, monthly_job_limit INTEGER NOT NULL DEFAULT 100, is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES orgs(id), email TEXT UNIQUE NOT NULL, name TEXT,
  password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member', created_at TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL, last_seen_at TEXT
);
CREATE TABLE IF NOT EXISTS invites (
  code TEXT PRIMARY KEY, org_id TEXT NOT NULL REFERENCES orgs(id), role TEXT NOT NULL DEFAULT 'member',
  created_by TEXT, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, used_by TEXT, used_at TEXT
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, user_id TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, status TEXT NOT NULL, filename TEXT NOT NULL, data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_org_created ON jobs(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
"""


def db_path() -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / "dfc.sqlite3"


def init_db() -> None:
    global _initialized
    with _init_lock:
        if _initialized:
            return
        con = sqlite3.connect(db_path())
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA)
            con.commit()
        finally:
            con.close()
        _initialized = True


@contextmanager
def connect():
    init_db()
    con = sqlite3.connect(db_path(), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
