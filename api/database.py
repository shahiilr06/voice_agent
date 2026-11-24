"""
Database session management and connection setup.
Supports PostgreSQL (with native pgvector) and SQLite (with fallback) for zero-config local testing.
"""
import os
import json
from typing import Generator
from sqlalchemy import create_engine, TypeDecorator, Text, JSON
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hotel_booking.db")

# Detect engine dialect
is_sqlite = DATABASE_URL.startswith("sqlite")

connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class CompatibleVector(TypeDecorator):
    """
    Cross-dialect Vector column:
    Uses native pgvector Vector on PostgreSQL if available,
    and falls back to JSON-serialized floats on SQLite.
    """
    impl = JSON
    cache_ok = True

    def __init__(self, dimensions: int = 384, **kwargs):
        super().__init__(**kwargs)
        self.dimensions = dimensions

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            try:
                from pgvector.sqlalchemy import Vector
                return dialect.type_descriptor(Vector(self.dimensions))
            except ImportError:
                return dialect.type_descriptor(JSON())
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            if dialect and getattr(dialect, "name", "") == "postgresql":
                return value
            return json.dumps(list(value))
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return list(value)


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session and safely closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize tables in the database."""
    # Ensure all models are imported before creating tables
    import api.models.room # noqa: F401
    import api.models.booking # noqa: F401
    import api.models.faq # noqa: F401

    if not is_sqlite:
        with engine.connect() as conn:
            from sqlalchemy import text
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
            except Exception:
                pass

    Base.metadata.create_all(bind=engine)
