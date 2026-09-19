from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.database import get_db
from app.db.models import Case
from app.main import app
from app.security.auth import seed_default_users


def test_two_person_approval_workflow(tmp_path: Path) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: Settings(storage_dir=tmp_path)
    client = TestClient(app)

    try:
        with test_session() as session:
            seed_default_users(session)

        # Login tokens
        inv_res = client.post("/api/auth/login", json={"email": "investigator@forensecure.local", "password": "Investigator@123"})
        inv_token = inv_res.json()["access_token"]
        inv_headers = {"Authorization": f"Bearer {inv_token}"}

        off1_res = client.post("/api/auth/login", json={"email": "officer1@forensecure.local", "password": "Officer@123"})
        off1_token = off1_res.json()["access_token"]
        off1_headers = {"Authorization": f"Bearer {off1_token}"}

        off2_res = client.post("/api/auth/login", json={"email": "officer2@forensecure.local", "password": "Officer@123"})
        off2_token = off2_res.json()["access_token"]
        off2_headers = {"Authorization": f"Bearer {off2_token}"}

        # Create case without legal hold
        case_res = client.post(
            "/api/cases",
            json={"case_number": "CASE-APPROVAL-01", "title": "Approval Test", "legal_hold": False},
            headers=inv_headers,
        )
        case_id = case_res.json()["id"]

        # Request sanitization approval
        appr_req = client.post(
            f"/api/cases/{case_id}/approval-request",
            json={"target_id": "file-123", "target_type": "file", "sanitization_method": "overwrite_then_delete"},
            headers=inv_headers,
        )
        assert appr_req.status_code == 201
        approval_id = appr_req.json()["id"]
        assert appr_req.json()["status"] == "pending_first_approval"

        # 1. Investigator attempts to approve -> 403 Forbidden (RBAC violation)
        inv_approve = client.post(f"/api/approvals/{approval_id}/approve", headers=inv_headers)
        assert inv_approve.status_code == 403

        # 2. Officer 1 approves -> status becomes pending_second_approval
        first_approve = client.post(
            f"/api/approvals/{approval_id}/approve",
            json={"note": "Primary review verified - case closed"},
            headers=off1_headers,
        )
        assert first_approve.status_code == 200
        assert first_approve.json()["status"] == "pending_second_approval"

        # 3. Officer 1 attempts second approval -> 403 Forbidden (must be distinct approver)
        dup_approve = client.post(f"/api/approvals/{approval_id}/approve", headers=off1_headers)
        assert dup_approve.status_code == 403
        assert "distinct officer" in dup_approve.json()["detail"].lower()

        # 4. Officer 2 approves -> status becomes approved
        second_approve = client.post(
            f"/api/approvals/{approval_id}/approve",
            json={"note": "Secondary review confirmed - proceed to sanitize"},
            headers=off2_headers,
        )
        assert second_approve.status_code == 200
        assert second_approve.json()["status"] == "approved"

    finally:
        app.dependency_overrides.clear()


def test_approval_rejection_workflow(tmp_path: Path) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: Settings(storage_dir=tmp_path)
    client = TestClient(app)

    try:
        with test_session() as session:
            seed_default_users(session)

        inv_res = client.post("/api/auth/login", json={"email": "investigator@forensecure.local", "password": "Investigator@123"})
        inv_headers = {"Authorization": f"Bearer {inv_res.json()['access_token']}"}

        off1_res = client.post("/api/auth/login", json={"email": "officer1@forensecure.local", "password": "Officer@123"})
        off1_headers = {"Authorization": f"Bearer {off1_res.json()['access_token']}"}

        case_res = client.post(
            "/api/cases",
            json={"case_number": "CASE-REJECT-01", "title": "Reject Test", "legal_hold": False},
            headers=inv_headers,
        )
        case_id = case_res.json()["id"]

        appr_req = client.post(
            f"/api/cases/{case_id}/approval-request",
            json={"target_id": "file-reject", "target_type": "file"},
            headers=inv_headers,
        )
        approval_id = appr_req.json()["id"]

        # Officer 1 rejects
        rej_res = client.post(
            f"/api/approvals/{approval_id}/reject",
            json={"note": "Evidence may still be needed for appellate review"},
            headers=off1_headers,
        )
        assert rej_res.status_code == 200
        assert rej_res.json()["status"] == "rejected"

        # Subsequent approve attempt fails
        retry_res = client.post(f"/api/approvals/{approval_id}/approve", headers=off1_headers)
        assert retry_res.status_code == 400
    finally:
        app.dependency_overrides.clear()
