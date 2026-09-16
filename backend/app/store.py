"""작업 저장소 — SQLite(jobs 테이블)에 본문 JSON을 저장하고, 업로드·산출물은 조직별 폴더에 둔다.

DATA_DIR/orgs/<org_id>/jobs/<job_id>/uploads/ , outputs/
조직 격리는 두 겹이다: DB 조회는 항상 org_id로 걸고, 파일 경로에도 org_id가 들어간다.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional

from .config import settings
from .db import connect
from .schema import Job


def job_dir(org_id: str, job_id: str) -> Path:
    return settings.data_dir / "orgs" / org_id / "jobs" / job_id


def outputs_dir(org_id: str, job_id: str) -> Path:
    p = job_dir(org_id, job_id) / "outputs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def uploads_dir(org_id: str, job_id: str) -> Path:
    p = job_dir(org_id, job_id) / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def save(job: Job) -> Job:
    job.updated_at = Job.now()
    with connect() as con:
        con.execute(
            """INSERT INTO jobs(id, org_id, user_id, created_at, updated_at, status, filename, data)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at, status = excluded.status, data = excluded.data""",
            (job.id, job.org_id, job.user_id, job.created_at, job.updated_at, job.status, job.filename, job.model_dump_json()),
        )
    return job


def load(job_id: str, org_id: Optional[str] = None) -> Optional[Job]:
    """org_id를 주면 그 조직의 작업만 돌려준다. (다른 조직 ID를 알아도 볼 수 없음)"""
    with connect() as con:
        if org_id is None:
            row = con.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
        else:
            row = con.execute("SELECT data FROM jobs WHERE id = ? AND org_id = ?", (job_id, org_id)).fetchone()
    return Job.model_validate_json(row["data"]) if row else None


def list_jobs(org_id: str, limit: int = 50) -> list[Job]:
    with connect() as con:
        rows = con.execute("SELECT data FROM jobs WHERE org_id = ? ORDER BY created_at DESC LIMIT ?", (org_id, limit)).fetchall()
    items = []
    for r in rows:
        j = Job.model_validate_json(r["data"])
        items.append(j.model_copy(update={"result": None, "progress": []}))  # 목록엔 무거운 본문 제외
    return items


ACTIVE_STATUSES = ("queued", "uploading", "running", "postprocessing")


def fail_active_jobs(reason: str) -> int:
    """진행 중이던 작업을 모두 실패로 바꾼다. 서버 재시작 직후에 부른다 —
    검증은 프로세스 안에서 돌기 때문에 재시작되면 이어갈 수 없다."""
    n = 0
    with connect() as con:
        rows = con.execute(
            f"SELECT data FROM jobs WHERE status IN ({','.join('?' * len(ACTIVE_STATUSES))})", ACTIVE_STATUSES
        ).fetchall()
    for r in rows:
        job = Job.model_validate_json(r["data"])
        job.status = "failed"
        job.error = reason
        save(job)
        n += 1
    return n


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
