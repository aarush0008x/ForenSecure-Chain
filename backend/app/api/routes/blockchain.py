from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import BlockchainBlock
from app.blockchain.ledger import verify_chain
from app.schemas.blockchain import (
    BlockchainFileResponse,
    BlockchainListResponse,
    BlockchainVerificationResponse,
)


router = APIRouter(prefix="/api/blockchain", tags=["blockchain"])


@router.get("", response_model=BlockchainListResponse)
@router.get("/blocks", response_model=BlockchainListResponse)
def list_blockchain(db: Session = Depends(get_db)) -> BlockchainListResponse:
    blocks = list(
        db.scalars(select(BlockchainBlock).order_by(BlockchainBlock.block_index.asc()))
    )
    return BlockchainListResponse(total_blocks=len(blocks), blocks=blocks)


@router.get("/verify", response_model=BlockchainVerificationResponse)
def verify_blockchain(db: Session = Depends(get_db)) -> dict[str, object]:
    return verify_chain(db)


@router.get("/file/{file_id}", response_model=BlockchainFileResponse)
def file_blockchain(file_id: str, db: Session = Depends(get_db)) -> BlockchainFileResponse:
    blocks = list(
        db.scalars(
            select(BlockchainBlock)
            .where(BlockchainBlock.file_id == file_id)
            .order_by(BlockchainBlock.block_index.asc())
        )
    )
    return BlockchainFileResponse(file_id=file_id, total_blocks=len(blocks), blocks=blocks)