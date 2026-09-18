import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import BlockchainBlock


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def canonical_timestamp(timestamp: datetime) -> str:
    """Serialize aware and database-returned naive UTC timestamps identically."""
    normalized = timestamp
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=UTC)
    return normalized.isoformat()


def _block_payload(
    block_index: int,
    timestamp: datetime,
    action: str,
    file_id: str | None,
    file_hash: str,
    previous_hash: str | None,
    audit_data: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "index": block_index,
        "timestamp": canonical_timestamp(timestamp),
        "action": action,
        "file_id": file_id,
        "file_hash": file_hash,
        "previous_hash": previous_hash,
        "audit_data": audit_data,
    }


def calculate_current_hash(
    block_index: int,
    timestamp: datetime,
    action: str,
    file_id: str | None,
    file_hash: str,
    previous_hash: str | None,
    audit_data: dict[str, Any] | None,
) -> str:
    payload = _block_payload(
        block_index,
        timestamp,
        action,
        file_id,
        file_hash,
        previous_hash,
        audit_data,
    )
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def append_block(
    db: Session,
    action: str,
    file_id: str | None,
    file_hash: str,
    audit_data: dict[str, Any] | None,
    timestamp: datetime | None = None,
) -> BlockchainBlock:
    """Append one block to the local tamper-evident ledger."""
    previous_block = db.scalar(
        select(BlockchainBlock)
        .order_by(BlockchainBlock.block_index.desc())
        .with_for_update()
    )
    previous_hash = previous_block.current_hash if previous_block else None
    latest_index = db.scalar(select(func.max(BlockchainBlock.block_index)))
    block_index = 0 if latest_index is None else latest_index + 1
    block_timestamp = timestamp or datetime.now(UTC)
    current_hash = calculate_current_hash(
        block_index,
        block_timestamp,
        action,
        file_id,
        file_hash,
        previous_hash,
        audit_data,
    )
    block = BlockchainBlock(
        block_index=block_index,
        timestamp=block_timestamp,
        action=action,
        file_id=file_id,
        file_hash=file_hash,
        previous_hash=previous_hash,
        current_hash=current_hash,
        audit_data=audit_data,
    )
    db.add(block)
    db.flush()
    return block


def _invalid_block(block: BlockchainBlock, reasons: list[str]) -> dict[str, Any]:
    return {
        "block_id": block.block_id,
        "block_index": block.block_index,
        "reasons": reasons,
    }


def verify_chain(db: Session) -> dict[str, Any]:
    blocks = list(
        db.scalars(select(BlockchainBlock).order_by(BlockchainBlock.block_index.asc()))
    )
    invalid_blocks: list[dict[str, Any]] = []
    previous_block: BlockchainBlock | None = None

    for expected_index, block in enumerate(blocks):
        reasons: list[str] = []
        if block.block_index != expected_index:
            reasons.append("block_order_invalid")

        expected_previous_hash = previous_block.current_hash if previous_block else None
        if block.previous_hash != expected_previous_hash:
            reasons.append("previous_hash_link_invalid")

        recalculated_hash = calculate_current_hash(
            block.block_index,
            block.timestamp,
            block.action,
            block.file_id,
            block.file_hash,
            block.previous_hash,
            block.audit_data,
        )
        if block.current_hash != recalculated_hash:
            reasons.append("current_hash_invalid")

        if reasons:
            invalid_blocks.append(_invalid_block(block, reasons))
        previous_block = block

    return {
        "valid": not invalid_blocks,
        "total_blocks": len(blocks),
        "invalid_blocks": invalid_blocks,
    }