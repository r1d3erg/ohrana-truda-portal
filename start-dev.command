#!/bin/bash
# Локальный запуск портала «Охрана труда»: бэкенд (FastAPI, :8000) + фронтенд (Vite, :5173).
# Запуск: двойной клик в Finder или ./start-dev.command в терминале. Остановка: Ctrl+C.
cd "$(dirname "$0")" || exit 1
ROOT="$(pwd)"

# --- Python 3.10+ ---
PY=""
for c in python3.13 python3.12 python3.11 python3.10 \
         /opt/homebrew/bin/python3 /usr/local/bin/python3 "$HOME/.conda/bin/python3" \
         "$HOME/miniconda3/bin/python3" "$HOME/anaconda3/bin/python3" python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$(command -v "$c")"; break
  fi
done
if [ -z "$PY" ]; then
  echo "❌ Нужен Python 3.10 или новее (сейчас: $(python3 --version 2>&1)). Установите: brew install python@3.12"
  read -r -p "Нажмите Enter для выхода"; exit 1
fi
echo "✅ Python: $PY ($("$PY" --version))"

# --- Бэкенд ---
cd "$ROOT/backend" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "📦 Создаю виртуальное окружение бэкенда..."
  "$PY" -m venv .venv || { read -r -p "Ошибка venv. Enter для выхода"; exit 1; }
fi
echo "📦 Устанавливаю зависимости бэкенда..."
.venv/bin/pip install -q --upgrade pip >/dev/null 2>&1
.venv/bin/pip install -q -r requirements.txt || { read -r -p "Ошибка pip install. Enter для выхода"; exit 1; }

echo "🚀 Запускаю бэкенд на http://localhost:8000 ..."
.venv/bin/uvicorn app.main:app --reload --port 8000 &
BACK_PID=$!
trap 'echo; echo "Останавливаю бэкенд..."; kill $BACK_PID 2>/dev/null' EXIT INT TERM

# --- Фронтенд ---
cd "$ROOT" || exit 1
if ! command -v npm >/dev/null 2>&1; then
  echo "❌ Не найден npm. Установите Node.js: brew install node"
  read -r -p "Нажмите Enter для выхода"; exit 1
fi
echo "📦 npm install..."
npm install --no-audit --no-fund || { read -r -p "Ошибка npm install. Enter для выхода"; exit 1; }

(sleep 4; open "http://localhost:5173") &
echo "🚀 Запускаю фронтенд на http://localhost:5173 (остановка: Ctrl+C)"
npm run dev
