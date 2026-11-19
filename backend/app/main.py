"""HTTP API модуля «Охрана труда». Все маршруты — под префиксом /api.

Интерактивная документация: /api/docs (Swagger UI).
"""
from contextlib import asynccontextmanager
from datetime import date

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config, registers, services
from .models import RiskAssessment, SoutAssessment
from .db import get_db, init_db
from .parser import OFFICE_CODE_RE, STATUS_LABELS, ChecklistParseError

ALLOWED_EXTENSIONS = (".xlsx", ".xlsm")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Охрана труда — API",
    version="0.2.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
    lifespan=lifespan,
)

if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

api = APIRouter(prefix="/api")


def _not_found(exc: services.NotFound):
    raise HTTPException(status_code=404, detail={"message": str(exc)})


# --- Служебное --------------------------------------------------------------
@api.get("/health", tags=["service"])
def health():
    return {"status": "ok"}


@api.get("/config", tags=["service"])
def get_config():
    """Подписи статусов и пороги — чтобы фронтенд не дублировал эти правила."""
    return {**services.public_config(), **registers.public_dictionaries()}


# --- Загрузка сводной таблицы ----------------------------------------------
@api.post("/imports", tags=["imports"], summary="Загрузить сводную таблицу (чек-лист) офиса")
async def upload_checklist(
    file: UploadFile = File(..., description="Файл .xlsx с листом «Чек-лист документов»"),
    dry_run: bool = Query(False, description="Только проверить и показать результат, ничего не сохраняя"),
    db: Session = Depends(get_db),
):
    name = (file.filename or "").strip()
    if not name.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=415, detail={
            "message": "Нужен файл Excel в формате .xlsx",
            "errors": [f"Файл «{name or 'без имени'}» имеет неподдерживаемое расширение"],
        })

    limit = config.MAX_UPLOAD_MB * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail={
            "message": f"Файл больше {config.MAX_UPLOAD_MB} МБ",
            "errors": [],
        })
    if not data:
        raise HTTPException(status_code=422, detail={"message": "Пустой файл", "errors": []})

    try:
        return services.import_checklist(db, data, name, dry_run=dry_run)
    except ChecklistParseError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail={
            "message": "Файл не прошёл проверку — исправьте ошибки и загрузите снова",
            "errors": exc.errors,
        })


@api.get("/imports/{import_id}", tags=["imports"], summary="Загрузка: шапка, сводка и все позиции")
def get_import(import_id: int, db: Session = Depends(get_db)):
    try:
        imp = services.get_import(db, import_id)
    except services.NotFound as exc:
        _not_found(exc)
    items = list(imp.items)
    return {
        "import": services.import_to_dict(imp),
        "is_current": imp.office.current_import_id == imp.id,
        "by_category": services.category_summary(items),
        "items": [services.item_to_dict(i) for i in items],
    }


@api.delete("/imports/{import_id}", tags=["imports"], summary="Удалить ошибочную загрузку")
def delete_import(import_id: int, db: Session = Depends(get_db)):
    try:
        office = services.delete_import(db, import_id)
    except services.NotFound as exc:
        _not_found(exc)
    return {"deleted": import_id, "office": services.office_to_dict(office, services.current_import(db, office))}


# --- Офисы ------------------------------------------------------------------
class OfficeCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=64, description="Номер офиса, как в шапке таблицы (напр. cy1)")
    name: str | None = Field(None, max_length=255)
    responsible: str | None = Field(None, max_length=255)


class OfficeUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    responsible: str | None = Field(None, max_length=255)


@api.get("/offices", tags=["offices"], summary="Список офисов с индексом соответствия")
def list_offices(db: Session = Depends(get_db)):
    return services.list_offices(db)


@api.post("/offices", tags=["offices"], status_code=201, summary="Создать офис вручную")
def create_office(body: OfficeCreate, db: Session = Depends(get_db)):
    code = body.code.strip()
    if not OFFICE_CODE_RE.match(code):
        raise HTTPException(status_code=422, detail={"message": "Недопустимый номер офиса", "errors": []})
    try:
        office = services.create_office(db, code, body.name, body.responsible)
    except services.Conflict as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc)})
    return services.office_to_dict(office, None)


