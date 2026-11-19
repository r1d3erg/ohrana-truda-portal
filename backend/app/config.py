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
