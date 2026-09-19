from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict

from app.schemas.file import FileResponse


class DeviceCreateRequest(BaseModel):
    device_type: str
    serial_or_identifier: str
    source_hash: str
    acquisition_status: str = "acquired"


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    device_type: str
    serial_or_identifier: str
    acquisition_status: str
    source_hash: str
    created_at: datetime


class CaseCreateRequest(BaseModel):
    case_number: str
    title: str
    description: str | None = None
    legal_hold: bool = True


class CaseUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    legal_hold: bool | None = None


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_number: str
    title: str
    description: str | None = None
    investigator_id: str | None = None
    status: str
    legal_hold: bool
    created_at: datetime
    closed_at: datetime | None = None


class CaseDetailResponse(CaseResponse):
    devices: list[DeviceResponse] = []
    files: list[FileResponse] = []
    total_evidence: int = 0


class TimelineEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    event_type: str
    timestamp: datetime
    source: str
    description: str
    metadata_json: dict[str, Any] | None = None


class TimelineResponse(BaseModel):
    case_id: str
    case_number: str
    events: list[TimelineEventResponse]
    total_events: int
