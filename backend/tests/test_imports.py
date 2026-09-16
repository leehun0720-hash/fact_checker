"""모든 모듈이 import되는지 확인 — main.py는 verifier를 작업 실행 시점에 지연 import하므로
문법 오류가 있어도 서버는 뜬다. 여기서 미리 잡는다."""
import importlib
import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())

import pytest


@pytest.mark.parametrize("mod", ["app.main", "app.verifier", "app.mock", "app.postprocess", "app.lawapi",
                                 "app.report_pdf", "app.auth", "app.store", "app.db", "app.prompts", "app.schema"])
def test_module_imports(mod):
    importlib.import_module(mod)
