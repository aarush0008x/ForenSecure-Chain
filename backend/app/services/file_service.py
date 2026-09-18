import hashlib
import json
import mimetypes
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.blockchain.ledger import canonical_timestamp
from app.core.config import Settings
from app.db.models import AuditLog, BlockchainBlock, File


class FileServiceError(Exception):
    """Expected validation or storage failure in the file workflow."""


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _hash_stream(source: BinaryIO, destination: BinaryIO, max_size: int) -> tuple[int, str]:
    digest = hashlib.sha256()
    file_size = 0

    while chunk := source.read(1024 * 1024):
        file_size += len(chunk)
        if file_size > max_size:
            raise FileServiceError(f"File exceeds the {max_size} byte upload limit")
        digest.update(chunk)
        destination.write(chunk)

    return file_size, digest.hexdigest()


def _next_block_index(db: Session) -> int:
    latest_index = db.scalar(select(func.max(BlockchainBlock.block_index)))
    return 0 if latest_index is None else latest_index + 1


def _create_upload_block(
    db: Session,
    file_record: File,
    audit_log: AuditLog,
    action: str = "upload",
) -> BlockchainBlock:
    previous_block = db.scalar(
        select(BlockchainBlock)
        .order_by(BlockchainBlock.block_index.desc())
        .with_for_update()
    )
    previous_hash = previous_block.current_hash if previous_block else None
    block_index = _next_block_index(db)
    block_timestamp = datetime.now(UTC)
    audit_data = {
        "audit_id": audit_log.audit_id,
        "action": audit_log.action,
        "file_id": file_record.file_id,
        "file_hash": file_record.original_hash,
    }
    block_payload = {
        "index": block_index,
        "timestamp": canonical_timestamp(block_timestamp),
        "action": action,
        "file_id": file_record.file_id,
        "file_hash": file_record.original_hash,
        "previous_hash": previous_hash,
        "audit_data": audit_data,
    }
    current_hash = hashlib.sha256(_canonical_json(block_payload).encode("utf-8")).hexdigest()
    return BlockchainBlock(
        block_index=block_index,
        timestamp=block_timestamp,
        action=action,
        file_id=file_record.file_id,
        file_hash=file_record.original_hash,
        previous_hash=previous_hash,
        current_hash=current_hash,
        audit_data=audit_data,
    )


async def upload_file(db: Session, upload: UploadFile, settings: Settings) -> File:
    original_filename = Path(upload.filename or "").name
    if not original_filename or original_filename in {".", ".."}:
        raise FileServiceError("A valid filename is required")

    suffix = Path(original_filename).suffix.lower()
    file_id = str(uuid4())
    upload_dir = settings.storage_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / f"{file_id}{suffix}"

    try:
        await upload.seek(0)
        with stored_path.open("wb") as destination:
            file_size, original_hash = _hash_stream(
                upload.file, destination, settings.max_upload_size
            )
        if file_size == 0:
            raise FileServiceError("Uploaded file cannot be empty")

        file_type = upload.content_type or mimetypes.guess_type(original_filename)[0]
        file_record = File(
            file_id=file_id,
            original_filename=original_filename,
            file_path=os.fspath(stored_path.relative_to(settings.storage_dir)),
            file_size=file_size,
            file_type=file_type,
            original_hash=original_hash,
            status="uploaded",
        )
        db.add(file_record)
        db.flush()

        audit_timestamp = datetime.now(UTC)
        audit_details = {
            "original_filename": original_filename,
            "file_size": file_size,
            "file_type": file_type,
            "stored_path": file_record.file_path,
        }
        audit_payload = {
            "action": "upload",
            "file_id": file_id,
            "operation_id": None,
            "timestamp": audit_timestamp.isoformat(),
            "details": audit_details,
        }
        audit_log = AuditLog(
            file_id=file_id,
            action="upload",
            timestamp=audit_timestamp,
            hash=hashlib.sha256(_canonical_json(audit_payload).encode("utf-8")).hexdigest(),
            details=audit_details,
        )
        db.add(audit_log)
        db.flush()
        db.add(_create_upload_block(db, file_record, audit_log))

        hashing_timestamp = datetime.now(UTC)
        hashing_details = {
            "algorithm": "SHA-256",
            "hash": original_hash,
            "file_size": file_size,
            "status": "verified",
        }
        hashing_payload = {
            "action": "hashing",
            "file_id": file_id,
            "operation_id": None,
            "timestamp": hashing_timestamp.isoformat(),
            "details": hashing_details,
        }
        hashing_log = AuditLog(
            file_id=file_id,
            action="hashing",
            timestamp=hashing_timestamp,
            hash=hashlib.sha256(_canonical_json(hashing_payload).encode("utf-8")).hexdigest(),
            details=hashing_details,
        )
        db.add(hashing_log)
        db.flush()
        db.add(_create_upload_block(db, file_record, hashing_log, action="hashing"))
        db.commit()
        db.refresh(file_record)
        return file_record
    except FileServiceError:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise
    except Exception as error:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise FileServiceError("Unable to store the uploaded file") from error