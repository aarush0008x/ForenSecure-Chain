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
from app.recovery.carving import carve


def test_carver_detects_expanded_formats() -> None:
    # 1. Construct binary stream with JPEG, PNG, PDF, and ZIP
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xff\xd9"
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\x00\x00\x00\x1f\xf3\xffa\x00\x00\x00\x00IEND\xaeB`\x82"
    pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj\nxref\ntrailer<<>>\nstartxref\n%%EOF"
    zip_bytes = b"PK\x03\x04\x14\x00\x00\x00\x08\x00testfilePK\x05\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"

    raw_stream = b"NOISE_BEFORE_" + jpeg_bytes + b"_GAP_" + png_bytes + b"_GAP_" + pdf_bytes + b"_GAP_" + zip_bytes + b"_NOISE_AFTER"

    candidates = carve(raw_stream)
    carved_types = [c.file_type for c in candidates]

    assert "image/jpeg" in carved_types
    assert "image/png" in carved_types
    assert "application/pdf" in carved_types
    assert "application/zip" in carved_types


def test_recovery_endpoint_with_expanded_formats(tmp_path: Path) -> None:
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
        # Create dump with ZIP artifact
        zip_bytes = b"PK\x03\x04\x14\x00\x00\x00\x08\x00data.txtPK\x05\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
        dump = b"\x00" * 64 + zip_bytes + b"\x00" * 64

        upload_res = client.post(
            "/api/files/upload",
            files={"upload": ("memory_dump.raw", io.BytesIO(dump), "application/octet-stream")},
        )
        file_id = upload_res.json()["file_id"]

        scan_res = client.post(f"/api/recovery/scan/{file_id}")
        assert scan_res.status_code == 201
        scan_data = scan_res.json()
        assert scan_data["number_of_files_detected"] >= 1
        assert any(f["file_type"] == "application/zip" for f in scan_data["recovered_files"])

    finally:
        app.dependency_overrides.clear()
