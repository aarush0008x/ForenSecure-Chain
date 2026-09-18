from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.database import get_db
from app.schemas.erasure import ErasureResponse
from app.services.erasure_service import (
    ErasureServiceError,
    erase_file,
    get_erasure_certificate,
)


router = APIRouter(prefix="/api/erasure", tags=["erasure"])


@router.post("/{file_id}", response_model=ErasureResponse)
def erase(
    file_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return erase_file(db, file_id, settings)
    except ErasureServiceError as error:
        detail = str(error)
        response_status = (
            status.HTTP_404_NOT_FOUND
            if detail in {"File not found", "Erasure certificate not found"}
            else status.HTTP_409_CONFLICT
            if detail == "File has already been erased"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=response_status, detail=detail) from error


@router.get("/{file_id}/certificate", response_model=ErasureResponse)
def certificate(file_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return get_erasure_certificate(db, file_id)
    except ErasureServiceError as error:
        response_status = (
            status.HTTP_404_NOT_FOUND
            if str(error) in {"File not found", "Erasure certificate not found"}
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=response_status, detail=str(error)) from error