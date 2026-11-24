"""Модель данных.

offices            — офисы (ключ — номер офиса из шапки таблицы, напр. «cy1»)
checklist_imports  — каждая загрузка сводной таблицы (снимок на дату проверки)
checklist_items    — позиции чек-листа конкретной загрузки
users, user_offices, auth_sessions — пользователи, их офисы и сессии входа (auth.py)

Офис ссылается на актуальную загрузку через current_import_id — именно из неё
портал берёт индекс соответствия, статус и список документов.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint,
)
from sqlalchemy import select
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Office(Base):
    __tablename__ = "offices"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    responsible: Mapped[str | None] = mapped_column(String(255))
    # Без внешнего ключа, чтобы не было циклической зависимости таблиц;
    # целостность поддерживает services.refresh_current_import()
    current_import_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    imports: Mapped[list[ChecklistImport]] = relationship(
        back_populates="office", cascade="all, delete-orphan", passive_deletes=True
    )


class ChecklistImport(Base):
    __tablename__ = "checklist_imports"
    __table_args__ = (UniqueConstraint("office_id", "file_sha256", name="uq_import_office_file"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    filename: Mapped[str | None] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    sheet_name: Mapped[str | None] = mapped_column(String(255))

    # Шапка таблицы
    check_date: Mapped[date | None] = mapped_column(Date)
    inspector: Mapped[str | None] = mapped_column(String(255))
    reddy_number: Mapped[str | None] = mapped_column(String(64))
    organization: Mapped[str | None] = mapped_column(String(255))
    headcount: Mapped[int | None] = mapped_column(Integer)
    msp_status: Mapped[str | None] = mapped_column(String(64))

    # Итоги (денормализованы, чтобы список офисов и дашборд не пересчитывали позиции)
    total: Mapped[int] = mapped_column(Integer, default=0)
    done: Mapped[int] = mapped_column(Integer, default=0)
    in_progress: Mapped[int] = mapped_column(Integer, default=0)
    missing: Mapped[int] = mapped_column(Integer, default=0)
    not_set: Mapped[int] = mapped_column(Integer, default=0)
    readiness: Mapped[float] = mapped_column(Float, default=0.0)

    warnings: Mapped[str | None] = mapped_column(Text)  # JSON-массив строк

    office: Mapped[Office] = relationship(back_populates="imports")
    items: Mapped[list[ChecklistItem]] = relationship(
        back_populates="import_", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ChecklistItem.number",
    )


class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("checklist_imports.id", ondelete="CASCADE"), index=True)
    row: Mapped[int] = mapped_column(Integer)
    number: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(255), index=True)
    group_name: Mapped[str | None] = mapped_column(String(255))
    subgroup: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    responsible: Mapped[str | None] = mapped_column(String(255))
    item_date: Mapped[date | None] = mapped_column(Date)
    item_date_raw: Mapped[str | None] = mapped_column(String(64))

    import_: Mapped[ChecklistImport] = relationship(back_populates="items")


# ---------------------------------------------------------------------------
# Ручной ввод: СОУТ и ОПР (подробно — docs/sout-opr.md)
# ---------------------------------------------------------------------------
class SoutAssessment(Base):
    """Специальная оценка условий труда (426-ФЗ) по офису. Одна запись — одна СОУТ
    (плановая, внеплановая или в упрощённом порядке); записи образуют историю."""
    __tablename__ = "sout_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    kind: Mapped[str] = mapped_column(String(16), default="planned")        # planned / unplanned
    procedure: Mapped[str] = mapped_column(String(16), default="regular")   # regular / simplified
    status: Mapped[str] = mapped_column(String(16), default="completed")    # planned / in_progress / completed
    reason: Mapped[str | None] = mapped_column(String(32))                  # основание внеплановой
    reason_date: Mapped[date | None] = mapped_column(Date)                  # дата наступления основания
    due_date: Mapped[date | None] = mapped_column(Date)                     # срок проведения

    contractor: Mapped[str | None] = mapped_column(String(255))             # организация-оценщик
    contractor_reg_number: Mapped[str | None] = mapped_column(String(64))   # № в реестре
    commission_order: Mapped[str | None] = mapped_column(String(255))       # приказ о комиссии (№, дата)
    start_date: Mapped[date | None] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)                  # утверждение отчёта
    fgis_date: Mapped[date | None] = mapped_column(Date)                    # внесение в ФГИС СОУТ
    valid_until: Mapped[date | None] = mapped_column(Date)                  # окончание срока действия

    workplaces_total: Mapped[int | None] = mapped_column(Integer)
    workplaces_assessed: Mapped[int | None] = mapped_column(Integer)
    analogous_workplaces: Mapped[int | None] = mapped_column(Integer)
    employees_covered: Mapped[int | None] = mapped_column(Integer)

    class_1: Mapped[int] = mapped_column(Integer, default=0)
    class_2: Mapped[int] = mapped_column(Integer, default=0)
    class_3_1: Mapped[int] = mapped_column(Integer, default=0)
    class_3_2: Mapped[int] = mapped_column(Integer, default=0)
    class_3_3: Mapped[int] = mapped_column(Integer, default=0)
    class_3_4: Mapped[int] = mapped_column(Integer, default=0)
    class_4: Mapped[int] = mapped_column(Integer, default=0)

    declaration_submitted: Mapped[bool] = mapped_column(default=False)
    declaration_date: Mapped[date | None] = mapped_column(Date)
    declaration_number: Mapped[str | None] = mapped_column(String(64))
    declaration_terminated: Mapped[bool] = mapped_column(default=False)     # наступили обстоятельства ч.5 ст.11

    familiarized_date: Mapped[date | None] = mapped_column(Date)            # ознакомление завершено
    employees_familiarized: Mapped[int | None] = mapped_column(Integer)
    published_date: Mapped[date | None] = mapped_column(Date)               # размещено на сайте
    measures_planned: Mapped[int | None] = mapped_column(Integer)           # мероприятия по улучшению УТ
    measures_done: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    office: Mapped[Office] = relationship()


class RiskAssessment(Base):
    """Оценка профессиональных рисков (ст. 214, 218 ТК РФ, приказ Минтруда № 776н) по офису."""
    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    kind: Mapped[str] = mapped_column(String(16), default="periodic")       # initial / periodic / unplanned
    status: Mapped[str] = mapped_column(String(16), default="completed")    # planned / in_progress / completed
    reason: Mapped[str | None] = mapped_column(String(255))                 # основание внеплановой
    performed_by: Mapped[str] = mapped_column(String(16), default="self")   # self / contractor
    contractor: Mapped[str | None] = mapped_column(String(255))
    method: Mapped[str | None] = mapped_column(String(64))
    commission_order: Mapped[str | None] = mapped_column(String(255))

    assessment_date: Mapped[date | None] = mapped_column(Date)              # утверждение результатов
    next_review_date: Mapped[date | None] = mapped_column(Date)             # плановый пересмотр

    workplaces_total: Mapped[int | None] = mapped_column(Integer)
    workplaces_assessed: Mapped[int | None] = mapped_column(Integer)
    professions_assessed: Mapped[int | None] = mapped_column(Integer)
    hazards_identified: Mapped[int | None] = mapped_column(Integer)
    risks_low: Mapped[int] = mapped_column(Integer, default=0)
    risks_medium: Mapped[int] = mapped_column(Integer, default=0)
    risks_high: Mapped[int] = mapped_column(Integer, default=0)

    plan_approved_date: Mapped[date | None] = mapped_column(Date)           # план мероприятий
    measures_planned: Mapped[int | None] = mapped_column(Integer)
    measures_done: Mapped[int | None] = mapped_column(Integer)
    employees_informed_date: Mapped[date | None] = mapped_column(Date)      # ознакомление с результатами
    notes: Mapped[str | None] = mapped_column(Text)

    office: Mapped[Office] = relationship()


class OfficeDirection(Base):
    """Карточка офиса по направлению (fire / electro / go): ручной ввод, поля — directions.SPECS."""
    __tablename__ = "office_directions"
    __table_args__ = (UniqueConstraint("office_id", "kind", name="uq_office_direction"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("offices.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    office: Mapped[Office] = relationship()


# --- Пользователи и сессии (auth.py) ------------------------------------------------
user_offices = Table(
    "user_offices", Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("office_id", ForeignKey("offices.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    role: Mapped[str] = mapped_column(String(16))  # admin / responsible / viewer
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    offices: Mapped[list[Office]] = relationship(secondary=user_offices, lazy="selectin")


class AuthSession(Base):
    """Сессия входа. В БД хранится только SHA-256 токена; сам токен — в HttpOnly-cookie."""
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")


def offices_query(office_ids=None):
    """Офисы по номеру; office_ids — ограничение области видимости (None — все офисы).

    Ответственный офиса видит только назначенные ему офисы (auth.visible_office_ids)."""
    q = select(Office).order_by(Office.code)
    if office_ids is not None:
        q = q.where(Office.id.in_(list(office_ids)))
    return q
