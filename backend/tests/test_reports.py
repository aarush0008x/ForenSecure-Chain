import hashlib
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.blockchain.ledger import append_block
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.database import get_db
from app.db.models import AuditLog, BlockchainBlock, Certificate, File, Operation, RecoveredFile, RecoveryRun
from app.main import app


def test_report_contains_erasure_recovery_verification_and_download(tmp_path: Path) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = Settings(storage_dir=tmp_path)
    file_id = "report-file-1"
    source_hash = "a" * 64
    generated_at = datetime(2026, 1, 1, tzinfo=UTC)

    def override_get_db():
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings

    try:
        with test_session() as session:
            session.add(
                File(
                    file_id=file_id,
                    original_filename="evidence.bin",
                    file_path="uploads/evidence.bin",
                    file_size=42,
                    file_type="application/octet-stream",
                    original_hash=source_hash,
                    status="erased",
                )
            )
            session.add(
                Operation(
                    operation_id="verification-operation",
                    file_id=file_id,
                    operation_type="verification",
                    status="completed",
                    started_at=generated_at,
                    completed_at=generated_at,
                    details={
                        "comparison_result": "NOT_AVAILABLE",
                        "hash_algorithm": "SHA-256",
                    },
                )
            )
            session.add(
                AuditLog(
                    audit_id="verification-audit",
                    file_id=file_id,
                    operation_id="verification-operation",
                    action="verification",
                    timestamp=generated_at,
                    hash="b" * 64,
                    details={"comparison_result": "NOT_AVAILABLE"},
                )
            )
            session.add(
                Certificate(
                    certificate_id="erasure-certificate",
                    file_id=file_id,
                    certificate_type="overwrite_then_delete",
                    generated_at=generated_at,
                    details={
                        "original_hash": source_hash,
                        "file_size": 42,
                        "method": "overwrite_then_delete",
                        "status": "completed",
                    },
                )
            )
            session.add(
                RecoveryRun(
                    recovery_id="recovery-1",
                    file_id=file_id,
                    status="completed",
                    started_at=generated_at,
                    completed_at=generated_at,
                    source_hash=source_hash,
                    detected_count=1,
                    details={"source_path": "uploads/evidence.bin", "source_size": 42},
                )
            )
            recovered_bytes = b"recovered"
            recovered_path = settings.storage_dir / "recovered" / "recovery-1" / "recovered.txt"
            recovered_path.parent.mkdir(parents=True)
            recovered_path.write_bytes(recovered_bytes)
            session.add(
                RecoveredFile(
                    recovery_id="recovered-1",
                    recovery_run_id="recovery-1",
                    file_id=file_id,
                    recovered_filename="recovered.txt",
                    file_type="text/plain",
                    file_size=len(recovered_bytes),
                    recovered_path="recovered/recovery-1/recovered.txt",
                    recovered_hash=hashlib.sha256(recovered_bytes).hexdigest(),
                    recovery_timestamp=generated_at,
                    metadata_info={"actual": {"format": "text"}, "inferred": {}},
                )
            )
            append_block(
                session,
                action="verification",
                file_id=file_id,
                file_hash=source_hash,
                audit_data={"audit_id": "verification-audit"},
                timestamp=generated_at,
            )
            session.commit()

        client = TestClient(app)
        response = client.get(f"/api/reports/{file_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["file_id"] == file_id
        assert payload["erasure_certificate"]["certificate_id"] == "erasure-certificate"
        assert payload["erasure_certificate"]["original_filename"] == "evidence.bin"
        assert payload["recovery_reports"][0]["recovery_id"] == "recovery-1"
        assert payload["recovery_reports"][0]["recovered_files"][0]["sha256"] == hashlib.sha256(recovered_bytes).hexdigest()
        assert payload["verification_information"]["comparison_result"] == "NOT_AVAILABLE"
        assert payload["blockchain_audit_references"][-1]["action"] == "report_generation"
        assert (settings.storage_dir / payload["report_path"]).is_file()

        download = client.get(f"/api/reports/{file_id}/download")
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/json")
        assert download.json()["file_id"] == file_id

        with test_session() as session:
            report_operation = session.scalar(
                select(Operation).where(Operation.operation_type == "report_generation")
            )
            report_audit = session.scalar(
                select(AuditLog).where(AuditLog.action == "report_generation")
            )
            report_block = session.scalar(
                select(BlockchainBlock).where(BlockchainBlock.action == "report_generation")
            )
            assert report_operation is not None
            assert report_audit is not None and len(report_audit.hash) == 64
            assert report_block is not None
    finally:
        app.dependency_overrides.clear()


def test_report_requires_erasure_or_recovery_evidence(tmp_path: Path) -> None:
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
    try:
        with test_session() as session:
            session.add(
                File(
                    file_id="no-evidence",
                    original_filename="empty.bin",
                    file_path="uploads/empty.bin",
                    file_size=0,
                    file_type="application/octet-stream",
                    original_hash="a" * 64,
                    status="uploaded",
                )
            )
            session.commit()
        response = TestClient(app).get("/api/reports/no-evidence")
        assert response.status_code == 400
        assert response.json()["detail"] == "No erasure or recovery evidence available"
    finally:
        app.dependency_overrides.clear()