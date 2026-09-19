from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.approval import Approval
    from app.db.models.certificate import Certificate


class SanitizationJob(Base):
    __tablename__ = "sanitization_jobs"
    __table_args__ = (
        Index("ix_sanitization_jobs_target", "target_id"),
        Index("ix_sanitization_jobs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"))
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, default="file")
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id", ondelete="SET NULL"))
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[str | None] = mapped_column(String(255))
    method: Mapped[str] = mapped_column(String(64), nullable=False, default="overwrite_then_delete")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    approval: Mapped["Approval | None"] = relationship(back_populates="sanitization_jobs")
    certificates: Mapped[list["Certificate"]] = relationship(back_populates="sanitization_job")
