from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.audit import AuditTrailResponse
from app.services.audit_service import AuditServiceError, get_file_audit_trail


router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/{file_id}", response_model=AuditTrailResponse)
def audit_trail(file_id: str, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        return get_file_audit_trail(db, file_id)
    except AuditServiceError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error