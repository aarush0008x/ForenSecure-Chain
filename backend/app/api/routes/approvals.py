from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.blockchain.ledger import append_block
from app.db.database import get_db
from app.db.models import ActivityEvent, User
from app.db.models.approval import Approval
from app.schemas.approval import ApprovalDecisionRequest, ApprovalResponse
from app.security.auth import get_current_user, require_role

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.get("", response_model=list[ApprovalResponse])
def list_approvals(db: Session = Depends(get_db)) -> list[Approval]:
    return list(db.scalars(select(Approval).order_by(Approval.created_at.desc())))


@router.get("/{id}", response_model=ApprovalResponse)
def get_approval(id: str, db: Session = Depends(get_db)) -> Approval:
    approval = db.get(Approval, id)
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")
    return approval


@router.post("/{id}/approve", response_model=ApprovalResponse)
def approve_request(
    id: str,
    decision: ApprovalDecisionRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("authorized_officer", "admin")),
) -> Approval:
    approval = db.get(Approval, id)
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")

    if approval.status not in {"pending_first_approval", "pending_second_approval"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve request in status '{approval.status}'",
        )

    # Cannot approve own request
    if approval.requested_by == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requester cannot approve their own sanitization request",
        )

    note_text = decision.note if decision and decision.note else ""

    if approval.status == "pending_first_approval":
        approval.first_approved_by = current_user.id
        approval.status = "pending_second_approval"
        if note_text:
            approval.note = f"{approval.note or ''} [1st Approval Note: {note_text}]".strip()

        db.add(
            ActivityEvent(
                case_id=approval.case_id,
                event_type="approval_first_granted",
                source="Two-Person Approval Gate",
                description=f"First officer approval granted by {current_user.name} ({current_user.role})",
                metadata_json={"approval_id": approval.id, "approver": current_user.id},
            )
        )
    elif approval.status == "pending_second_approval":
        # Must be distinct second approver!
        if approval.first_approved_by == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Second approval must be granted by a distinct officer",
            )
        approval.second_approved_by = current_user.id
        approval.status = "approved"
        if note_text:
            approval.note = f"{approval.note or ''} [2nd Approval Note: {note_text}]".strip()

        db.add(
            ActivityEvent(
                case_id=approval.case_id,
                event_type="approval_final_granted",
                source="Two-Person Approval Gate",
                description=f"Dual-authorization complete: Final sanitization approval granted by {current_user.name}",
                metadata_json={"approval_id": approval.id, "approver": current_user.id},
            )
        )

    append_block(
        db=db,
        action=f"approval_{approval.status}",
        file_id=approval.target_id if approval.target_type == "file" else None,
        file_hash="0" * 64,
        audit_data={"approval_id": approval.id, "status": approval.status, "approver": current_user.name},
        actor_id=current_user.id,
        case_id=approval.case_id,
    )
    db.commit()
    db.refresh(approval)
    return approval


@router.post("/{id}/reject", response_model=ApprovalResponse)
def reject_request(
    id: str,
    decision: ApprovalDecisionRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("authorized_officer", "admin")),
) -> Approval:
    approval = db.get(Approval, id)
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found")

    if approval.status in {"approved", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject request in status '{approval.status}'",
        )

    note_text = decision.note if decision and decision.note else "Rejected by authorized officer"
    approval.status = "rejected"
    approval.note = f"{approval.note or ''} [Rejection: {note_text}]".strip()

    db.add(
        ActivityEvent(
            case_id=approval.case_id,
            event_type="approval_rejected",
            source="Two-Person Approval Gate",
            description=f"Sanitization request rejected by {current_user.name}: {note_text}",
            metadata_json={"approval_id": approval.id, "rejector": current_user.id},
        )
    )
    append_block(
        db=db,
        action="approval_rejected",
        file_id=approval.target_id if approval.target_type == "file" else None,
        file_hash="0" * 64,
        audit_data={"approval_id": approval.id, "reason": note_text},
        actor_id=current_user.id,
        case_id=approval.case_id,
    )
    db.commit()
    db.refresh(approval)
    return approval