@api.patch("/offices/{code}", tags=["offices"], summary="Переименовать офис / назначить ответственного")
def update_office(code: str, body: OfficeUpdate, db: Session = Depends(get_db)):
    try:
        office = services.update_office(db, code, body.name, body.responsible, body.model_fields_set)
    except services.NotFound as exc:
        _not_found(exc)
    return services.office_to_dict(office, services.current_import(db, office))


@api.get("/offices/{code}", tags=["offices"], summary="Карточка офиса: индекс и сводка по разделам")
def get_office(code: str, db: Session = Depends(get_db)):
    try:
        office = services.get_office(db, code)
    except services.NotFound as exc:
        _not_found(exc)
    imp = services.current_import(db, office)
    return {
        **services.office_to_dict(office, imp),
        "current_import": services.import_to_dict(imp) if imp else None,
        "by_category": services.category_summary(list(imp.items)) if imp else [],
    }


@api.get("/offices/{code}/checklist", tags=["offices"], summary="Документы офиса из актуальной загрузки")
def get_office_checklist(
    code: str,
    status: str | None = Query(None, description="done / in_progress / missing / not_set"),
    category: str | None = Query(None, description="Раздел, напр. «Пожарная безопасность»"),
    q: str | None = Query(None, description="Поиск по наименованию"),
    db: Session = Depends(get_db),
):
    try:
        office = services.get_office(db, code)
    except services.NotFound as exc:
        _not_found(exc)
    if status and status not in STATUS_LABELS:
        raise HTTPException(status_code=422, detail={"message": f"Неизвестный статус «{status}»"})
    imp = services.current_import(db, office)
    if imp is None:
        return {"office_code": office.code, "import": None, "items": []}
    items = list(imp.items)
    if status:
        items = [i for i in items if i.status == status]
    if category:
        items = [i for i in items if i.category == category]
    if q:
        needle = q.strip().lower()
        items = [i for i in items if needle in i.title.lower()]
    return {
        "office_code": office.code,
        "import": services.import_to_dict(imp),
        "items": [services.item_to_dict(i) for i in items],
    }


@api.get("/offices/{code}/imports", tags=["offices"], summary="История загрузок офиса")
def get_office_imports(code: str, db: Session = Depends(get_db)):
    try:
        office = services.get_office(db, code)
    except services.NotFound as exc:
        _not_found(exc)
    return services.office_imports(db, office)


# --- Дашборд ----------------------------------------------------------------
@api.get("/dashboard", tags=["dashboard"], summary="Сводные показатели по всем офисам")
def get_dashboard(db: Session = Depends(get_db)):
    return {**services.dashboard(db), "registers": registers.dashboard_block(db)}


# --- СОУТ и ОПР: ручной ввод -----------------------------------------------
def Count():  # noqa: N802 — новое поле на каждый атрибут
    return Field(None, ge=0, le=1_000_000)


class SoutIn(BaseModel):
    kind: str | None = Field(None, description="planned / unplanned")
    procedure: str | None = Field(None, description="regular / simplified")
    status: str | None = Field(None, description="planned / in_progress / completed")
    reason: str | None = None
    reason_date: date | None = None
    due_date: date | None = None
    contractor: str | None = Field(None, max_length=255)
    contractor_reg_number: str | None = Field(None, max_length=64)
    commission_order: str | None = Field(None, max_length=255)
    start_date: date | None = None
    report_date: date | None = None
    fgis_date: date | None = None
    valid_until: date | None = None
    workplaces_total: int | None = Count()
    workplaces_assessed: int | None = Count()
    analogous_workplaces: int | None = Count()
    employees_covered: int | None = Count()
    class_1: int | None = Count()
    class_2: int | None = Count()
    class_3_1: int | None = Count()
    class_3_2: int | None = Count()
    class_3_3: int | None = Count()
    class_3_4: int | None = Count()
    class_4: int | None = Count()
    declaration_submitted: bool = False
    declaration_date: date | None = None
    declaration_number: str | None = Field(None, max_length=64)
    declaration_terminated: bool = False
    familiarized_date: date | None = None
    employees_familiarized: int | None = Count()
    published_date: date | None = None
    measures_planned: int | None = Count()
    measures_done: int | None = Count()
    notes: str | None = Field(None, max_length=5000)


