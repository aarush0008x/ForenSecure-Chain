import hashlib
from datetime import UTC, datetime
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


def test_verification_returns_hashes_and_related_records(tmp_path: Path) -> None:
    client, test_session, settings = _test_client(tmp_path)
    source = b"source evidence"
    recovered = b"recovered evidence"
    file_id = "verification-source"
    source_path = settings.storage_dir / "uploads" / "source.bin"
    recovered_path = settings.storage_dir / "recovered" / "run-1" / "recovered.bin"
    source_path.parent.mkdir(parents=True)
    recovered_path.parent.mkdir(parents=True)
    source_path.write_bytes(source)
    recovered_path.write_bytes(recovered)
    source_hash = hashlib.sha256(source).hexdigest()
    recovered_hash = hashlib.sha256(recovered).hexdigest()

    with test_session() as session:
        session.add(
            File(
                file_id=file_id,
                original_filename="source.bin",
                file_path="uploads/source.bin",
                file_size=len(source),
                file_type="application/octet-stream",
                original_hash=source_hash,
                status="uploaded",
            )
        )
        session.add(
            RecoveryRun(
                recovery_id="run-1",
                file_id=file_id,
                status="completed",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                source_hash=source_hash,
                detected_count=1,
            )
        )
        session.add(
            RecoveredFile(
                recovery_id="recovered-1",
                recovery_run_id="run-1",
                file_id=file_id,
                recovered_filename="recovered.bin",
                file_type="application/octet-stream",
                file_size=len(recovered),
                recovered_path="recovered/run-1/recovered.bin",
                recovered_hash=recovered_hash,
                recovery_timestamp=datetime.now(UTC),
            )
        )
        session.commit()

    try:
        response = client.get(f"/api/verification/{file_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["hash_algorithm"] == "SHA-256"
        assert payload["original_hash"] == source_hash
        assert payload["current_hash"] == source_hash
        assert payload["comparison_result"] == "VERIFIED"
        assert payload["recovered_hashes"] == [
            {
                "recovery_id": "recovered-1",
                "recovered_filename": "recovered.bin",
                "stored_hash": recovered_hash,
                "current_hash": recovered_hash,
                "status": "VERIFIED",
            }
        ]
        assert payload["related_operation"]["operation_type"] == "verification"
        assert payload["related_blockchain_block"]["action"] == "verification"

        with test_session() as session:
            operation = session.scalar(select(Operation).where(Operation.file_id == file_id))
            audit_log = session.scalar(select(AuditLog).where(AuditLog.file_id == file_id))
            block = session.scalar(select(BlockchainBlock).where(BlockchainBlock.file_id == file_id))
            assert operation is not None and operation.operation_type == "verification"
            assert audit_log is not None and audit_log.action == "verification"
            assert block is not None and block.action == "verification"
    finally:
        app.dependency_overrides.clear()


def test_verification_reports_mismatch_and_unavailable(tmp_path: Path) -> None:
    client, test_session, settings = _test_client(tmp_path)
    file_id = "verification-state-source"
    source_path = settings.storage_dir / "uploads" / "state.bin"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"changed content")

    with test_session() as session:
        session.add(
            File(
                file_id=file_id,
                original_filename="state.bin",
                file_path="uploads/state.bin",
                file_size=11,
                file_type="application/octet-stream",
                original_hash=hashlib.sha256(b"original content").hexdigest(),
                status="uploaded",
            )
        )
        session.commit()

    try:
        mismatch = client.get(f"/api/verification/{file_id}")
        assert mismatch.status_code == 200
        assert mismatch.json()["comparison_result"] == "MISMATCH"

        source_path.unlink()
        unavailable = client.get(f"/api/verification/{file_id}")
        assert unavailable.status_code == 200
        assert unavailable.json()["comparison_result"] == "NOT_AVAILABLE"
        assert unavailable.json()["current_hash"] is None
    finally:
        app.dependency_overrides.clear()