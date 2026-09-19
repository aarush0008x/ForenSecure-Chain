from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class SanitizationExecuteRequest(BaseModel):
    approval_id: str


class SanitizationJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str | None = None
    target_id: str
    target_type: str
    approval_id: str | None = None
    requested_by: str | None = None
    approved_by: str | None = None
    method: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None


class SanitizationCertificateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    certificate_id: str
    certificate_number: str
    verification_token: str
    case_id: str | None = None
    target_id: str
    target_type: str
    method: str
    original_hash: str
    status: str
    generated_at: datetime
    signed_at: datetime | None = None
    certificate_pdf_url: str | None = None
    details: dict[str, Any] | None = None
