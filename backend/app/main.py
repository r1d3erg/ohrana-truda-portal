"""HTTP API модуля «Охрана труда». Все маршруты — под префиксом /api.

Интерактивная документация: /api/docs (Swagger UI).
"""
from contextlib import asynccontextmanager
from datetime import date

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, config, directions, registers, services
from .auth import current_user, ensure_office_access, ensure_office_visible, require_admin, require_editor, visible_office_ids
from .models import Office, RiskAssessment, SoutAssessment, User
from .db import SessionLocal, get_db, init_db
from .parser import OFFICE_CODE_RE, normalize_office_code, STATUS_LABELS, ChecklistParseError

ALLOWED_EXTENSIONS = (".xlsx", ".xlsm")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        auth.bootstrap_admin(db)
    yield


app = FastAPI(
    title="Охрана труда — API",
    version="0.2.0",
    docs_url="/api/docs" if config.API_DOCS else None,
    openapi_url="/api/openapi.json" if config.API_DOCS else None,
    redoc_url=None,
    lifespan=lifespan,
)

if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Requested-With"],
        allow_credentials=True,
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api"):
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response

api = APIRouter(prefix="/api")


def _not_found(exc: services.NotFound):
    raise HTTPException(status_code=404, detail={"message": str(exc)})


def _office_for(db: Session, code: str, user: User) -> Office:
    """Офис по номеру с проверкой, что пользователь его видит (ответственный — только свои)."""
    try:
        office = services.get_office(db, code)
    except services.NotFound as exc:
        _not_found(exc)
    ensure_office_visible(user, office)
    return office


# --- Служебное --------------------------------------------------------------
@api.get("/health", tags=["service"])
def health():
    return {"status": "ok"}


@api.get("/config", tags=["service"])
def get_config():
    """Подписи статусов и пороги — чтобы фронтенд не дублировал эти правила."""
    return {**services.public_config(), **registers.public_dictionaries()}



# --- Вход и пользователи (auth.py, docs/auth.md) --------------------------------------
class LoginIn(BaseModel):
    login: str = Field(..., max_length=64)
    password: str = Field(..., max_length=128)


class PasswordIn(BaseModel):
    current_password: str = Field(..., max_length=128)
    new_password: str = Field(..., max_length=128)


@api.post("/auth/login", tags=["auth"], summary="Вход по логину и паролю")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth.check_csrf(request)
    login_ = auth.normalize_login(body.login)
    ip = auth.client_ip(request)
    keys = (f"ip:{ip}", f"login:{login_}")
    if auth.throttle.blocked(*keys):
        raise HTTPException(status_code=429, detail={
            "message": f"Слишком много неудачных попыток. Попробуйте через {config.LOGIN_WINDOW_MIN} мин."})
    user = db.scalar(select(User).where(User.login == login_))
    ok = auth.verify_password(body.password, user.password_hash if user else auth._DUMMY_HASH)
    if not user or not ok or not user.is_active:
        auth.throttle.fail(*keys)
        auth.log.warning("Неудачный вход: login=%s ip=%s", user.login if user else "<неизвестный>", ip)
        raise HTTPException(status_code=401, detail={"message": "Неверный логин или пароль"})
    auth.throttle.reset(*keys)
    token = auth.create_session(db, user, request)
    auth.set_cookie(response, token)
    auth.log.info("Вход: %s ip=%s", user.login, ip)
    return auth.user_to_dict(user)


@api.post("/auth/logout", tags=["auth"], summary="Выход")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth.check_csrf(request)
    token = request.cookies.get(auth.COOKIE)
    if token:
        db.query(auth.AuthSession).filter(auth.AuthSession.token_hash == auth._token_hash(token)).delete()
        db.commit()
    auth.clear_cookie(response)
    return {"ok": True}


@api.get("/auth/me", tags=["auth"], summary="Текущий пользователь")
def me(user: User = Depends(current_user)):
    return auth.user_to_dict(user)


