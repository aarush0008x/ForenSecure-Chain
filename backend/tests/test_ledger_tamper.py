from datetime import UTC, datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.blockchain.ledger import append_block, verify_chain
from app.db.base import Base
from app.db.database import get_db
from app.db.models.blockchain_block import BlockchainBlock
from app.main import app


def test_ledger_tamper_detection_and_actor_tracking() -> None:
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
    client = TestClient(app)

    try:
        with test_session() as session:
            # Append initial valid blocks
            append_block(
                db=session,
                action="case_registration",
                file_id=None,
                file_hash="0" * 64,
                audit_data={"detail": "init"},
                actor_id="user-inv-01",
                case_id="case-101",
            )
            append_block(
                db=session,
                action="evidence_acquisition",
                file_id="file-01",
                file_hash="a" * 64,
                audit_data={"detail": "acquired"},
                actor_id="user-inv-01",
                case_id="case-101",
            )
            append_block(
                db=session,
                action="sanitization",
                file_id="file-01",
                file_hash="a" * 64,
                audit_data={"detail": "sanitized"},
                actor_id="user-off-01",
                case_id="case-101",
            )
            session.commit()

        # 1. Verify chain is initially valid
        res = client.get("/api/blockchain/verify")
        assert res.status_code == 200
        assert res.json()["valid"] is True
        assert res.json()["total_blocks"] == 3

        # 2. Check blocks endpoint returns actor_id and case_id
        blocks_res = client.get("/api/blockchain/blocks")
        assert blocks_res.status_code == 200
        blocks = blocks_res.json()["blocks"]
        assert blocks[0]["actor_id"] == "user-inv-01"
        assert blocks[0]["case_id"] == "case-101"

        # 3. Simulate malicious database tampering on block 1
        with test_session() as session:
            block1 = session.scalar(select(BlockchainBlock).where(BlockchainBlock.block_index == 1))
            block1.file_hash = "f" * 64  # Tamper with file hash
            session.commit()

        # 4. Verify chain detects tampering!
        tamper_res = client.get("/api/blockchain/verify")
        assert tamper_res.status_code == 200
        tamper_data = tamper_res.json()
        assert tamper_data["valid"] is False
        assert len(tamper_data["invalid_blocks"]) > 0

    finally:
        app.dependency_overrides.clear()
