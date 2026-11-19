"""HTTP API модуля «Охрана труда». Все маршруты — под префиксом /api.

Интерактивная документация: /api/docs (Swagger UI).
"""
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import config, services
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
    return services.public_config()


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
    return services.dashboard(db)


app.include_router(api)
