import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.blockchain.ledger import canonical_timestamp
from app.core.config import Settings
from app.db.models import AuditLog, BlockchainBlock, File, Operation, RecoveredFile, RecoveryRun
from app.recovery.carving import CarveCandidate, carve
from app.recovery.metadata import build_recovered_metadata, extract_source_filesystem_metadata


RECOVERY_ACTION = "file_carving_scan"


class RecoveryServiceError(Exception):
    """Expected validation, safety, or carving failure."""


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _controlled_source_path(file_record: File, settings: Settings) -> Path:
    storage_root = settings.storage_dir.resolve()
    unresolved = storage_root / file_record.file_path
    if unresolved.is_symlink():
        raise RecoveryServiceError("Symlinks are not eligible for recovery scans")
    source_path = unresolved.resolve()
    try:
        source_path.relative_to(storage_root)
    except ValueError as error:
        raise RecoveryServiceError("The selected source is outside controlled storage") from error
    if source_path.is_symlink() or not source_path.is_file():
        raise RecoveryServiceError("The selected source is not available in controlled storage")
    return source_path


def _next_block_index(db: Session) -> int:
    latest_index = db.scalar(select(func.max(BlockchainBlock.block_index)))
    return 0 if latest_index is None else latest_index + 1


def _create_block(
    db: Session,
    file_record: File,
    operation: Operation,
    audit_log: AuditLog,
    source_hash: str,
    timestamp: datetime,
    detected_count: int,
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
        "recovery_id": operation.details.get("recovery_id") if operation.details else None,
        "detected_count": detected_count,
    }
    payload = {
        "index": block_index,
        "timestamp": canonical_timestamp(timestamp),
        "action": RECOVERY_ACTION,
        "file_id": file_record.file_id,
        "file_hash": source_hash,
        "previous_hash": previous_hash,
        "audit_data": audit_data,
    }
    current_hash = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return BlockchainBlock(
        block_index=block_index,
        timestamp=timestamp,
        action=RECOVERY_ACTION,
        file_id=file_record.file_id,
        file_hash=source_hash,
        previous_hash=previous_hash,
        current_hash=current_hash,
        audit_data=audit_data,
    )


def _response(run: RecoveryRun, artifacts: list[RecoveredFile]) -> dict[str, object]:
    return {
        "recovery_id": run.recovery_id,
        "file_id": run.file_id,
        "number_of_files_detected": run.detected_count,
        "recovery_timestamp": run.completed_at,
        "recovered_files": artifacts,
    }


def scan_file(db: Session, file_id: str, settings: Settings) -> dict[str, object]:
    file_record = db.get(File, file_id)
    if file_record is None:
        raise RecoveryServiceError("File not found")

    source_path = _controlled_source_path(file_record, settings)
    source_data = source_path.read_bytes()
    if len(source_data) > settings.max_recovery_input_size:
        raise RecoveryServiceError("Source file exceeds the recovery input limit")

    source_hash = hashlib.sha256(source_data).hexdigest()
    if source_hash != file_record.original_hash:
        raise RecoveryServiceError("Source integrity verification failed before recovery")

    candidates = carve(source_data)
    source_filesystem = extract_source_filesystem_metadata(source_path)
    recovery_id = str(uuid4())
    started_at = datetime.now(UTC)
    recovery_dir = settings.storage_dir / "recovered" / recovery_id
    recovery_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[RecoveredFile] = []

    try:
        for index, candidate in enumerate(candidates, start=1):
            recovered_id = str(uuid4())
            filename = f"recovered_{index:04d}.{candidate.extension}"
            destination = recovery_dir / filename
            destination.write_bytes(candidate.data)
            recovered_hash = hashlib.sha256(candidate.data).hexdigest()
            artifacts.append(
                RecoveredFile(
                    recovery_id=recovered_id,
                    recovery_run_id=recovery_id,
                    file_id=file_id,
                    recovered_filename=filename,
                    file_type=candidate.file_type,
                    file_size=len(candidate.data),
                    recovered_path=str(destination.relative_to(settings.storage_dir)),
                    recovered_hash=recovered_hash,
                    recovery_timestamp=started_at,
                    metadata_info=build_recovered_metadata(
                        candidate=candidate,
                        filename=filename,
                        file_size=len(candidate.data),
                        recovered_hash=recovered_hash,
                        recovery_timestamp=started_at,
                        source_filesystem=source_filesystem,
                    ) | {
                        "source_offsets": {
                            "start": candidate.start_offset,
                            "end": candidate.end_offset,
                        },
                    },
                )
            )

        completed_at = datetime.now(UTC)
        run = RecoveryRun(
            recovery_id=recovery_id,
            file_id=file_id,
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            source_hash=source_hash,
            detected_count=len(artifacts),
            details={
                "source_path": file_record.file_path,
                "source_size": len(source_data),
                "supported_types": ["image/jpeg", "image/png", "application/pdf"],
            },
        )
        operation = Operation(
            operation_id=str(uuid4()),
            file_id=file_id,
            operation_type="recovery",
            status="completed",
            started_at=started_at,
            completed_at=completed_at,
            details={
                "recovery_id": recovery_id,
                "source_hash": source_hash,
                "detected_count": len(artifacts),
            },
        )
        db.add(run)
        db.add(operation)
        db.add_all(artifacts)
        db.flush()

        audit_details = {
            "recovery_id": recovery_id,
            "source_hash": source_hash,
            "detected_count": len(artifacts),
            "recovered_hashes": [artifact.recovered_hash for artifact in artifacts],
        }
        audit_payload = {
            "action": RECOVERY_ACTION,
            "file_id": file_id,
            "operation_id": operation.operation_id,
            "timestamp": completed_at.isoformat(),
            "details": audit_details,
        }
        audit_log = AuditLog(
            file_id=file_id,
            operation_id=operation.operation_id,
            action=RECOVERY_ACTION,
            timestamp=completed_at,
            hash=hashlib.sha256(_canonical_json(audit_payload).encode("utf-8")).hexdigest(),
            details=audit_details,
        )
        db.add(audit_log)
        db.flush()
        db.add(
            _create_block(
                db,
                file_record,
                operation,
                audit_log,
                source_hash,
                completed_at,
                len(artifacts),
            )
        )
        db.commit()
        db.refresh(run)
        for artifact in artifacts:
            db.refresh(artifact)
        return _response(run, artifacts)
    except Exception as error:
        db.rollback()
        shutil.rmtree(recovery_dir, ignore_errors=True)
        if isinstance(error, RecoveryServiceError):
            raise
        raise RecoveryServiceError("Unable to record the recovery scan") from error


def get_scan_results(db: Session, recovery_id: str) -> dict[str, object]:
    run = db.get(RecoveryRun, recovery_id)
    if run is None:
        raise RecoveryServiceError("Recovery scan not found")
    artifacts = list(
        db.scalars(
            select(RecoveredFile)
            .where(RecoveredFile.recovery_run_id == recovery_id)
            .order_by(RecoveredFile.recovery_timestamp, RecoveredFile.recovered_filename)
        )
    )
    return _response(run, artifacts)