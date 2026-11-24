"""Авторизация и роли: вход, сессии, CSRF, ограничение попыток, права по ролям и офисам."""
from conftest import ADMIN_PASSWORD, CSRF, login_client, make_user
from factory import build_checklist

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def upload(c, office):
    return c.post("/api/imports", files={"file": (f"{office}.xlsx", build_checklist(office=office), XLSX)})


# --- Вход, сессия, CSRF ----------------------------------------------------------
def test_anonymous_gets_401(client, anon):
    for path in ("/api/offices", "/api/dashboard", "/api/sout", "/api/directions/fire", "/api/users"):
        assert anon.get(path).status_code == 401, path
    assert anon.get("/api/health").status_code == 200
    assert anon.get("/api/config").status_code == 200


def test_login_logout_and_me(client, anon):
    r = anon.post("/api/auth/login", json={"login": "ADMIN ", "password": ADMIN_PASSWORD})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie
    assert anon.get("/api/auth/me").json()["login"] == "admin"
    assert anon.post("/api/auth/logout").status_code == 200
    assert anon.get("/api/auth/me").status_code == 401


def test_wrong_password_is_generic_401(client, anon):
    r1 = anon.post("/api/auth/login", json={"login": "admin", "password": "nope-nope-1"})
    r2 = anon.post("/api/auth/login", json={"login": "ghost", "password": "nope-nope-1"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()


def test_login_throttled_after_5_fails(client, anon):
    for _ in range(5):
        assert anon.post("/api/auth/login", json={"login": "admin", "password": "bad-pass-123"}).status_code == 401
    r = anon.post("/api/auth/login", json={"login": "admin", "password": ADMIN_PASSWORD})
    assert r.status_code == 429


def test_login_key_has_higher_limit_than_ip():
    from app.auth import throttle

    throttle.clear()
    for _ in range(5):
        throttle.fail("login:admin")
    assert not throttle.blocked("login:admin")   # для логина порог 10
    for _ in range(5):
        throttle.fail("ip:1.2.3.4")
    assert throttle.blocked("ip:1.2.3.4")
    throttle.clear()


def test_csrf_header_required_for_changes(client):
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    assert c.post("/api/auth/login", json={"login": "admin", "password": ADMIN_PASSWORD}).status_code == 403
    # С заголовком — вход, без заголовка — изменения запрещены, чтение разрешено
    c.headers.update(CSRF)
    assert c.post("/api/auth/login", json={"login": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    del c.headers["X-Requested-With"]
    assert c.get("/api/offices").status_code == 200
    assert c.post("/api/offices", json={"code": "x1"}).status_code == 403


def test_forged_cookie_rejected(client, anon):
    anon.cookies.set("ot_session", "forged-token", path="/api")
    assert anon.get("/api/offices").status_code == 401


# --- Временный пароль --------------------------------------------------------------
def test_must_change_password_flow(client):
    make_user("newbie", "viewer", "Temp-pass-123", must_change=True)
    c = login_client("newbie", "Temp-pass-123")
    assert c.get("/api/auth/me").json()["must_change_password"] is True
    assert c.get("/api/offices").status_code == 403
    bad = c.post("/api/auth/password", json={"current_password": "Temp-pass-123", "new_password": "short"})
    assert bad.status_code == 422
    ok = c.post("/api/auth/password", json={"current_password": "Temp-pass-123", "new_password": "Brand-new-pass-7"})
    assert ok.status_code == 200 and ok.json()["must_change_password"] is False
    assert c.get("/api/offices").status_code == 200


# --- Роли ---------------------------------------------------------------------------
def test_viewer_reads_but_cannot_change(client):
    assert upload(client, "v1").status_code == 200
    make_user("boss", "viewer")
    v = login_client("boss", "Strong-pass-1")
    assert v.get("/api/dashboard").status_code == 200
    assert [o["code"] for o in v.get("/api/offices").json()] == ["v1"]  # руководитель видит все офисы
    assert v.get("/api/offices/v1").status_code == 200
    assert upload(v, "v1").status_code == 403
    assert v.post("/api/offices/v1/sout", json={}).status_code == 403
    assert v.put("/api/offices/v1/directions/fire", json={}).status_code == 403
    assert v.get("/api/users").status_code == 403


def test_responsible_limited_to_own_offices(client):
    assert upload(client, "own").status_code == 200
    assert upload(client, "other").status_code == 200
    make_user("resp", "responsible", offices=["own"])
    r = login_client("resp", "Strong-pass-1")

    # видит только свои офисы — везде: список, дашборд, реестры, карточки
    assert [o["code"] for o in r.get("/api/offices").json()] == ["own"]
    dash = r.get("/api/dashboard").json()
    assert [m["code"] for m in dash["matrix"]] == ["own"]
    assert set(dash["registers"]["sout"]["by_office"]) == {"own"}
    assert set(dash["registers"]["directions"]["fire"]["by_office"]) == {"own"}
    assert all(a["office_code"] == "own" for a in dash["registers"]["alerts"])
    assert [s["office_code"] for s in r.get("/api/sout").json()] == ["own"]
    assert [s["office_code"] for s in r.get("/api/opr").json()] == ["own"]
    assert [s["office_code"] for s in r.get("/api/directions/go").json()] == ["own"]
    for path in ("/api/offices/other", "/api/offices/other/checklist", "/api/offices/other/imports",
                 "/api/offices/other/sout", "/api/offices/other/opr", "/api/offices/other/directions/fire"):
        assert r.get(path).status_code == 404, path
    other_import = client.get("/api/offices/other/imports").json()[0]["id"]
    assert r.get(f"/api/imports/{other_import}").status_code == 404
    # служба ОТ и руководитель видят всё
    assert len(client.get("/api/offices").json()) == 2
    # запись — только своих
    assert r.put("/api/offices/own/directions/fire", json={"responsible": "Я"}).status_code == 200
    assert r.put("/api/offices/other/directions/fire", json={"responsible": "Я"}).status_code == 404
    rec = r.post("/api/offices/own/sout", json={"kind": "planned", "status": "planned"})
    assert rec.status_code == 201
    assert r.post("/api/offices/other/sout", json={"kind": "planned", "status": "planned"}).status_code == 404
    other_rec = client.post("/api/offices/other/sout", json={"kind": "planned", "status": "planned"}).json()
    assert r.put(f"/api/sout/{other_rec['id']}", json={"kind": "planned", "status": "planned"}).status_code == 404
    # удаление и управление — только служба ОТ
    assert r.delete(f"/api/sout/{rec.json()['id']}").status_code == 403
    assert r.post("/api/offices", json={"code": "new"}).status_code == 403
    assert r.patch("/api/offices/own", json={"responsible": "x"}).status_code == 403

    # загрузка: своя — можно, чужая — нет, новый офис — нет
    own2 = build_checklist(office="own", check_date="18.08.2026")
    assert r.post("/api/imports", files={"file": ("own.xlsx", own2, XLSX)}).status_code == 200
    assert upload(r, "other").status_code == 404
    assert upload(r, "brand-new").status_code == 403
    assert client.get("/api/offices/brand-new").status_code == 404


# --- Управление пользователями -------------------------------------------------------
def test_admin_manages_users(client):
    assert upload(client, "u1").status_code == 200
    r = client.post("/api/users", json={"login": "Ivanov", "full_name": "Иванов И.", "role": "responsible",
                                        "password": "Temp-pass-123", "offices": ["u1"]})
    assert r.status_code == 201, r.text
    u = r.json()
    assert u["login"] == "ivanov" and u["offices"] == ["u1"] and u["must_change_password"] is True

    assert client.post("/api/users", json={"login": "ivanov", "role": "viewer", "password": "Temp-pass-123"}).status_code == 409
    weak = client.post("/api/users", json={"login": "petrov", "role": "viewer", "password": "12345678901"})
    assert weak.status_code == 422
    assert client.post("/api/users", json={"login": "x y", "role": "viewer", "password": "Temp-pass-123"}).status_code == 422
    assert client.post("/api/users", json={"login": "z1", "role": "god", "password": "Temp-pass-123"}).status_code == 422
    assert client.post("/api/users", json={"login": "z2", "role": "responsible", "password": "Temp-pass-123",
                                           "offices": ["nope"]}).status_code == 422

    # отключение закрывает сессии пользователя
    c = login_client("ivanov", "Temp-pass-123")
    assert c.get("/api/auth/me").status_code == 200
    assert client.patch(f"/api/users/{u['id']}", json={"is_active": False}).status_code == 200
    assert c.get("/api/auth/me").status_code == 401
    assert c.post("/api/auth/login", json={"login": "ivanov", "password": "Temp-pass-123"}).status_code == 401

    # роль viewer — офисы снимаются
    upd = client.patch(f"/api/users/{u['id']}", json={"role": "viewer", "is_active": True}).json()
    assert upd["role"] == "viewer" and upd["offices"] == []


def test_admin_cannot_lock_himself_out(client):
    me = client.get("/api/auth/me").json()
    assert client.patch(f"/api/users/{me['id']}", json={"role": "viewer"}).status_code == 422
    assert client.patch(f"/api/users/{me['id']}", json={"is_active": False}).status_code == 422


def test_password_reset_by_admin_forces_change(client):
    make_user("lena", "viewer")
    c = login_client("lena", "Strong-pass-1")
    uid = c.get("/api/auth/me").json()["id"]
    assert client.patch(f"/api/users/{uid}", json={"password": "Reset-pass-123"}).status_code == 200
    assert c.get("/api/auth/me").status_code == 401   # старые сессии закрыты
    c2 = login_client("lena", "Reset-pass-123")
    assert c2.get("/api/auth/me").json()["must_change_password"] is True


def test_password_hash_not_exposed(client):
    users = client.get("/api/users").json()
    assert users
    for u in users:
        assert "password_hash" not in u and "password" not in u
        assert not any("scrypt$" in str(v) for v in u.values())


def test_generated_admin_password_goes_to_file_not_log(monkeypatch, tmp_path, caplog):
    import os
    import stat

    from app import auth, config
    from app.db import Base, SessionLocal, engine

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    pw_file = tmp_path / "initial-admin-password.txt"
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(config, "INITIAL_PASSWORD_FILE", str(pw_file))
    with SessionLocal() as db:
        auth.bootstrap_admin(db)
    text = pw_file.read_text()
    password = text.split("password: ")[1].strip()
    assert password and password not in caplog.text
    assert stat.S_IMODE(os.stat(pw_file).st_mode) == 0o600
    auth.remove_initial_password_file()
    assert not pw_file.exists()


def test_bootstrap_admin(monkeypatch):
    from app import auth, config
    from app.db import Base, SessionLocal, engine
    from app.models import User
    from sqlalchemy import select

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "Boot-pass-123")
    with SessionLocal() as db:
        auth.bootstrap_admin(db)
        auth.bootstrap_admin(db)  # второй раз ничего не делает
        users = db.scalars(select(User)).all()
        assert len(users) == 1 and users[0].role == "admin" and users[0].must_change_password
        assert auth.verify_password("Boot-pass-123", users[0].password_hash)
