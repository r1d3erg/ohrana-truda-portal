# Портал «Охрана труда» (React)

Модуль экосистемы на React + Vite.

## Запуск

```bash
npm install
npm run dev
```

Откроется на http://localhost:5173

## Сборка

```bash
npm run build
npm run preview
```

## Структура

- `src/App.jsx` — основное приложение
- `src/index.css` — стили
- `Dockerfile`, `nginx.conf`, `docker-compose.yml` — сборка и деплой
- `backend/`, `docs/` — план бэкенда и архитектура
- Роли: Супер-админ / Ответственный офиса
- Создание офисов и назначение ответственных (только супер-админ)
- Модули, FAQ, уведомления

## Docker

```bash
docker compose up -d --build
```

Портал откроется на http://localhost:8080

Сборка двухэтапная: в образе `node` выполняется `npm run build`, затем готовая
статика из `dist/` раздаётся nginx (конфиг — `nginx.conf`, со SPA-фолбэком и
кэшированием ассетов).

Для воспроизводимых сборок закоммитьте `package-lock.json` (создаётся при
`npm install`) — тогда Dockerfile автоматически переключится на `npm ci`.

Учётные данные для будущих backend/БД задаются в `.env` по образцу `.env.example`.
