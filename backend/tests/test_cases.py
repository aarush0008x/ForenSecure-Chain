import io
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.database import get_db
from app.main import app
from app.security.auth import seed_default_users


def test_case_lifecycle_device_and_legal_hold(tmp_path: Path) -> None:
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

        # Investigator login
        login_res = client.post(
            "/api/auth/login",
            json={"email": "investigator@forensecure.local", "password": "Investigator@123"},
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create Case
        case_res = client.post(
            "/api/cases",
            json={
                "case_number": "CASE-2026-001",
                "title": "Suspect Hard Drive Forensics",
                "description": "Investigation into unauthorized data exfiltration",
                "legal_hold": True,
            },
            headers=headers,
        )
        assert case_res.status_code == 201
        case_data = case_res.json()
        case_id = case_data["id"]
        assert case_data["case_number"] == "CASE-2026-001"
        assert case_data["legal_hold"] is True

        # 2. Register Device
        dev_res = client.post(
            f"/api/cases/{case_id}/devices",
            json={
                "device_type": "HDD - Western Digital 1TB",
                "serial_or_identifier": "WD-WCC4N012345",
                "source_hash": "e" * 64,
                "acquisition_status": "acquired",
            },
            headers=headers,
        )
        assert dev_res.status_code == 201
        dev_data = dev_res.json()
        dev_id = dev_data["id"]
        assert dev_data["serial_or_identifier"] == "WD-WCC4N012345"

        # 3. Acquire Evidence File
        sample_bytes = b"Crucial forensic evidentiary data"
        upload_res = client.post(
            f"/api/cases/{case_id}/evidence",
            params={"device_id": dev_id},
            files={"upload": ("evidence.raw", io.BytesIO(sample_bytes), "application/octet-stream")},
            headers=headers,
        )
        assert upload_res.status_code == 201
        file_data = upload_res.json()
        assert file_data["case_id"] == case_id
        file_id = file_data["file_id"]

        # 4. Attempt sanitization approval request while legal_hold is True -> MUST FAIL
        appr_res = client.post(
            f"/api/cases/{case_id}/approval-request",
            json={"target_id": file_id, "sanitization_method": "overwrite_then_delete"},
            headers=headers,
        )
        assert appr_res.status_code == 400
        assert "legal hold" in appr_res.json()["detail"].lower()

        # 5. Release legal hold
        hold_res = client.patch(
            f"/api/cases/{case_id}/legal-hold",
            params={"legal_hold": False},
            headers=headers,
        )
        assert hold_res.status_code == 200
        assert hold_res.json()["legal_hold"] is False

        # 6. Now sanitization approval request succeeds!
        appr_res2 = client.post(
            f"/api/cases/{case_id}/approval-request",
            json={"target_id": file_id, "sanitization_method": "overwrite_then_delete"},
            headers=headers,
        )
        assert appr_res2.status_code == 201
        assert appr_res2.json()["status"] == "pending_first_approval"

        # 7. Timeline reflects all operations chronologically
        timeline_res = client.get(f"/api/cases/{case_id}/timeline")
        assert timeline_res.status_code == 200
        timeline_data = timeline_res.json()
        assert timeline_data["total_events"] >= 4
        event_types = [e["event_type"] for e in timeline_data["events"]]
        assert "case_created" in event_types
        assert "device_registered" in event_types
        assert "evidence_acquired" in event_types
        assert "legal_hold_changed" in event_types
        assert "sanitization_requested" in event_types

        # 8. Evidence PDF report generation
        pdf_res = client.get(f"/api/cases/{case_id}/report/pdf")
        assert pdf_res.status_code == 200
        assert pdf_res.headers["content-type"] == "application/pdf"
        assert len(pdf_res.content) > 1000

    finally:
        app.dependency_overrides.clear()
