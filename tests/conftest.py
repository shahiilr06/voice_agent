import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from api.database import Base, get_db
import api.database as db_module
from api.models.room import Room
from api.models.booking import Booking
from api.models.faq import FAQ
from seeds.seed_data import seed_database

TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["LIVEKIT_URL"] = "wss://test.livekit.cloud"
    os.environ["LIVEKIT_API_KEY"] = "test_key"
    os.environ["LIVEKIT_API_SECRET"] = "test_secret_123456789012345678901234"
    os.environ.pop("SARVAM_API_KEY", None)

    test_engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_module.engine = test_engine
    db_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Initialize and seed test database
    Base.metadata.create_all(bind=test_engine)
    session = db_module.SessionLocal()
    seed_database(session)
    session.close()

    yield


@pytest.fixture(autouse=True)
def clean_test_bookings():
    """Ensure bookings table is clean before each test to prevent date conflicts."""
    session = db_module.SessionLocal()
    try:
        session.query(Booking).delete()
        session.commit()
    finally:
        session.close()
