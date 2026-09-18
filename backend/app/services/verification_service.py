import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.blockchain.ledger import canonical_timestamp
from app.core.config import Settings
from app.db.models import AuditLog, BlockchainBlock, File, Operation, RecoveredFile


VERIFICATION_ACTION = "verification"
HASH_ALGORITHM = "SHA-256"


class VerificationServiceError(Exception):
    """Expected verification request failure."""


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _controlled_file_path(relative_path: str, settings: Settings) -> Path | None:
    storage_root = settings.storage_dir.resolve()
    unresolved = storage_root / relative_path
    if unresolved.is_symlink():
        return None
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(storage_root)
    except ValueError:
        return None
    if candidate.is_symlink() or not candidate.is_file():
        return None
    return candidate


def _next_block_index(db: Session) -> int:
    latest_index = db.scalar(select(func.max(BlockchainBlock.block_index)))
    return 0 if latest_index is None else latest_index + 1


def _create_block(
    db: Session,
    file_record: File,
    operation: Operation,
    audit_log: AuditLog,
    hash_for_record: str,
    timestamp: datetime,
    comparison_result: str,
) -> BlockchainBlock:
    previous_block = db.scalar(
        select(BlockchainBlock)
        .order_by(BlockchainBlock.block_index.desc())
        .with_for_update()
    )
    previous_hash = previous_block.current_hash if previous_block else None
    block_index = _next_block_index(db)
    audit_data = {
        "audit_id": audit_log.audit_id,
        "operation_id": operation.operation_id,
        "comparison_result": comparison_result,
    }
    payload = {
        "index": block_index,
        "timestamp": canonical_timestamp(timestamp),
        "action": VERIFICATION_ACTION,
        "file_id": file_record.file_id,
        "file_hash": hash_for_record,
        "previous_hash": previous_hash,
        "audit_data": audit_data,
    }
    current_hash = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return BlockchainBlock(
        block_index=block_index,
        timestamp=timestamp,
        action=VERIFICATION_ACTION,
        file_id=file_record.file_id,
        file_hash=hash_for_record,
        previous_hash=previous_hash,
        current_hash=current_hash,
        audit_data=audit_data,
    )


def _recovered_hashes(
    db: Session,
    file_id: str,
    settings: Settings,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    recovered_files = list(
        db.scalars(
            select(RecoveredFile)
            .where(RecoveredFile.file_id == file_id)
            .order_by(RecoveredFile.recovery_timestamp, RecoveredFile.recovered_filename)
        )
    )
    for recovered_file in recovered_files:
        path = _controlled_file_path(recovered_file.recovered_path, settings)
        current_hash = _hash_file(path) if path else None
        result = (
            "NOT_AVAILABLE"
            if current_hash is None
            else "VERIFIED"
            if current_hash == recovered_file.recovered_hash
            else "MISMATCH"
        )
        results.append(
            {
                "recovery_id": recovered_file.recovery_id,
                "recovered_filename": recovered_file.recovered_filename,
                "stored_hash": recovered_file.recovered_hash,
                "current_hash": current_hash,
                "status": result,
            }
        )
    return results


def verify_file(db: Session, file_id: str, settings: Settings) -> dict[str, object]:
    file_record = db.get(File, file_id)
    if file_record is None:
        raise VerificationServiceError("File not found")

    current_path = _controlled_file_path(file_record.file_path, settings)
    current_hash = _hash_file(current_path) if current_path else None
    original_hash = file_record.original_hash
    comparison_result = (
        "NOT_AVAILABLE"
        if not original_hash or not current_hash
        else "VERIFIED"
        if original_hash == current_hash
        else "MISMATCH"
    )
    verification_timestamp = datetime.now(UTC)
    recovered_hashes = _recovered_hashes(db, file_id, settings)
    operation_id = str(uuid4())
    details = {
        "hash_algorithm": HASH_ALGORITHM,
        "original_hash_available": bool(original_hash),
        "current_hash_available": bool(current_hash),
        "recovered_hash_count": len(recovered_hashes),
        "comparison_result": comparison_result,
    }
    operation = Operation(
        operation_id=operation_id,
        file_id=file_id,
        operation_type="verification",
        status="completed",
        started_at=verification_timestamp,
        completed_at=verification_timestamp,
        details=details,
    )
    audit_payload = {
        "action": VERIFICATION_ACTION,
        "file_id": file_id,
        "operation_id": operation_id,
        "timestamp": verification_timestamp.isoformat(),
        "details": details,
    }
    audit_log = AuditLog(
        file_id=file_id,
        operation_id=operation_id,
        action=VERIFICATION_ACTION,
        timestamp=verification_timestamp,
        hash=hashlib.sha256(_canonical_json(audit_payload).encode("utf-8")).hexdigest(),
        details=details,
    )
    hash_for_block = current_hash or original_hash
    try:
        db.add(operation)
        db.add(audit_log)
        db.flush()
        block = _create_block(
            db,
            file_record,
            operation,
            audit_log,
            hash_for_block,
            verification_timestamp,
            comparison_result,
        )
        db.add(block)
        db.commit()
        db.refresh(operation)
        db.refresh(block)
    except Exception as error:
        db.rollback()
        raise VerificationServiceError("Unable to record the verification operation") from error

    return {
        "file_id": file_id,
        "hash_algorithm": HASH_ALGORITHM,
        "original_hash": original_hash,
        "current_hash": current_hash,
        "recovered_hashes": recovered_hashes,
        "comparison_result": comparison_result,
        "verification_timestamp": verification_timestamp,
        "related_operation": operation,
        "related_blockchain_block": block,
        "details": details,
    }