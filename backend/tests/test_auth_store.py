import os, tempfile, pathlib

os.environ["DATA_DIR"] = tempfile.mkdtemp()
os.environ["MOCK_VERIFIER"] = "1"

import pytest
from fastapi import HTTPException

from app import auth, store
from app.schema import Job, Usage


def _job(org_id, user_id, name="a.pdf"):
    j = Job(id=store.new_id(), org_id=org_id, user_id=user_id, user_email="x@y.z", created_at=Job.now(),
            updated_at=Job.now(), status="queued", filename=name, size_bytes=10, usage=Usage())
    return store.save(j)


def test_org_isolation_and_sessions():
    org_a = auth.create_org("A사", 3)
    org_b = auth.create_org("B사", 3)
    ua = auth.create_user(org_a["id"], "A@a.com", "password1", "가", role="owner")
    ub = auth.create_user(org_b["id"], "b@b.com", "password2", None)
    assert ua.email == "a@a.com" and ua.role == "owner" and ub.role == "member"

    token, user = auth.login("a@a.com", "password1")
    assert auth.user_from_token(token).id == ua.id
    assert auth.user_from_token("nope") is None
    with pytest.raises(HTTPException):
        auth.login("a@a.com", "wrong-password")

    ja = _job(org_a["id"], ua.id)
    jb = _job(org_b["id"], ub.id, "b.pdf")
    assert store.load(ja.id, org_a["id"]).filename == "a.pdf"
    assert store.load(ja.id, org_b["id"]) is None          # 다른 조직 ID로는 보이지 않음
    assert [j.id for j in store.list_jobs(org_a["id"])] == [ja.id]
    assert store.uploads_dir(org_a["id"], ja.id).parts[-4] == org_a["id"]
    assert auth.jobs_this_month(org_a["id"]) == 1 and auth.jobs_this_month(org_b["id"]) == 1

    auth.logout(token)
    assert auth.user_from_token(token) is None


def test_invites_and_deactivation():
    org = auth.create_org("C사")
    owner = auth.create_user(org["id"], "o@c.com", "password3", None, role="owner")
    inv = auth.create_invite(org["id"], owner.id)
    m = auth.accept_invite(inv["code"], "m@c.com", "password4", "멤버")
    assert m.org_id == org["id"] and m.role == "member"
    with pytest.raises(HTTPException):
        auth.accept_invite(inv["code"], "m2@c.com", "password5", None)  # 재사용 불가
    with pytest.raises(HTTPException):
        auth.create_user(org["id"], "m@c.com", "password6", None)        # 중복 이메일
    with pytest.raises(HTTPException):
        auth.create_user(org["id"], "s@c.com", "short", None)            # 짧은 비밀번호

    token, _ = auth.login("m@c.com", "password4")
    auth.set_member_active(org["id"], m.id, False)
    assert auth.user_from_token(token) is None                           # 비활성화 시 세션 제거
    with pytest.raises(HTTPException):
        auth.login("m@c.com", "password4")


def test_password_hash_roundtrip():
    h = auth.hash_password("correct horse")
    assert h.startswith("scrypt$") and auth.verify_password("correct horse", h)
    assert not auth.verify_password("wrong", h) and not auth.verify_password("x", "garbage")


def test_interrupted_and_stale_jobs_are_failed():
    from datetime import datetime, timedelta
    from app.main import _reap_if_stale, STALE_AFTER

    org = auth.create_org("C사", 3)
    u = auth.create_user(org["id"], "c@c.com", "password3", None)
    running = _job(org["id"], u.id, "run.pdf"); running.status = "running"; store.save(running)
    done = _job(org["id"], u.id, "done.pdf"); done.status = "done"; store.save(done)

    # 재시작 정리: 활성 작업만 실패로, 완료 작업은 그대로
    assert store.fail_active_jobs("재시작") >= 1
    assert store.load(running.id, org["id"]).status == "failed"
    assert store.load(done.id, org["id"]).status == "done"

    # 오래 멈춘 작업: updated_at이 임계보다 오래되면 조회 시 실패 처리
    stale = _job(org["id"], u.id, "stale.pdf"); stale.status = "running"; store.save(stale)
    stale.updated_at = (datetime.now().astimezone() - STALE_AFTER - timedelta(minutes=1)).isoformat(timespec="seconds")
    assert _reap_if_stale(stale).status == "failed" and "진행 기록" in (stale.error or "")
    fresh = _job(org["id"], u.id, "fresh.pdf"); fresh.status = "running"; store.save(fresh)
    assert _reap_if_stale(fresh).status == "running"
