from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.database import get_db
from app.schemas.recovery import RecoveryResponse, RecoveryScanRequest
from app.services.recovery_service import RecoveryServiceError, get_scan_results, scan_file


router = APIRouter(prefix="/api/recovery", tags=["recovery"])


@router.post("/scan", response_model=RecoveryResponse, status_code=status.HTTP_201_CREATED)
def scan(
    request: RecoveryScanRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return scan_file(db, request.file_id, settings)
    except RecoveryServiceError as error:
        response_status = (
            status.HTTP_404_NOT_FOUND
            if str(error) == "File not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=response_status, detail=str(error)) from error


@router.post("/scan/{file_id}", response_model=RecoveryResponse, status_code=status.HTTP_201_CREATED)
def scan_by_file_id(
    file_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return scan_file(db, file_id, settings)
    except RecoveryServiceError as error:
        response_status = (
            status.HTTP_404_NOT_FOUND
            if str(error) == "File not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=response_status, detail=str(error)) from error


@router.get("/results/{recovery_id}", response_model=RecoveryResponse)
def results(recovery_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return get_scan_results(db, recovery_id)
    except RecoveryServiceError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error