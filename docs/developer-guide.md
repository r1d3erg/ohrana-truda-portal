# Руководство разработчика

Руководство для программистов, которые подключают к порталу свои отчёты:
новые типы Excel-файлов, выгрузки из других систем, новые разделы. Здесь
описано, как устроен проект, каких соглашений держаться и как по шагам
добавить новый отчёт, чтобы он появился на страницах портала и на дашборде.

Связанные документы:

- [checklist-import.md](checklist-import.md) — эталонный пример импорта
  Excel: формат, разбор, проверки, модель, API, связь с порталом;
- [sout-opr.md](sout-opr.md) — эталонный пример ручного ввода с расчётом
  сроков и предупреждениями;
- [architecture.md](architecture.md) — состав модулей и их состояние.

Содержание:

1. [Стек и требования](#1-стек-и-требования)
2. [Структура репозитория](#2-структура-репозитория)
3. [Запуск, тесты, CI](#3-запуск-тесты-ci)
4. [Как устроен бэкенд](#4-как-устроен-бэкенд)
5. [Как устроен фронтенд](#5-как-устроен-фронтенд)
6. [Соглашения (контракт для новых отчётов)](#6-соглашения-контракт-для-новых-отчётов)
7. [Три способа подключить отчёт](#7-три-способа-подключить-отчёт)
8. [Пошагово: новый импорт Excel](#8-пошагово-новый-импорт-excel)
9. [Интеграция через API без интерфейса](#9-интеграция-через-api-без-интерфейса)
10. [Изменение схемы БД](#10-изменение-схемы-бд)
11. [Чек-лист готовности](#11-чек-лист-готовности)
12. [Известные ограничения и технический долг](#12-известные-ограничения-и-технический-долг)

---

## 1. Стек и требования

| Часть | Технологии | Версии |
|---|---|---|
| Фронтенд | React 18, Vite 5, без UI-библиотек и роутера; стили — `src/index.css` | Node.js 20+ (в Docker и CI — 22) |
| Бэкенд | FastAPI, SQLAlchemy 2 (typed `Mapped`), Pydantic 2, openpyxl + defusedxml | Python **3.10+** (синтаксис `X \| None`); в Docker и CI — 3.12 |
| БД | PostgreSQL 16 в Docker (драйвер psycopg 3); SQLite — для разработки и тестов | |
| Деплой | Docker Compose: `portal` (nginx: статика + прокси `/api`), `backend`, `db` | |
| CI | GitHub Actions: сборка фронтенда, pytest, сборка образов, сквозная проверка стека | |

Зависимости бэкенда — `backend/requirements.txt` (диапазоны версий, без lock-файла);
фронтенда — `package.json` + `package-lock.json` (сборки через `npm ci`).

---

## 2. Структура репозитория

```
├── src/                      фронтенд
│   ├── App.jsx               каркас: меню, роли, переключение страниц, общие данные
│   ├── api.js                клиент API, форматтеры дат/процентов, подписи статусов
│   ├── components.jsx        общие компоненты (бейджи, ошибки, сводка по разделам)
│   ├── registerParts.jsx     модальная форма, поля, список предупреждений
│   ├── index.css             все стили
│   └── pages/                Dashboard, Offices, Documents, Sout, Opr
├── backend/
│   ├── app/
│   │   ├── config.py         настройки из переменных окружения
│   │   ├── db.py             движок, сессии, create_all
│   │   ├── models.py         таблицы SQLAlchemy
│   │   ├── parser.py         разбор Excel чек-листа (чистая функция)
│   │   ├── services.py       импорт чек-листа, расчёты, дашборд
│   │   ├── registers.py      СОУТ/ОПР: справочники, проверки, сроки, предупреждения
│   │   └── main.py           HTTP API (FastAPI), всё под /api
│   ├── tests/                pytest: conftest, factory (синтетический Excel), тесты
│   ├── Dockerfile
│   └── requirements*.txt
├── docs/                     документация
├── Dockerfile, nginx.conf    образ портала
├── docker-compose.yml, .env.example
├── start-dev.command         локальный запуск на macOS одной кнопкой
└── .github/workflows/ci.yml
```

---

## 3. Запуск, тесты, CI

```bash
# весь стек
cp .env.example .env && docker compose up -d --build     # http://localhost:8080

# разработка
cd backend && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000                 # Swagger: http://localhost:8000/api/docs
npm install && npm run dev                                # из корня: http://localhost:5173

# тесты
cd backend && pytest -v
npm run build                                             # проверка сборки фронтенда
```

CI (`.github/workflows/ci.yml`) запускается на каждый push в `main` и на pull
request:

| Job | Что делает |
|---|---|
| `frontend` | `npm ci && npm run build` |
| `backend` | `pip install -r requirements-dev.txt && pytest -v` |
| `docker` | `docker compose config`, сборка образов портала и бэкенда |
| `e2e` | поднимает весь стек через compose, загружает синтетическую таблицу через nginx, проверяет ответы API и отдачу страницы |

Новый отчёт считается подключённым, только когда все четыре job зелёные.

---

## 4. Как устроен бэкенд

Слои и их ответственность (держитесь этого разделения в новом коде):

| Слой | Файл | Что делает | Чего не делает |
|---|---|---|---|
| Разбор | `parser.py` | байты файла → dataclass с данными + список предупреждений; при ошибках — исключение со **всеми** ошибками | не знает про БД и HTTP |
| Бизнес-логика | `services.py`, `registers.py` | поиск/создание офиса, дубликаты, сохранение, расчёт показателей, статусов, сроков и предупреждений, сериализация в dict | не знает про HTTP (кроме доменных исключений) |
| HTTP | `main.py` | маршруты, Pydantic-модели входа, лимиты, перевод исключений в коды ответа | не считает показатели |
| Модель | `models.py` | таблицы и связи | |

Ключевые решения, на которые опирается весь портал:

- **Офис — общий ключ.** Таблица `offices`, поле `code` (`cy1`, `msk-1`):
  буквы, цифры, `.`, `-`, `_`, до 64 символов (`parser.OFFICE_CODE_RE`).
  Любой отчёт привязывается к офису по коду. Если офиса нет, импорт создаёт
  его (`Office(code=…, name=code)`). Так сделано в чек-листе: делайте так же,
  либо явно возвращайте 404/422.
- **Снимки, а не перезапись.** Каждая загрузка — отдельная запись с историей;
  «актуальная» выбирается по дате отчёта (у чек-листа — по `check_date`, затем по
  `id`). Итоги денормализуются в запись загрузки, чтобы список офисов и дашборд
  не пересчитывали строки.
- **Дубликаты** определяются по SHA-256 файла в пределах офиса
  (`UNIQUE(office_id, file_sha256)`).
- **Предпросмотр** (`dry_run=true`) — тот же код до записи в БД, без commit.
- **Транзакции:** одна загрузка — одна транзакция (`db.flush()` при
  необходимости id, затем `db.commit()`); при ошибке разбора — `db.rollback()`.
- **Уровни** везде одни и те же: `good` / `warn` / `bad` / `new` (нет данных).
  Для процентов — `services.level_for(value)` с порогами `READINESS_GOOD` /
  `READINESS_WARN`.
- **Схема БД** создаётся `Base.metadata.create_all()` при старте
  (`db.init_db()` в lifespan). Новые таблицы появятся сами; изменение
  существующих — см. раздел 10.

---

## 5. Как устроен фронтенд

- **Без роутера:** текущая страница — состояние `page` в `App.jsx`; меню
  строится из объекта `PAGES`; реализованные страницы перечислены в
  `IMPLEMENTED`, остальные показывают заглушку.
- **Общие данные** (`offices`, `dashboard`, `cfg` из `/api/config`)
  загружаются в `App.jsx`; функция `reload()` перезапрашивает их после любых
  изменений. Страница получает `onChanged={reload}` и вызывает его после
  сохранения.
- **API-клиент** — `src/api.js`: `request()` ходит на относительный `/api/…`
  (в разработке проксирует Vite, в Docker — nginx), разбирает ошибки в
  `ApiError(status, message, errors[])`. Компонент `ErrorBox` показывает
  `message` и список `errors` — поэтому бэкенд обязан отдавать ошибки в формате
  из раздела 6.
- **Переходы между страницами** — через колбэки из `App.jsx`: `drill()`
  (в «Документы» с фильтром), `openRegister(kind, code)` (в СОУТ/ОПР с
  открытой карточкой офиса).
- **Цвета состояний** — CSS-классы `lvl-good|warn|bad|new` (текст),
  `lvl-bg-*` (заливка), `lvl-tint-*` (ячейки), бейджи `LevelBadge`.
  Цвет никогда не единственный носитель смысла: рядом число, иконка ✓ ! ✕ или
  подпись.
- **Формы** — компоненты из `registerParts.jsx` (`Modal`, `Fieldset`,
  `TextField`, `NumberField`, `DateField`, `SelectField`, `CheckField`,
  `toBody`, `toForm`); пример — `src/pages/Sout.jsx`.

---

## 6. Соглашения (контракт для новых отчётов)

**Маршруты.** Всё под `/api`. Ресурсы офиса — `/api/offices/{code}/<отчёт>`;
сводка по всем офисам — `GET /api/<отчёт>`; запись — `/api/<отчёт>/{id}`;
загрузка файла — `POST /api/<отчёт>/imports` (`multipart/form-data`, поле
`file`, query `dry_run`).

**Формат ошибок** — единый для всего API:

```json
{"detail": {"message": "Короткое описание для пользователя", "errors": ["Строка 12: …", "…"]}}
```

| Код | Когда |
|---|---|
| 404 | не найден офис / запись (`detail.message`) |
| 409 | конфликт (офис уже существует) |
| 413 | файл больше лимита |
| 415 | неподдерживаемое расширение |
| 422 | ошибки разбора файла или проверки формы — **все сразу**, с номерами строк Excel |

**Даты** — ISO 8601: `"2026-08-17"` для дат, `"2026-11-19T08:40:00+00:00"` для
времени (UTC). **Проценты** — число с одним знаком (`55.6`). **Статусы и коды** —
латиницей (`done`, `in_progress`), подписи на русском отдаются рядом
(`status_label`) или через `/api/config`.

**Офис в ответах** — сериализуйте через `services.office_to_dict()` и
добавляйте свои поля рядом.

**Предупреждения**, которые должны попасть на дашборд в «Сроки и
нарушения», — словари одного формата:

```python
{"severity": "bad" | "warn", "text": "Что не так", "due": "2026-12-01" | None,
 "kind": "<отчёт>", "office_code": "cy1"}
```

Сейчас список собирает `registers.dashboard_block()`, клик по пункту на
дашборде вызывает `openRegister(alert.kind, alert.office_code)`. Для своего
`kind` добавьте обработку в `App.jsx` (на какую страницу переходить).

**Безопасность ввода:** для файлов — проверка расширения, лимит размера,
`zipfile`-проверка распакованного размера, `openpyxl.load_workbook(...,
read_only=True, data_only=True)`, лимиты строк/колонок (см.
`parser._check_archive`, `MAX_SCAN_ROWS`); для JSON — Pydantic с `ge=0`,
`max_length` (см. `SoutIn` в `main.py`).

**Персональные данные:** реальные файлы офисов в репозиторий и тесты не
кладутся — только синтетика (`tests/factory.py`).

**Коммиты** — осмысленные сообщения на английском в повелительном наклонении
(«Add …», «Fix …»), как в истории репозитория.

---

## 7. Три способа подключить отчёт

| Способ | Когда подходит | Образец |
|---|---|---|
| **A. Импорт файла** (Excel) | отчёт приходит файлом по шаблону | чек-лист: `parser.py` → `services.import_checklist()` → `POST /api/imports` |
| **B. Ручной ввод** | данных немного, вводит человек | СОУТ/ОПР: `registers.py` + `_register_routes()` в `main.py` + `Sout.jsx` |
| **C. Интеграция через API** | данные есть в другой системе | скрипт или сервис вызывает JSON-эндпоинты портала (раздел 9) |

Часто разумно сочетать: например, импорт файла (A) пишет в те же таблицы, что
и ручной ввод (B), а интеграция (C) использует те же POST-эндпоинты.

---

## 8. Пошагово: новый импорт Excel

Пример — условный отчёт «Журнал инструктажей» (`briefings`). Имена файлов и
полей — образец; содержимое разбора зависит от вашего шаблона.

### Шаг 1. Описать формат

Сначала сделайте документ `docs/briefings-import.md` по образцу
[checklist-import.md](checklist-import.md): листы; шапка (подпись → поле →
обязательность → обработка); заголовок таблицы (колонки по названию); типы
строк; допустимые значения; ошибки и предупреждения; формулы показателей.
Это и техзадание, и будущая документация.

### Шаг 2. Парсер — `backend/app/briefings_parser.py`

Чистая функция без БД и HTTP. Переиспользуйте помощники из `parser.py`
(`_check_archive`, `_norm`, `_text`, `_parse_date`, `_parse_int`,
`_read_meta`) или вынесите их в общий модуль.

```python
from dataclasses import dataclass, field
from datetime import date
import io
from openpyxl import load_workbook
from .parser import (ChecklistParseError as ParseError, OFFICE_CODE_RE,
                     _check_archive, _norm, _text, _parse_date)

@dataclass
class BriefingRow:
    row: int
    employee_position: str
    kind: str
    held_on: date | None

@dataclass
class ParsedBriefings:
    office_code: str
    period_end: date | None
    rows: list[BriefingRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

def parse_briefings(data: bytes) -> ParsedBriefings:
    _check_archive(data)                         # zip, лимиты, понятная ошибка для .xls
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    errors, warnings, rows = [], [], []
    try:
        ws = wb.worksheets[0]
        for row_no, values in enumerate(ws.iter_rows(max_row=5000, max_col=30, values_only=True), 1):
            ...                                  # шапка → таблица → строки; ошибки копить в errors
    finally:
        wb.close()
    if errors:
        raise ParseError(errors)                 # все ошибки сразу, с «Строка N: …»
    return ParsedBriefings(office_code=..., period_end=..., rows=rows, warnings=warnings)
```

### Шаг 3. Модель — `backend/app/models.py`

Таблица загрузки (снимок) + таблица строк; связь с офисом; итоги в загрузке.

```python
class BriefingImport(Base):
    __tablename__ = "briefing_imports"
    __table_args__ = (UniqueConstraint("office_id", "file_sha256", name="uq_briefing_office_file"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    filename: Mapped[str | None] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    period_end: Mapped[date | None] = mapped_column(Date)
    total: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[str | None] = mapped_column(Text)      # JSON-массив
    office: Mapped[Office] = relationship()
    rows: Mapped[list["BriefingRowModel"]] = relationship(cascade="all, delete-orphan", passive_deletes=True)

class BriefingRowModel(Base):
    __tablename__ = "briefing_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("briefing_imports.id", ondelete="CASCADE"), index=True)
    ...
```

Новые таблицы создадутся при следующем старте бэкенда автоматически.

### Шаг 4. Сервис — `backend/app/briefings.py`

Повторите последовательность из `services.import_checklist()`:

1. `parsed = parse_briefings(data)` (ошибки → наружу);
2. `sha = hashlib.sha256(data).hexdigest()`;
3. найти офис по `parsed.office_code` (или создать);
4. дубликат по `(office_id, sha)` → `{"result": "duplicate", …}`;
5. посчитать итоги и предупреждения;
6. `dry_run` → вернуть `{"result": "preview", …}` без записи;
7. создать загрузку и строки, `db.commit()`;
8. вернуть `{"result": "created", "office": office_to_dict(...), "summary": …, "warnings": […]}`.

Плюс функции для страниц: состояние по офисам (`summary(db)`), карточка
офиса, и, если нужно, `alerts(db)` в формате из раздела 6.

### Шаг 5. Маршруты — `backend/app/main.py`

```python
@api.post("/briefings/imports", tags=["briefings"])
async def upload_briefings(file: UploadFile = File(...), dry_run: bool = Query(False),
                           db: Session = Depends(get_db)):
    # повторите проверки upload_checklist(): расширение, лимит MAX_UPLOAD_MB, пустой файл
    try:
        return briefings.import_file(db, data, file.filename, dry_run=dry_run)
    except ChecklistParseError as exc:
        db.rollback()
        raise HTTPException(422, detail={"message": "Файл не прошёл проверку", "errors": exc.errors})

@api.get("/briefings", tags=["briefings"])
def briefings_summary(db: Session = Depends(get_db)):
    return briefings.summary(db)

@api.get("/offices/{code}/briefings", tags=["briefings"])
def office_briefings(code: str, db: Session = Depends(get_db)): ...
```

Если отчёт должен влиять на дашборд — добавьте блок в ответ
`get_dashboard()` (сейчас: `{**services.dashboard(db), "registers": …}`),
например `"briefings": briefings.dashboard_block(db)`, а его предупреждения —
в общий список (или соберите общий список в одном месте).

### Шаг 6. Тесты — `backend/tests/`

- `factory.py` (или свой `briefings_factory.py`): функция, которая собирает
  синтетический `.xlsx` вашего формата через `openpyxl.Workbook()`;
- `test_briefings_parser.py`: корректный файл, каждая ошибка из таблицы
  ошибок, предупреждения, крайние случаи (пустые ячейки, даты текстом, числа как
  float);
- `test_briefings_api.py`: загрузка создаёт офис и данные; дубликат; `dry_run`
  ничего не пишет; 415/413/422; данные видны в `GET`-эндпоинтах и на дашборде.

Фикстура `client` из `conftest.py` даёт чистую SQLite на каждый тест.

### Шаг 7. Фронтенд

1. `src/api.js` — методы: `uploadBriefings(file, {dryRun})` (по образцу
   `uploadChecklist`), `briefings()`, `officeBriefings(code)`.
2. `src/pages/Briefings.jsx` — страница: загрузка с кнопками «Проверить» /
   «Загрузить» (образец — `UploadSection` в `Documents.jsx`), сводная таблица
   по офисам, карточка офиса.
3. `src/App.jsx` — пункт в `PAGES`, ключ в `IMPLEMENTED`, рендер страницы с
   `onChanged={reload}`.
4. `src/pages/Dashboard.jsx` — блок или колонка в тепловой карте (образец —
   `RegCell` и `RegistersBlock`).

### Шаг 8. Документация и сквозная проверка

- дописать `docs/briefings-import.md` (шаг 1) фактическими сообщениями ошибок
  и примерами ответов;
- добавить ссылку в `README.md` и строку в таблицу модулей
  `docs/architecture.md`;
- при желании — шаг в job `e2e` CI: загрузка синтетического файла через
  `http://localhost:8080/api/briefings/imports` и проверка ответа.

---

## 9. Интеграция через API без интерфейса

Все операции портала доступны как HTTP API — внешняя система может
отправлять данные напрямую. Полный список и схемы — Swagger `/api/docs`.

```bash
# создать офис (если ещё нет)
curl -X POST http://portal/api/offices -H 'Content-Type: application/json' \
     -d '{"code": "msk-1", "name": "Москва, офис 1"}'

# загрузить файл чек-листа
curl -F "file=@cy1.xlsx" http://portal/api/imports

# записать СОУТ из своей системы
curl -X POST http://portal/api/offices/msk-1/sout -H 'Content-Type: application/json' \
     -d '{"report_date": "2026-03-01", "fgis_date": "2026-03-10", "workplaces_total": 12,
          "workplaces_assessed": 12, "class_2": 12, "familiarized_date": "2026-03-15"}'
```

Пока аутентификации нет (раздел 12), такие интеграции допустимы только
внутри доверенной сети. После подключения AD понадобится сервисная учётная
запись или токен.

---

## 10. Изменение схемы БД

`create_all()` **создаёт** отсутствующие таблицы, но **не изменяет**
существующие (новые колонки, типы, индексы не появятся). Поэтому:

- новые таблицы — можно сразу;
- новые колонки в существующих таблицах — нужна миграция. Рекомендуется
  подключить Alembic: `alembic init`, базовая ревизия по текущим моделям,
  затем `alembic revision --autogenerate` на каждое изменение и
  `alembic upgrade head` при деплое (в entrypoint контейнера бэкенда);
- до внедрения Alembic в разработке можно пересоздать SQLite
  (`backend/data/portal.db`), но **не** продуктивную БД PostgreSQL.

---

## 11. Чек-лист готовности

- [ ] формат отчёта описан в `docs/<отчёт>.md` (поля, правила, ошибки, примеры);
- [ ] парсер — чистая функция, все ошибки сразу, номера строк Excel;
- [ ] лимиты и безопасный разбор файла (как в `parser.py`);
- [ ] данные привязаны к офису по `code`; история (снимки), дубликаты, `dry_run`;
- [ ] ошибки API в формате `{"detail": {"message", "errors"}}`;
- [ ] даты ISO, уровни `good/warn/bad/new`, предупреждения в общем формате;
- [ ] тесты парсера и API на синтетических файлах, без реальных данных;
- [ ] страница и пункт меню; при необходимости — блок на дашборде;
- [ ] все job CI зелёные;
- [ ] ссылки в README и `architecture.md`.

---

## 12. Известные ограничения и технический долг

| Что | Последствие | Что делать |
|---|---|---|
| Нет аутентификации и авторизации; роли переключаются в браузере | API доступно всем, кто видит сервер | Интеграция с AD (LDAP/Kerberos или OIDC через ADFS), проверка ролей на сервере, сервисные токены для интеграций; до этого — только внутренняя сеть |
| Нет миграций БД | изменения существующих таблиц не применяются | Alembic (раздел 10) |
| Фильтры чек-листа и сводки считаются в Python по всем строкам | при тысячах офисов дашборд замедлится | перенести агрегации в SQL (`GROUP BY`), кэш |
| Нет роутера и URL у страниц | нельзя дать ссылку на страницу/офис | React Router (или hash-роутинг) |
| Нет тестов фронтенда | регрессии интерфейса ловятся вручную | Vitest + Testing Library, Playwright для сценариев |
| Бэкенд-зависимости без lock-файла | возможны отличия версий между сборками | `pip-tools` / `uv lock` |
| Справочники СОУТ/ОПР в коде | правка законодательных сроков требует деплоя | при необходимости — таблица справочников с админкой |
