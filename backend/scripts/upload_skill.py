#!/usr/bin/env python3
"""doc-fact-checker 스킬을 Claude API 워크스페이스에 올린다.

처음:     python scripts/upload_skill.py            → skill_01... 출력 → .env의 DFC_SKILL_ID에 넣는다
수정 후:  python scripts/upload_skill.py --skill-id skill_01...   → 새 버전 생성, skver_... 출력
목록:     python scripts/upload_skill.py --list

운영에서는 DFC_SKILL_VERSION을 latest 대신 skver_... 로 고정해 스킬 수정이 곧바로 운영 동작을 바꾸지 않게 한다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import anthropic
from anthropic.lib import files_from_dir

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "skill" / "doc-fact-checker"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-id", help="기존 스킬에 새 버전을 올릴 때")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dir", default=str(SKILL_DIR))
    a = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY 환경변수가 필요합니다.", file=sys.stderr)
        return 1
    client = anthropic.Anthropic()

    if a.list:
        for s in client.skills.list(source="custom"):
            print(s.id, getattr(s, "display_name", ""), getattr(s, "latest_version_id", ""))
        return 0

    skill_dir = Path(a.dir)
    if not (skill_dir / "SKILL.md").exists():
        print(f"SKILL.md가 없습니다: {skill_dir}", file=sys.stderr)
        return 1

    if a.skill_id:
        ver = client.skills.versions.create(skill_id=a.skill_id, files=files_from_dir(str(skill_dir)))
        print("새 버전 생성:", ver.id)
        print("→ .env: DFC_SKILL_VERSION=" + ver.id + "  (또는 latest)")
    else:
        skill = client.skills.create(files=files_from_dir(str(skill_dir)), display_name="TEN AI Doc Fact Checker")
        print("스킬 생성:", skill.id)
        print("→ .env: DFC_SKILL_ID=" + skill.id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
