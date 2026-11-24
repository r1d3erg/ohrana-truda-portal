"""Направления «Пожарная безопасность», «Электробезопасность», «ГО и ЧС»: ручной ввод по офису.

У каждого офиса по каждому направлению — одна карточка (данные в JSON). Состав полей и
правила сроков описаны здесь, в SPECS; фронтенд строит форму по /api/directions/<kind>/spec,
поэтому новое поле добавляется только в этом файле.

Правила (CHECKS):
  every  — поле хранит дату последнего события; следующее = дата + months
           (warn_days — своё окно предупреждения для частых событий)
           (months может зависеть от других полей). Просрочено → bad, скоро → warn,
           не заполнено → warn (или bad, если missing='bad').
  due    — поле хранит крайнюю дату (напр. перезарядка огнетушителей).
  flag   — булево поле должно быть True (иначе предупреждение).
  count  — числовое поле должно быть 0 (иначе предупреждение с числом).
  filled — текстовое поле должно быть заполнено.
  min_group — группа по электробезопасности не ниже заданной.
Любое правило может иметь when(data) -> bool: проверяется только при выполнении условия.
Основания и периодичность — docs/directions.md и модуль «Инструкция».
"""
from __future__ import annotations

from datetime import date
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .models import Office, OfficeDirection, offices_query
from .registers import ValidationFailed, add_months, today

GROUPS = {"II": "II", "III": "III", "IV": "IV", "V": "V"}
GROUP_ORDER = ["I", "II", "III", "IV", "V"]

STATES = {
    "ok": ("В норме", "good"),
    "soon": ("Скоро срок", "warn"),
    "attention": ("Требует внимания", "warn"),
    "overdue": ("Просрочено", "bad"),
    "none": ("Нет данных", "new"),
}


def _f(key, label, type_="text", section="", hint=None, options=None, wide=False):
    d = {"key": key, "label": label, "type": type_, "section": section}
    if hint:
        d["hint"] = hint
    if options:
        d["options"] = options
    if wide:
        d["wide"] = True
    return d


# ---------------------------------------------------------------------------
# Пожарная безопасность
# ---------------------------------------------------------------------------
FIRE_FIELDS = [
    _f("responsible", "Ответственный за пожарную безопасность (ФИО)", section="Ответственный"),
    _f("responsible_training_date", "Дата обучения по ДПО в области ПБ", "date", "Ответственный",
       "Приказ МЧС № 1120, прил. 4. Повтор — раз в 5 лет по внутреннему регламенту"),
    _f("order_date", "Дата приказа о назначении", "date", "Ответственный"),
    _f("people_50plus", "В помещении одновременно 50 и более человек", "bool", "Помещение",
       "Тогда повторный противопожарный инструктаж — раз в полгода"),
    _f("duties_split", "Кто отвечает за сигнализацию, планы эвакуации, огнетушители", "enum", "Помещение",
       options={"company": "Компания", "landlord": "Арендодатель (записано в договоре)", "unclear": "Не определено в договоре"}),
    _f("instruction_approved", "Инструкция о мерах пожарной безопасности утверждена", "bool", "Помещение"),
    _f("evac_plan", "Планы эвакуации вывешены", "bool", "Помещение", "Обязательны, если на этаже более 10 человек"),
    _f("evac_plan_date", "Дата актуализации планов эвакуации", "date", "Помещение"),
    _f("alarm_check_date", "Дата акта проверки сигнализации и оповещения", "date", "Помещение"),
    _f("extinguishers_count", "Огнетушителей, шт.", "int", "Огнетушители"),
    _f("extinguishers_recharge_due", "Ближайшая перезарядка", "date", "Огнетушители", "Самая ранняя дата по паспортам"),
    _f("extinguishers_inspection_date", "Последний осмотр (журнал эксплуатации)", "date", "Огнетушители", "Ежеквартально"),
    _f("briefing_repeat_date", "Последний повторный противопожарный инструктаж", "date", "Инструктажи и тренировки"),
    _f("drill_date", "Последняя тренировка по эвакуации", "date", "Инструктажи и тренировки", "Не реже раза в полгода, с актом"),
    _f("notes", "Примечания", "textarea", "Примечания", wide=True),
]

