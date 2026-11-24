"""Бизнес-логика: загрузка сводной таблицы и выдача данных порталу."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import ChecklistImport, ChecklistItem, Office
from .parser import (
    STATUS_DONE, STATUS_IN_PROGRESS, STATUS_LABELS, STATUS_MISSING, STATUS_NOT_SET,
    ParsedChecklist, empty_counts, parse_checklist, readiness, summarize,
)

LEVEL_LABELS = {
    "good": "Хорошо",
    "warn": "Требует внимания",
    "bad": "Критично",
    "new": "Нет данных",
}

# «Вес» статуса для определения, стало лучше или хуже
_STATUS_RANK = {STATUS_MISSING: 0, STATUS_NOT_SET: 0, STATUS_IN_PROGRESS: 1, STATUS_DONE: 2}


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


# ---------------------------------------------------------------------------
# Сериализация
# ---------------------------------------------------------------------------
def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:  # SQLite возвращает время без зоны — храним в UTC
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def level_for(readiness_value: float | None) -> str:
    if readiness_value is None:
        return "new"
    if readiness_value >= config.READINESS_GOOD:
        return "good"
    if readiness_value >= config.READINESS_WARN:
        return "warn"
    return "bad"


def _counts(imp: ChecklistImport) -> dict:
    return {
        "total": imp.total,
        STATUS_DONE: imp.done,
        STATUS_IN_PROGRESS: imp.in_progress,
        STATUS_MISSING: imp.missing,
        STATUS_NOT_SET: imp.not_set,
    }


def import_to_dict(imp: ChecklistImport) -> dict:
    return {
        "id": imp.id,
        "office_code": imp.office.code if imp.office else None,
        "uploaded_at": _iso(imp.uploaded_at),
        "filename": imp.filename,
        "sheet_name": imp.sheet_name,
        "check_date": _iso(imp.check_date),
        "inspector": imp.inspector,
        "reddy_number": imp.reddy_number,
        "organization": imp.organization,
        "headcount": imp.headcount,
        "msp_status": imp.msp_status,
        "counts": _counts(imp),
        "readiness": imp.readiness,
        "level": level_for(imp.readiness),
        "warnings": json.loads(imp.warnings) if imp.warnings else [],
    }


def item_to_dict(item: ChecklistItem) -> dict:
    return {
        "id": item.id,
        "number": item.number,
        "row": item.row,
        "category": item.category,
        "group": item.group_name,
        "subgroup": item.subgroup,
        "title": item.title,
        "status": item.status,
        "status_label": STATUS_LABELS[item.status],
        "comment": item.comment,
        "responsible": item.responsible,
        "date": _iso(item.item_date),
        "date_raw": item.item_date_raw,
    }


def office_to_dict(office: Office, current: ChecklistImport | None) -> dict:
    r = current.readiness if current else None
    lvl = level_for(r)
    return {
        "code": office.code,
        "name": office.name,
        "responsible": office.responsible,
        "readiness": r,
        "level": lvl,
        "level_label": LEVEL_LABELS[lvl],
        "check_date": _iso(current.check_date) if current else None,
        "inspector": current.inspector if current else None,
        "headcount": current.headcount if current else None,
        "counts": _counts(current) if current else None,
        "current_import_id": current.id if current else None,
        "last_uploaded_at": _iso(current.uploaded_at) if current else None,
    }


def category_summary(items: list[ChecklistItem]) -> list[dict]:
    _, cats = summarize([(i.category, i.status) for i in items])
    return cats


# ---------------------------------------------------------------------------
# Офисы
# ---------------------------------------------------------------------------
def get_office(db: Session, code: str) -> Office:
    office = db.scalar(select(Office).where(Office.code == code))
    if office is None:
        raise NotFound(f"Офис «{code}» не найден")
    return office


def current_import(db: Session, office: Office) -> ChecklistImport | None:
    if office.current_import_id is None:
        return None
    return db.get(ChecklistImport, office.current_import_id)


def refresh_current_import(db: Session, office: Office) -> None:
    """Актуальная загрузка = с самой поздней датой проверки; при равенстве — последняя загруженная."""
    db.flush()
    latest = db.scalar(
        select(ChecklistImport)
        .where(ChecklistImport.office_id == office.id)
        .order_by(ChecklistImport.check_date.desc(), ChecklistImport.id.desc())
        .limit(1)
    )
    office.current_import_id = latest.id if latest else None


def list_offices(db: Session) -> list[dict]:
    offices = db.scalars(select(Office).order_by(Office.code)).all()
    ids = [o.current_import_id for o in offices if o.current_import_id]
    imports = {i.id: i for i in db.scalars(select(ChecklistImport).where(ChecklistImport.id.in_(ids)))} if ids else {}
    return [office_to_dict(o, imports.get(o.current_import_id)) for o in offices]


def create_office(db: Session, code: str, name: str | None, responsible: str | None) -> Office:
    if db.scalar(select(Office).where(Office.code == code)):
        raise Conflict(f"Офис «{code}» уже существует")
    office = Office(code=code, name=(name or code).strip(), responsible=(responsible or None))
    db.add(office)
    db.commit()
    return office


def update_office(db: Session, code: str, name: str | None, responsible: str | None,
                  fields_set: set[str]) -> Office:
    office = get_office(db, code)
    if "name" in fields_set and name:
        office.name = name.strip()
    if "responsible" in fields_set:
        office.responsible = responsible.strip() if responsible and responsible.strip() else None
    db.commit()
    return office


# ---------------------------------------------------------------------------
# Загрузка сводной таблицы
# ---------------------------------------------------------------------------
def _title_key(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().lower()


def diff_items(prev: list, new: list) -> dict:
    """Сравнение с предыдущей актуальной загрузкой офиса (по наименованию документа)."""
    prev_map = {_title_key(p.title): p for p in prev}
    new_map = {_title_key(n.title): n for n in new}
    changed = []
    for key, n in new_map.items():
        p = prev_map.get(key)
        if p is not None and p.status != n.status:
            delta = _STATUS_RANK[n.status] - _STATUS_RANK[p.status]
            changed.append({
                "number": n.number,
                "title": n.title,
                "category": n.category,
                "from": p.status,
                "to": n.status,
                "direction": "better" if delta > 0 else "worse" if delta < 0 else "changed",
            })
    changed.sort(key=lambda c: c["number"])
    return {
        "has_previous": bool(prev),
        "changed": changed,
        "improved": sum(1 for c in changed if c["direction"] == "better"),
        "worsened": sum(1 for c in changed if c["direction"] == "worse"),
        "added": sorted(n.number for k, n in new_map.items() if k not in prev_map) if prev else [],
        "removed": sorted(({"number": p.number, "title": p.title} for k, p in prev_map.items() if k not in new_map),
                          key=lambda x: x["number"]) if prev else [],
    }


def import_checklist(db: Session, data: bytes, filename: str | None, dry_run: bool = False,
                     authorize=None) -> dict:
    """authorize(office | None) — проверка прав до любых изменений (бросает HTTPException)."""
    parsed: ParsedChecklist = parse_checklist(data)  # ChecklistParseError -> 422
    sha = hashlib.sha256(data).hexdigest()
    warnings = list(parsed.warnings)
    check_date = parsed.check_date or datetime.now(timezone.utc).date()

    office = db.scalar(select(Office).where(Office.code == parsed.office_code))
    if authorize is not None:
        authorize(office)
    office_created = office is None

    totals, by_category = summarize([(i.category, i.status) for i in parsed.items])

    if office is not None:
        dup = db.scalar(select(ChecklistImport).where(
            ChecklistImport.office_id == office.id, ChecklistImport.file_sha256 == sha))
        if dup is not None:
            return {
                "result": "duplicate",
                "message": f"Этот файл уже загружен для офиса «{office.code}» ({_iso(dup.uploaded_at)})",
                "office": office_to_dict(office, current_import(db, office)),
                "import": import_to_dict(dup),
                "summary": totals,
                "by_category": by_category,
                "warnings": warnings,
                "changes": None,
            }
        prev = current_import(db, office)
        prev_items = list(prev.items) if prev else []
    else:
        prev = None
        prev_items = []

    changes = diff_items(prev_items, parsed.items)
    if prev is not None and prev.check_date and check_date < prev.check_date:
        warnings.append(
            f"Дата проверки ({check_date:%d.%m.%Y}) раньше, чем у актуальной загрузки "
            f"({prev.check_date:%d.%m.%Y}): файл сохранится в истории, но индекс офиса не изменится"
        )

    if dry_run:
        preview_office = {
            "code": parsed.office_code,
            "exists": not office_created,
        }
        return {
            "result": "preview",
            "message": "Предпросмотр: данные не сохранены",
            "office": preview_office,
            "import": {
                "check_date": _iso(check_date), "inspector": parsed.inspector,
                "reddy_number": parsed.reddy_number, "organization": parsed.organization,
                "headcount": parsed.headcount, "msp_status": parsed.msp_status,
                "sheet_name": parsed.sheet_name, "filename": filename,
            },
            "summary": totals,
            "by_category": by_category,
            "warnings": warnings,
            "changes": changes,
        }

    if office_created:
        office = Office(code=parsed.office_code, name=parsed.office_code)
        db.add(office)
        db.flush()

    imp = ChecklistImport(
        office_id=office.id,
        filename=(filename or "")[:255] or None,
        file_sha256=sha,
        sheet_name=parsed.sheet_name,
        check_date=check_date,
        inspector=parsed.inspector,
        reddy_number=parsed.reddy_number,
        organization=parsed.organization,
        headcount=parsed.headcount,
        msp_status=parsed.msp_status,
        total=totals["total"],
        done=totals[STATUS_DONE],
        in_progress=totals[STATUS_IN_PROGRESS],
        missing=totals[STATUS_MISSING],
        not_set=totals[STATUS_NOT_SET],
        readiness=totals["readiness"],
        warnings=json.dumps(warnings, ensure_ascii=False) if warnings else None,
    )
    imp.items = [
        ChecklistItem(
            row=i.row, number=i.number, category=i.category, group_name=i.group, subgroup=i.subgroup,
            title=i.title, status=i.status, comment=i.comment, responsible=i.responsible,
            item_date=i.item_date, item_date_raw=i.item_date_raw,
        )
        for i in parsed.items
    ]
    db.add(imp)
    refresh_current_import(db, office)
    db.commit()

    return {
        "result": "created",
        "message": (f"Создан офис «{office.code}», " if office_created else "")
                   + f"загружено позиций: {totals['total']}, готовность {totals['readiness']}%",
        "office_created": office_created,
        "is_current": office.current_import_id == imp.id,
        "office": office_to_dict(office, current_import(db, office)),
        "import": import_to_dict(imp),
        "summary": totals,
        "by_category": by_category,
        "warnings": warnings,
        "changes": changes,
    }


def get_import(db: Session, import_id: int) -> ChecklistImport:
    imp = db.get(ChecklistImport, import_id)
    if imp is None:
        raise NotFound(f"Загрузка #{import_id} не найдена")
    return imp


def delete_import(db: Session, import_id: int) -> Office:
    imp = get_import(db, import_id)
    office = imp.office
    db.delete(imp)
    refresh_current_import(db, office)
    db.commit()
    return office


def office_imports(db: Session, office: Office) -> list[dict]:
    rows = db.scalars(
        select(ChecklistImport).where(ChecklistImport.office_id == office.id)
        .order_by(ChecklistImport.check_date.desc(), ChecklistImport.id.desc())
    ).all()
    out = []
    for r in rows:
        d = import_to_dict(r)
        d["is_current"] = r.id == office.current_import_id
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Дашборд
# ---------------------------------------------------------------------------
def dashboard(db: Session) -> dict:
    """Сводка по всем офисам: KPI, матрица «офис × направление», слабые места,
    чаще всего отсутствующие документы. Считается по актуальным загрузкам."""
    offices = db.scalars(select(Office).order_by(Office.code)).all()
    ids = [o.current_import_id for o in offices if o.current_import_id]
    imports = {i.id: i for i in db.scalars(select(ChecklistImport).where(ChecklistImport.id.in_(ids)))} if ids else {}

    levels = {k: 0 for k in LEVEL_LABELS}
    for o in offices:
        imp = imports.get(o.current_import_id)
        levels[level_for(imp.readiness if imp else None)] += 1

    docs = empty_counts()
    for i in imports.values():
        for k, v in _counts(i).items():
            docs[k] += v

    rows = []
    if ids:
        rows = db.execute(
            select(ChecklistItem.import_id, ChecklistItem.number, ChecklistItem.category,
                   ChecklistItem.status, ChecklistItem.title)
            .where(ChecklistItem.import_id.in_(ids))
            .order_by(ChecklistItem.import_id, ChecklistItem.number)
        ).all()

    # Порядок направлений — как в шаблоне (по первому появлению)
    categories: list[str] = []
    for r in rows:
        if r.category not in categories:
            categories.append(r.category)

    _, by_cat = summarize([(r.category, r.status) for r in rows])

    # --- Матрица офис × направление ------------------------------------------
    per_office: dict[int, list[tuple[str, str]]] = {}
    for r in rows:
        per_office.setdefault(r.import_id, []).append((r.category, r.status))

    prev_readiness = _previous_readiness(db, offices)

    matrix = []
    for o in offices:
        imp = imports.get(o.current_import_id)
        if imp is None:
            continue
        _, cats = summarize(per_office.get(imp.id, []))
        cells = {}
        for c in cats:
            lvl = level_for(c["readiness"])
            cells[c.pop("category")] = {**c, "level": lvl}
        prev = prev_readiness.get(o.id)
        matrix.append({
            "code": o.code,
            "name": o.name,
            "responsible": o.responsible,
            "readiness": imp.readiness,
            "level": level_for(imp.readiness),
            "check_date": _iso(imp.check_date),
            "counts": _counts(imp),
            "prev_readiness": prev,
            "delta": round(imp.readiness - prev, 1) if prev is not None else None,
            "cells": cells,
        })
    matrix.sort(key=lambda m: (m["readiness"], m["code"]))

    # Средняя готовность направления по офисам и сколько офисов проседают
    for c in by_cat:
        vals = [m["cells"][c["category"]]["readiness"] for m in matrix if c["category"] in m["cells"]]
        c["offices"] = len(vals)
        c["offices_avg"] = round(sum(vals) / len(vals), 1) if vals else None
        c["offices_below_good"] = sum(1 for v in vals if v < config.READINESS_GOOD)
        c["level"] = level_for(c["readiness"])

    # --- Слабые места: пары офис × направление ниже порога «Хорошо» -----------
    weak = []
    for m in matrix:
        for cat, cell in m["cells"].items():
            if cell["readiness"] < config.READINESS_GOOD:
                weak.append({
                    "code": m["code"], "name": m["name"], "category": cat,
                    "readiness": cell["readiness"], "level": cell["level"],
                    "total": cell["total"], "done": cell[STATUS_DONE],
                    "in_progress": cell[STATUS_IN_PROGRESS],
                    "missing": cell[STATUS_MISSING] + cell[STATUS_NOT_SET],
                })
    weak.sort(key=lambda w: (w["readiness"], -w["missing"], w["code"]))

    # --- Документы, которых чаще всего нет -------------------------------------
    code_by_import = {o.current_import_id: o.code for o in offices if o.current_import_id}
    missing_docs: dict[str, dict] = {}
    for r in rows:
        if r.status not in (STATUS_MISSING, STATUS_NOT_SET):
            continue
        key = _title_key(r.title)
        d = missing_docs.setdefault(key, {
            "title": r.title, "category": r.category, "number": r.number, "offices": [],
        })
        d["offices"].append(code_by_import[r.import_id])
    top_missing = sorted(missing_docs.values(), key=lambda d: (-len(d["offices"]), d["number"]))
    for d in top_missing:
        d["count"] = len(d["offices"])
        d["share"] = round(d["count"] * 100 / len(imports), 1) if imports else 0.0

    avg = round(sum(i.readiness for i in imports.values()) / len(imports), 1) if imports else None
    last = max((i.uploaded_at for i in imports.values()), default=None)
    return {
        "offices_total": len(offices),
        "offices_with_data": len(imports),
        "avg_readiness": avg,
        "avg_level": level_for(avg),
        "levels": levels,
        "documents": {**docs, "readiness": readiness(docs[STATUS_DONE], docs["total"])},
        "categories": categories,
        "by_category": by_cat,
        "matrix": matrix,
        "weak_spots": weak[:20],
        "weak_spots_total": len(weak),
        "top_missing": top_missing[:10],
        "top_missing_total": len(top_missing),
        "thresholds": {"good": config.READINESS_GOOD, "warn": config.READINESS_WARN},
        "last_uploaded_at": _iso(last),
    }


def _previous_readiness(db: Session, offices: list[Office]) -> dict[int, float]:
    """Готовность по предыдущей (до актуальной) проверке каждого офиса — для динамики."""
    out: dict[int, float] = {}
    office_ids = [o.id for o in offices if o.current_import_id]
    if not office_ids:
        return out
    current = {o.id: o.current_import_id for o in offices}
    rows = db.execute(
        select(ChecklistImport.office_id, ChecklistImport.id, ChecklistImport.readiness)
        .where(ChecklistImport.office_id.in_(office_ids))
        .order_by(ChecklistImport.office_id, ChecklistImport.check_date.desc(), ChecklistImport.id.desc())
    ).all()
    seen_current: set[int] = set()
    for office_id, imp_id, r in rows:
        if office_id in out:
            continue
        if imp_id == current.get(office_id):
            seen_current.add(office_id)
            continue
        if office_id in seen_current:
            out[office_id] = r
    return out


def public_config() -> dict:
    return {
        "statuses": STATUS_LABELS,
        "levels": LEVEL_LABELS,
        "readiness_good": config.READINESS_GOOD,
        "readiness_warn": config.READINESS_WARN,
        "max_upload_mb": config.MAX_UPLOAD_MB,
    }
