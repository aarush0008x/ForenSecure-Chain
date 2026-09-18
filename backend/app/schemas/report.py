from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ReportResponse(BaseModel):
    file_id: str
    generated_at: datetime
    report_path: str
    download_url: str
    erasure_certificate: dict[str, Any] | None
    recovery_reports: list[dict[str, Any]]
    verification_information: dict[str, Any] | None
    blockchain_audit_references: list[dict[str, Any]]