from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.file import File


class BlockchainBlock(Base):
    __tablename__ = "blockchain_blocks"
    __table_args__ = (
        Index("ix_blockchain_blocks_file_id", "file_id"),
        Index("ix_blockchain_blocks_current_hash", "current_hash"),
    )

    block_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_index: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    file_id: Mapped[str | None] = mapped_column(ForeignKey("files.file_id", ondelete="SET NULL"))
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    current_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    audit_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    file: Mapped["File | None"] = relationship(back_populates="blockchain_blocks")
