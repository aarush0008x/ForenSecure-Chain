import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.blockchain.ledger import append_block
from app.core.config import Settings
from app.db.models import (
    AuditLog,
    BlockchainBlock,
    Certificate,
    File,
    Operation,
    RecoveredFile,
    RecoveryRun,
)


REPORT_ACTION = "report_generation"


class ReportServiceError(Exception):
    """Expected report generation or retrieval failure."""


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _block_reference(block: BlockchainBlock) -> dict[str, Any]:
    return {
        "block_id": block.block_id,
        "block_index": block.block_index,
        "action": block.action,
        "timestamp": block.timestamp,
        "current_hash": block.current_hash,
        "previous_hash": block.previous_hash,
    }


def _verification_information(db: Session, file_id: str) -> dict[str, Any] | None:
    operation = db.scalar(
        select(Operation)
        .where(
            Operation.file_id == file_id,
            Operation.operation_type == "verification",
        )
        .order_by(Operation.completed_at.desc(), Operation.started_at.desc())
    )
    if operation is None:
        return None
    details = operation.details or {}
    audit = db.scalar(
        select(AuditLog).where(AuditLog.operation_id == operation.operation_id)
    )
    return {
        "operation_id": operation.operation_id,
        "status": operation.status,
        "completed_at": operation.completed_at,
        "comparison_result": details.get("comparison_result"),
        "hash_algorithm": details.get("hash_algorithm"),
        "audit_id": audit.audit_id if audit else None,
        "audit_hash": audit.hash if audit else None,
    }


def _erasure_certificate(db: Session, file_record: File) -> dict[str, Any] | None:
    certificate = db.scalar(
        select(Certificate)
        .where(
            Certificate.file_id == file_record.file_id,
            Certificate.certificate_type == "overwrite_then_delete",
        )
        .order_by(Certificate.generated_at.desc())
    )
    if certificate is None:
        return None
    details = certificate.details or {}
    return {
        "certificate_id": certificate.certificate_id,
        "file_id": file_record.file_id,
        "original_filename": file_record.original_filename,
        "original_sha256": details.get("original_hash", file_record.original_hash),
        "file_size": details.get("file_size", file_record.file_size),
        "erasure_method": details.get("method", certificate.certificate_type),
        "erasure_timestamp": certificate.generated_at,
        "final_status": details.get("status", file_record.status),
    }


def _recovery_reports(db: Session, file_id: str) -> list[dict[str, Any]]:
    runs = list(
        db.scalars(
            select(RecoveryRun)
            .where(RecoveryRun.file_id == file_id)
            .order_by(RecoveryRun.completed_at.asc(), RecoveryRun.recovery_id.asc())
        )
    )
    reports = []
    for run in runs:
        artifacts = list(
            db.scalars(
                select(RecoveredFile)
                .where(RecoveredFile.recovery_run_id == run.recovery_id)
                .order_by(RecoveredFile.recovered_filename.asc())
            )
        )
        reports.append(
            {
                "recovery_id": run.recovery_id,
                "status": run.status,
                "source_information": {
                    "file_id": file_id,
                    "source_path": (run.details or {}).get("source_path"),
                    "source_hash": run.source_hash,
                    "source_size": (run.details or {}).get("source_size"),
                },
                "recovered_files": [
                    {
                        "recovery_id": artifact.recovery_id,
                        "filename": artifact.recovered_filename,
                        "file_type": artifact.file_type,
                        "size": artifact.file_size,
                        "sha256": artifact.recovered_hash,
                        "recovered_path": artifact.recovered_path,
                        "metadata": artifact.metadata_info,
                    }
                    for artifact in artifacts
                ],
                "recovery_timestamp": run.completed_at or run.started_at,
                "detected_count": run.detected_count,
            }
        )
    return reports


