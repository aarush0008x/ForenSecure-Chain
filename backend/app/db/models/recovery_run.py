from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.file import File
    from app.db.models.recovered_file import RecoveredFile


class RecoveryRun(Base):
    __tablename__ = "recovery_runs"
    __table_args__ = (
        Index("ix_recovery_runs_file_id", "file_id"),
        Index("ix_recovery_runs_status", "status"),
    )

    recovery_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    file_id: Mapped[str] = mapped_column(
        ForeignKey("files.file_id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    detected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    file: Mapped["File"] = relationship(back_populates="recovery_runs")
    recovered_files: Mapped[list["RecoveredFile"]] = relationship(
        back_populates="recovery_run", cascade="all, delete-orphan"
    )