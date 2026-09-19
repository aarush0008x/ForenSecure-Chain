from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.blockchain.ledger import append_block
from app.core.config import Settings, get_settings
from app.db.database import get_db
from app.db.models import ActivityEvent, Case, Certificate, File, User
from app.db.models.approval import Approval
from app.db.models.sanitization_job import SanitizationJob
from app.reports.pdf_generator import generate_sanitization_certificate_pdf
from app.schemas.sanitization import (
    SanitizationCertificateResponse,
    SanitizationJobResponse,
)
from app.security.auth import get_current_user, get_optional_user
from app.services.erasure_service import _contained_regular_file, _overwrite_file, _sha256_file

router = APIRouter(prefix="/api/sanitization", tags=["sanitization"])


@router.post("/{approval_id}/execute", response_model=SanitizationCertificateResponse)
def execute_sanitization(
    approval_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    current_user: User | None = Depends(get_optional_user),
) -> SanitizationCertificateResponse:
    approval = db.get(Approval, approval_id)
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval record not found")

    if approval.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sanitization execution is locked. Current approval status: '{approval.status}'. Requires two-person approval.",
        )

    case_record = db.get(Case, approval.case_id) if approval.case_id else None
    if case_record and case_record.legal_hold:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot execute sanitization while case is under legal hold.",
        )

    file_record = db.get(File, approval.target_id)
    target_hash = ""
    target_name = approval.target_id

    if file_record:
        if file_record.status == "erased":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Target has already been sanitized")

        target_name = file_record.original_filename
        target_path = _contained_regular_file(file_record, settings)
        with target_path.open("rb") as source:
            file_size, original_hash = _sha256_file(source)

        if original_hash != file_record.original_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pre-sanitization hash verification mismatch",
            )
        target_hash = original_hash

        # Execute safe controlled prototype sanitization
        _overwrite_file(target_path, file_size)
        file_record.status = "erased"
    else:
        target_hash = "0" * 64

    # Create SanitizationJob
    completed_at = datetime.now(UTC)
    approver1 = db.get(User, approval.first_approved_by) if approval.first_approved_by else None
    approver2 = db.get(User, approval.second_approved_by) if approval.second_approved_by else None
    requester = db.get(User, approval.requested_by) if approval.requested_by else None

    job = SanitizationJob(
        case_id=approval.case_id,
        target_id=approval.target_id,
        target_type=approval.target_type,
        approval_id=approval.id,
        requested_by=approval.requested_by,
        approved_by=f"{approver1.name if approver1 else 'Officer 1'} & {approver2.name if approver2 else 'Officer 2'}",
        method=approval.sanitization_method,
        status="completed",
        started_at=completed_at,
        completed_at=completed_at,
    )
    db.add(job)
    db.flush()

    # Generate verification token & certificate number
    cert_num = f"CERT-FS-{datetime.now(UTC).strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"
    token = f"VTOK-{uuid4().hex[:12].upper()}"

    # Generate PDF
    pdf_bytes = generate_sanitization_certificate_pdf(
        certificate_number=cert_num,
        verification_token=token,
        case_number=case_record.case_number if case_record else "N/A",
        target_name=target_name,
        target_hash=target_hash,
        method=approval.sanitization_method,
        status="completed",
        requested_by_name=requester.name if requester else "Investigator",
        first_approver_name=approver1.name if approver1 else "Authorized Officer 1",
        second_approver_name=approver2.name if approver2 else "Authorized Officer 2",
        timestamp=completed_at,
    )

    cert_dir = settings.storage_dir / "certificates"
    cert_dir.mkdir(parents=True, exist_ok=True)
    pdf_filename = f"{cert_num}.pdf"
    pdf_file_path = cert_dir / pdf_filename
    pdf_file_path.write_bytes(pdf_bytes)

    relative_pdf_path = str(pdf_file_path.relative_to(settings.storage_dir))

    # Certificate entity
    cert = Certificate(
        file_id=approval.target_id if file_record else None,
        case_id=approval.case_id,
        sanitization_job_id=job.id,
        certificate_type="sanitization",
        certificate_number=cert_num,
        verification_token=token,
        generated_at=completed_at,
        signed_at=completed_at,
        certificate_path=relative_pdf_path,
        details={
            "certificate_number": cert_num,
            "verification_token": token,
            "target_id": approval.target_id,
            "original_hash": target_hash,
            "method": approval.sanitization_method,
            "status": "completed",
            "approval_id": approval.id,
            "approved_by": job.approved_by,
        },
    )
    db.add(cert)

    if approval.case_id:
        db.add(
            ActivityEvent(
                case_id=approval.case_id,
                event_type="sanitization_executed",
                source="Sanitization Service",
                description=f"Sanitization executed for target {approval.target_id} under policy '{approval.sanitization_method}'",
                metadata_json={"certificate_number": cert_num, "job_id": job.id},
            )
        )

    # Append to blockchain ledger
    append_block(
        db=db,
        action="sanitization_completed",
        file_id=approval.target_id if file_record else None,
        file_hash=target_hash,
        audit_data={"job_id": job.id, "cert_number": cert_num, "token": token},
        actor_id=current_user.id if current_user else None,
        case_id=approval.case_id,
    )
    db.commit()
    db.refresh(cert)

    return SanitizationCertificateResponse(
        certificate_id=cert.certificate_id,
        certificate_number=cert_num,
        verification_token=token,
        case_id=approval.case_id,
        target_id=approval.target_id,
        target_type=approval.target_type,
        method=approval.sanitization_method,
        original_hash=target_hash,
        status="completed",
        generated_at=cert.generated_at,
        signed_at=cert.signed_at,
        certificate_pdf_url=f"/api/sanitization/{cert.certificate_id}/certificate/pdf",
        details=cert.details,
    )


