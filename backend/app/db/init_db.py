from app.db.base import Base
from app.db.database import engine
from app.db import models


def init_db() -> None:
    """Create all prototype tables for a local database."""
    Base.metadata.create_all(bind=engine)