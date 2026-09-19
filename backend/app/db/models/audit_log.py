from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.file import File
    from app.db.models.operation import Operation


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_file_id", "file_id"),
        Index("ix_audit_logs_operation_id", "operation_id"),
        Index("ix_audit_logs_timestamp", "timestamp"),
        Index("ix_audit_logs_case_id", "case_id"),
        Index("ix_audit_logs_actor_id", "actor_id"),
    )

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("files.file_id", ondelete="SET NULL"))
    operation_id: Mapped[str | None] = mapped_column(
        ForeignKey("operations.operation_id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    hash: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    file: Mapped["File | None"] = relationship(back_populates="audit_logs")
    operation: Mapped["Operation | None"] = relationship(back_populates="audit_logs")
