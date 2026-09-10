from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config.settings import DATABASE_URL


# SQLite requires this when using multiple threads,
# which is common with FastAPI.
connect_args = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {
        "check_same_thread": False
    }


engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


Base = declarative_base()


def get_db():
    """
    Provide a database session.
    """

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


def create_tables():
    """
    Create all registered database tables.
    """

    from app.database import models

    Base.metadata.create_all(bind=engine)