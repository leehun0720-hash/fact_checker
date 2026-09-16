#!/usr/bin/env python3
"""첫 조직과 관리자(owner) 계정을 만든다. 운영자용 스크립트.

  python scripts/create_org.py --org "TEN AI" --email admin@example.com --password '********' --name 홍길동
  python scripts/create_org.py --org "고객사A" --email a@client.com --password '...' --limit 50

.env(DATA_DIR)가 있는 backend/ 폴더에서 실행한다. 이후 팀원은 앱의 '조직' 화면에서 owner가 만든 초대 코드로 가입한다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/ 를 import 경로에 추가

from app import auth  # noqa: E402
from app.config import settings  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", required=True, help="조직 이름")
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True, help="8자 이상")
    ap.add_argument("--name", default=None)
    ap.add_argument("--limit", type=int, default=settings.default_monthly_job_limit, help="월 검증 한도")
    a = ap.parse_args()

    org = auth.create_org(a.org, a.limit)
    user = auth.create_user(org["id"], a.email, a.password, a.name, role="owner")
    print(f"조직 생성: {org['name']} (id={org['id']}, slug={org['slug']}, 월 한도 {a.limit}건)")
    print(f"관리자 계정: {user.email} (role={user.role})")
    print(f"데이터 위치: {settings.data_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
