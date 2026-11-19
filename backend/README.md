# Backend модуля «Охрана труда»

FastAPI + SQLAlchemy 2 + PostgreSQL (SQLite для разработки и тестов).

Подробное описание формата таблицы, алгоритма загрузки, API и связи с
порталом: [../docs/checklist-import.md](../docs/checklist-import.md).
Как добавить свой отчёт: [../docs/developer-guide.md](../docs/developer-guide.md).

## Реализовано

- Загрузка сводной таблицы (чек-листа) офиса из Excel: `POST /api/imports`
  (с режимом предпросмотра `dry_run`)
- Офисы, индекс соответствия, уровни «Хорошо / Требует внимания / Критично»
- Чек-лист офиса с фильтрами, история загрузок, сравнение с прошлой проверкой
- Дашборд по всем офисам
- СОУТ и ОПР: ручной ввод, сроки, статусы и предупреждения ([../docs/sout-opr.md](../docs/sout-opr.md))
- Swagger UI: `/api/docs`

## Структура

```
app/
  config.py     — настройки из переменных окружения
  db.py         — подключение к БД, сессии, create_all
  models.py     — таблицы offices, checklist_imports, checklist_items,
                  sout_assessments, risk_assessments
  parser.py     — разбор .xlsx чек-листа (не зависит от веба и БД)
  services.py   — загрузка чек-листа, расчёты, дашборд
  registers.py  — СОУТ и ОПР: справочники, проверки, сроки, предупреждения
  main.py       — HTTP API (все маршруты под /api)
tests/
  conftest.py   — временная SQLite, фикстура client
  factory.py    — генератор синтетической таблицы того же формата
  test_parser.py, test_api.py, test_registers.py
```

## Запуск

```bash
python3 -m venv .venv && . .venv/bin/activate   # нужен Python 3.10+
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
pytest
```

## Планируется

- Интеграция с Active Directory (аутентификация и проверка ролей на сервере)
- Миграции БД (Alembic)
- Обучение, уведомления о сроках (Redis-очереди)
