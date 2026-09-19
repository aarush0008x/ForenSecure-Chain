from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.audit_log import AuditLog
    from app.db.models.blockchain_block import BlockchainBlock
    from app.db.models.case import Case
    from app.db.models.certificate import Certificate
    from app.db.models.device import Device
    from app.db.models.operation import Operation
    from app.db.models.recovered_file import RecoveredFile
    from app.db.models.recovery_run import RecoveryRun


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        Index("ix_files_original_hash", "original_hash"),
        Index("ix_files_status", "status"),
        Index("ix_files_case_id", "case_id"),
        Index("ix_files_device_id", "device_id"),
    )

    file_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str | None] = mapped_column(ForeignKey("cases.id", ondelete="SET NULL"))
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(127))
    original_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    upload_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")

    case: Mapped["Case | None"] = relationship(back_populates="files")
    device: Mapped["Device | None"] = relationship(back_populates="files")

    operations: Mapped[list["Operation"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    recovered_files: Mapped[list["RecoveredFile"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    recovery_runs: Mapped[list["RecoveryRun"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="file")
    certificates: Mapped[list["Certificate"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )
    blockchain_blocks: Mapped[list["BlockchainBlock"]] = relationship(back_populates="file")
