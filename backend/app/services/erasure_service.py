import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.blockchain.ledger import canonical_timestamp
from app.core.config import Settings
from app.db.models import AuditLog, BlockchainBlock, Certificate, File, Operation


ERASURE_METHOD = "overwrite_then_delete"


class ErasureServiceError(Exception):
    """Expected validation, safety, or erasure failure."""


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _contained_regular_file(file_record: File, settings: Settings) -> Path:
    storage_root = settings.storage_dir.resolve()
    unresolved_candidate = storage_root / file_record.file_path
    if unresolved_candidate.is_symlink():
        raise ErasureServiceError("Symlinks are not eligible for erasure")
    candidate = unresolved_candidate.resolve()
    try:
        candidate.relative_to(storage_root)
    except ValueError as error:
        raise ErasureServiceError("The selected file is outside controlled storage") from error

    if candidate.is_symlink() or not candidate.is_file():
        raise ErasureServiceError("The selected file is not available in controlled storage")
    return candidate


def _sha256_file(source: BinaryIO) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(1024 * 1024):
        size += len(chunk)
        digest.update(chunk)
    return size, digest.hexdigest()


def _overwrite_file(path: Path, file_size: int) -> None:
    with path.open("r+b") as target:
        remaining = file_size
        zero_chunk = b"\x00" * (1024 * 1024)
        while remaining:
            chunk_size = min(remaining, len(zero_chunk))
            target.write(zero_chunk[:chunk_size])
            remaining -= chunk_size
        target.flush()
        os.fsync(target.fileno())
    path.unlink()


def _next_block_index(db: Session) -> int:
    latest_index = db.scalar(select(func.max(BlockchainBlock.block_index)))
    return 0 if latest_index is None else latest_index + 1


def _create_erasure_block(
    db: Session,
    file_record: File,
    operation: Operation,
    audit_log: AuditLog,
    timestamp: datetime,
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
        "status": "completed",
    }
    block_payload = {
        "index": block_index,
        "timestamp": canonical_timestamp(timestamp),
        "action": "erasure",
        "file_id": file_record.file_id,
        "file_hash": file_record.original_hash,
        "previous_hash": previous_hash,
        "audit_data": audit_data,
    }
    current_hash = hashlib.sha256(_canonical_json(block_payload).encode("utf-8")).hexdigest()
    return BlockchainBlock(
        block_index=block_index,
        timestamp=timestamp,
        action="erasure",
        file_id=file_record.file_id,
        file_hash=file_record.original_hash,
        previous_hash=previous_hash,
        current_hash=current_hash,
        audit_data=audit_data,
    )


def _certificate_response(certificate: Certificate, file_record: File) -> dict[str, object]:
    details = certificate.details or {}
    return {
        "certificate_id": certificate.certificate_id,
        "file_id": file_record.file_id,
        "original_hash": details.get("original_hash", file_record.original_hash),
        "method": details.get("method", certificate.certificate_type),
        "timestamp": certificate.generated_at,
        "status": details.get("status", "completed"),
    }


def erase_file(db: Session, file_id: str, settings: Settings) -> dict[str, object]:
    file_record = db.get(File, file_id)
    if file_record is None:
        raise ErasureServiceError("File not found")
    if file_record.status == "erased":
        raise ErasureServiceError("File has already been erased")

    path = _contained_regular_file(file_record, settings)
    with path.open("rb") as source:
        file_size, original_hash = _sha256_file(source)
    if original_hash != file_record.original_hash:
        raise ErasureServiceError("File integrity verification failed before erasure")

    operation_id = str(uuid4())
    started_at = datetime.now(UTC)
    try:
        _overwrite_file(path, file_size)
        if path.exists():
            raise ErasureServiceError("Erasure verification failed: file is still available")

        completed_at = datetime.now(UTC)
        operation = Operation(
            operation_id=operation_id,
            file_id=file_id,
            operation_type="erasure",
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            details={
                "original_hash": original_hash,
                "file_size": file_size,
                "method": ERASURE_METHOD,
                "status": "completed",
            },
        )
        file_record.status = "erased"
        db.add(operation)
        db.flush()

        audit_details = {
            "original_hash": original_hash,
            "file_size": file_size,
            "method": ERASURE_METHOD,
            "status": "completed",
        }
        audit_payload = {
            "action": "erasure",
            "file_id": file_id,
            "operation_id": operation_id,
            "timestamp": completed_at.isoformat(),
            "details": audit_details,
        }
        audit_log = AuditLog(
            file_id=file_id,
            operation_id=operation_id,
            action="erasure",
            timestamp=completed_at,
            hash=hashlib.sha256(_canonical_json(audit_payload).encode("utf-8")).hexdigest(),
            details=audit_details,
        )
        certificate = Certificate(
            certificate_id=str(uuid4()),
            file_id=file_id,
            operation_id=operation_id,
            certificate_type=ERASURE_METHOD,
            generated_at=completed_at,
            details={
                "original_hash": original_hash,
                "file_size": file_size,
                "method": ERASURE_METHOD,
                "status": "completed",
            },
        )
        db.add(audit_log)
        db.add(certificate)
        db.flush()
        db.add(_create_erasure_block(db, file_record, operation, audit_log, completed_at))
        db.commit()
        db.refresh(certificate)
        return _certificate_response(certificate, file_record)
    except ErasureServiceError:
        db.rollback()
        raise
    except Exception as error:
        db.rollback()
        raise ErasureServiceError("Unable to record the erasure operation") from error


def get_erasure_certificate(db: Session, file_id: str) -> dict[str, object]:
    file_record = db.get(File, file_id)
    if file_record is None:
        raise ErasureServiceError("File not found")

    certificate = db.scalar(
        select(Certificate)
        .where(
            Certificate.file_id == file_id,
            Certificate.certificate_type == ERASURE_METHOD,
        )
        .order_by(Certificate.generated_at.desc())
    )
    if certificate is None:
        raise ErasureServiceError("Erasure certificate not found")
    return _certificate_response(certificate, file_record)