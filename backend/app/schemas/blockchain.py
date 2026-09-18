from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BlockchainBlockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    block_id: int
    block_index: int
    timestamp: datetime
    action: str
    file_id: str | None
    file_hash: str
    previous_hash: str | None
    current_hash: str
    audit_data: dict[str, Any] | None


class BlockchainListResponse(BaseModel):
    total_blocks: int
    blocks: list[BlockchainBlockResponse]


class BlockchainFileResponse(BlockchainListResponse):
    file_id: str


class InvalidBlockResponse(BaseModel):
    block_id: int
    block_index: int
    reasons: list[str]


class BlockchainVerificationResponse(BaseModel):
    valid: bool
    total_blocks: int
    invalid_blocks: list[InvalidBlockResponse]