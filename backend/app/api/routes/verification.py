from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.database import get_db
from app.schemas.verification import VerificationResponse
from app.services.verification_service import VerificationServiceError, verify_file


router = APIRouter(prefix="/api/verification", tags=["verification"])


@router.get("/{file_id}", response_model=VerificationResponse)
def verification(
    file_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    try:
        return verify_file(db, file_id, settings)
    except VerificationServiceError as error:
        response_status = (
            status.HTTP_404_NOT_FOUND
            if str(error) == "File not found"
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=response_status, detail=str(error)) from error