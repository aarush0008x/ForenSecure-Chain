from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.activity_event import ActivityEvent
    from app.db.models.approval import Approval
    from app.db.models.device import Device
    from app.db.models.file import File
    from app.db.models.user import User


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        Index("ix_cases_case_number", "case_number", unique=True),
        Index("ix_cases_investigator_id", "investigator_id"),
        Index("ix_cases_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    case_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    investigator_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    investigator: Mapped["User | None"] = relationship(back_populates="cases")
    devices: Mapped[list["Device"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    files: Mapped[list["File"]] = relationship(back_populates="case")
    activity_events: Mapped[list["ActivityEvent"]] = relationship(back_populates="case", cascade="all, delete-orphan")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="case", cascade="all, delete-orphan")
