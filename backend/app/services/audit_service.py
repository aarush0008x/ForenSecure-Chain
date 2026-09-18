from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, BlockchainBlock, File, Operation


class AuditServiceError(Exception):
    """Expected audit trail request failure."""


def _event_status(audit_log: AuditLog, operation: Operation | None) -> str:
    details = audit_log.details or {}
    status = details.get("status") or details.get("comparison_result")
    if isinstance(status, str):
        return status
    if operation is not None:
        return operation.status
    return "recorded"


def get_file_audit_trail(db: Session, file_id: str) -> dict[str, Any]:
    if db.get(File, file_id) is None:
        raise AuditServiceError("File not found")

    audit_logs = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.file_id == file_id)
            .order_by(AuditLog.timestamp.asc(), AuditLog.audit_id.asc())
        )
    )
    operation_ids = {audit_log.operation_id for audit_log in audit_logs if audit_log.operation_id}
    operations = {
        operation.operation_id: operation
        for operation in db.scalars(
            select(Operation).where(Operation.operation_id.in_(operation_ids))
        )
    }
    blocks = list(
        db.scalars(
            select(BlockchainBlock)
            .where(BlockchainBlock.file_id == file_id)
            .order_by(BlockchainBlock.block_index.asc())
        )
    )
    block_indexes_by_audit_id = {
        block.audit_data.get("audit_id"): block.block_index
        for block in blocks
        if block.audit_data and block.audit_data.get("audit_id")
    }

    events = []
    for audit_log in audit_logs:
        operation = operations.get(audit_log.operation_id)
        events.append(
            {
                "audit_id": audit_log.audit_id,
                "action": audit_log.action,
                "timestamp": audit_log.timestamp,
                "file_id": file_id,
                "hash": audit_log.hash,
                "operation_id": audit_log.operation_id,
                "blockchain_block_index": block_indexes_by_audit_id.get(audit_log.audit_id),
                "details": audit_log.details or {},
                "status": _event_status(audit_log, operation),
            }
        )

    return {"file_id": file_id, "total_events": len(events), "events": events}