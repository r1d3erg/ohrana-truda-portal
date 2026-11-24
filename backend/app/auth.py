"""Авторизация портала: пользователи, роли, сессии.

Уровень — «обычный»: логин и пароль, серверные сессии в HttpOnly-cookie, защита от CSRF
заголовком, ограничение попыток входа. Только стандартная библиотека Python.

Роли:
  admin       — служба ОТ: всё, включая пользователей, офисы и удаление.
  responsible — ответственный офиса: видит и изменяет только назначенные ему офисы
                (дашборд, документы, загрузка чек-листа, СОУТ, ОПР, ПБ, ЭБ, ГО ЧС). Удалять не может.
                Чужие офисы для него не существуют: на запрос — 404.
  viewer      — руководитель / наблюдатель: только просмотр.

Подробно — docs/auth.md.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import AuthSession, Office, User

log = logging.getLogger("ohrana.auth")

ROLES = {
    "admin": "Служба охраны труда (администратор)",
    "responsible": "Ответственный офиса",
    "viewer": "Руководитель (просмотр)",
}

COOKIE = "ot_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "ot-portal"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

PASSWORD_MIN = 10
LOGIN_RE_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789._-@")

# --- Пароли: scrypt (hashlib, без внешних зависимостей) ------------------------------
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, maxmem=64 * 1024 * 1024, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                              dklen=len(bytes.fromhex(dk)), maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(calc.hex(), dk)
    except (ValueError, TypeError):
        return False


# Хэш-заглушка: при неизвестном логине тратим столько же времени, сколько на проверку пароля
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def password_problems(password: str, login: str | None = None) -> list[str]:
    errs = []
    if len(password) < PASSWORD_MIN:
        errs.append(f"Пароль не короче {PASSWORD_MIN} символов")
    if len(password) > 128:
        errs.append("Пароль не длиннее 128 символов")
    if login and password.lower() == login.lower():
        errs.append("Пароль не должен совпадать с логином")
    if password.isdigit() or password.isalpha():
        errs.append("В пароле нужны и буквы, и цифры или символы")
    return errs


def normalize_login(login: str) -> str:
    return (login or "").strip().lower()


def login_problems(login: str) -> list[str]:
    if not (3 <= len(login) <= 64) or not set(login) <= LOGIN_RE_CHARS:
        return ["Логин: 3–64 символа, латиница в нижнем регистре, цифры, «.», «_», «-», «@»"]
    return []


# --- Ограничение попыток входа (в памяти процесса) -------------------------------------
class _Throttle:
    def __init__(self):
        self._lock = threading.Lock()
        self._fails: dict[str, list[float]] = {}

    def _key_list(self, key: str, now: float) -> list[float]:
        window = config.LOGIN_WINDOW_MIN * 60
        lst = [t for t in self._fails.get(key, []) if now - t < window]
        self._fails[key] = lst
        return lst

    @staticmethod
    def _limit(key: str) -> int:
        # На логин — вдвое больше попыток, чем на IP: подбор с одного адреса блокируется быстрее,
        # а чужие попытки не запирают учётную запись так же легко
        return config.LOGIN_MAX_FAILS * (2 if key.startswith("login:") else 1)

    def blocked(self, *keys: str) -> bool:
        now = time.monotonic()
        with self._lock:
            return any(len(self._key_list(k, now)) >= self._limit(k) for k in keys)

    def fail(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            for k in keys:
                self._key_list(k, now).append(now)

    def reset(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._fails.pop(k, None)

    def clear(self) -> None:
        with self._lock:
            self._fails.clear()


throttle = _Throttle()


def client_ip(request: Request) -> str:
    # За nginx реальный адрес — в X-Real-IP (выставляет наш nginx.conf). Иначе — адрес соединения.
    if config.TRUST_PROXY:
        ip = request.headers.get("x-real-ip")
        if ip:
            return ip.strip()[:64]
    return request.client.host if request.client else "unknown"


# --- Сессии --------------------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    # SQLite возвращает время без зоны — считаем его UTC
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, request: Request) -> str:
    token = secrets.token_urlsafe(32)
    now = _now()
    db.add(AuthSession(
        token_hash=_token_hash(token), user_id=user.id, created_at=now, last_seen_at=now,
        expires_at=now + timedelta(hours=config.SESSION_HOURS),
        ip=client_ip(request), user_agent=(request.headers.get("user-agent") or "")[:255],
    ))
    user.last_login_at = now
    # Чистим просроченные сессии
    db.execute(delete(AuthSession).where(AuthSession.expires_at < now))
    db.commit()
    return token


def set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE, token, max_age=config.SESSION_HOURS * 3600, httponly=True,
        secure=config.COOKIE_SECURE, samesite="strict", path="/api",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/api", secure=config.COOKIE_SECURE, httponly=True, samesite="strict")


def _session_from_request(db: Session, request: Request) -> AuthSession | None:
    token = request.cookies.get(COOKIE)
    if not token or len(token) > 200:
        return None
    s = db.scalar(select(AuthSession).where(AuthSession.token_hash == _token_hash(token)))
    if s is None:
        return None
    now = _now()
    idle = timedelta(minutes=config.SESSION_IDLE_MIN)
    if _aware(s.expires_at) < now or now - _aware(s.last_seen_at) > idle:
        db.delete(s)
        db.commit()
        return None
    if now - _aware(s.last_seen_at) > timedelta(minutes=1):
        s.last_seen_at = now
        db.commit()
    return s


def revoke_user_sessions(db: Session, user_id: int, keep_hash: str | None = None) -> None:
    q = delete(AuthSession).where(AuthSession.user_id == user_id)
    if keep_hash:
        q = q.where(AuthSession.token_hash != keep_hash)
    db.execute(q)


# --- Зависимости FastAPI -----------------------------------------------------------------
def _unauthorized(message="Требуется вход в систему"):
    raise HTTPException(status_code=401, detail={"message": message})


def _forbidden(message="Недостаточно прав"):
    raise HTTPException(status_code=403, detail={"message": message})


def check_csrf(request: Request) -> None:
    """Изменяющие запросы принимаются только с заголовком X-Requested-With: ot-portal.

    Чужой сайт не может отправить такой заголовок без CORS-разрешения, а CORS для чужих
    доменов не открыт. Вместе с SameSite=Strict это закрывает CSRF.
    """
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        _forbidden("Запрос отклонён: нет заголовка защиты от CSRF")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    check_csrf(request)
    s = _session_from_request(db, request)
    if s is None:
        _unauthorized()
    user = db.get(User, s.user_id)
    if user is None or not user.is_active:
        _unauthorized("Учётная запись отключена")
    request.state.session_hash = s.token_hash
    # Со временным паролем можно только сменить пароль и выйти
    if user.must_change_password and request.url.path not in (
            "/api/auth/me", "/api/auth/password", "/api/auth/logout"):
        _forbidden("Смените временный пароль")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        _forbidden("Действие доступно только службе охраны труда")
    return user


def require_editor(user: User = Depends(current_user)) -> User:
    if user.role not in ("admin", "responsible"):
        _forbidden("Роль «Руководитель» — только просмотр")
    return user


def office_ids(user: User) -> set[int]:
    return {o.id for o in user.offices}


def visible_office_ids(user: User) -> set[int] | None:
    """Какие офисы видит пользователь: None — все (служба ОТ, руководитель), иначе — назначенные."""
    return None if user.role in ("admin", "viewer") else office_ids(user)


def ensure_office_visible(user: User, office: Office) -> None:
    """Чужой офис для ответственного — «не найден» (не раскрываем, что он существует)."""
    ids = visible_office_ids(user)
    if ids is not None and office.id not in ids:
        raise HTTPException(status_code=404, detail={"message": f"Офис «{office.code}» не найден"})


def can_edit_office(user: User, office: Office) -> bool:
    return user.role == "admin" or (user.role == "responsible" and office.id in office_ids(user))


def ensure_office_access(user: User, office: Office) -> None:
    ensure_office_visible(user, office)  # чужой офис для ответственного — 404, а не 403
    if not can_edit_office(user, office):
        _forbidden(f"Нет прав на изменение данных офиса «{office.code}»")


def user_to_dict(user: User) -> dict:
    return {
        "id": user.id,
        "login": user.login,
        "full_name": user.full_name,
        "role": user.role,
        "role_label": ROLES.get(user.role, user.role),
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "offices": sorted(o.code for o in user.offices),
        "last_login_at": _aware(user.last_login_at).isoformat() if user.last_login_at else None,
        "created_at": _aware(user.created_at).isoformat() if user.created_at else None,
    }


# --- Первый администратор ----------------------------------------------------------------
def _write_initial_password(login: str, password: str) -> str:
    import os
    from pathlib import Path

    path = Path(config.INITIAL_PASSWORD_FILE).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"login: {login}\npassword: {password}\n")
    return str(path)


def remove_initial_password_file() -> None:
    """После смены пароля администратором временный пароль на диске больше не нужен."""
    from pathlib import Path

    try:
        Path(config.INITIAL_PASSWORD_FILE).unlink(missing_ok=True)
    except OSError:
        log.warning("Не удалось удалить файл с временным паролем %s", config.INITIAL_PASSWORD_FILE)


def bootstrap_admin(db: Session) -> None:
    """Если пользователей нет — создать администратора.

    Пароль берётся из ADMIN_PASSWORD; если не задан — генерируется и пишется в лог один раз.
    В обоих случаях при первом входе пароль нужно сменить.
    """
    if db.scalar(select(User.id).limit(1)) is not None:
        return
    login = normalize_login(config.ADMIN_LOGIN) or "admin"
    password = config.ADMIN_PASSWORD
    generated = not password
    if generated:
        password = secrets.token_urlsafe(12)
    db.add(User(login=login, full_name="Администратор", role="admin",
                password_hash=hash_password(password), must_change_password=True))
    db.commit()
    if generated:
        path = _write_initial_password(login, password)
        log.warning("Создан администратор «%s». Временный пароль записан в файл %s (права 600) — "
                    "смените пароль при первом входе, файл удалится автоматически", login, path)
    else:
        log.warning("Создан администратор «%s» (пароль из ADMIN_PASSWORD) — смените его при первом входе", login)
