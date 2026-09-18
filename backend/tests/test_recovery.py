import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.database import get_db
from app.db.models import AuditLog, BlockchainBlock, File, Operation, RecoveredFile, RecoveryRun
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


def _sample_binary() -> bytes:
    jpeg = b"\xff\xd8\xffjpeg sample\xff\xd9"
    pdf = b"%PDF-1.7\nprototype sample\n%%EOF"
    png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + b"\x00\x00\x00\x10\x00\x00\x00\x10\x08\x02\x00\x00\x00"
        + b"IEND\xaeB`\x82"
    )
    return b"controlled prefix" + jpeg + b"padding" + pdf + b"padding" + png


def test_scan_recovers_supported_signatures_and_records_audit(tmp_path: Path) -> None:
    client, test_session, settings = _test_client(tmp_path)
    source_data = _sample_binary()
    file_id = "controlled-recovery-source"
    source_path = settings.storage_dir / "samples" / "disk-image.bin"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source_data)

    with test_session() as session:
        session.add(
            File(
                file_id=file_id,
                original_filename="disk-image.bin",
                file_path="samples/disk-image.bin",
                file_size=len(source_data),
                file_type="application/octet-stream",
                original_hash=hashlib.sha256(source_data).hexdigest(),
                status="uploaded",
            )
        )
        session.commit()

    try:
        response = client.post("/api/recovery/scan", json={"file_id": file_id})
        assert response.status_code == 201
        payload = response.json()
        assert payload["file_id"] == file_id
        assert payload["number_of_files_detected"] == 3
        assert [artifact["file_type"] for artifact in payload["recovered_files"]] == [
            "image/jpeg",
            "application/pdf",
            "image/png",
        ]

        for artifact in payload["recovered_files"]:
            recovered_path = settings.storage_dir / artifact["recovered_path"]
            assert recovered_path.is_file()
            assert recovered_path.stat().st_size == artifact["file_size"]
            assert hashlib.sha256(recovered_path.read_bytes()).hexdigest() == artifact["recovered_hash"]
            assert artifact["metadata_info"]["actual"]
            assert artifact["metadata_info"]["inferred"]["boundary"]
            artifact_metadata = artifact["metadata_info"]["artifact"]
            assert artifact_metadata["filename"] == artifact["recovered_filename"]
            assert artifact_metadata["extension"]
            assert artifact_metadata["mime_type"] == artifact["file_type"]
            assert artifact_metadata["file_size"] == artifact["file_size"]
            assert artifact_metadata["sha256"] == artifact["recovered_hash"]
            source_metadata = artifact["metadata_info"]["source_filesystem"]
            assert source_metadata["available"] is True
            assert source_metadata["size"] == len(source_data)
            assert source_metadata["created_at"] is not None
            assert source_metadata["modified_at"] is not None

        result_response = client.get(f"/api/recovery/results/{payload['recovery_id']}")
        assert result_response.status_code == 200
        assert result_response.json() == payload

        with test_session() as session:
            run = session.get(RecoveryRun, payload["recovery_id"])
            operation = session.scalar(select(Operation).where(Operation.file_id == file_id))
            artifacts = list(session.scalars(select(RecoveredFile).where(RecoveredFile.file_id == file_id)))
            audit_log = session.scalar(select(AuditLog).where(AuditLog.file_id == file_id))
            block = session.scalar(select(BlockchainBlock).where(BlockchainBlock.file_id == file_id))
            assert run is not None and run.detected_count == 3
            assert operation is not None and operation.operation_type == "recovery"
            assert len(artifacts) == 3
            assert audit_log is not None and audit_log.action == "file_carving_scan"
            assert block is not None and block.action == "file_carving_scan"
    finally:
        app.dependency_overrides.clear()


def test_scan_rejects_source_outside_controlled_storage(tmp_path: Path) -> None:
    client, test_session, settings = _test_client(tmp_path)
    outside_path = tmp_path.parent / "outside-sample.bin"
    outside_data = b"must remain untouched"
    outside_path.write_bytes(outside_data)
    file_id = "outside-recovery-source"

    with test_session() as session:
        session.add(
            File(
                file_id=file_id,
                original_filename=outside_path.name,
                file_path="../outside-sample.bin",
                file_size=len(outside_data),
                file_type="application/octet-stream",
                original_hash=hashlib.sha256(outside_data).hexdigest(),
                status="uploaded",
            )
        )
        session.commit()

    try:
        response = client.post("/api/recovery/scan", json={"file_id": file_id})
        assert response.status_code == 400
        assert "outside controlled storage" in response.json()["detail"]
        assert outside_path.read_bytes() == outside_data
    finally:
        outside_path.unlink(missing_ok=True)
        app.dependency_overrides.clear()