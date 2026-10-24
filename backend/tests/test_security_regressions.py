import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from threading import Barrier

import pytest
from fastapi import BackgroundTasks, HTTPException, UploadFile
from fastapi.testclient import TestClient

from app import auth, db, main, store
from app.config import settings
from app.schema import Job, Usage


def account(label="a", limit=100):
    org = auth.create_org(label, limit)
    return auth.create_user(org["id"], f"{label}@example.test", "test-password", None, role="owner")


def job(user, created=None):
    return Job(id=store.new_id(), org_id=user.org_id, user_id=user.id, user_email=user.email,
               created_at=created or Job.now(), updated_at=Job.now(), status="queued",
               filename="test.txt", size_bytes=1, usage=Usage())


def upload(name, content):
    return UploadFile(filename=name, file=BytesIO(content))


def submit(user, primary=b"hello", extras=None, filename="test.txt"):
    tasks = BackgroundTasks()
    result = asyncio.run(main.create_job(tasks, upload(filename, primary), None, "all", None,
                                         False, extras or [], user))
    return result, tasks


def test_cross_org_deactivate_cannot_revoke_session():
    a, b = account("a"), account("b")
    token, _ = auth.login(b.email, "test-password")
    with TestClient(main.app) as client:
        atoken, _ = auth.login(a.email, "test-password")
        response = client.post(f"/api/org/members/{b.id}/deactivate", headers={"Authorization": f"Bearer {atoken}"})
        assert response.status_code == 404
    assert auth.user_from_token(token).id == b.id
    auth.set_member_active(b.org_id, b.id, False)
    assert auth.user_from_token(token) is None


@pytest.mark.parametrize("role", ["member", "owner"])
def test_invite_concurrent_single_use(role):
    owner = account()
    invite = auth.create_invite(owner.org_id, owner.id, role)
    gate = Barrier(6)
    def join(i):
        gate.wait()
        try:
            return auth.accept_invite(invite["code"], f"join{i}@example.test", "test-password", None).role
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(join, range(6)))
    assert results.count(role) == 1
    assert results.count(400) == 5
    assert len(auth.list_members(owner.org_id)) == 2


def test_invite_failure_does_not_consume_and_expired_denied():
    owner = account()
    invite = auth.create_invite(owner.org_id, owner.id)
    with pytest.raises(HTTPException) as err:
        auth.accept_invite(invite["code"], owner.email, "test-password", None)
    assert err.value.status_code == 409
    assert len(auth.list_open_invites(owner.org_id)) == 1
    auth.accept_invite(invite["code"], "fresh@example.test", "test-password", None)
    expired = auth.create_invite(owner.org_id, owner.id)
    with db.connect() as con:
        con.execute("UPDATE invites SET expires_at = ? WHERE code = ?", ("2000-01-01", expired["code"]))
    with pytest.raises(HTTPException):
        auth.accept_invite(expired["code"], "expired@example.test", "test-password", None)


def test_invite_transaction_rolls_back_user_on_consume_failure():
    owner = account()
    invite = auth.create_invite(owner.org_id, owner.id)
    with db.connect() as con:
        con.execute("CREATE TRIGGER reject_consume BEFORE UPDATE ON invites BEGIN SELECT RAISE(ABORT, 'synthetic'); END")
    with pytest.raises(sqlite3.IntegrityError):
        auth.accept_invite(invite["code"], "rollback@example.test", "test-password", None)
    assert len(auth.list_members(owner.org_id)) == 1
    assert len(auth.list_open_invites(owner.org_id)) == 1


def test_invalid_invite_rejected_before_password_hash(monkeypatch):
    def should_not_hash(_):
        pytest.fail("Invalid invite must not trigger expensive password hashing")
    monkeypatch.setattr(auth, "hash_password", should_not_hash)
    with pytest.raises(HTTPException) as err:
        auth.accept_invite("invalid", "new@example.test", "test-password", None)
    assert err.value.status_code == 400


def test_quota_concurrent_atomic_admission_and_org_isolation():
    owner = account(limit=1)
    gate = Barrier(6)
    def reserve(i):
        gate.wait()
        try:
            store.reserve_job(job(owner), 1)
            return 200
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(reserve, range(6)))
    assert results.count(200) == 1 and results.count(429) == 5
    assert auth.jobs_this_month(owner.org_id) == 1
    other = account("other", 1)
    store.reserve_job(job(other), 1)
    assert auth.jobs_this_month(other.org_id) == 1


def test_old_month_does_not_consume_current_quota():
    owner = account(limit=1)
    store.save(job(owner, "2000-01-01T00:00:00+00:00"))
    store.reserve_job(job(owner), 1)
    assert auth.jobs_this_month(owner.org_id) == 1


def test_late_quota_rejection_cleans_uploads(monkeypatch):
    owner = account(limit=1)
    store.save(job(owner))
    monkeypatch.setattr(auth, "jobs_this_month", lambda _: 0)  # stale initial observation
    with pytest.raises(HTTPException) as err:
        submit(owner)
    assert err.value.status_code == 429
    assert not list(settings.data_dir.rglob("uploads"))
    assert len(store.list_jobs(owner.org_id)) == 1


