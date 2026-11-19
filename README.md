# Портал «Охрана труда»

Модуль экосистемы: портал (React + Vite) и бэкенд (FastAPI + PostgreSQL).
Индекс соответствия офисов считается по сводной таблице «Чек-лист обязательных
документов» (Excel), которая загружается через портал.

📄 **Как устроена загрузка таблицы и связь данных с порталом:**
[docs/checklist-import.md](docs/checklist-import.md)

## Запуск в Docker

```bash
cp .env.example .env      # задайте пароль БД
docker compose up -d --build
```

- Портал: http://localhost:8080
- API: http://localhost:8080/api/…, Swagger: http://localhost:8080/api/docs

Сервисы: `portal` (nginx: статика и прокси `/api` → `backend`), `backend`
(FastAPI), `db` (PostgreSQL 16, данные в томе `pgdata`). Бэкенд и БД наружу не
публикуются.

## Локальная разработка

```bash
# бэкенд — http://localhost:8000 (SQLite в backend/data/)
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# фронтенд — http://localhost:5173 (из корня; /api проксируется на :8000)
npm install
npm run dev
```

Тесты бэкенда: `cd backend && pytest`.

## Структура

- `src/App.jsx` — каркас портала, навигация, роли
- `src/pages/` — страницы «Дашборд», «Офисы», «Документы» (загрузка таблицы, чек-лист офиса, история)
- `src/api.js` — клиент API; `src/components.jsx` — общие компоненты
- `backend/app/parser.py` — разбор сводной таблицы
- `backend/app/services.py` — загрузка, расчёт показателей, данные для портала
- `backend/app/main.py` — HTTP API; `backend/app/models.py` — модель данных
- `backend/tests/` — тесты (таблица для тестов генерируется синтетически)
- `docs/` — архитектура и подробное описание загрузки
- `Dockerfile`, `nginx.conf`, `backend/Dockerfile`, `docker-compose.yml` — сборка и деплой
- `.github/workflows/ci.yml` — сборка фронтенда, тесты бэкенда, сборка образов, сквозная проверка стека

## Важно

Аутентификации пока нет: вход и роли — заглушка в интерфейсе. До интеграции
с Active Directory портал можно использовать только во внутренней сети.
