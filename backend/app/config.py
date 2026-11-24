"""Настройки бэкенда из переменных окружения."""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# SQLite по умолчанию — для локальной разработки и тестов.
# В Docker задаётся PostgreSQL: postgresql+psycopg://user:pass@db:5432/ohrana
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/portal.db")

# Максимальный размер загружаемого файла, МБ
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 10)

# Пороги % готовности для оценки офиса
READINESS_GOOD = _int("READINESS_GOOD", 90)   # от этого значения — «Хорошо»
READINESS_WARN = _int("READINESS_WARN", 70)   # от этого значения — «Требует внимания», ниже — «Критично»

# Разрешённые источники для CORS (через запятую). Пусто — CORS выключен
# (фронтенд ходит в API через тот же домен: прокси Vite или nginx).
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

# СОУТ / ОПР
SOUT_VALIDITY_YEARS = _int("SOUT_VALIDITY_YEARS", 5)          # ч. 4 ст. 8 426-ФЗ
SOUT_WARN_DAYS = _int("SOUT_WARN_DAYS", 180)                 # за сколько дней предупреждать об окончании
OPR_REVIEW_MONTHS = _int("OPR_REVIEW_MONTHS", 12)            # пересмотр ОПР по умолчанию (задаёт работодатель)
OPR_WARN_DAYS = _int("OPR_WARN_DAYS", 60)

# Пожарная безопасность, электробезопасность, ГО и ЧС: за сколько дней предупреждать о сроке
DIRECTIONS_WARN_DAYS = _int("DIRECTIONS_WARN_DAYS", 30)

# --- Авторизация (auth.py, docs/auth.md) ---
# Первый администратор создаётся, если пользователей нет. Без ADMIN_PASSWORD пароль генерируется
# и пишется в лог бэкенда. При первом входе пароль нужно сменить.
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SESSION_HOURS = _int("SESSION_HOURS", 12)            # максимальная длительность сессии
SESSION_IDLE_MIN = _int("SESSION_IDLE_MIN", 120)     # выход после бездействия
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() in ("1", "true", "yes")  # true за HTTPS
TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() in ("1", "true", "yes")      # true за nginx
LOGIN_MAX_FAILS = _int("LOGIN_MAX_FAILS", 5)        # неудачных попыток до блокировки
LOGIN_WINDOW_MIN = _int("LOGIN_WINDOW_MIN", 15)     # окно и длительность блокировки, мин
API_DOCS = os.getenv("API_DOCS", "true").lower() in ("1", "true", "yes")  # Swagger на /api/docs
