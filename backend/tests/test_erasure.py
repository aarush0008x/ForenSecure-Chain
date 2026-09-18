import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.database import get_db
from app.db.models import AuditLog, BlockchainBlock, Certificate, File, Operation
from app.main import app


def _test_client(tmp_path: Path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = Settings(storage_dir=tmp_path)

    def override_get_db():
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app), test_session, settings


def test_erasure_deletes_controlled_file_and_creates_certificate(tmp_path: Path) -> None:
    client, test_session, settings = _test_client(tmp_path)
    content = b"controlled evidence content"
    file_id = "file-under-erasure-test"
    stored_path = settings.storage_dir / "uploads" / "evidence.bin"
    stored_path.parent.mkdir(parents=True)
    stored_path.write_bytes(content)

    with test_session() as session:
        session.add(
            File(
                file_id=file_id,
                original_filename="evidence.bin",
                file_path="uploads/evidence.bin",
                file_size=len(content),
                file_type="application/octet-stream",
                original_hash=hashlib.sha256(content).hexdigest(),
                status="uploaded",
            )
        )
        session.commit()

    try:
        response = client.post(f"/api/erasure/{file_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["certificate_id"]
        assert payload["file_id"] == file_id
        assert payload["original_hash"] == hashlib.sha256(content).hexdigest()
        assert payload["method"] == "overwrite_then_delete"
        assert payload["status"] == "completed"
        assert not stored_path.exists()

        certificate_response = client.get(f"/api/erasure/{file_id}/certificate")
        assert certificate_response.status_code == 200
        assert certificate_response.json() == payload

        with test_session() as session:
            file_record = session.get(File, file_id)
            operation = session.scalar(select(Operation).where(Operation.file_id == file_id))
            certificate = session.scalar(select(Certificate).where(Certificate.file_id == file_id))
            audit_log = session.scalar(select(AuditLog).where(AuditLog.file_id == file_id))
            block = session.scalar(select(BlockchainBlock).where(BlockchainBlock.file_id == file_id))
            assert file_record is not None and file_record.status == "erased"
            assert operation is not None and operation.status == "completed"
            assert certificate is not None
            assert audit_log is not None and audit_log.action == "erasure"
            assert block is not None and block.action == "erasure"

        repeated = client.post(f"/api/erasure/{file_id}")
        assert repeated.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_erasure_rejects_path_outside_controlled_storage(tmp_path: Path) -> None:
    client, test_session, settings = _test_client(tmp_path)
    outside_path = tmp_path.parent / "must-not-be-erased.bin"
    outside_content = b"outside controlled storage"
    outside_path.write_bytes(outside_content)
    file_id = "outside-path-test"

    with test_session() as session:
        session.add(
            File(
                file_id=file_id,
                original_filename=outside_path.name,
                file_path="../must-not-be-erased.bin",
                file_size=len(outside_content),
                file_type="application/octet-stream",
                original_hash=hashlib.sha256(outside_content).hexdigest(),
                status="uploaded",
            )
        )
        session.commit()

    try:
        response = client.post(f"/api/erasure/{file_id}")
        assert response.status_code == 400
        assert "outside controlled storage" in response.json()["detail"]
        assert outside_path.read_bytes() == outside_content
    finally:
        outside_path.unlink(missing_ok=True)
        app.dependency_overrides.clear()