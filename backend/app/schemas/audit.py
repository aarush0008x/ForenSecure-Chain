from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditEventResponse(BaseModel):
    audit_id: str
    action: str
    timestamp: datetime
    file_id: str
    hash: str
    operation_id: str | None
    blockchain_block_index: int | None
    details: dict[str, Any]
    status: str


class AuditTrailResponse(BaseModel):
    file_id: str
    total_events: int
    events: list[AuditEventResponse]