FIRE_CHECKS = [
    {"type": "filled", "field": "responsible", "text": "Не назначен ответственный за пожарную безопасность", "severity": "bad"},
    {"type": "every", "field": "responsible_training_date", "months": 60, "label": "Обучение ответственного по ДПО"},
    {"type": "flag", "field": "instruction_approved", "text": "Не утверждена инструкция о мерах пожарной безопасности"},
    {"type": "flag", "field": "evac_plan", "text": "Нет планов эвакуации"},
    {"type": "flag", "field": "duties_split", "text": "В договоре аренды не распределены обязанности по ПБ",
     "test": lambda v: v in ("company", "landlord")},
    {"type": "every", "field": "alarm_check_date", "months": 12, "label": "Проверка сигнализации и оповещения",
     "when": lambda d: d.get("duties_split") == "company"},
    {"type": "due", "field": "extinguishers_recharge_due", "label": "Перезарядка огнетушителей"},
    {"type": "every", "field": "extinguishers_inspection_date", "months": 3, "label": "Осмотр огнетушителей", "warn_days": 14},
    {"type": "every", "field": "briefing_repeat_date", "label": "Повторный противопожарный инструктаж",
     "months": lambda d: 6 if d.get("people_50plus") else 12, "missing": "bad"},
    {"type": "every", "field": "drill_date", "months": 6, "label": "Тренировка по эвакуации",
     "when": lambda d: bool(d.get("evac_plan"))},
]

# ---------------------------------------------------------------------------
# Электробезопасность
# ---------------------------------------------------------------------------
ELECTRO_FIELDS = [
    _f("network_owner", "Чья электросеть офиса", "enum", "Электрохозяйство",
       options={"company": "На балансе компании", "landlord": "Арендодателя (записано в договоре)"}),
    _f("responsible", "Ответственный за электрохозяйство (ФИО)", section="Электрохозяйство",
       hint="Нужен, если сеть на балансе компании"),
    _f("responsible_group", "Группа ответственного", "enum", "Электрохозяйство", options=GROUPS),
    _f("responsible_check_date", "Последняя проверка знаний ответственного", "date", "Электрохозяйство", "Раз в год"),
    _f("assigner", "Кто присваивает I группу (ФИО)", section="I группа",
       hint="Электротехнический персонал с группой не ниже III"),
    _f("assigner_group", "Группа присваивающего", "enum", "I группа", options=GROUPS),
    _f("program_approved", "Программа инструктажа на I группу и перечень должностей утверждены", "bool", "I группа"),
    _f("group1_date", "Последнее присвоение I группы по офису", "date", "I группа", "Раз в год всем сотрудникам"),
    _f("group1_overdue", "Сотрудников с просроченной I группой", "int", "I группа"),
    _f("walkthrough_date", "Последний обход офиса", "date", "Обход",
       "Удлинители, обогреватели, щиты, кабели — ежемесячно"),
    _f("violations_open", "Неустранённых нарушений", "int", "Обход"),
    _f("notes", "Примечания", "textarea", "Примечания", wide=True),
]

