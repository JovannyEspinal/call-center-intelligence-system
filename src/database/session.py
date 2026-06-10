"""Database engine and session helpers."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from src.database.schema import Base


def create_sqlite_engine(database_path: str | Path) -> Engine:
    """Create a SQLite engine for the app or an isolated test database."""
    return create_engine(f"sqlite:///{database_path}", future=True)


def create_session_factory(engine: Engine) -> sessionmaker:
    """Create a SQLAlchemy session factory."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_database(engine: Engine) -> None:
    """Create persistence tables if they do not already exist."""
    Base.metadata.create_all(engine)
    ensure_schema_migrations(engine)


def ensure_schema_migrations(engine: Engine) -> None:
    """Apply tiny SQLite migrations needed by local schema iterations."""
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(transcription_cache_entries)"
            )
        }
        if "privacy_events_json" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE transcription_cache_entries "
                "ADD COLUMN privacy_events_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "cache_version" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE transcription_cache_entries "
                "ADD COLUMN cache_version TEXT NOT NULL DEFAULT 'legacy'"
            )
