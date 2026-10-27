from pathlib import Path
from datetime import datetime

from sqlalchemy import create_engine, inspect, text
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
    pool_pre_ping=True,
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

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def create_tables():
    """
    Create all registered database tables.
    """

    from app.database import models

    Base.metadata.create_all(bind=engine)
    if "users" in inspect(engine).get_table_names():
        columns = {column["name"] for column in inspect(engine).get_columns("users")}
        legacy_auth_migration = "is_legacy" not in columns
        with engine.begin() as connection:
            if "username" not in columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(32)"))
            if "password_hash" not in columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
            if legacy_auth_migration:
                connection.execute(text("ALTER TABLE users ADD COLUMN is_legacy BOOLEAN NOT NULL DEFAULT 1"))
            if legacy_auth_migration:
                connection.execute(text("UPDATE users SET is_legacy = 1, password_hash = NULL"))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)"
            ))
            if connection.execute(text("SELECT 1 FROM users WHERE id = 1")).first() is None:
                connection.execute(text(
                    "INSERT INTO users (id, name, email, username, password_hash, is_legacy, created_at) "
                    "VALUES (1, 'Legacy Local Data', NULL, NULL, NULL, 1, :created_at)"
                ), {"created_at": datetime.utcnow()})

    owned_tables = (
        "notes",
        "marks",
        "study_plans",
        "memories",
        "reminders",
        "calendar_events",
        "conversations",
    )
    for table in owned_tables:
        if table in inspect(engine).get_table_names():
            columns = {column["name"] for column in inspect(engine).get_columns(table)}
            with engine.begin() as connection:
                if "user_id" not in columns:
                    nullability = " NOT NULL DEFAULT 1" if table == "conversations" else ""
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER{nullability}")
                    )
                connection.execute(
                    text(f"UPDATE {table} SET user_id = 1 WHERE user_id IS NULL")
                )
                connection.execute(
                    text(
                        f"CREATE INDEX IF NOT EXISTS ix_{table}_user_id "
                        f"ON {table} (user_id)"
                    )
                )
    if "study_plans" in inspect(engine).get_table_names():
        columns = {column["name"] for column in inspect(engine).get_columns("study_plans")}
        if "priority" not in columns:
            with engine.begin() as connection:
                connection.execute(text(
                    "ALTER TABLE study_plans ADD COLUMN priority VARCHAR(20) NOT NULL DEFAULT 'medium'"
                ))
        if "estimated_minutes" not in columns:
            with engine.begin() as connection:
                connection.execute(text(
                    "ALTER TABLE study_plans ADD COLUMN estimated_minutes INTEGER NOT NULL DEFAULT 60"
                ))
    if "notes" in inspect(engine).get_table_names():
        columns = {column["name"] for column in inspect(engine).get_columns("notes")}
        if "pdf_filename" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE notes ADD COLUMN pdf_filename VARCHAR(255)"))
        if "pdf_storage_name" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE notes ADD COLUMN pdf_storage_name VARCHAR(100)"))
    if "conversations" in inspect(engine).get_table_names():
        columns = {column["name"] for column in inspect(engine).get_columns("conversations")}
        if "template" not in columns:
            with engine.begin() as connection:
                connection.execute(text(
                    "ALTER TABLE conversations ADD COLUMN template VARCHAR(20) NOT NULL DEFAULT 'general'"
                ))
    from app.rag.vector_store import assign_legacy_owner

    assign_legacy_owner(1)