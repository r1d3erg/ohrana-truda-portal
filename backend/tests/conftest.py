import os
import sys
import tempfile
from pathlib import Path

import pytest

# БД для тестов — временная SQLite; задаётся до импорта приложения
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.db import Base, engine
    from app.main import app

    with TestClient(app) as c:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        yield c
