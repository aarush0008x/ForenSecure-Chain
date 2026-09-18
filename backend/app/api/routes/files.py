from fastapi import APIRouter, Depends, File as UploadFileParameter, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.database import get_db
from app.db.models import File
from app.schemas.file import FileListResponse, FileResponse
from app.services.file_service import FileServiceError, upload_file


router = APIRouter(prefix="/api/files", tags=["files"])


@router.post(
    "/upload",
    response_model=FileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload(
    upload: UploadFile = UploadFileParameter(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> File:
    try:
        return await upload_file(db, upload, settings)
    except FileServiceError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.get("", response_model=FileListResponse)
def list_files(db: Session = Depends(get_db)) -> FileListResponse:
    files = list(db.scalars(select(File).order_by(File.upload_timestamp.desc())))
    return FileListResponse(items=files, total=len(files))


@router.get("/{file_id}", response_model=FileResponse)
def get_file(file_id: str, db: Session = Depends(get_db)) -> File:
    file_record = db.get(File, file_id)
    if file_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return file_record