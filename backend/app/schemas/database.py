from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatabaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class FileCreate(BaseModel):
    original_filename: str = Field(min_length=1, max_length=255)
    file_path: str = Field(min_length=1)
    file_size: int = Field(ge=0)
    file_type: str | None = Field(default=None, max_length=127)
    original_hash: str = Field(min_length=64, max_length=64)
    status: str = Field(default="uploaded", max_length=32)


class FileRead(DatabaseSchema):
    file_id: str
    original_filename: str
    file_path: str
    file_size: int
    file_type: str | None
    original_hash: str
    upload_timestamp: datetime
    status: str


class OperationCreate(BaseModel):
    file_id: str
    operation_type: str = Field(min_length=1, max_length=32)
    status: str = Field(default="pending", max_length=32)
    details: dict[str, Any] | None = None


class OperationRead(DatabaseSchema):
    operation_id: str
    file_id: str
    operation_type: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    details: dict[str, Any] | None


class RecoveredFileRead(DatabaseSchema):
    recovery_id: str
    file_id: str
    recovered_filename: str
    file_type: str | None
    file_size: int
    recovered_path: str
    recovered_hash: str
    recovery_timestamp: datetime
    metadata_info: dict[str, Any] | None


class AuditLogRead(DatabaseSchema):
    audit_id: str
    file_id: str | None
    operation_id: str | None
    action: str
    timestamp: datetime
    hash: str
    details: dict[str, Any] | None


class CertificateRead(DatabaseSchema):
    certificate_id: str
    file_id: str
    operation_id: str | None
    certificate_type: str
    generated_at: datetime
    certificate_path: str | None
    details: dict[str, Any] | None


class BlockchainBlockRead(DatabaseSchema):
    block_id: int
    block_index: int
    timestamp: datetime
    action: str
    file_id: str | None
    file_hash: str
    previous_hash: str | None
    current_hash: str
    audit_data: dict[str, Any] | None