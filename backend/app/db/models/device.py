from datetime import datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.case import Case
    from app.db.models.file import File


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        Index("ix_devices_case_id", "case_id"),
        Index("ix_devices_serial", "serial_or_identifier"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)
    serial_or_identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    acquisition_status: Mapped[str] = mapped_column(String(32), nullable=False, default="acquired")
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    case: Mapped["Case"] = relationship(back_populates="devices")
    files: Mapped[list["File"]] = relationship(back_populates="device")
