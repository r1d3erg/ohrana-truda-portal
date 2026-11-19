"""Ручной ввод СОУТ и ОПР: справочники, расчёт сроков, статусы офисов, предупреждения.

Правовые основания и смысл полей — docs/sout-opr.md.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import Office, RiskAssessment, SoutAssessment

# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------
STATUSES = {"planned": "Запланирована", "in_progress": "Проводится", "completed": "Завершена"}

SOUT_KINDS = {"planned": "Плановая", "unplanned": "Внеплановая"}
SOUT_PROCEDURES = {
    "regular": "С экспертной организацией",
    "simplified": "В упрощённом порядке (ПП РФ № 1830)",
}
# Основание внеплановой СОУТ (ч. 1 ст. 17 426-ФЗ) -> (подпись, срок проведения в месяцах).
# Сроки — ч. 2 ст. 17: 12 месяцев по п. 1 и 3 ч. 1, 6 месяцев по п. 2, 4–7 ч. 1.
SOUT_REASONS = {
    "new_workplaces": ("Ввод в эксплуатацию новых рабочих мест", 12),                       # п. 1
    "git_order": ("Предписание государственного инспектора труда", 6),                     # п. 2
    "process_change": ("Изменение технологического процесса, замена оборудования", 12),    # п. 3
    "materials_change": ("Изменение состава материалов или сырья", 6),                     # п. 4
    "ppe_change": ("Изменение применяемых средств индивидуальной и коллективной защиты", 6),  # п. 5
    "accident": ("Несчастный случай на производстве / профзаболевание", 6),                # п. 6
    "union_request": ("Мотивированное предложение выборного органа профсоюза", 6),         # п. 7
    # Прекращение декларации (ч. 5 ст. 11) наступает из-за несчастного случая,
    # профзаболевания или нарушений — срок взят как для п. 6
    "declaration_terminated": ("Прекращение действия декларации (ч. 5 ст. 11)", 6),
    "other": ("Иное основание", None),
}
SOUT_CLASSES = [
    ("class_1", "1"), ("class_2", "2"), ("class_3_1", "3.1"), ("class_3_2", "3.2"),
    ("class_3_3", "3.3"), ("class_3_4", "3.4"), ("class_4", "4"),
]
HARMFUL_CLASSES = ["class_3_1", "class_3_2", "class_3_3", "class_3_4", "class_4"]

OPR_KINDS = {"initial": "Первичная", "periodic": "Плановый пересмотр", "unplanned": "Внеплановая"}
OPR_PERFORMERS = {"self": "Своими силами (комиссия работодателя)", "contractor": "Сторонняя организация"}
OPR_METHODS = {
    "matrix": "Матричный метод",
    "fine_kinney": "Метод Файна — Кинни",
    "checklist": "Метод контрольных листов",
    "other": "Иной метод (по положению работодателя)",
}

SOUT_STATES = {
    "ok": ("Действует", "good"),
    "declared": ("Декларация, без повторной СОУТ", "good"),
    "expiring": ("Истекает срок", "warn"),
    "expired": ("Срок истёк", "bad"),
    "planned": ("Только запланирована", "warn"),
    "none": ("Нет данных", "new"),
}
OPR_STATES = {
    "ok": ("Действует", "good"),
    "review_soon": ("Скоро пересмотр", "warn"),
    "review_overdue": ("Пересмотр просрочен", "bad"),
    "planned": ("Только запланирована", "warn"),
    "none": ("Нет данных", "new"),
}

SOUT_FIELDS = [
    "kind", "procedure", "status", "reason", "reason_date", "due_date", "contractor",
    "contractor_reg_number", "commission_order", "start_date", "report_date", "fgis_date",
    "valid_until", "workplaces_total", "workplaces_assessed", "analogous_workplaces",
    "employees_covered", *[c for c, _ in SOUT_CLASSES], "declaration_submitted",
    "declaration_date", "declaration_number", "declaration_terminated", "familiarized_date",
    "employees_familiarized", "published_date", "measures_planned", "measures_done", "notes",
]
OPR_FIELDS = [
    "kind", "status", "reason", "performed_by", "contractor", "method", "commission_order",
    "assessment_date", "next_review_date", "workplaces_total", "workplaces_assessed",
    "professions_assessed", "hazards_identified", "risks_low", "risks_medium", "risks_high",
    "plan_approved_date", "measures_planned", "measures_done", "employees_informed_date", "notes",
]

FAMILIARIZATION_DAYS = 30  # ч. 5 ст. 15 426-ФЗ: ознакомление под подпись
PUBLICATION_DAYS = 30      # ч. 6 ст. 15 426-ФЗ: размещение на сайте (при наличии)


class ValidationFailed(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


# ---------------------------------------------------------------------------
# Даты
# ---------------------------------------------------------------------------
def today() -> date:
    return datetime.now(timezone.utc).date()


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def add_years(d: date, years: int) -> date:
    return add_months(d, years * 12)


def _iso(v):
    return v.isoformat() if isinstance(v, (date, datetime)) else v


def _days_left(d: date | None, ref: date) -> int | None:
    return (d - ref).days if d else None


# ---------------------------------------------------------------------------
# Валидация и нормализация ввода
# ---------------------------------------------------------------------------
def _check_enum(errors, value, allowed: dict, label: str):
    if value is not None and value not in allowed:
        errors.append(f"{label}: недопустимое значение «{value}»")


def _check_le(errors, a, b, text):
    if a is not None and b is not None and a > b:
        errors.append(text)


def prepare_sout(data: dict) -> dict:
    """Проверить и дополнить данные СОУТ (срок действия, срок внеплановой)."""
    d = {k: data.get(k) for k in SOUT_FIELDS}
    errors: list[str] = []
    d["kind"] = d["kind"] or "planned"
    d["procedure"] = d["procedure"] or "regular"
    d["status"] = d["status"] or "completed"
    for c, _ in SOUT_CLASSES:
        d[c] = d[c] or 0
    d["declaration_submitted"] = bool(d["declaration_submitted"])
    d["declaration_terminated"] = bool(d["declaration_terminated"])

    _check_enum(errors, d["kind"], SOUT_KINDS, "Вид СОУТ")
    _check_enum(errors, d["procedure"], SOUT_PROCEDURES, "Порядок проведения")
    _check_enum(errors, d["status"], STATUSES, "Статус")
    _check_enum(errors, d["reason"], SOUT_REASONS, "Основание внеплановой СОУТ")

    if d["kind"] == "unplanned" and not d["reason"]:
        errors.append("Для внеплановой СОУТ укажите основание")
    if d["status"] == "completed" and not d["report_date"]:
        errors.append("Для завершённой СОУТ укажите дату утверждения отчёта")
    if d["report_date"] and d["start_date"] and d["report_date"] < d["start_date"]:
        errors.append("Дата утверждения отчёта раньше даты начала")
    if d["fgis_date"] and d["report_date"] and d["fgis_date"] < d["report_date"]:
        errors.append("Дата внесения в ФГИС раньше даты утверждения отчёта")

    _check_le(errors, d["workplaces_assessed"], d["workplaces_total"],
              "Оценено рабочих мест больше, чем всего рабочих мест")
    _check_le(errors, d["analogous_workplaces"], d["workplaces_assessed"],
              "Аналогичных рабочих мест больше, чем оценено")
    _check_le(errors, d["measures_done"], d["measures_planned"],
              "Выполнено мероприятий больше, чем запланировано")
    class_sum = sum(d[c] for c, _ in SOUT_CLASSES)
    if d["workplaces_assessed"] is not None and class_sum > d["workplaces_assessed"]:
        errors.append(f"Сумма по классам ({class_sum}) больше числа оценённых рабочих мест ({d['workplaces_assessed']})")
    if d["declaration_submitted"] and sum(d[c] for c in HARMFUL_CLASSES) and not (d["class_1"] or d["class_2"]):
        errors.append("Декларация подаётся только на рабочие места с классами 1 и 2")
    if errors:
        raise ValidationFailed(errors)

    # Срок действия: 5 лет со дня внесения сведений в ФГИС (ч. 4 ст. 8), если не указан вручную
    base = d["fgis_date"] or d["report_date"]
    if not d["valid_until"] and base and d["status"] == "completed":
        d["valid_until"] = add_years(base, config.SOUT_VALIDITY_YEARS)
    # Срок внеплановой: 12 или 6 месяцев со дня наступления основания (ч. 2 ст. 17)
    if d["kind"] == "unplanned" and d["reason_date"] and not d["due_date"]:
        months = SOUT_REASONS.get(d["reason"], (None, None))[1]
        if months:
            d["due_date"] = add_months(d["reason_date"], months)
    return d


def prepare_opr(data: dict) -> dict:
    d = {k: data.get(k) for k in OPR_FIELDS}
    errors: list[str] = []
    d["kind"] = d["kind"] or "periodic"
    d["status"] = d["status"] or "completed"
    d["performed_by"] = d["performed_by"] or "self"
    for k in ("risks_low", "risks_medium", "risks_high"):
        d[k] = d[k] or 0

    _check_enum(errors, d["kind"], OPR_KINDS, "Вид оценки")
    _check_enum(errors, d["status"], STATUSES, "Статус")
    _check_enum(errors, d["performed_by"], OPR_PERFORMERS, "Кем проводится")
    _check_enum(errors, d["method"], OPR_METHODS, "Метод")
    if d["status"] == "completed" and not d["assessment_date"]:
        errors.append("Для завершённой оценки укажите дату утверждения результатов")
    if d["next_review_date"] and d["assessment_date"] and d["next_review_date"] <= d["assessment_date"]:
        errors.append("Дата пересмотра должна быть позже даты оценки")
    _check_le(errors, d["workplaces_assessed"], d["workplaces_total"],
              "Оценено рабочих мест больше, чем всего рабочих мест")
    _check_le(errors, d["measures_done"], d["measures_planned"],
              "Выполнено мероприятий больше, чем запланировано")
    if errors:
        raise ValidationFailed(errors)

    if not d["next_review_date"] and d["assessment_date"] and d["status"] == "completed":
        d["next_review_date"] = add_months(d["assessment_date"], config.OPR_REVIEW_MONTHS)
    return d


# ---------------------------------------------------------------------------
# Расчёты по записи
# ---------------------------------------------------------------------------
def sout_to_dict(r: SoutAssessment, ref: date | None = None) -> dict:
    ref = ref or today()
    classes = {c: getattr(r, c) for c, _ in SOUT_CLASSES}
    harmful = sum(classes[c] for c in HARMFUL_CLASSES)
    class_total = sum(classes.values())
    declared = bool(r.declaration_submitted and not r.declaration_terminated and class_total and harmful == 0)
    fam_deadline = r.report_date + timedelta(days=FAMILIARIZATION_DAYS) if r.report_date else None
    pub_deadline = r.report_date + timedelta(days=PUBLICATION_DAYS) if r.report_date else None
    out = {k: _iso(getattr(r, k)) for k in SOUT_FIELDS}
    out.update({
        "id": r.id,
        "office_code": r.office.code if r.office else None,
        "kind_label": SOUT_KINDS.get(r.kind),
        "procedure_label": SOUT_PROCEDURES.get(r.procedure),
        "status_label": STATUSES.get(r.status),
        "reason_label": SOUT_REASONS.get(r.reason, (None,))[0] if r.reason else None,
        "classes": classes,
        "class_total": class_total,
        "harmful_workplaces": harmful,
        "declared_indefinite": declared,
        "coverage": round(r.workplaces_assessed * 100 / r.workplaces_total, 1)
                    if r.workplaces_total and r.workplaces_assessed is not None else None,
        "days_left": _days_left(r.valid_until, ref),
        "familiarization_deadline": _iso(fam_deadline),
        "familiarization_overdue": bool(fam_deadline and not r.familiarized_date and ref > fam_deadline),
        "publication_deadline": _iso(pub_deadline),
        "publication_overdue": bool(pub_deadline and not r.published_date and ref > pub_deadline),
        "due_overdue": bool(r.status != "completed" and r.due_date and ref > r.due_date),
        "updated_at": _iso(r.updated_at),
    })
    return out


def opr_to_dict(r: RiskAssessment, ref: date | None = None) -> dict:
    ref = ref or today()
    out = {k: _iso(getattr(r, k)) for k in OPR_FIELDS}
    risks_total = r.risks_low + r.risks_medium + r.risks_high
    out.update({
        "id": r.id,
        "office_code": r.office.code if r.office else None,
        "kind_label": OPR_KINDS.get(r.kind),
        "status_label": STATUSES.get(r.status),
        "performed_by_label": OPR_PERFORMERS.get(r.performed_by),
        "method_label": OPR_METHODS.get(r.method) if r.method else None,
        "risks_total": risks_total,
        "coverage": round(r.workplaces_assessed * 100 / r.workplaces_total, 1)
                    if r.workplaces_total and r.workplaces_assessed is not None else None,
        "measures_progress": round(r.measures_done * 100 / r.measures_planned, 1)
                             if r.measures_planned and r.measures_done is not None else None,
        "days_to_review": _days_left(r.next_review_date, ref),
        "updated_at": _iso(r.updated_at),
    })
    return out


# ---------------------------------------------------------------------------
# Статус офиса и предупреждения
# ---------------------------------------------------------------------------
def _sout_sort_key(r: SoutAssessment):
    return (r.fgis_date or r.report_date or date.min, r.id)


def sout_office_state(office: Office, records: list[SoutAssessment], ref: date | None = None) -> dict:
    ref = ref or today()
    completed = sorted([r for r in records if r.status == "completed"], key=_sout_sort_key, reverse=True)
    pending = sorted([r for r in records if r.status != "completed"],
                     key=lambda r: (r.due_date or date.max, r.id))
    current = completed[0] if completed else None
    cur = sout_to_dict(current, ref) if current else None
    alerts: list[dict] = []

    if cur is None:
        state = "planned" if pending else "none"
    elif cur["declared_indefinite"]:
        state = "declared"
    elif current.valid_until and current.valid_until < ref:
        state = "expired"
    elif current.valid_until and (current.valid_until - ref).days <= config.SOUT_WARN_DAYS:
        state = "expiring"
    else:
        state = "ok"

    def alert(sev, text, due=None, kind="sout"):
        alerts.append({"severity": sev, "text": text, "due": _iso(due), "kind": kind, "office_code": office.code})

    if state == "expired":
        alert("bad", f"Срок действия СОУТ истёк {current.valid_until:%d.%m.%Y}", current.valid_until)
    elif state == "expiring":
        alert("warn", f"СОУТ действует до {current.valid_until:%d.%m.%Y} — пора планировать новую", current.valid_until)
    if state == "none":
        alert("warn", "Нет сведений о СОУТ")
    if cur:
        if cur["familiarization_overdue"]:
            deadline = current.report_date + timedelta(days=FAMILIARIZATION_DAYS)
            alert("bad", f"Не завершено ознакомление работников с результатами СОУТ (срок {deadline:%d.%m.%Y})", deadline)
        if cur["publication_overdue"]:
            alert("warn", "Результаты СОУТ не размещены на сайте (если сайт есть)",
                  current.report_date + timedelta(days=PUBLICATION_DAYS))
        if current.workplaces_total and current.workplaces_assessed is not None \
                and current.workplaces_assessed < current.workplaces_total:
            alert("warn", f"СОУТ охватывает {current.workplaces_assessed} из {current.workplaces_total} рабочих мест")
        if current.declaration_terminated and not pending:
            alert("bad", "Декларация прекращена — нужна внеплановая СОУТ (запланируйте её)")
        if cur["harmful_workplaces"]:
            alert("warn", f"Рабочих мест с вредными/опасными условиями: {cur['harmful_workplaces']}")
    for p in pending:
        label = SOUT_REASONS.get(p.reason, ("",))[0] if p.reason else SOUT_KINDS.get(p.kind)
        if p.due_date and p.due_date < ref:
            alert("bad", f"Просрочена {SOUT_KINDS.get(p.kind, '').lower()} СОУТ: {label}", p.due_date)
        elif p.due_date:
            alert("warn", f"Запланирована {SOUT_KINDS.get(p.kind, '').lower()} СОУТ до {p.due_date:%d.%m.%Y}: {label}", p.due_date)

    label, level = SOUT_STATES[state]
    if any(a["severity"] == "bad" for a in alerts):
        level = "bad"
    return {
        "office_code": office.code, "office_name": office.name,
        "state": state, "state_label": label, "level": level,
        "current": cur,
        "pending": [sout_to_dict(p, ref) for p in pending],
        "records_count": len(records),
        "alerts": alerts,
    }


def opr_office_state(office: Office, records: list[RiskAssessment], ref: date | None = None) -> dict:
    ref = ref or today()
    completed = sorted([r for r in records if r.status == "completed"],
                       key=lambda r: (r.assessment_date or date.min, r.id), reverse=True)
    pending = [r for r in records if r.status != "completed"]
    current = completed[0] if completed else None
    cur = opr_to_dict(current, ref) if current else None
    alerts: list[dict] = []

    def alert(sev, text, due=None):
        alerts.append({"severity": sev, "text": text, "due": _iso(due), "kind": "opr", "office_code": office.code})

    if current is None:
        state = "planned" if pending else "none"
        alert("warn", "Нет сведений об оценке профессиональных рисков")
    elif current.next_review_date and current.next_review_date < ref:
        state = "review_overdue"
        alert("bad", f"Пересмотр ОПР просрочен (плановая дата {current.next_review_date:%d.%m.%Y})", current.next_review_date)
    elif current.next_review_date and (current.next_review_date - ref).days <= config.OPR_WARN_DAYS:
        state = "review_soon"
        alert("warn", f"Плановый пересмотр ОПР до {current.next_review_date:%d.%m.%Y}", current.next_review_date)
    else:
        state = "ok"

    if current is not None:
        if (current.risks_high or current.risks_medium) and not current.plan_approved_date:
            alert("warn", "Есть средние/высокие риски, но не утверждён план мероприятий по их снижению")
        if current.risks_high:
            done = f", мероприятия: {current.measures_done or 0} из {current.measures_planned}" if current.measures_planned else ""
            sev = "bad" if not current.measures_planned or (current.measures_done or 0) < current.measures_planned else "warn"
            alert(sev, f"Высоких рисков: {current.risks_high}{done}")
        if not current.employees_informed_date:
            alert("warn", "Работники не ознакомлены с результатами ОПР")
        if current.workplaces_total and current.workplaces_assessed is not None \
                and current.workplaces_assessed < current.workplaces_total:
            alert("warn", f"ОПР охватывает {current.workplaces_assessed} из {current.workplaces_total} рабочих мест")

    label, level = OPR_STATES[state]
    if any(a["severity"] == "bad" for a in alerts):
        level = "bad"
    return {
        "office_code": office.code, "office_name": office.name,
        "state": state, "state_label": label, "level": level,
        "current": cur,
        "pending": [opr_to_dict(p, ref) for p in pending],
        "records_count": len(records),
        "alerts": alerts,
    }


def _grouped(db: Session, model, offices: list[Office]) -> dict[int, list]:
    out: dict[int, list] = {o.id: [] for o in offices}
    if offices:
        for r in db.scalars(select(model).where(model.office_id.in_(list(out)))):
            out[r.office_id].append(r)
    return out


def sout_summary(db: Session) -> list[dict]:
    offices = db.scalars(select(Office).order_by(Office.code)).all()
    grouped = _grouped(db, SoutAssessment, offices)
    return [sout_office_state(o, grouped[o.id]) for o in offices]


def opr_summary(db: Session) -> list[dict]:
    offices = db.scalars(select(Office).order_by(Office.code)).all()
    grouped = _grouped(db, RiskAssessment, offices)
    return [opr_office_state(o, grouped[o.id]) for o in offices]


_LEVEL_ORDER = {"bad": 0, "warn": 1}


def dashboard_block(db: Session) -> dict:
    """Сводка СОУТ/ОПР для дашборда: состояния по офисам и общий список предупреждений."""
    sout = sout_summary(db)
    opr = opr_summary(db)
    sout_counts = {k: 0 for k in SOUT_STATES}
    opr_counts = {k: 0 for k in OPR_STATES}
    for s in sout:
        sout_counts[s["state"]] += 1
    for o in opr:
        opr_counts[o["state"]] += 1
    alerts = [a for s in sout for a in s["alerts"]] + [a for o in opr for a in o["alerts"]]
    alerts.sort(key=lambda a: (_LEVEL_ORDER.get(a["severity"], 2), a["due"] or "9999", a["office_code"]))
    harmful = sum((s["current"] or {}).get("harmful_workplaces", 0) for s in sout)
    high_risks = sum((o["current"] or {}).get("risks_high", 0) for o in opr)
    return {
        "sout": {
            "counts": sout_counts,
            "harmful_workplaces": harmful,
            "by_office": {s["office_code"]: {
                "state": s["state"], "state_label": s["state_label"], "level": s["level"],
                "valid_until": (s["current"] or {}).get("valid_until"),
            } for s in sout},
        },
        "opr": {
            "counts": opr_counts,
            "high_risks": high_risks,
            "by_office": {o["office_code"]: {
                "state": o["state"], "state_label": o["state_label"], "level": o["level"],
                "next_review_date": (o["current"] or {}).get("next_review_date"),
                "risks_high": (o["current"] or {}).get("risks_high", 0),
            } for o in opr},
        },
        "alerts": alerts[:30],
        "alerts_total": len(alerts),
        "alerts_bad": sum(1 for a in alerts if a["severity"] == "bad"),
    }


def public_dictionaries() -> dict:
    return {
        "statuses": STATUSES,
        "sout_kinds": SOUT_KINDS,
        "sout_procedures": SOUT_PROCEDURES,
        "sout_reasons": {k: {"label": v[0], "months": v[1]} for k, v in SOUT_REASONS.items()},
        "sout_classes": [{"field": f, "label": l} for f, l in SOUT_CLASSES],
        "opr_kinds": OPR_KINDS,
        "opr_performers": OPR_PERFORMERS,
        "opr_methods": OPR_METHODS,
        "sout_validity_years": config.SOUT_VALIDITY_YEARS,
        "sout_warn_days": config.SOUT_WARN_DAYS,
        "opr_review_months": config.OPR_REVIEW_MONTHS,
        "opr_warn_days": config.OPR_WARN_DAYS,
    }
