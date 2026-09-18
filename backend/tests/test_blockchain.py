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
from app.db.models import BlockchainBlock
from app.main import app


def test_blockchain_list_file_query_and_tamper_detection(tmp_path: Path) -> None:
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
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)

    try:
        with test_session() as session:
            append_block(
                session,
                action="upload",
                file_id="file-1",
                file_hash="a" * 64,
                audit_data={"audit_id": "audit-1"},
                timestamp=timestamp,
            )
            append_block(
                session,
                action="recovery",
                file_id="file-1",
                file_hash="b" * 64,
                audit_data={"audit_id": "audit-2"},
                timestamp=timestamp,
            )
            append_block(
                session,
                action="report_generation",
                file_id="file-1",
                file_hash="b" * 64,
                audit_data={"audit_id": "audit-3"},
                timestamp=timestamp,
            )
            session.commit()

        client = TestClient(app)
        valid = client.get("/api/blockchain/verify")
        assert valid.status_code == 200
        assert valid.json() == {"valid": True, "total_blocks": 3, "invalid_blocks": []}

        listing = client.get("/api/blockchain")
        assert listing.status_code == 200
        assert listing.json()["total_blocks"] == 3
        assert [block["block_index"] for block in listing.json()["blocks"]] == [0, 1, 2]

        file_blocks = client.get("/api/blockchain/file/file-1")
        assert file_blocks.status_code == 200
        assert file_blocks.json()["total_blocks"] == 3

        with test_session() as session:
            second_block = session.scalar(
                select(BlockchainBlock).where(BlockchainBlock.block_index == 1)
            )
            assert second_block is not None
            second_block.current_hash = "f" * 64
            session.commit()

        tampered = client.get("/api/blockchain/verify")
        assert tampered.status_code == 200
        assert tampered.json()["valid"] is False
        assert tampered.json()["invalid_blocks"][0]["block_index"] == 1
        assert "current_hash_invalid" in tampered.json()["invalid_blocks"][0]["reasons"]
    finally:
        app.dependency_overrides.clear()