@api.post("/auth/password", tags=["auth"], summary="Сменить свой пароль")
def change_password(body: PasswordIn, request: Request, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    if not auth.verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=422, detail={"message": "Текущий пароль указан неверно", "errors": []})
    errs = auth.password_problems(body.new_password, user.login)
    if body.new_password == body.current_password:
        errs.append("Новый пароль должен отличаться от текущего")
    if errs:
        raise HTTPException(status_code=422, detail={"message": "Пароль не подходит", "errors": errs})
    user.password_hash = auth.hash_password(body.new_password)
    user.must_change_password = False
    if user.role == "admin":
        auth.remove_initial_password_file()
    # Остальные сессии пользователя закрываются, текущая остаётся
    auth.revoke_user_sessions(db, user.id, keep_hash=getattr(request.state, "session_hash", None))
    db.commit()
    return auth.user_to_dict(user)


class UserCreate(BaseModel):
    login: str = Field(..., max_length=64)
    full_name: str = Field("", max_length=255)
    role: str
    password: str = Field(..., max_length=128, description="Временный пароль: при первом входе его нужно сменить")
    offices: list[str] = Field(default_factory=list, max_length=500)


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, max_length=255)
    role: str | None = None
    is_active: bool | None = None
    offices: list[str] | None = Field(None, max_length=500)
    password: str | None = Field(None, max_length=128, description="Новый временный пароль (сброс)")


def _resolve_offices(db: Session, codes: list[str]) -> list[Office]:
    out, missing = [], []
    for c in dict.fromkeys(codes):
        o = db.scalar(select(Office).where(Office.code == c))
        (out if o else missing).append(o or c)
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Офисы не найдены", "errors": missing})
    return out


def _check_role(role: str):
    if role not in auth.ROLES:
        raise HTTPException(status_code=422, detail={"message": f"Неизвестная роль «{role}»", "errors": []})


@api.get("/users", tags=["users"], summary="Пользователи (только служба ОТ)")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [auth.user_to_dict(u) for u in db.scalars(select(User).order_by(User.login))]


@api.get("/roles", tags=["users"], summary="Роли и их описание")
def list_roles(_: User = Depends(current_user)):
    return auth.ROLES


@api.post("/users", tags=["users"], status_code=201, summary="Создать пользователя")
def create_user(body: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    login_ = auth.normalize_login(body.login)
    _check_role(body.role)
    errs = auth.login_problems(login_) + auth.password_problems(body.password, login_)
    if errs:
        raise HTTPException(status_code=422, detail={"message": "Проверьте данные пользователя", "errors": errs})
    if db.scalar(select(User.id).where(User.login == login_)):
        raise HTTPException(status_code=409, detail={"message": f"Логин «{login_}» уже занят"})
    user = User(login=login_, full_name=body.full_name.strip(), role=body.role,
                password_hash=auth.hash_password(body.password), must_change_password=True)
    user.offices = _resolve_offices(db, body.offices) if body.role == "responsible" else []
    db.add(user)
    db.commit()
    auth.log.info("Пользователь %s создан администратором %s", user.login, admin.login)
    return auth.user_to_dict(user)


@api.patch("/users/{user_id}", tags=["users"], summary="Изменить пользователя: роль, офисы, блокировка, сброс пароля")
def update_user(user_id: int, body: UserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail={"message": "Пользователь не найден"})
    fields = body.model_fields_set
    if user.id == admin.id and (("role" in fields and body.role != "admin") or ("is_active" in fields and not body.is_active)):
        raise HTTPException(status_code=422, detail={"message": "Нельзя снять с себя роль администратора или отключить себя", "errors": []})
    if "full_name" in fields and body.full_name is not None:
        user.full_name = body.full_name.strip()
    if "role" in fields and body.role:
        _check_role(body.role)
        user.role = body.role
    if "offices" in fields and body.offices is not None:
        user.offices = _resolve_offices(db, body.offices)
    if user.role != "responsible":
        user.offices = []
    if "is_active" in fields and body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            auth.revoke_user_sessions(db, user.id)
    if "password" in fields and body.password:
        errs = auth.password_problems(body.password, user.login)
        if errs:
            raise HTTPException(status_code=422, detail={"message": "Пароль не подходит", "errors": errs})
        user.password_hash = auth.hash_password(body.password)
        user.must_change_password = True
        auth.revoke_user_sessions(db, user.id)
    db.commit()
    auth.log.info("Пользователь %s изменён администратором %s: %s", user.login, admin.login, sorted(fields - {"password"}))
    return auth.user_to_dict(user)


# --- Загрузка сводной таблицы ----------------------------------------------
@api.post("/imports", tags=["imports"], summary="Загрузить сводную таблицу (чек-лист) офиса")
async def upload_checklist(
    file: UploadFile = File(..., description="Файл .xlsx с листом «Чек-лист документов»"),
    dry_run: bool = Query(False, description="Только проверить и показать результат, ничего не сохраняя"),
    user: User = Depends(require_editor),
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
        return services.import_checklist(db, data, name, dry_run=dry_run,
                                         authorize=lambda office: _authorize_upload(user, office))
    except ChecklistParseError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail={
            "message": "Файл не прошёл проверку — исправьте ошибки и загрузите снова",
            "errors": exc.errors,
        })


def _authorize_upload(user: User, office: Office | None) -> None:
    """Ответственный загружает таблицы только своих офисов; новый офис создаёт только служба ОТ."""
    if office is None:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail={
                "message": "Офиса из таблицы нет в портале. Создать новый офис может только служба охраны труда"})
        return
    ensure_office_access(user, office)


