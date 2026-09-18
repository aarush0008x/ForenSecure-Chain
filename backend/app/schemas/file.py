from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id: str
    original_filename: str
    file_path: str
    file_size: int
    file_type: str | None
    original_hash: str
    upload_timestamp: datetime
    status: str


class FileListResponse(BaseModel):
    items: list[FileResponse]
    total: int