class OprIn(BaseModel):
    kind: str | None = Field(None, description="initial / periodic / unplanned")
    status: str | None = None
    reason: str | None = Field(None, max_length=255)
    performed_by: str | None = Field(None, description="self / contractor")
    contractor: str | None = Field(None, max_length=255)
    method: str | None = None
    commission_order: str | None = Field(None, max_length=255)
    assessment_date: date | None = None
    next_review_date: date | None = None
    workplaces_total: int | None = Count()
    workplaces_assessed: int | None = Count()
    professions_assessed: int | None = Count()
    hazards_identified: int | None = Count()
    risks_low: int | None = Count()
    risks_medium: int | None = Count()
    risks_high: int | None = Count()
    plan_approved_date: date | None = None
    measures_planned: int | None = Count()
    measures_done: int | None = Count()
    employees_informed_date: date | None = None
    notes: str | None = Field(None, max_length=5000)


def _clean(body: BaseModel) -> dict:
    data = body.model_dump()
    for k, v in data.items():
        if isinstance(v, str):
            data[k] = v.strip() or None
    return data


def _validation_error(exc: registers.ValidationFailed):
    raise HTTPException(status_code=422, detail={"message": "Проверьте заполнение формы", "errors": exc.errors})


def _register_routes(prefix: str, model, prepare, to_dict, summary_fn, state_fn, body_cls, title: str):
    @api.get(f"/{prefix}", tags=[prefix], operation_id=f"{prefix}_list", summary=f"{title}: состояние по всем офисам")
    def list_summary(db: Session = Depends(get_db)):
        return summary_fn(db)

    @api.get(f"/offices/{{code}}/{prefix}", tags=[prefix], operation_id=f"{prefix}_office", summary=f"{title}: история и состояние офиса")
    def office_records(code: str, db: Session = Depends(get_db)):
        try:
            office = services.get_office(db, code)
        except services.NotFound as exc:
            _not_found(exc)
        records = list(db.scalars(select(model).where(model.office_id == office.id)))
        state = state_fn(office, records)
        ordered = sorted(records, key=lambda r: r.id, reverse=True)
        return {**state, "records": [to_dict(r) for r in ordered]}

    @api.post(f"/offices/{{code}}/{prefix}", tags=[prefix], operation_id=f"{prefix}_create", status_code=201, summary=f"{title}: добавить запись")
    def create_record(code: str, body: body_cls, db: Session = Depends(get_db)):  # type: ignore[valid-type]
        try:
            office = services.get_office(db, code)
            data = prepare(_clean(body))
        except services.NotFound as exc:
            _not_found(exc)
        except registers.ValidationFailed as exc:
            _validation_error(exc)
        rec = model(office_id=office.id, **data)
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return to_dict(rec)

    @api.put(f"/{prefix}/{{record_id}}", tags=[prefix], operation_id=f"{prefix}_update", summary=f"{title}: изменить запись")
    def update_record(record_id: int, body: body_cls, db: Session = Depends(get_db)):  # type: ignore[valid-type]
        rec = db.get(model, record_id)
        if rec is None:
            raise HTTPException(status_code=404, detail={"message": f"Запись #{record_id} не найдена"})
        try:
            data = prepare(_clean(body))
        except registers.ValidationFailed as exc:
            _validation_error(exc)
        for k, v in data.items():
            setattr(rec, k, v)
        db.commit()
        db.refresh(rec)
        return to_dict(rec)

    @api.delete(f"/{prefix}/{{record_id}}", tags=[prefix], operation_id=f"{prefix}_delete", summary=f"{title}: удалить запись")
    def delete_record(record_id: int, db: Session = Depends(get_db)):
        rec = db.get(model, record_id)
        if rec is None:
            raise HTTPException(status_code=404, detail={"message": f"Запись #{record_id} не найдена"})
        db.delete(rec)
        db.commit()
        return {"deleted": record_id}


_register_routes("sout", SoutAssessment, registers.prepare_sout, registers.sout_to_dict,
                 registers.sout_summary, registers.sout_office_state, SoutIn, "СОУТ")
_register_routes("opr", RiskAssessment, registers.prepare_opr, registers.opr_to_dict,
                 registers.opr_summary, registers.opr_office_state, OprIn, "ОПР")


app.include_router(api)
