"""Разбор сводной таблицы «Чек-лист обязательных документов» (.xlsx).

Модуль не зависит от веб-фреймворка и БД: на вход — байты файла,
на выход — ParsedChecklist (шапка + позиции + предупреждения)
или исключение ChecklistParseError со списком ошибок.

Подробное описание формата и алгоритма — docs/checklist-import.md.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime

from openpyxl import load_workbook

# --- Лимиты защиты от «плохих» файлов --------------------------------------
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # защита от zip-бомб
MAX_ZIP_ENTRIES = 2000
MAX_SCAN_ROWS = 5000  # чек-лист не бывает длиннее; дальше не читаем
MAX_SCAN_COLS = 30

PREFERRED_SHEET = "чек-лист документов"

# --- Статусы ---------------------------------------------------------------
STATUS_DONE = "done"
STATUS_IN_PROGRESS = "in_progress"
STATUS_MISSING = "missing"
STATUS_NOT_SET = "not_set"

STATUS_LABELS = {
    STATUS_DONE: "Есть",
    STATUS_IN_PROGRESS: "В работе",
    STATUS_MISSING: "Нет",
    STATUS_NOT_SET: "Не указан",
}

_STATUS_ALIASES = {
    "есть": STATUS_DONE,
    "в работе": STATUS_IN_PROGRESS,
    "нет": STATUS_MISSING,
}

# --- Поля шапки: подпись в таблице -> ключ ---------------------------------
_META_LABELS = {
    "номер офиса": "office_code",
    "дата проверки": "check_date",
    "проверил": "inspector",
    "номер редди": "reddy_number",
    "организация": "organization",
    "численность": "headcount",
    "статус мсп": "msp_status",
}

OFFICE_CODE_RE = re.compile(r"^[\w.\-]{1,64}$", re.UNICODE)
_GROUP_RE = re.compile(r"^\d+\.\s*\S")
_DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y")


class ChecklistParseError(Exception):
    """Файл не удалось разобрать. errors — список понятных пользователю причин."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass
class ParsedItem:
    row: int                 # номер строки в Excel (для сообщений об ошибках)
    number: int              # «№» позиции
    category: str            # «Раздел» (Охрана труда, Пожарная безопасность …)
    group: str | None        # заголовок блока («1. ОХРАНА ТРУДА И СУОТ»)
    subgroup: str | None     # подзаголовок («Организационные документы»)
    title: str               # «Документ / Наименование»
    status: str              # done / in_progress / missing / not_set
    comment: str | None
    responsible: str | None
    item_date: date | None
    item_date_raw: str | None