ELECTRO_CHECKS = [
    {"type": "flag", "field": "network_owner", "text": "Не указано, чья электросеть офиса",
     "test": lambda v: v in ("company", "landlord")},
    {"type": "filled", "field": "responsible", "text": "Не назначен ответственный за электрохозяйство", "severity": "bad",
     "when": lambda d: d.get("network_owner") == "company"},
    {"type": "min_group", "field": "responsible_group", "min": "IV", "text": "Группа ответственного за электрохозяйство ниже IV",
     "when": lambda d: d.get("network_owner") == "company"},
    {"type": "every", "field": "responsible_check_date", "months": 12, "label": "Проверка знаний ответственного",
     "when": lambda d: d.get("network_owner") == "company"},
    {"type": "filled", "field": "assigner", "text": "Не назначен сотрудник, присваивающий I группу", "severity": "bad"},
    {"type": "min_group", "field": "assigner_group", "min": "III", "text": "Присваивающий I группу имеет группу ниже III"},
    {"type": "flag", "field": "program_approved", "text": "Не утверждены программа инструктажа на I группу и перечень должностей"},
    {"type": "every", "field": "group1_date", "months": 12, "label": "Присвоение I группы", "missing": "bad"},
    {"type": "count", "field": "group1_overdue", "text": "Сотрудников с просроченной I группой", "severity": "bad"},
    {"type": "every", "field": "walkthrough_date", "months": 1, "label": "Обход офиса", "warn_days": 5},
    {"type": "count", "field": "violations_open", "text": "Неустранённых нарушений по электробезопасности"},
]

# ---------------------------------------------------------------------------
# ГО и ЧС
# ---------------------------------------------------------------------------
GO_FIELDS = [
    _f("go_category", "Компания отнесена к категории по гражданской обороне", "bool", "Общее",
       "Обычный IT-офис — нет. Если да, нужен план ГО"),
    _f("go_plan_date", "Дата утверждения плана ГО", "date", "Общее"),
    _f("authorized", "Уполномоченный по ГО и ЧС (ФИО)", section="Уполномоченный и обучение"),
    _f("authorized_training_date", "Обучение уполномоченного (УМЦ ГОЧС)", "date", "Уполномоченный и обучение", "Раз в 5 лет"),
    _f("head_training_date", "Обучение руководителя по ГО и ЧС", "date", "Уполномоченный и обучение", "Раз в 5 лет"),
    _f("program_approved", "Программа вводного инструктажа по ГО и инструктажа по ЧС утверждена", "bool", "Инструктажи"),
    _f("es_briefing_date", "Последний ежегодный инструктаж по ЧС", "date", "Инструктажи"),
    _f("newcomers_without_briefing", "Новичков без инструктажа по ГО в первый месяц", "int", "Инструктажи"),
    _f("exercise_date", "Последние учения / тренировка", "date", "Учения", "Удобно совмещать с эвакуацией"),
    _f("memo_posted", "Памятка вывешена (сигнал «Внимание всем!», укрытие, 112)", "bool", "Учения"),
    _f("notes", "Примечания", "textarea", "Примечания", wide=True),
]

GO_CHECKS = [
    {"type": "filled", "field": "authorized", "text": "Не назначен уполномоченный по ГО и ЧС", "severity": "bad"},
    {"type": "every", "field": "authorized_training_date", "months": 60, "label": "Обучение уполномоченного по ГО и ЧС"},
    {"type": "every", "field": "head_training_date", "months": 60, "label": "Обучение руководителя по ГО и ЧС"},
    {"type": "flag", "field": "program_approved", "text": "Не утверждена программа инструктажа по ГО и ЧС"},
    {"type": "every", "field": "es_briefing_date", "months": 12, "label": "Ежегодный инструктаж по ЧС", "missing": "bad"},
    {"type": "count", "field": "newcomers_without_briefing", "text": "Новичков без вводного инструктажа по ГО", "severity": "bad"},
    {"type": "every", "field": "exercise_date", "months": 12, "label": "Учения / тренировка по ГО и ЧС"},
    {"type": "flag", "field": "memo_posted", "text": "Не вывешена памятка по действиям при ЧС"},
    {"type": "filled", "field": "go_plan_date", "text": "Компания категорирована по ГО, но план ГО не утверждён", "severity": "bad",
     "when": lambda d: bool(d.get("go_category"))},
]

