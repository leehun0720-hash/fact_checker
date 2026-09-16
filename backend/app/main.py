from __future__ import annotations

import logging
import re
import threading
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import auth, store
from .auth import AuthUser, current_user, require_owner
from .config import settings
from .db import init_db
from .postprocess import postprocess
from .schema import Job, JobOptions, Usage

log = logging.getLogger("dfc")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Doc Fact Checker API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)
init_db()

_job_slots = threading.Semaphore(settings.max_concurrent_jobs)


def _safe_name(name: str) -> str:
    name = Path(name or "upload").name
    name = re.sub(r"[^\w.\-가-힣 ()\[\]]", "_", name)
    return name[:120] or "upload"


def _user_payload(u: AuthUser) -> dict:
    used = auth.jobs_this_month(u.org_id)
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "org": {"id": u.org_id, "name": u.org_name, "slug": u.org_slug,
                    "monthly_job_limit": u.monthly_job_limit, "jobs_this_month": used}}


# ---------- 실행 ----------

def _execute(job_id: str, org_id: str) -> None:
    job = store.load(job_id, org_id)
    if job is None:
        return

    def on_progress(j: Job) -> None:
        store.save(j)

    with _job_slots:
        try:
            if settings.mock_verifier:
                from .mock import run_mock
                outcome = run_mock(job, on_progress)
            else:
                from .verifier import run_verification
                outcome = run_verification(job, on_progress)

            outdir = store.outputs_dir(job.org_id, job.id)
            for name, data in outcome.files.items():
                (outdir / _safe_name(name)).write_bytes(data)
            store.write_json(outdir / "log.json", [e.model_dump() for e in outcome.events])
            if outcome.final_text:
                (outdir / "final_response.md").write_text(outcome.final_text, encoding="utf-8")

            job.status = "postprocessing"
            store.save(job)
            result = postprocess(outcome.raw_result)
            if not result.document.name:
                result.document.name = job.filename
            store.write_json(outdir / "result.normalized.json", result.model_dump())

            job.result = result
            job.usage = outcome.usage
            job.has_report = (outdir / "report.md").exists()
            job.has_corrected = (outdir / "corrected.md").exists()
            job.status = "done"
            store.save(job)
        except Exception as exc:  # noqa: BLE001 — 작업 단위로 실패를 기록한다
            log.exception("job %s failed", job_id)
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
            store.save(job)


# ---------- 인증 ----------

class LoginIn(BaseModel):
    email: str
    password: str


class RegisterIn(BaseModel):
    org_name: str
    email: str
    password: str
    name: Optional[str] = None


class JoinIn(BaseModel):
    code: str
    email: str
    password: str
    name: Optional[str] = None


class InviteIn(BaseModel):
    role: str = "member"


@app.get("/api/health")
def health():
    return {"ok": True, "mock": settings.mock_verifier, "model": settings.claude_model,
            "skill_configured": bool(settings.dfc_skill_id), "law_api": bool(settings.law_api_oc),
            "self_signup": settings.allow_self_signup}


@app.post("/api/auth/login")
def api_login(body: LoginIn):
    token, user = auth.login(body.email, body.password)
    return {"token": token, "user": _user_payload(user)}


@app.post("/api/auth/register")
def api_register(body: RegisterIn):
    if not settings.allow_self_signup:
        raise HTTPException(403, "지금은 초대 코드로만 가입할 수 있습니다. 조직 관리자에게 초대 코드를 요청하세요.")
    org = auth.create_org(body.org_name, settings.default_monthly_job_limit)
    auth.create_user(org["id"], body.email, body.password, body.name, role="owner")
    token, user = auth.login(body.email, body.password)
    return {"token": token, "user": _user_payload(user)}


@app.post("/api/auth/join")
def api_join(body: JoinIn):
    auth.accept_invite(body.code, body.email, body.password, body.name)
    token, user = auth.login(body.email, body.password)
    return {"token": token, "user": _user_payload(user)}


@app.post("/api/auth/logout")
def api_logout(token: str = Depends(auth.bearer_token)):
    if token:
        auth.logout(token)
    return {"ok": True}


@app.get("/api/auth/me")
def api_me(user: AuthUser = Depends(current_user)):
    return _user_payload(user)


# ---------- 조직 ----------

@app.get("/api/org")
def api_org(user: AuthUser = Depends(current_user)):
    return {**_user_payload(user)["org"], "members": auth.list_members(user.org_id),
            "invites": auth.list_open_invites(user.org_id) if user.role == "owner" else []}


@app.post("/api/org/invites")
def api_create_invite(body: InviteIn, user: AuthUser = Depends(require_owner)):
    return auth.create_invite(user.org_id, user.id, body.role)


@app.post("/api/org/members/{user_id}/deactivate")
def api_deactivate(user_id: str, user: AuthUser = Depends(require_owner)):
    if user_id == user.id:
        raise HTTPException(400, "자기 자신은 비활성화할 수 없습니다.")
    auth.set_member_active(user.org_id, user_id, False)
    return {"ok": True}


