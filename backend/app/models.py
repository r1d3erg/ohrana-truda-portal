"""Модель данных.

offices            — офисы (ключ — номер офиса из шапки таблицы, напр. «cy1»)
checklist_imports  — каждая загрузка сводной таблицы (снимок на дату проверки)
checklist_items    — позиции чек-листа конкретной загрузки

Офис ссылается на актуальную загрузку через current_import_id — именно из неё
портал берёт индекс соответствия, статус и список документов.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
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
