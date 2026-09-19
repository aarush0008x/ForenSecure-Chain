from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File as UploadFileParameter,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.blockchain.ledger import append_block
from app.core.config import Settings, get_settings
from app.db.database import get_db
from app.db.models import ActivityEvent, Case, Device, File, User
from app.db.models.approval import Approval
from app.db.models.audit_log import AuditLog
from app.reports.pdf_generator import generate_case_report_pdf
from app.schemas.approval import ApprovalCreateRequest, ApprovalResponse
from app.schemas.case import (
    CaseCreateRequest,
    CaseDetailResponse,
    CaseResponse,
    CaseUpdateRequest,
    DeviceCreateRequest,
    DeviceResponse,
    TimelineEventResponse,
    TimelineResponse,
)
from app.schemas.file import FileResponse
from app.security.auth import get_current_user, get_optional_user
from app.services.file_service import FileServiceError, upload_file

router = APIRouter(prefix="/api/cases", tags=["cases"])


@router.post("", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    case_in: CaseCreateRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> Case:
    existing = db.scalar(select(Case).where(Case.case_number == case_in.case_number))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Case number '{case_in.case_number}' already exists",
        )

    investigator_id = current_user.id if current_user else None
    case_record = Case(
        case_number=case_in.case_number,
        title=case_in.title,
        description=case_in.description,
        investigator_id=investigator_id,
        status="open",
        legal_hold=case_in.legal_hold,
    )
    db.add(case_record)
    db.flush()

    # Timeline event
    event = ActivityEvent(
        case_id=case_record.id,
        event_type="case_created",
        source="Case Management",
        description=f"Case '{case_record.case_number}' registered: {case_record.title}",
        metadata_json={
            "legal_hold": case_record.legal_hold,
            "created_by": current_user.name if current_user else "System",
        },
    )
    db.add(event)

    # Append to tamper-evident ledger
    append_block(
        db=db,
        action="case_registration",
        file_id=None,
        file_hash="0" * 64,
        audit_data={"case_id": case_record.id, "case_number": case_record.case_number},
        actor_id=investigator_id,
        case_id=case_record.id,
    )
    db.commit()
    db.refresh(case_record)
    return case_record


