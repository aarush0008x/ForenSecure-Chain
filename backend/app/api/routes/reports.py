from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.database import get_db
from app.schemas.report import ReportResponse
from app.services.report_service import (
    ReportServiceError,
    generate_report,
    report_path_for_file,
)


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/{file_id}/download")
def download_report(
    file_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    try:
        report_path = report_path_for_file(db, file_id, settings)
        return FileResponse(report_path, media_type="application/json", filename=f"{file_id}-report.json")
    except ReportServiceError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error


@router.get("/{file_id}", response_model=ReportResponse)
def report(
    file_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    try:
        return generate_report(db, file_id, settings)
    except ReportServiceError as error:
        response_status = (
            status.HTTP_404_NOT_FOUND
            if str(error) == "File not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=response_status, detail=str(error)) from error