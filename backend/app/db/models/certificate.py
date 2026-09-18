from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.file import File
    from app.db.models.operation import Operation


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = (
        Index("ix_certificates_file_id", "file_id"),
        Index("ix_certificates_operation_id", "operation_id"),
    )

    certificate_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    file_id: Mapped[str] = mapped_column(
        ForeignKey("files.file_id", ondelete="CASCADE"), nullable=False
    )
    operation_id: Mapped[str | None] = mapped_column(
        ForeignKey("operations.operation_id", ondelete="SET NULL")
    )
    certificate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    certificate_path: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    file: Mapped["File"] = relationship(back_populates="certificates")
    operation: Mapped["Operation | None"] = relationship(back_populates="certificates")
