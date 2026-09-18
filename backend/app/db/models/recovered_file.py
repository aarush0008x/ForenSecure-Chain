from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.file import File
    from app.db.models.recovery_run import RecoveryRun


class RecoveredFile(Base):
    __tablename__ = "recovered_files"
    __table_args__ = (
        Index("ix_recovered_files_file_id", "file_id"),
        Index("ix_recovered_files_recovered_hash", "recovered_hash"),
    )

    recovery_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    recovery_run_id: Mapped[str] = mapped_column(
        ForeignKey("recovery_runs.recovery_id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[str] = mapped_column(
        ForeignKey("files.file_id", ondelete="CASCADE"), nullable=False
    )
    recovered_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(127))
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    recovered_path: Mapped[str] = mapped_column(Text, nullable=False)
    recovered_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    recovery_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    metadata_info: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)

    file: Mapped["File"] = relationship(back_populates="recovered_files")
    recovery_run: Mapped["RecoveryRun"] = relationship(back_populates="recovered_files")