def generate_report(db: Session, file_id: str, settings: Settings) -> dict[str, Any]:
    file_record = db.get(File, file_id)
    if file_record is None:
        raise ReportServiceError("File not found")

    erasure_certificate = _erasure_certificate(db, file_record)
    recovery_reports = _recovery_reports(db, file_id)
    if erasure_certificate is None and not recovery_reports:
        raise ReportServiceError("No erasure or recovery evidence available")

    generated_at = datetime.now(UTC)
    report_id = str(uuid4())
    existing_blocks = list(
        db.scalars(
            select(BlockchainBlock)
            .where(BlockchainBlock.file_id == file_id)
            .order_by(BlockchainBlock.block_index.asc())
        )
    )
    verification_information = _verification_information(db, file_id)
    report = {
        "file_id": file_id,
        "generated_at": generated_at,
        "report_path": None,
        "download_url": f"/api/reports/{file_id}/download",
        "erasure_certificate": erasure_certificate,
        "recovery_reports": recovery_reports,
        "verification_information": verification_information,
        "blockchain_audit_references": [_block_reference(block) for block in existing_blocks],
    }
    report_dir = settings.storage_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{report_id}.json"
    report["report_path"] = str(report_path.relative_to(settings.storage_dir))

    operation = Operation(
        operation_id=str(uuid4()),
        file_id=file_id,
        operation_type=REPORT_ACTION,
        status="completed",
        started_at=generated_at,
        completed_at=generated_at,
        details={"report_id": report_id, "report_path": report["report_path"]},
    )
    audit_details = {
        "report_id": report_id,
        "report_path": report["report_path"],
        "has_erasure_certificate": erasure_certificate is not None,
        "recovery_count": len(recovery_reports),
    }
    audit_log = AuditLog(
        file_id=file_id,
        operation_id=operation.operation_id,
        action=REPORT_ACTION,
        timestamp=generated_at,
        hash=hashlib.sha256(
            json.dumps(
                {
                    "action": REPORT_ACTION,
                    "file_id": file_id,
                    "operation_id": operation.operation_id,
                    "timestamp": generated_at.isoformat(),
                    "details": audit_details,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        details=audit_details,
    )
    try:
        report_path.write_text(
            json.dumps(_json_value(report), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        db.add(operation)
        db.add(audit_log)
        db.flush()
        report_block = append_block(
            db,
            action=REPORT_ACTION,
            file_id=file_id,
            file_hash=file_record.original_hash,
            audit_data={
                "audit_id": audit_log.audit_id,
                "operation_id": operation.operation_id,
                "report_id": report_id,
            },
            timestamp=generated_at,
        )
        certificate = Certificate(
            certificate_id=report_id,
            file_id=file_id,
            operation_id=operation.operation_id,
            certificate_type=REPORT_ACTION,
            generated_at=generated_at,
            certificate_path=report["report_path"],
            details=audit_details,
        )
        db.add(certificate)
        db.commit()
        db.refresh(report_block)
        report["blockchain_audit_references"].append(_block_reference(report_block))
        report_path.write_text(
            json.dumps(_json_value(report), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return _json_value(report)
    except Exception as error:
        db.rollback()
        report_path.unlink(missing_ok=True)
        raise ReportServiceError("Unable to generate report") from error


def report_path_for_file(db: Session, file_id: str, settings: Settings) -> Path:
    report = db.scalar(
        select(Certificate)
        .where(
            Certificate.file_id == file_id,
            Certificate.certificate_type == REPORT_ACTION,
        )
        .order_by(Certificate.generated_at.desc())
    )
    if report is None or not report.certificate_path:
        raise ReportServiceError("Report not found")
    storage_root = settings.storage_dir.resolve()
    candidate = (storage_root / report.certificate_path).resolve()
    try:
        candidate.relative_to(storage_root)
    except ValueError as error:
        raise ReportServiceError("Report path is outside controlled storage") from error
    if not candidate.is_file():
        raise ReportServiceError("Report file is not available")
    return candidate