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


ADMIN_PASSWORD = "Admin-pass-123"
CSRF = {"X-Requested-With": "ot-portal"}


def make_user(login: str, role: str, password: str = "Strong-pass-1", offices=(), must_change=False):
    """Создать пользователя напрямую в БД (для тестов)."""
    from app import auth
    from app.db import SessionLocal
    from app.models import Office, User
    from sqlalchemy import select

    with SessionLocal() as db:
        u = User(login=login, full_name=login, role=role, password_hash=auth.hash_password(password),
                 must_change_password=must_change)
        u.offices = [db.scalar(select(Office).where(Office.code == c)) for c in offices]
        db.add(u)
        db.commit()
        return u.id


def login_client(login: str, password: str):
    """Отдельный клиент (свои cookie), вошедший под пользователем."""
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    c.headers.update(CSRF)
    r = c.post("/api/auth/login", json={"login": login, "password": password})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture()
def anon():
    """Клиент без входа (но с заголовком CSRF)."""
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    c.headers.update(CSRF)
    return c


@pytest.fixture()
def client():
    """Клиент, вошедший под администратором (служба ОТ)."""
    from fastapi.testclient import TestClient

    from app.auth import throttle
    from app.db import Base, engine
    from app.main import app

    with TestClient(app) as c:
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        throttle.clear()
        make_user("admin", "admin", ADMIN_PASSWORD)
        c.headers.update(CSRF)
        r = c.post("/api/auth/login", json={"login": "admin", "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        yield c