@dataclass
class ParsedChecklist:
    sheet_name: str
    office_code: str
    check_date: date | None = None
    inspector: str | None = None
    reddy_number: str | None = None
    organization: str | None = None
    headcount: int | None = None
    msp_status: str | None = None
    items: list[ParsedItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def _norm(value) -> str:
    """Нормализованный текст ячейки: без лишних пробелов, в нижнем регистре."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def _text(value) -> str | None:
    """Текст ячейки как есть (без крайних пробелов) или None для пустой."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = str(value).strip()
    return s or None


def _parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_int(value) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    s = str(value).strip().replace(" ", "")
    return int(s) if s.isdigit() else None


def _check_archive(data: bytes) -> None:
    """Файл должен быть xlsx (zip) разумного размера в распакованном виде."""
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise ChecklistParseError(
            ["Файл не является книгой Excel .xlsx (старый формат .xls не поддерживается — "
             "пересохраните файл как .xlsx)"]
        )
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise ChecklistParseError(["Файл содержит слишком много внутренних частей"])
        if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
            raise ChecklistParseError(["Файл слишком большой в распакованном виде"])


def _find_sheet(wb):
    for ws in wb.worksheets:
        if _norm(ws.title) == PREFERRED_SHEET:
            return ws
    return wb.worksheets[0]


def _map_header(row: tuple) -> dict[str, int] | None:
    """Если строка — заголовок таблицы, вернуть {поле: индекс колонки}."""
    cols: dict[str, int] = {}
    for idx, cell in enumerate(row):
        n = _norm(cell)
        if not n:
            continue
        if n in ("№", "no", "n", "#", "№ п/п") and "number" not in cols:
            cols["number"] = idx
        elif n == "раздел":
            cols["category"] = idx
        elif n.startswith("документ") or n.startswith("наименование"):
            cols["title"] = idx
        elif n == "статус":
            cols["status"] = idx
        elif n.startswith("комментарий") or n.startswith("примечание"):
            cols["comment"] = idx
        elif n.startswith("ответственн"):
            cols["responsible"] = idx
        elif n.startswith("дата"):
            cols["date"] = idx
    if {"number", "title", "status"} <= cols.keys():
        return cols
    return None


def _read_meta(row: tuple, meta: dict) -> None:
    """Подписи шапки вида «Номер офиса:» — значение берётся из следующей непустой ячейки."""
    for idx, cell in enumerate(row):
        label = _norm(cell).rstrip(":").strip()
        key = _META_LABELS.get(label)
        if key is None or key in meta:
            continue
        for value in row[idx + 1:]:
            if value is None or str(value).strip() == "":
                continue
            # Следующая непустая ячейка — уже другая подпись: значение не заполнено
            if isinstance(value, str) and value.strip().endswith(":"):
                break
            meta[key] = value
            break


def _cell(row: tuple, cols: dict[str, int], key: str):
    idx = cols.get(key)
    if idx is None or idx >= len(row):
        return None
    return row[idx]


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------
def parse_checklist(data: bytes) -> ParsedChecklist:
    _check_archive(data)
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # повреждённый/зашифрованный файл
        raise ChecklistParseError([f"Не удалось открыть книгу Excel: {exc.__class__.__name__}"])

    try:
        ws = _find_sheet(wb)
        rows = ws.iter_rows(max_row=MAX_SCAN_ROWS, max_col=MAX_SCAN_COLS, values_only=True)

        meta: dict = {}
        cols: dict[str, int] | None = None
        errors: list[str] = []
        warnings: list[str] = []
        items: list[ParsedItem] = []
        seen_numbers: dict[int, int] = {}
        group: str | None = None
        subgroup: str | None = None

        for row_no, row in enumerate(rows, start=1):
            if cols is None:
                cols = _map_header(row)
                if cols is None:
                    _read_meta(row, meta)
                continue

            first = _text(row[0]) if row else None
            non_empty = [v for v in row if v is not None and str(v).strip() != ""]
            if not non_empty:
                continue
            if first and _norm(first).startswith("итого"):
                break  # блок «ИТОГО ПО СТАТУСАМ» и примечания — не позиции

            raw_number = _cell(row, cols, "number")
            number = _parse_int(raw_number)

            # Заголовки блоков: текст в первой колонке, остальное пусто
            if number is None:
                if len(non_empty) == 1 and isinstance(non_empty[0], str):
                    heading = non_empty[0].strip()
                    if heading.startswith("▸"):
                        subgroup = heading.lstrip("▸").strip() or None
                    elif _GROUP_RE.match(heading):
                        group, subgroup = heading, None
                continue

            title = _text(_cell(row, cols, "title"))
            if not title:
                errors.append(f"Строка {row_no}: у позиции №{number} не заполнено наименование документа")
                continue

            if number in seen_numbers:
                errors.append(
                    f"Строка {row_no}: номер позиции №{number} повторяется (уже был в строке {seen_numbers[number]})"
                )
                continue
            seen_numbers[number] = row_no

            raw_status = _text(_cell(row, cols, "status"))
            if raw_status is None:
                status = STATUS_NOT_SET
                warnings.append(f"Строка {row_no}: у позиции №{number} не указан статус")
            else:
                status = _STATUS_ALIASES.get(_norm(raw_status))
                if status is None:
                    errors.append(
                        f"Строка {row_no}: неизвестный статус «{raw_status}» у позиции №{number} "
                        f"(допустимо: Есть / В работе / Нет)"
                    )
                    continue

            category = _text(_cell(row, cols, "category"))
            if not category:
                category = re.sub(r"^\d+\.\s*", "", group).strip().capitalize() if group else "Без раздела"

            raw_date = _cell(row, cols, "date")
            item_date = _parse_date(raw_date)
            item_date_raw = _text(raw_date) if not isinstance(raw_date, (date, datetime)) else None
            if raw_date not in (None, "") and item_date is None:
                warnings.append(f"Строка {row_no}: дату «{raw_date}» не удалось распознать, сохранена как текст")

            items.append(ParsedItem(
                row=row_no,
                number=number,
                category=category,
                group=group,
                subgroup=subgroup,
                title=title,
                status=status,
                comment=_text(_cell(row, cols, "comment")),
                responsible=_text(_cell(row, cols, "responsible")),
                item_date=item_date,
                item_date_raw=item_date_raw if item_date is None else None,
            ))
    finally:
        wb.close()

    if cols is None:
        raise ChecklistParseError([
            "Не найдена строка заголовков таблицы (ожидаются колонки «№», «Документ / Наименование», «Статус»)"
        ])

    # --- Шапка ---------------------------------------------------------------
    office_code = _text(meta.get("office_code"))
    if not office_code:
        errors.insert(0, "В шапке не заполнен «Номер офиса»")
    elif not OFFICE_CODE_RE.match(office_code):
        errors.insert(0, f"Недопустимый номер офиса «{office_code}» (буквы, цифры, точка, дефис, подчёркивание; до 64 символов)")

    if not items and not errors:
        errors.append("В таблице не найдено ни одной позиции")

    if errors:
        raise ChecklistParseError(errors)

    check_date = _parse_date(meta.get("check_date"))
    if meta.get("check_date") not in (None, "") and check_date is None:
        warnings.append(f"Дату проверки «{meta.get('check_date')}» не удалось распознать")
    if check_date is None:
        warnings.append("Дата проверки не указана — будет использована дата загрузки")

    headcount = _parse_int(meta.get("headcount"))
    if meta.get("headcount") not in (None, "") and headcount is None:
        warnings.append(f"Численность «{meta.get('headcount')}» не является числом — пропущена")

    return ParsedChecklist(
        sheet_name=ws.title,
        office_code=office_code,
        check_date=check_date,
        inspector=_text(meta.get("inspector")),
        reddy_number=_text(meta.get("reddy_number")),
        organization=_text(meta.get("organization")),
        headcount=headcount,
        msp_status=_text(meta.get("msp_status")),
        items=items,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Подсчёт сводки (повторяет лист «Сводка по разделам» из Excel)
# ---------------------------------------------------------------------------
def empty_counts() -> dict[str, int]:
    return {"total": 0, STATUS_DONE: 0, STATUS_IN_PROGRESS: 0, STATUS_MISSING: 0, STATUS_NOT_SET: 0}


def readiness(done: int, total: int) -> float:
    """% готовности = «Есть» / «Всего позиций» × 100, как в Excel."""
    return round(done * 100 / total, 1) if total else 0.0


def summarize(statuses_by_category: list[tuple[str, str]]) -> tuple[dict, list[dict]]:
    """[(раздел, статус), …] -> (итог, [сводка по разделам в порядке появления])."""
    totals = empty_counts()
    by_cat: dict[str, dict[str, int]] = {}
    for category, status in statuses_by_category:
        c = by_cat.setdefault(category, empty_counts())
        for bucket in (c, totals):
            bucket["total"] += 1
            bucket[status] += 1
    totals_out = {**totals, "readiness": readiness(totals[STATUS_DONE], totals["total"])}
    cats_out = [
        {"category": name, **c, "readiness": readiness(c[STATUS_DONE], c["total"])}
        for name, c in by_cat.items()
    ]
    return totals_out, cats_out
