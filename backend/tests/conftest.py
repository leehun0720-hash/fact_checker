"""Use only temporary SQLite/files and never call an external provider in tests."""
import os
import tempfile
from pathlib import Path

import pytest

# Set before importing app.config, even when pytest is invoked directly.
_session_data = tempfile.TemporaryDirectory(prefix="dfc-tests-")
os.environ["DATA_DIR"] = _session_data.name
os.environ["MOCK_VERIFIER"] = "1"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["LAW_API_OC"] = ""

from pydantic_settings import BaseSettings

# app.config normally reads .env; prevent that during test collection too.
_settings_init = BaseSettings.__init__

def _without_dotenv(self, **values):
    values["_env_file"] = None
    _settings_init(self, **values)

BaseSettings.__init__ = _without_dotenv
try:
    from app.config import settings
finally:
    BaseSettings.__init__ = _settings_init

from app import db


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "mock_verifier", True)
    monkeypatch.setattr(settings, "allow_self_signup", False)
    monkeypatch.setattr(db, "_initialized", False)
    from app import auth
    auth._attempts.clear()
    db.init_db()
