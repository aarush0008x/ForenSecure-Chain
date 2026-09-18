import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.recovery.carving import CarveCandidate


def _timestamp_or_none(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=UTC).isoformat()


def extract_source_filesystem_metadata(source_path: Path) -> dict[str, Any]:
    """Return only filesystem facts available from the controlled source file."""
    try:
        file_stat = source_path.stat()
    except OSError:
        return {
            "available": False,
            "path": str(source_path),
            "created_at": None,
            "modified_at": None,
            "size": None,
        }

    birth_time = getattr(file_stat, "st_birthtime", None)
    if birth_time is None and os.name == "nt":
        birth_time = file_stat.st_ctime

    return {
        "available": True,
        "path": str(source_path),
        "created_at": _timestamp_or_none(birth_time),
        "modified_at": _timestamp_or_none(getattr(file_stat, "st_mtime", None)),
        "size": file_stat.st_size,
    }


def build_recovered_metadata(
    candidate: CarveCandidate,
    filename: str,
    file_size: int,
    recovered_hash: str,
    recovery_timestamp: datetime,
    source_filesystem: dict[str, Any],
) -> dict[str, Any]:
    return {
        "artifact": {
            "filename": filename,
            "extension": f".{candidate.extension}",
            "mime_type": candidate.file_type,
            "file_size": file_size,
            "sha256": recovered_hash,
            "recovery_timestamp": recovery_timestamp.isoformat(),
        },
        "source_filesystem": source_filesystem,
        **candidate.metadata,
    }