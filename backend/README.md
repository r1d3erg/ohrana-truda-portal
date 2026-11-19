# Backend модуля «Охрана труда»

FastAPI + SQLAlchemy 2 + PostgreSQL (SQLite для разработки и тестов).

Подробное описание формата таблицы, алгоритма загрузки, API и связи с
порталом: [../docs/checklist-import.md](../docs/checklist-import.md).

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
  config.py    — настройки из переменных окружения
  db.py        — подключение к БД
  models.py    — таблицы offices, checklist_imports, checklist_items
  parser.py    — разбор .xlsx (не зависит от веба и БД)
  services.py  — загрузка, расчёты, данные для портала
  main.py      — HTTP API
tests/
  factory.py   — генератор синтетической таблицы того же формата
  test_parser.py, test_api.py
```

## Запуск

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
pytest
```

## Планируется

- Интеграция с Active Directory (аутентификация и проверка ролей на сервере)
- Миграции БД (Alembic)
- Обучение, уведомления о сроках (Redis-очереди)
