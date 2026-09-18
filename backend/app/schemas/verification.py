from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RecoveredHashVerification(BaseModel):
    recovery_id: str
    recovered_filename: str
    stored_hash: str
    current_hash: str | None
    status: str


class RelatedOperation(BaseModel):
    operation_id: str
    operation_type: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None


class RelatedBlockchainBlock(BaseModel):
    block_id: int
    block_index: int
    action: str
    timestamp: datetime
    previous_hash: str | None
    current_hash: str


class VerificationResponse(BaseModel):
    file_id: str
    hash_algorithm: str
    original_hash: str | None
    current_hash: str | None
    recovered_hashes: list[RecoveredHashVerification]
    comparison_result: str
    verification_timestamp: datetime
    related_operation: RelatedOperation
    related_blockchain_block: RelatedBlockchainBlock
    details: dict[str, Any]