SPECS: dict[str, dict] = {
    "fire": {"title": "Пожарная безопасность", "short": "ПБ", "fields": FIRE_FIELDS, "checks": FIRE_CHECKS,
             "guide": "fire-electro"},
    "electro": {"title": "Электробезопасность", "short": "ЭБ", "fields": ELECTRO_FIELDS, "checks": ELECTRO_CHECKS,
                "guide": "fire-electro"},
    "go": {"title": "ГО и ЧС", "short": "ГО ЧС", "fields": GO_FIELDS, "checks": GO_CHECKS, "guide": "go"},
}
KINDS = list(SPECS)


class UnknownKind(Exception):
    pass


def spec(kind: str) -> dict:
    if kind not in SPECS:
        raise UnknownKind(kind)
    s = SPECS[kind]
    return {"kind": kind, "title": s["title"], "short": s["short"], "guide": s["guide"], "fields": s["fields"],
            "warn_days": config.DIRECTIONS_WARN_DAYS}


# ---------------------------------------------------------------------------
# Ввод
# ---------------------------------------------------------------------------
def _parse_date(v):
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v.isoformat()
    try:
        return date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        raise ValueError("ожидается дата ГГГГ-ММ-ДД")


def prepare(kind: str, raw: dict) -> dict:
    """Оставить только известные поля, привести типы. Ошибки — ValidationFailed."""
    s = SPECS[kind]
    out: dict = {}
    errors: list[str] = []
    for f in s["fields"]:
        k, t, v = f["key"], f["type"], raw.get(f["key"])
        try:
            if t == "date":
                out[k] = _parse_date(v)
            elif t == "int":
                if v in (None, ""):
                    out[k] = None
                else:
                    n = int(v)
                    if n < 0 or n > 100000:
                        raise ValueError("число от 0 до 100000")
                    out[k] = n
            elif t == "bool":
                out[k] = bool(v)
            elif t == "enum":
                if v in (None, ""):
                    out[k] = None
                elif v not in f["options"]:
                    raise ValueError(f"недопустимое значение «{v}»")
                else:
                    out[k] = v
            else:
                text = (str(v).strip() if v is not None else "") or None
                limit = 5000 if t == "textarea" else 255
                if text and len(text) > limit:
                    raise ValueError(f"не длиннее {limit} символов")
                out[k] = text
        except (TypeError, ValueError) as exc:
            errors.append(f"{f['label']}: {exc}")
    for k, v in out.items():
        if k.endswith("_date") and v and v > today().isoformat():
            label = next(f["label"] for f in s["fields"] if f["key"] == k)
            errors.append(f"{label}: дата в будущем")
    if errors:
        raise ValidationFailed(errors)
    return out


# ---------------------------------------------------------------------------
# Оценка состояния
# ---------------------------------------------------------------------------
def _group_rank(g):
    return GROUP_ORDER.index(g) if g in GROUP_ORDER else -1