@api.get("/imports/{import_id}", tags=["imports"], summary="Загрузка: шапка, сводка и все позиции")
def get_import(import_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        imp = services.get_import(db, import_id)
    except services.NotFound as exc:
        _not_found(exc)
    ensure_office_visible(user, imp.office)
    items = list(imp.items)
    return {
        "import": services.import_to_dict(imp),
        "is_current": imp.office.current_import_id == imp.id,
        "by_category": services.category_summary(items),
        "items": [services.item_to_dict(i) for i in items],
    }


@api.delete("/imports/{import_id}", tags=["imports"], summary="Удалить ошибочную загрузку")
def delete_import(import_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
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
def list_offices(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return services.list_offices(db, visible_office_ids(user))


@api.post("/offices", tags=["offices"], status_code=201, summary="Создать офис вручную")
def create_office(body: OfficeCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    code = normalize_office_code(body.code) or ""
    if not OFFICE_CODE_RE.match(code):
        raise HTTPException(status_code=422, detail={"message": "Недопустимый номер офиса", "errors": []})
    try:
        office = services.create_office(db, code, body.name, body.responsible)
    except services.Conflict as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc)})
    return services.office_to_dict(office, None)


@api.get("/offices/{code:path}/checklist", tags=["offices"], summary="Документы офиса из актуальной загрузки")
def get_office_checklist(
    code: str,
    status: str | None = Query(None, description="done / in_progress / missing / not_set"),
    category: str | None = Query(None, description="Раздел, напр. «Пожарная безопасность»"),
    q: str | None = Query(None, description="Поиск по наименованию"),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    office = _office_for(db, code, user)
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


@api.get("/offices/{code:path}/imports", tags=["offices"], summary="История загрузок офиса")
def get_office_imports(code: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    office = _office_for(db, code, user)
    return services.office_imports(db, office)


# --- Дашборд ----------------------------------------------------------------
@api.get("/dashboard", tags=["dashboard"], summary="Сводные показатели по всем офисам")
def get_dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ids = visible_office_ids(user)  # ответственный — только свои офисы
    dirs = directions.dashboard_block(db, ids)
    reg = registers.dashboard_block(db, extra_alerts=dirs["alerts"], office_ids=ids)
    reg["directions"] = dirs["directions"]
    return {**services.dashboard(db, ids), "registers": reg}


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
    def list_summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
        return summary_fn(db, visible_office_ids(user))

    @api.get(f"/offices/{{code:path}}/{prefix}", tags=[prefix], operation_id=f"{prefix}_office", summary=f"{title}: история и состояние офиса")
    def office_records(code: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
        office = _office_for(db, code, user)
        records = list(db.scalars(select(model).where(model.office_id == office.id)))
        state = state_fn(office, records)
        ordered = sorted(records, key=lambda r: r.id, reverse=True)
        return {**state, "records": [to_dict(r) for r in ordered]}

    @api.post(f"/offices/{{code:path}}/{prefix}", tags=[prefix], operation_id=f"{prefix}_create", status_code=201, summary=f"{title}: добавить запись")
    def create_record(code: str, body: body_cls, user: User = Depends(require_editor),  # type: ignore[valid-type]
                      db: Session = Depends(get_db)):
        try:
            office = services.get_office(db, code)
            ensure_office_access(user, office)
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
    def update_record(record_id: int, body: body_cls, user: User = Depends(require_editor),  # type: ignore[valid-type]
                      db: Session = Depends(get_db)):
        rec = db.get(model, record_id)
        if rec is None:
            raise HTTPException(status_code=404, detail={"message": f"Запись #{record_id} не найдена"})
        ensure_office_access(user, rec.office)
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
    def delete_record(record_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
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


# --- Пожарная безопасность, электробезопасность, ГО и ЧС ---------------------
def _kind(kind: str) -> str:
    if kind not in directions.SPECS:
        raise HTTPException(status_code=404, detail={"message": f"Неизвестное направление «{kind}»"})
    return kind


@api.get("/directions", tags=["directions"], summary="Список направлений с ручным вводом")
def directions_list(_: User = Depends(current_user)):
    return [directions.spec(k) for k in directions.KINDS]


@api.get("/directions/{kind}/spec", tags=["directions"], summary="Поля формы направления")
def direction_spec(kind: str, _: User = Depends(current_user)):
    return directions.spec(_kind(kind))


@api.get("/directions/{kind}", tags=["directions"], summary="Состояние направления по всем офисам")
def direction_summary(kind: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return directions.summary(db, _kind(kind), visible_office_ids(user))


@api.get("/offices/{code:path}/directions/{kind}", tags=["directions"], summary="Карточка офиса по направлению")
def direction_office(code: str, kind: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _kind(kind)
    office = _office_for(db, code, user)
    return directions.office_state(db, kind, office)


@api.put("/offices/{code:path}/directions/{kind}", tags=["directions"], summary="Сохранить карточку офиса по направлению")
def direction_save(code: str, kind: str, body: dict, user: User = Depends(require_editor),
                   db: Session = Depends(get_db)):
    _kind(kind)
    try:
        office = services.get_office(db, code)
        ensure_office_access(user, office)
        return directions.save(db, kind, office, body)
    except services.NotFound as exc:
        _not_found(exc)
    except registers.ValidationFailed as exc:
        _validation_error(exc)


# Карточка офиса — последней: «{code:path}» иначе перехватит /offices/<код>/checklist и т.п.
@api.patch("/offices/{code:path}", tags=["offices"], summary="Переименовать офис / назначить ответственного")
def update_office(code: str, body: OfficeUpdate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        office = services.update_office(db, code, body.name, body.responsible, body.model_fields_set)
    except services.NotFound as exc:
        _not_found(exc)
    return services.office_to_dict(office, services.current_import(db, office))


@api.get("/offices/{code:path}", tags=["offices"], summary="Карточка офиса: индекс и сводка по разделам")
def get_office(code: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    office = _office_for(db, code, user)
    imp = services.current_import(db, office)
    return {
        **services.office_to_dict(office, imp),
        "current_import": services.import_to_dict(imp) if imp else None,
        "by_category": services.category_summary(list(imp.items)) if imp else [],
    }


app.include_router(api)
