from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RecoveredFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recovery_id: str
    recovered_filename: str
    file_type: str | None
    file_size: int
    recovered_path: str
    recovered_hash: str
    recovery_timestamp: datetime
    metadata_info: dict[str, Any] | None


class RecoveryResponse(BaseModel):
    recovery_id: str
    file_id: str
    number_of_files_detected: int
    recovery_timestamp: datetime
    recovered_files: list[RecoveredFileResponse]


class RecoveryScanRequest(BaseModel):
    file_id: str