@app.post("/api/org/members/{user_id}/activate")
def api_activate(user_id: str, user: AuthUser = Depends(require_owner)):
    auth.set_member_active(user.org_id, user_id, True)
    return {"ok": True}


# ---------- 작업 ----------

@app.post("/api/jobs")
async def create_job(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    as_of: Optional[str] = Form(default=None),
    scope: str = Form(default="전체"),
    notes: Optional[str] = Form(default=None),
    want_corrected: bool = Form(default=False),
    extra_files: list[UploadFile] = File(default=[]),
    user: AuthUser = Depends(current_user),
):
    used = auth.jobs_this_month(user.org_id)
    if used >= user.monthly_job_limit:
        raise HTTPException(429, f"이번 달 검증 한도({user.monthly_job_limit}건)를 모두 썼습니다. 한도 조정은 운영자에게 문의하세요.")

    name = _safe_name(file.filename or "")
    ext = Path(name).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(400, f"지원하지 않는 형식입니다: {ext or '(확장자 없음)'} — 가능: {', '.join(settings.allowed_extensions)}")

    data = await file.read()
    limit = settings.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise HTTPException(413, f"파일이 {settings.max_upload_mb}MB를 넘습니다.")
    if not data:
        raise HTTPException(400, "빈 파일입니다.")

    job_id = store.new_id()
    updir = store.uploads_dir(user.org_id, job_id)
    (updir / name).write_bytes(data)

    extra_names: list[str] = []
    for ef in extra_files:
        if not ef.filename:
            continue
        en = _safe_name(ef.filename)
        if en == name:
            en = "extra_" + en
        edata = await ef.read()
        if len(edata) > limit:
            raise HTTPException(413, f"근거자료 {en}이(가) {settings.max_upload_mb}MB를 넘습니다.")
        (updir / en).write_bytes(edata)
        extra_names.append(en)

    job = Job(
        id=job_id, org_id=user.org_id, user_id=user.id, user_email=user.email,
        created_at=Job.now(), updated_at=Job.now(), status="queued",
        filename=name, size_bytes=len(data), extra_files=extra_names,
        options=JobOptions(as_of=(as_of or None), scope=scope or "전체", notes=(notes or None),
                           want_corrected=want_corrected),
        usage=Usage(),
    )
    store.save(job)
    background.add_task(_execute, job_id, user.org_id)
    return {"id": job_id, "status": job.status}


@app.get("/api/jobs")
def list_jobs(limit: int = 50, user: AuthUser = Depends(current_user)):
    return [j.model_dump() for j in store.list_jobs(user.org_id, limit=limit)]


def _load_or_404(job_id: str, user: AuthUser) -> Job:
    job = store.load(job_id, user.org_id)
    if job is None:
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, user: AuthUser = Depends(current_user)):
    return JSONResponse(_load_or_404(job_id, user).model_dump())


def _output_file(job: Job, name: str, media_type: str) -> FileResponse:
    p = store.outputs_dir(job.org_id, job.id) / name
    if not p.exists():
        raise HTTPException(404, f"{name}이(가) 아직 없습니다.")
    return FileResponse(p, media_type=media_type, filename=f"{job.id}_{name}")


@app.get("/api/jobs/{job_id}/report.md")
def get_report(job_id: str, user: AuthUser = Depends(current_user)):
    return _output_file(_load_or_404(job_id, user), "report.md", "text/markdown; charset=utf-8")


@app.get("/api/jobs/{job_id}/corrected.md")
def get_corrected(job_id: str, user: AuthUser = Depends(current_user)):
    return _output_file(_load_or_404(job_id, user), "corrected.md", "text/markdown; charset=utf-8")


@app.get("/api/jobs/{job_id}/result.json")
def get_result_json(job_id: str, user: AuthUser = Depends(current_user)):
    return _output_file(_load_or_404(job_id, user), "result.normalized.json", "application/json")


@app.get("/api/jobs/{job_id}/log.json")
def get_log(job_id: str, user: AuthUser = Depends(current_user)):
    return _output_file(_load_or_404(job_id, user), "log.json", "application/json")


@app.get("/api/jobs/{job_id}/report.pdf")
def get_report_pdf(job_id: str, user: AuthUser = Depends(current_user)):
    """후처리된 결과로 PDF를 만든다. 한 번 만들면 outputs/report.pdf에 두고 재사용한다."""
    job = _load_or_404(job_id, user)
    if job.status != "done" or job.result is None:
        raise HTTPException(409, "검증이 끝난 뒤에 받을 수 있습니다.")
    outdir = store.outputs_dir(job.org_id, job.id)
    pdf_path = outdir / "report.pdf"
    if not pdf_path.exists():
        from .report_pdf import html_to_pdf, render_html
        try:
            pdf_path.write_bytes(html_to_pdf(render_html(job, job.result)))
        except RuntimeError as exc:
            raise HTTPException(503, str(exc))
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"검증보고서_{Path(job.filename).stem}.pdf")
