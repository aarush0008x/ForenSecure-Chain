from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.blockchain.ledger import append_block
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.database import get_db
from app.db.models import AuditLog, File, Operation
from app.main import app


def test_file_audit_trail_is_chronological_and_links_blocks(tmp_path: Path) -> None:
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
    file_id = "audit-file-1"
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    actions = [
        ("upload", "uploaded", None),
        ("hashing", "verified", "operation-hash"),
        ("erasure", "completed", "operation-erasure"),
        ("recovery", "completed", "operation-recovery"),
        ("verification", "VERIFIED", "operation-verification"),
        ("report_generation", "completed", "operation-report"),
    ]

    try:
        with test_session() as session:
            session.add(
                File(
                    file_id=file_id,
                    original_filename="audit.bin",
                    file_path="uploads/audit.bin",
                    file_size=10,
                    file_type="application/octet-stream",
                    original_hash="a" * 64,
                    status="uploaded",
                )
            )
            for index, (action, event_status, operation_id) in enumerate(actions):
                if operation_id:
                    session.add(
                        Operation(
                            operation_id=operation_id,
                            file_id=file_id,
                            operation_type=action,
                            status=event_status,
                            started_at=base_time + timedelta(minutes=index),
                            completed_at=base_time + timedelta(minutes=index),
                        )
                    )
                audit_id = f"audit-{index}"
                timestamp = base_time + timedelta(minutes=index)
                session.add(
                    AuditLog(
                        audit_id=audit_id,
                        file_id=file_id,
                        operation_id=operation_id,
                        action=action,
                        timestamp=timestamp,
                        hash=f"{index:064d}",
                        details={"status": event_status, "sequence": index},
                    )
                )
                append_block(
                    session,
                    action=action,
                    file_id=file_id,
                    file_hash="a" * 64,
                    audit_data={"audit_id": audit_id, "status": event_status},
                    timestamp=timestamp,
                )
            session.commit()

        response = TestClient(app).get(f"/api/audit/{file_id}")
        assert response.status_code == 200
        payload = response.json()
        assert payload["file_id"] == file_id
        assert payload["total_events"] == len(actions)
        assert [event["action"] for event in payload["events"]] == [
            action for action, _, _ in actions
        ]
        assert [event["blockchain_block_index"] for event in payload["events"]] == list(range(6))
        assert payload["events"][0]["operation_id"] is None
        assert payload["events"][1]["operation_id"] == "operation-hash"
        assert payload["events"][4]["status"] == "VERIFIED"
        assert payload["events"][5]["details"]["sequence"] == 5
    finally:
        app.dependency_overrides.clear()


def test_audit_trail_returns_not_found_for_unknown_file(tmp_path: Path) -> None:
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
    try:
        response = TestClient(app).get("/api/audit/missing-file")
        assert response.status_code == 404
        assert response.json()["detail"] == "File not found"
    finally:
        app.dependency_overrides.clear()