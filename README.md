# Портал «Охрана труда»

Модуль экосистемы: портал (React + Vite) и бэкенд (FastAPI + PostgreSQL).
Индекс соответствия офисов считается по сводной таблице «Чек-лист обязательных
документов» (Excel), которая загружается через портал.

📄 **Как устроена загрузка таблицы и связь данных с порталом:**
[docs/checklist-import.md](docs/checklist-import.md)

📄 **СОУТ и ОПР — ручной ввод, сроки и предупреждения:** [docs/sout-opr.md](docs/sout-opr.md)

🛠 **Для разработчиков — как устроен проект и как подключить свой отчёт:**
[docs/developer-guide.md](docs/developer-guide.md)

Требования: Docker (для запуска стека) или Python 3.10+ и Node.js 20+ (для
локальной разработки; в Docker и CI — Python 3.12 и Node.js 22).

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

**macOS, одной кнопкой:** двойной клик по `start-dev.command` в Finder (или
`./start-dev.command` в терминале). Скрипт найдёт Python 3.10+, поставит
зависимости, поднимет бэкенд (:8000) и фронтенд (:5173) и откроет портал в
браузере. Остановка — Ctrl+C или закрыть окно Терминала.

Вручную:

```bash
# бэкенд — http://localhost:8000 (SQLite в backend/data/)
cd backend
python3 -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000

# фронтенд — http://localhost:5173 (из корня; /api проксируется на :8000)
npm install
npm run dev
```

Тесты бэкенда: `cd backend && pytest`.

## Структура

- `src/App.jsx` — каркас портала, навигация, роли
- `src/pages/` — страницы «Дашборд», «Офисы», «Документы» (загрузка таблицы, чек-лист офиса, история), «СОУТ», «ОПР»
- `src/api.js` — клиент API; `src/components.jsx` — общие компоненты;
  `src/registerParts.jsx` — формы и списки предупреждений для СОУТ/ОПР
- `backend/app/parser.py` — разбор сводной таблицы
- `backend/app/services.py` — загрузка, расчёт показателей, данные для портала
- `backend/app/registers.py` — СОУТ и ОПР: справочники, сроки, статусы, предупреждения
- `backend/app/main.py` — HTTP API; `backend/app/models.py` — модель данных
- `backend/tests/` — тесты (таблица для тестов генерируется синтетически)
- `docs/` — архитектура, загрузка чек-листа, СОУТ/ОПР, руководство разработчика
- `Dockerfile`, `nginx.conf`, `backend/Dockerfile`, `docker-compose.yml` — сборка и деплой
- `start-dev.command` — локальный запуск на macOS одной кнопкой
- `.github/workflows/ci.yml` — сборка фронтенда, тесты бэкенда, сборка образов, сквозная проверка стека

## Важно

Аутентификации пока нет: вход и роли — заглушка в интерфейсе. До интеграции
с Active Directory портал можно использовать только во внутренней сети.
