import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.database import get_db
from app.db.models import AuditLog, BlockchainBlock, File
from app.main import app


def test_upload_list_and_get_file(tmp_path: Path) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = Settings(storage_dir=tmp_path, max_upload_size=1024)

    def override_get_db():
        with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    content = b"forensecure upload test"

    try:
        response = client.post(
            "/api/files/upload",
            files={"upload": ("evidence.txt", content, "text/plain")},
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["original_filename"] == "evidence.txt"
        assert payload["file_size"] == len(content)
        assert payload["original_hash"] == hashlib.sha256(content).hexdigest()

        stored_file = tmp_path / payload["file_path"]
        assert stored_file.is_file()
        assert stored_file.read_bytes() == content

        listing = client.get("/api/files")
        assert listing.status_code == 200
        assert listing.json()["total"] == 1

        detail = client.get(f"/api/files/{payload['file_id']}")
        assert detail.status_code == 200
        assert detail.json()["file_id"] == payload["file_id"]

        with test_session() as session:
            file_record = session.get(File, payload["file_id"])
            audit_log = session.scalar(select(AuditLog).where(AuditLog.file_id == payload["file_id"]))
            block = session.scalar(
                select(BlockchainBlock).where(BlockchainBlock.file_id == payload["file_id"])
            )
            assert file_record is not None
            assert audit_log is not None
            assert block is not None
            assert block.file_hash == file_record.original_hash
            assert block.current_hash
    finally:
        app.dependency_overrides.clear()


def test_upload_rejects_file_over_limit(tmp_path: Path) -> None:
    settings = Settings(storage_dir=tmp_path, max_upload_size=3)
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)

    try:
        response = client.post(
            "/api/files/upload",
            files={"upload": ("too-large.txt", b"1234", "text/plain")},
        )
        assert response.status_code == 400
        assert "upload limit" in response.json()["detail"]
        assert not list((tmp_path / "uploads").glob("*"))
    finally:
        app.dependency_overrides.clear()