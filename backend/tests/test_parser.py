from datetime import date, datetime

import pytest

from app.parser import ChecklistParseError, parse_checklist, summarize
from factory import build_checklist


def test_parses_header_and_items():
    p = parse_checklist(build_checklist())
    assert p.office_code == "t1"
    assert p.check_date == date(2026, 8, 17)
    assert p.inspector == "Тестов Т.Т."
    assert p.reddy_number == "12345678901"
    assert p.headcount == 120
    assert p.msp_status == "63"
    assert len(p.items) == 6  # строка после «ИТОГО» не прочитана

    first = p.items[0]
    assert first.number == 1
    assert first.category == "Охрана труда"
    assert first.group == "1. ОХРАНА ТРУДА И СУОТ"
    assert first.subgroup == "Организационные документы"
    assert first.status == "done"
    # подзаголовок сбрасывается при смене блока
    assert p.items[3].group == "2. ПЕРВАЯ ПОМОЩЬ" and p.items[3].subgroup is None


def test_summary_matches_excel_formulas():
    p = parse_checklist(build_checklist())
    totals, cats = summarize([(i.category, i.status) for i in p.items])
    assert totals == {"total": 6, "done": 3, "in_progress": 2, "missing": 1, "not_set": 0, "readiness": 50.0}
    assert [c["category"] for c in cats] == ["Охрана труда", "Первая помощь", "Пожарная безопасность"]
    assert cats[0]["readiness"] == 33.3


def test_status_is_case_and_space_insensitive():
    items = [("1. Б", None, "Охрана труда", "Док", "  в  РАБОТЕ ")]
    assert parse_checklist(build_checklist(items=items)).items[0].status == "in_progress"


def test_unknown_status_is_error_with_row():
    items = [("1. Б", None, "Охрана труда", "Док", "Готово")]
    with pytest.raises(ChecklistParseError) as e:
        parse_checklist(build_checklist(items=items))
    assert "неизвестный статус «Готово»" in e.value.errors[0]
    assert e.value.errors[0].startswith("Строка 11")


def test_empty_status_is_warning_and_counts_as_not_ready():
    items = [("1. Б", None, "Охрана труда", "Док", None), ("1. Б", None, "Охрана труда", "Док 2", "Есть")]
    p = parse_checklist(build_checklist(items=items))
    assert p.items[0].status == "not_set"
    assert any("не указан статус" in w for w in p.warnings)
    totals, _ = summarize([(i.category, i.status) for i in p.items])
    assert totals["readiness"] == 50.0


def test_missing_office_code():
    with pytest.raises(ChecklistParseError) as e:
        parse_checklist(build_checklist(office=None))
    assert "Номер офиса" in e.value.errors[0]


def test_invalid_office_code():
    with pytest.raises(ChecklistParseError):
        parse_checklist(build_checklist(office="офис 1/2"))


def test_numeric_office_code_kept_as_text():
    assert parse_checklist(build_checklist(office=101)).office_code == "101"


def test_duplicate_numbers():
    items = [
        ("1. Б", None, "Охрана труда", "Док 1", "Есть", {"number": 5}),
        ("1. Б", None, "Охрана труда", "Док 2", "Есть", {"number": 5}),
    ]
    with pytest.raises(ChecklistParseError) as e:
        parse_checklist(build_checklist(items=items))
    assert "повторяется" in e.value.errors[0]


def test_item_fields_and_dates():
    items = [
        ("1. Б", None, "Охрана труда", "Док 1", "Есть",
         {"comment": "Приказ №12", "responsible": "Иванов", "date": datetime(2026, 9, 1)}),
        ("1. Б", None, "Охрана труда", "Док 2", "Нет", {"date": "01.10.2026"}),
        ("1. Б", None, "Охрана труда", "Док 3", "Нет", {"date": "к концу квартала"}),
    ]
    p = parse_checklist(build_checklist(items=items))
    assert p.items[0].comment == "Приказ №12" and p.items[0].responsible == "Иванов"
    assert p.items[0].item_date == date(2026, 9, 1)
    assert p.items[1].item_date == date(2026, 10, 1)
    assert p.items[2].item_date is None and p.items[2].item_date_raw == "к концу квартала"
    assert any("не удалось распознать" in w for w in p.warnings)


def test_unparseable_check_date_is_warning():
    p = parse_checklist(build_checklist(check_date="вчера"))
    assert p.check_date is None
    assert any("вчера" in w for w in p.warnings)


def test_not_xlsx():
    with pytest.raises(ChecklistParseError) as e:
        parse_checklist(b"not an excel file")
    assert ".xlsx" in e.value.errors[0]


def test_no_items():
    with pytest.raises(ChecklistParseError) as e:
        parse_checklist(build_checklist(items=[]))
    assert "ни одной позиции" in e.value.errors[0]