@router.get("/{id}/certificate", response_model=SanitizationCertificateResponse)
def get_certificate(id: str, db: Session = Depends(get_db)) -> SanitizationCertificateResponse:
    cert = db.get(Certificate, id)
    if not cert:
        cert = db.scalar(
            select(Certificate)
            .where(
                (Certificate.certificate_number == id)
                | (Certificate.verification_token == id)
                | (Certificate.sanitization_job_id == id)
                | (Certificate.file_id == id)
            )
            .order_by(Certificate.generated_at.desc())
        )
    if not cert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found")

    details = cert.details or {}
    return SanitizationCertificateResponse(
        certificate_id=cert.certificate_id,
        certificate_number=cert.certificate_number or details.get("certificate_number", "UNKNOWN"),
        verification_token=cert.verification_token or details.get("verification_token", "UNKNOWN"),
        case_id=cert.case_id,
        target_id=cert.file_id or details.get("target_id", "UNKNOWN"),
        target_type="file",
        method=details.get("method", cert.certificate_type),
        original_hash=details.get("original_hash", ""),
        status=details.get("status", "completed"),
        generated_at=cert.generated_at,
        signed_at=cert.signed_at or cert.generated_at,
        certificate_pdf_url=f"/api/sanitization/{cert.certificate_id}/certificate/pdf",
        details=cert.details,
    )


@router.get("/{id}/certificate/pdf")
def get_certificate_pdf(
    id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    cert = db.get(Certificate, id)
    if not cert:
        cert = db.scalar(
            select(Certificate)
            .where((Certificate.certificate_number == id) | (Certificate.file_id == id))
            .order_by(Certificate.generated_at.desc())
        )
    if not cert or not cert.certificate_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate PDF not found")

    pdf_path = (settings.storage_dir / cert.certificate_path).resolve()
    if not pdf_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate file missing")

    return Response(
        content=pdf_path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={pdf_path.name}"},
    )


@router.get("/verify/{token}")
def verify_token(token: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    cert = db.scalar(select(Certificate).where(Certificate.verification_token == token))
    if not cert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid verification token")

    details = cert.details or {}
    return {
        "verified": True,
        "certificate_number": cert.certificate_number,
        "token": cert.verification_token,
        "generated_at": cert.generated_at.isoformat(),
        "target_id": cert.file_id or details.get("target_id"),
        "original_hash": details.get("original_hash"),
        "method": details.get("method"),
        "status": details.get("status", "completed"),
    }
