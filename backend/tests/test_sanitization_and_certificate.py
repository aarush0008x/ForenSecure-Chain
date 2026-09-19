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


def test_sanitization_execution_and_verifiable_certificate(tmp_path: Path) -> None:
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

        # Login
        inv_res = client.post("/api/auth/login", json={"email": "investigator@forensecure.local", "password": "Investigator@123"})
        inv_token = inv_res.json()["access_token"]
        inv_headers = {"Authorization": f"Bearer {inv_token}"}

        off1_res = client.post("/api/auth/login", json={"email": "officer1@forensecure.local", "password": "Officer@123"})
        off1_headers = {"Authorization": f"Bearer {off1_res.json()['access_token']}"}

        off2_res = client.post("/api/auth/login", json={"email": "officer2@forensecure.local", "password": "Officer@123"})
        off2_headers = {"Authorization": f"Bearer {off2_res.json()['access_token']}"}

        # 1. Create Case and acquire file
        case_res = client.post(
            "/api/cases",
            json={"case_number": "CASE-SAN-001", "title": "Sanitization Test", "legal_hold": False},
            headers=inv_headers,
        )
        case_id = case_res.json()["id"]

        sample_content = b"Top secret classified forensic target data"
        upload_res = client.post(
            f"/api/cases/{case_id}/evidence",
            files={"upload": ("secret.dat", io.BytesIO(sample_content), "application/octet-stream")},
            headers=inv_headers,
        )
        file_id = upload_res.json()["file_id"]
        original_hash = upload_res.json()["original_hash"]

        # 2. Request sanitization approval
        appr_res = client.post(
            f"/api/cases/{case_id}/approval-request",
            json={"target_id": file_id, "sanitization_method": "overwrite_then_delete"},
            headers=inv_headers,
        )
        approval_id = appr_res.json()["id"]

        # 3. Attempt execution before approval -> MUST FAIL
        pre_exec = client.post(f"/api/sanitization/{approval_id}/execute")
        assert pre_exec.status_code == 400
        assert "locked" in pre_exec.json()["detail"].lower()

        # 4. Perform 1st approval
        client.post(f"/api/approvals/{approval_id}/approve", headers=off1_headers)
        # Still cannot execute (only 1 approval)
        mid_exec = client.post(f"/api/sanitization/{approval_id}/execute")
        assert mid_exec.status_code == 400

        # 5. Perform 2nd approval
        client.post(f"/api/approvals/{approval_id}/approve", headers=off2_headers)

        # 6. Execute sanitization successfully
        exec_res = client.post(f"/api/sanitization/{approval_id}/execute")
        assert exec_res.status_code == 200
        cert_data = exec_res.json()
        assert cert_data["status"] == "completed"
        assert cert_data["original_hash"] == original_hash
        assert cert_data["verification_token"].startswith("VTOK-")
        assert cert_data["certificate_number"].startswith("CERT-FS-")
        cert_id = cert_data["certificate_id"]
        token = cert_data["verification_token"]

        # 7. File is now marked erased
        file_check = client.get(f"/api/files/{file_id}")
        assert file_check.status_code == 200
        assert file_check.json()["status"] == "erased"

        # 8. Downloadable PDF Certificate
        pdf_res = client.get(f"/api/sanitization/{cert_id}/certificate/pdf")
        assert pdf_res.status_code == 200
        assert pdf_res.headers["content-type"] == "application/pdf"
        assert len(pdf_res.content) > 1000

        # 9. Public verification token check
        verify_res = client.get(f"/api/sanitization/verify/{token}")
        assert verify_res.status_code == 200
        verify_data = verify_res.json()
        assert verify_data["verified"] is True
        assert verify_data["original_hash"] == original_hash
        assert verify_data["certificate_number"] == cert_data["certificate_number"]

        # 10. Repeat sanitization on erased file is rejected
        appr_res2 = client.post(
            f"/api/cases/{case_id}/approval-request",
            json={"target_id": file_id, "sanitization_method": "overwrite_then_delete"},
            headers=inv_headers,
        )
        approval_id2 = appr_res2.json()["id"]
        client.post(f"/api/approvals/{approval_id2}/approve", headers=off1_headers)
        client.post(f"/api/approvals/{approval_id2}/approve", headers=off2_headers)
        repeat_res = client.post(f"/api/sanitization/{approval_id2}/execute")
        assert repeat_res.status_code == 409

    finally:
        app.dependency_overrides.clear()