def evaluate(kind: str, office: Office, data: dict | None, ref: date | None = None) -> dict:
    ref = ref or today()
    s = SPECS[kind]
    alerts: list[dict] = []
    deadlines: list[dict] = []

    def alert(sev, text, due=None):
        alerts.append({"severity": sev, "text": text, "due": due, "kind": kind, "office_code": office.code})

    if not data:
        alert("warn", f"Нет данных по направлению «{s['title']}»")
        label, level = STATES["none"]
        return {"office_code": office.code, "office_name": office.name, "state": "none", "state_label": label,
                "level": level, "next_due": None, "alerts": alerts, "deadlines": [], "data": None, "updated_at": None}

    warn_days = config.DIRECTIONS_WARN_DAYS
    has_soon = False
    for c in s["checks"]:
        when: Callable | None = c.get("when")
        if when and not when(data):
            continue
        v = data.get(c["field"])
        t = c["type"]
        if t in ("every", "due"):
            if not v:
                alert(c.get("missing", "warn"), f"{c['label']}: дата не указана")
                continue
            d = date.fromisoformat(v)
            if t == "every":
                months = c["months"](data) if callable(c["months"]) else c["months"]
                nxt = add_months(d, months)
            else:
                nxt = d
            left = (nxt - ref).days
            deadlines.append({"label": c["label"], "date": nxt.isoformat(), "days_left": left})
            if left < 0:
                alert("bad", f"{c['label']}: просрочено с {nxt:%d.%m.%Y}", nxt.isoformat())
            elif left <= c.get("warn_days", warn_days):
                has_soon = True
                alert("warn", f"{c['label']}: до {nxt:%d.%m.%Y}", nxt.isoformat())
        elif t == "flag":
            ok = c["test"](v) if "test" in c else bool(v)
            if not ok:
                alert(c.get("severity", "warn"), c["text"])
        elif t == "filled":
            if not v:
                alert(c.get("severity", "warn"), c["text"])
        elif t == "count":
            if v:
                alert(c.get("severity", "warn"), f"{c['text']}: {v}")
        elif t == "min_group":
            if v and _group_rank(v) < _group_rank(c["min"]):
                alert("bad", c["text"])

    deadlines.sort(key=lambda x: x["date"])
    upcoming = [x for x in deadlines if x["days_left"] >= 0]
    if any(a["severity"] == "bad" for a in alerts):
        state = "overdue"
    elif has_soon:
        state = "soon"
    elif alerts:
        state = "attention"
    else:
        state = "ok"
    label, level = STATES[state]
    return {
        "office_code": office.code, "office_name": office.name,
        "state": state, "state_label": label, "level": level,
        "next_due": upcoming[0] if upcoming else (deadlines[0] if deadlines else None),
        "alerts": alerts, "deadlines": deadlines, "data": data, "updated_at": None,
    }


def _rows(db: Session, kind: str, offices: list[Office]) -> dict[int, OfficeDirection]:
    if not offices:
        return {}
    q = select(OfficeDirection).where(OfficeDirection.kind == kind,
                                      OfficeDirection.office_id.in_([o.id for o in offices]))
    return {r.office_id: r for r in db.scalars(q)}


def office_state(db: Session, kind: str, office: Office) -> dict:
    row = _rows(db, kind, [office]).get(office.id)
    st = evaluate(kind, office, row.data if row else None)
    st["updated_at"] = row.updated_at.isoformat() if row and row.updated_at else None
    return st


def summary(db: Session, kind: str, office_ids=None) -> list[dict]:
    offices = db.scalars(offices_query(office_ids)).all()
    rows = _rows(db, kind, offices)
    out = []
    for o in offices:
        row = rows.get(o.id)
        st = evaluate(kind, o, row.data if row else None)
        st["updated_at"] = row.updated_at.isoformat() if row and row.updated_at else None
        out.append(st)
    return out


def save(db: Session, kind: str, office: Office, raw: dict) -> dict:
    data = prepare(kind, raw)
    row = _rows(db, kind, [office]).get(office.id)
    if row is None:
        row = OfficeDirection(office_id=office.id, kind=kind, data=data)
        db.add(row)
    else:
        row.data = data
    db.commit()
    return office_state(db, kind, office)


def dashboard_block(db: Session, office_ids=None) -> dict:
    """Сводка для дашборда: по каждому направлению счётчики состояний и состояние каждого офиса."""
    out = {}
    all_alerts = []
    for kind in KINDS:
        items = summary(db, kind, office_ids)
        counts = {k: 0 for k in STATES}
        for it in items:
            counts[it["state"]] += 1
        all_alerts += [a for it in items for a in it["alerts"]]
        out[kind] = {
            "title": SPECS[kind]["title"], "short": SPECS[kind]["short"],
            "counts": counts,
            "by_office": {it["office_code"]: {
                "state": it["state"], "state_label": it["state_label"], "level": it["level"],
                "next_due": (it["next_due"] or {}).get("date"),
                "alerts": len(it["alerts"]),
            } for it in items},
        }
    return {"directions": out, "alerts": all_alerts}
