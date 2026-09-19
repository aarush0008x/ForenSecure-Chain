from app.db.base import Base
from app.db.database import SessionLocal, engine
from app.db import models
from app.security.auth import seed_default_users


def init_db() -> None:
    """Create all prototype tables for a local database."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_default_users(db)