def test_concurrent_uploads_admit_and_schedule_only_one(monkeypatch):
    owner = account(limit=1)
    gate = Barrier(4)
    def stale_count(_):
        gate.wait()
        return 0
    monkeypatch.setattr(auth, "jobs_this_month", stale_count)
    def attempt(_):
        try:
            result, tasks = submit(owner)
            return len(tasks.tasks)
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert results.count(1) == 1 and results.count(429) == 3
    assert len(store.list_jobs(owner.org_id)) == 1
    assert len(list(settings.data_dir.rglob("uploads"))) == 1


def test_job_directory_collision_preserves_existing_files(monkeypatch):
    owner = account()
    existing = store.uploads_dir(owner.org_id, "collision")
    (existing / "keep.txt").write_text("existing")
    monkeypatch.setattr(store, "new_id", lambda: "collision")
    with pytest.raises(FileExistsError):
        submit(owner)
    assert (existing / "keep.txt").read_text() == "existing"


@pytest.mark.parametrize("case,status", [("per_file",413),("total",413),("count",413),("empty",400),("duplicate",400)])
def test_upload_rejections_leave_no_jobs_or_files(monkeypatch, case, status):
    owner = account()
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    monkeypatch.setattr(settings, "max_total_upload_mb", 1)
    monkeypatch.setattr(settings, "max_extra_files", 1)
    primary, extras = b"x", []
    if case == "per_file": primary = b"x" * (1024 * 1024 + 1)
    if case == "total":
        primary = b"x" * (600 * 1024)
        extras = [upload("extra.txt", b"x" * (600 * 1024))]
    if case == "count": extras = [upload("a.txt", b"a"), upload("b.txt", b"b")]
    if case == "empty": primary = b""
    if case == "duplicate": extras = [upload("test.txt", b"extra")]
    with pytest.raises(HTTPException) as err:
        submit(owner, primary, extras)
    assert err.value.status_code == status
    assert not store.list_jobs(owner.org_id)
    assert not list(settings.data_dir.rglob("uploads"))


def test_upload_disk_failure_cleans_partial_files(monkeypatch):
    owner = account()
    real_save = main.save_upload
    async def fail_extra(item, target, remaining):
        if item.filename == "extra.txt":
            target.write_bytes(b"partial")
            raise OSError("synthetic disk failure")
        return await real_save(item, target, remaining)
    monkeypatch.setattr(main, "save_upload", fail_extra)
    with pytest.raises(OSError):
        submit(owner, extras=[upload("extra.txt", b"extra")])
    assert not list(settings.data_dir.rglob("uploads"))
    assert not store.list_jobs(owner.org_id)


def test_stream_stops_at_limit(monkeypatch):
    from app.uploads import save_upload
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    item = upload("test.txt", b"x" * (2 * 1024 * 1024))
    with pytest.raises(HTTPException):
        asyncio.run(save_upload(item, settings.data_dir / "stream.bin", 1024 * 1024))
    assert item.file.tell() == 1024 * 1024 + 1


def test_exact_size_boundary_succeeds(monkeypatch):
    owner = account()
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    monkeypatch.setattr(settings, "max_total_upload_mb", 1)
    result, tasks = submit(owner, b"x" * (1024 * 1024))
    assert store.load(result["id"], owner.org_id).size_bytes == 1024 * 1024
    assert len(tasks.tasks) == 1


def test_body_limit_rejects_declared_and_chunked_oversize(monkeypatch):
    monkeypatch.setattr(settings, "max_total_upload_mb", 1)
    with TestClient(main.app) as client:
        assert client.post("/api/jobs", content=b"", headers={"content-length": str(3*1024*1024)}).status_code == 413
        def chunks():
            yield b'--B\r\nContent-Disposition: form-data; name="file"; filename="test.txt"\r\n\r\n'
            yield b"x" * (3 * 1024 * 1024)
            yield b"\r\n--B--\r\n"
        assert client.post("/api/jobs", content=chunks(), headers={"content-type":"multipart/form-data; boundary=B"}).status_code == 413


def test_public_signup_closed_login_invite_and_upload_work(monkeypatch):
    owner = account()
    invite = auth.create_invite(owner.org_id, owner.id)
    executions = []
    monkeypatch.setattr(main, "_execute", lambda *args: executions.append(args))
    with TestClient(main.app) as client:
        response = client.post("/api/auth/register", json={"org_name":"blocked","email":"blocked@example.test","password":"test-password"})
        assert response.status_code == 403
        with db.connect() as con:
            assert con.execute("SELECT COUNT(*) FROM orgs").fetchone()[0] == 1
        login = client.post("/api/auth/login", json={"email":owner.email,"password":"test-password"})
        assert login.status_code == 200
        joined = client.post("/api/auth/join", json={"code":invite["code"],"email":"joined@example.test","password":"test-password"})
        assert joined.status_code == 200
        headers = {"Authorization": "Bearer " + joined.json()["token"]}
        uploaded = client.post("/api/jobs", headers=headers, files={"file":("test.txt", b"hello", "text/plain")})
        assert uploaded.status_code == 200
        assert len(executions) == 1
        jid = uploaded.json()["id"]
        assert client.get(f"/api/jobs/{jid}", headers=headers).status_code == 200
        (store.outputs_dir(owner.org_id, jid) / "report.md").write_text("synthetic report")
        assert client.get(f"/api/jobs/{jid}/report.md", headers=headers).text == "synthetic report"


def test_iac_closes_public_signup():
    source = Path(__file__).resolve().parents[2] / ".railway" / "railway.ts"
    assert 'ALLOW_SELF_SIGNUP: "0"' in source.read_text(encoding="utf-8")
