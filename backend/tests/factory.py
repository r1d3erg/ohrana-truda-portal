"""Генератор синтетической сводной таблицы той же структуры, что и рабочий шаблон.

Реальные файлы офисов в репозиторий не кладём — в них персональные данные.
"""
import io

from openpyxl import Workbook

DEFAULT_ITEMS = [
    # (заголовок блока, подзаголовок, раздел, наименование, статус)
    ("1. ОХРАНА ТРУДА И СУОТ", "Организационные документы", "Охрана труда", "Положение о СУОТ", "Есть"),
    ("1. ОХРАНА ТРУДА И СУОТ", "Организационные документы", "Охрана труда", "Политика в области охраны труда", "В работе"),
    ("1. ОХРАНА ТРУДА И СУОТ", "Инструкции и инструктажи", "Охрана труда", "Журнал вводного инструктажа", "Нет"),
    ("2. ПЕРВАЯ ПОМОЩЬ", None, "Первая помощь", "Журнал учёта аптечек", "Есть"),
    ("3. ПОЖАРНАЯ БЕЗОПАСНОСТЬ", None, "Пожарная безопасность", "Приказ о противопожарном режиме", "Есть"),
    ("3. ПОЖАРНАЯ БЕЗОПАСНОСТЬ", None, "Пожарная безопасность", "Планы эвакуации", "В работе"),
]


def build_checklist(
    office="t1",
    check_date="17.08.2026",
    items=None,
    inspector="Тестов Т.Т.",
    headcount=120,
    extra_rows=None,
) -> bytes:
    items = DEFAULT_ITEMS if items is None else items
    wb = Workbook()
    ws = wb.active
    ws.title = "Чек-лист документов"
    ws["A1"] = "ЧЕК-ЛИСТ ОБЯЗАТЕЛЬНЫХ ДОКУМЕНТОВ"
    ws["A4"], ws["B4"], ws["D4"], ws["E4"], ws["F4"], ws["G4"] = (
        "Номер офиса:", office, "Дата проверки:", check_date, "Проверил:", inspector)
    ws["A5"], ws["B5"], ws["D5"], ws["E5"], ws["F5"], ws["G5"] = (
        "номер редди:", 12345678901, "Численность:", headcount, "Статус МСП:", 63)
    ws["A7"], ws["B7"], ws["C7"], ws["D7"] = "Статусы:", "Есть", "В работе", "Нет"
    ws.append([])
    ws.append([])  # строки 8
    for col, title in enumerate(
            ["№", "Раздел", "Документ / Наименование", "Статус", "Комментарий / Примечание", "Ответственный", "Дата"],
            start=1):
        ws.cell(row=9, column=col, value=title)

    row = 10
    group = subgroup = None
    for n, item in enumerate(items, start=1):
        g, sg, cat, title, status = item[:5]
        extra = item[5] if len(item) > 5 else {}
        if g != group:
            ws.cell(row=row, column=1, value=g); row += 1
            group, subgroup = g, None
        if sg and sg != subgroup:
            ws.cell(row=row, column=1, value=f"   ▸ {sg}"); row += 1
            subgroup = sg
        ws.cell(row=row, column=1, value=extra.get("number", n))
        ws.cell(row=row, column=2, value=cat)
        ws.cell(row=row, column=3, value=title)
        ws.cell(row=row, column=4, value=status)
        ws.cell(row=row, column=5, value=extra.get("comment"))
        ws.cell(row=row, column=6, value=extra.get("responsible"))
        ws.cell(row=row, column=7, value=extra.get("date"))
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="ИТОГО ПО СТАТУСАМ"); row += 1
    ws.cell(row=row, column=1, value="Есть:"); ws.cell(row=row, column=2, value='=COUNTIF(D10:D100,"Есть")'); row += 1
    ws.cell(row=row, column=1, value=999); ws.cell(row=row, column=3, value="Строка после ИТОГО не должна читаться")
    for extra_row in extra_rows or []:
        ws.append(extra_row)

    wb.create_sheet("Сводка по разделам")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
