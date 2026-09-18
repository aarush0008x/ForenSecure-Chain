from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.audit_log import AuditLog
    from app.db.models.certificate import Certificate
    from app.db.models.file import File


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (
        Index("ix_operations_file_id", "file_id"),
        Index("ix_operations_status", "status"),
        Index("ix_operations_type", "operation_type"),
    )

    operation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    file_id: Mapped[str] = mapped_column(
        ForeignKey("files.file_id", ondelete="CASCADE"), nullable=False
    )
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    file: Mapped["File"] = relationship(back_populates="operations")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="operation")
    certificates: Mapped[list["Certificate"]] = relationship(back_populates="operation")
