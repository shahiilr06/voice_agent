import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.database import Base
from api.models.room import Room
from api.models.booking import Booking
from api.services.room_service import check_availability, create_room, get_all_rooms
from api.services.booking_service import create_booking, get_booking_by_code, cancel_booking
from api.services.embedding_service import embed_text, cosine_similarity
from api.services.vector_service import semantic_room_search
from api.schemas.room import RoomCreate
from api.schemas.booking import BookingCreateRequest


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()

    # Seed 2 test rooms
    r1 = Room(
        room_number="101",
        name="Deluxe Sea View",
        type="deluxe",
        floor=1,
        max_guests=2,
        price_per_night=4000.0,
        amenities=["Sea View", "AC", "WiFi"],
        description="Luxury room with sea view and king size bed",
        description_vector=embed_text("Luxury room with sea view and king size bed"),
        is_active=True,
    )
    r2 = Room(
        room_number="102",
        name="Standard Garden",
        type="standard",
        floor=1,
        max_guests=1,
        price_per_night=2000.0,
        amenities=["Garden View", "WiFi"],
        description="Cozy standard room with garden view",
        description_vector=embed_text("Cozy standard room with garden view"),
        is_active=True,
    )
    db.add(r1)
    db.add(r2)
    db.commit()

    yield db
    db.close()


def test_availability_and_overlap(test_db):
    today = date.today()
    d1 = today + timedelta(days=1)
    d3 = today + timedelta(days=3)
    d5 = today + timedelta(days=5)

    # Initially both rooms are available
    available = check_availability(test_db, "deluxe", d1, d3, num_guests=2)
    assert len(available) == 1
    assert available[0].room_number == "101"

    # Create a booking on room 101 from d1 to d3
    room = available[0]
    req = BookingCreateRequest(
        guest_name="Karthik Raja",
        guest_phone="9876543210",
        room_type="deluxe",
        check_in=d1,
        check_out=d3,
        num_guests=2,
    )
    booking = create_booking(test_db, req, room)
    assert booking.confirmation_code.startswith("BK-")
    assert float(booking.total_price) == 8000.0  # 2 nights * 4000

    # Overlapping check: same dates should return NO rooms
    avail_overlap = check_availability(test_db, "deluxe", d1, d3, num_guests=2)
    assert len(avail_overlap) == 0

    # Non-overlapping check: d3 to d5 should return room 101 as available again!
    avail_future = check_availability(test_db, "deluxe", d3, d5, num_guests=2)
    assert len(avail_future) == 1
    assert avail_future[0].room_number == "101"


def test_guest_capacity_constraint(test_db):
    today = date.today()
    d1 = today + timedelta(days=1)
    d2 = today + timedelta(days=2)

    # Standard room only holds 1 guest. Requesting for 3 should return 0 rooms
    avail = check_availability(test_db, "standard", d1, d2, num_guests=3)
    assert len(avail) == 0


def test_booking_cancellation(test_db):
    today = date.today()
    d1 = today + timedelta(days=1)
    d2 = today + timedelta(days=2)

    room = check_availability(test_db, "standard", d1, d2, num_guests=1)[0]
    req = BookingCreateRequest(
        guest_name="Priya",
        guest_phone="9123456789",
        room_type="standard",
        check_in=d1,
        check_out=d2,
        num_guests=1,
    )
    booking = create_booking(test_db, req, room)
    code = booking.confirmation_code

    # Room is booked
    assert len(check_availability(test_db, "standard", d1, d2, num_guests=1)) == 0

    # Cancel booking
    cancelled = cancel_booking(test_db, code)
    assert cancelled.status == "cancelled"

    # Room should now be available again!
    assert len(check_availability(test_db, "standard", d1, d2, num_guests=1)) == 1


def test_vector_search(test_db):
    results = semantic_room_search(test_db, "ocean sea view room", limit=2)
    assert len(results) >= 1
    top_room, score = results[0]
    assert top_room.name == "Deluxe Sea View"
    assert score > 0.0
