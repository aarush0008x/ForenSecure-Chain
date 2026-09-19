from datetime import datetime
from pydantic import BaseModel, ConfigDict


class ApprovalCreateRequest(BaseModel):
    target_id: str
    target_type: str = "file"  # "file" or "device"
    sanitization_method: str = "overwrite_then_delete"
    note: str | None = None


class ApprovalDecisionRequest(BaseModel):
    note: str | None = None


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    target_id: str
    target_type: str
    sanitization_method: str
    requested_by: str
    first_approved_by: str | None = None
    second_approved_by: str | None = None
    status: str
    note: str | None = None
    created_at: datetime
    updated_at: datetime
