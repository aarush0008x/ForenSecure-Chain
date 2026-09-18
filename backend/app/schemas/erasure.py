from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ErasureResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    certificate_id: str
    file_id: str
    original_hash: str
    method: str
    timestamp: datetime
    status: str