@router.get("", response_model=list[CaseResponse])
def list_cases(
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> list[Case]:
    cases = list(db.scalars(select(Case).order_by(Case.created_at.desc())))
    return cases


@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case(case_id: str, db: Session = Depends(get_db)) -> CaseDetailResponse:
    case_record = db.get(Case, case_id)
    if not case_record:
        # Check by case_number as fallback
        case_record = db.scalar(select(Case).where(Case.case_number == case_id))
    if not case_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    devices = list(db.scalars(select(Device).where(Device.case_id == case_record.id)))
    files = list(db.scalars(select(File).where(File.case_id == case_record.id)))

    return CaseDetailResponse(
        id=case_record.id,
        case_number=case_record.case_number,
        title=case_record.title,
        description=case_record.description,
        investigator_id=case_record.investigator_id,
        status=case_record.status,
        legal_hold=case_record.legal_hold,
        created_at=case_record.created_at,
        closed_at=case_record.closed_at,
        devices=[DeviceResponse.model_validate(d) for d in devices],
        files=[FileResponse.model_validate(f) for f in files],
        total_evidence=len(files),
    )


@router.patch("/{case_id}/legal-hold", response_model=CaseResponse)
def update_legal_hold(
    case_id: str,
    legal_hold: bool,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> Case:
    case_record = db.get(Case, case_id)
    if not case_record:
        case_record = db.scalar(select(Case).where(Case.case_number == case_id))
    if not case_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    old_hold = case_record.legal_hold
    case_record.legal_hold = legal_hold
    if not legal_hold and case_record.status == "open":
        case_record.status = "in_progress"

    db.add(
        ActivityEvent(
            case_id=case_record.id,
            event_type="legal_hold_changed",
            source="Legal Closure Service",
            description=f"Legal hold changed from {old_hold} to {legal_hold}",
            metadata_json={"actor": current_user.name if current_user else "System"},
        )
    )
    append_block(
        db=db,
        action="legal_hold_update",
        file_id=None,
        file_hash="0" * 64,
        audit_data={"legal_hold": legal_hold, "previous": old_hold},
        actor_id=current_user.id if current_user else None,
        case_id=case_record.id,
    )
    db.commit()
    db.refresh(case_record)
    return case_record


@router.post("/{case_id}/devices", response_model=DeviceResponse, status_code=status.HTTP_201_CREATED)
def register_device(
    case_id: str,
    device_in: DeviceCreateRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> Device:
    case_record = db.get(Case, case_id)
    if not case_record:
        case_record = db.scalar(select(Case).where(Case.case_number == case_id))
    if not case_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    device = Device(
        case_id=case_record.id,
        device_type=device_in.device_type,
        serial_or_identifier=device_in.serial_or_identifier,
        source_hash=device_in.source_hash,
        acquisition_status=device_in.acquisition_status,
    )
    db.add(device)
    db.flush()

    db.add(
        ActivityEvent(
            case_id=case_record.id,
            event_type="device_registered",
            source="Forensic Acquisition",
            description=f"Registered device: {device.device_type} (S/N: {device.serial_or_identifier}) with baseline SHA-256",
            metadata_json={"source_hash": device.source_hash, "device_id": device.id},
        )
    )
    append_block(
        db=db,
        action="device_acquisition",
        file_id=None,
        file_hash=device.source_hash,
        audit_data={"device_id": device.id, "serial": device.serial_or_identifier},
        actor_id=current_user.id if current_user else None,
        case_id=case_record.id,
    )
    db.commit()
    db.refresh(device)
    return device


@router.post("/{case_id}/evidence", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def acquire_evidence(
    case_id: str,
    device_id: str | None = None,
    upload: UploadFile = UploadFileParameter(...),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: User | None = Depends(get_optional_user),
) -> File:
    case_record = db.get(Case, case_id)
    if not case_record:
        case_record = db.scalar(select(Case).where(Case.case_number == case_id))
    if not case_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    try:
        file_record = await upload_file(db, upload, settings)
        file_record.case_id = case_record.id
        file_record.device_id = device_id
        db.flush()

        db.add(
            ActivityEvent(
                case_id=case_record.id,
                event_type="evidence_acquired",
                source="Forensic Acquisition",
                description=f"Evidence file '{file_record.original_filename}' acquired into controlled custody",
                metadata_json={
                    "file_id": file_record.file_id,
                    "sha256": file_record.original_hash,
                    "size": file_record.file_size,
                },
            )
        )
        db.commit()
        db.refresh(file_record)
        return file_record
    except FileServiceError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/{case_id}/approval-request", response_model=ApprovalResponse, status_code=status.HTTP_201_CREATED)
def request_sanitization_approval(
    case_id: str,
    request_in: ApprovalCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Approval:
    case_record = db.get(Case, case_id)
    if not case_record:
        case_record = db.scalar(select(Case).where(Case.case_number == case_id))
    if not case_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    # IMPORTANT: Legal hold check!
    if case_record.legal_hold:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot request sanitization approval while case is under active legal hold. Release legal hold first.",
        )

    approval = Approval(
        case_id=case_record.id,
        requested_by=current_user.id,
        target_id=request_in.target_id,
        target_type=request_in.target_type,
        sanitization_method=request_in.sanitization_method,
        note=request_in.note,
        status="pending_first_approval",
    )
    db.add(approval)
    db.flush()

    db.add(
        ActivityEvent(
            case_id=case_record.id,
            event_type="sanitization_requested",
            source="Sanitization Service",
            description=f"Sanitization approval requested by {current_user.name} for target {approval.target_id}",
            metadata_json={"approval_id": approval.id, "method": approval.sanitization_method},
        )
    )
    append_block(
        db=db,
        action="approval_requested",
        file_id=approval.target_id if approval.target_type == "file" else None,
        file_hash="0" * 64,
        audit_data={"approval_id": approval.id, "method": approval.sanitization_method},
        actor_id=current_user.id,
        case_id=case_record.id,
    )
    db.commit()
    db.refresh(approval)
    return approval


@router.get("/{case_id}/timeline", response_model=TimelineResponse)
def get_case_timeline(case_id: str, db: Session = Depends(get_db)) -> TimelineResponse:
    case_record = db.get(Case, case_id)
    if not case_record:
        case_record = db.scalar(select(Case).where(Case.case_number == case_id))
    if not case_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    events = list(
        db.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.case_id == case_record.id)
            .order_by(ActivityEvent.timestamp.asc())
        )
    )

    return TimelineResponse(
        case_id=case_record.id,
        case_number=case_record.case_number,
        events=[TimelineEventResponse.model_validate(e) for e in events],
        total_events=len(events),
    )


@router.get("/{case_id}/report")
def get_case_report(
    case_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    case_record = db.get(Case, case_id)
    if not case_record:
        case_record = db.scalar(select(Case).where(Case.case_number == case_id))
    if not case_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    devices = list(db.scalars(select(Device).where(Device.case_id == case_record.id)))
    files = list(db.scalars(select(File).where(File.case_id == case_record.id)))
    events = list(
        db.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.case_id == case_record.id)
            .order_by(ActivityEvent.timestamp.asc())
        )
    )
    approvals = list(db.scalars(select(Approval).where(Approval.case_id == case_record.id)))

    return {
        "case_id": case_record.id,
        "case_number": case_record.case_number,
        "title": case_record.title,
        "description": case_record.description,
        "status": case_record.status,
        "legal_hold": case_record.legal_hold,
        "created_at": case_record.created_at.isoformat(),
        "devices": [
            {
                "id": d.id,
                "type": d.device_type,
                "serial": d.serial_or_identifier,
                "source_hash": d.source_hash,
                "status": d.acquisition_status,
            }
            for d in devices
        ],
        "evidence_files": [
            {
                "file_id": f.file_id,
                "filename": f.original_filename,
                "size": f.file_size,
                "original_hash": f.original_hash,
                "status": f.status,
            }
            for f in files
        ],
        "timeline": [
            {
                "event_type": e.event_type,
                "timestamp": e.timestamp.isoformat(),
                "source": e.source,
                "description": e.description,
            }
            for e in events
        ],
        "approvals": [
            {
                "id": a.id,
                "target_id": a.target_id,
                "status": a.status,
                "method": a.sanitization_method,
            }
            for a in approvals
        ],
    }


@router.get("/{case_id}/report/pdf")
def get_case_report_pdf(
    case_id: str,
    db: Session = Depends(get_db),
) -> Response:
    case_record = db.get(Case, case_id)
    if not case_record:
        case_record = db.scalar(select(Case).where(Case.case_number == case_id))
    if not case_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

    investigator_name = "Assigned Investigator"
    if case_record.investigator:
        investigator_name = case_record.investigator.name

    devices = [
        {
            "device_type": d.device_type,
            "serial_or_identifier": d.serial_or_identifier,
            "source_hash": d.source_hash,
            "acquisition_status": d.acquisition_status,
        }
        for d in db.scalars(select(Device).where(Device.case_id == case_record.id))
    ]
    files = [
        {
            "original_filename": f.original_filename,
            "file_size": f.file_size,
            "original_hash": f.original_hash,
            "status": f.status,
        }
        for f in db.scalars(select(File).where(File.case_id == case_record.id))
    ]
    events = [
        {
            "event_type": e.event_type,
            "timestamp": e.timestamp,
            "description": e.description,
        }
        for e in db.scalars(
            select(ActivityEvent)
            .where(ActivityEvent.case_id == case_record.id)
            .order_by(ActivityEvent.timestamp.asc())
        )
    ]

    pdf_bytes = generate_case_report_pdf(
        case_number=case_record.case_number,
        title=case_record.title,
        description=case_record.description,
        investigator_name=investigator_name,
        status=case_record.status,
        legal_hold=case_record.legal_hold,
        created_at=case_record.created_at,
        devices=devices,
        files=files,
        timeline_events=events,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=ForensicReport_{case_record.case_number}.pdf"},
    )
