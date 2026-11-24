import pytest
from datetime import date, timedelta
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "bilingual_support" in data


def test_list_rooms_endpoint(client):
    resp = client.get("/rooms")
    assert resp.status_code == 200
    rooms = resp.json()
    assert isinstance(rooms, list)
    assert len(rooms) >= 1


def test_room_availability_endpoint(client):
    today = date.today()
    ci = (today + timedelta(days=10)).isoformat()
    co = (today + timedelta(days=12)).isoformat()

    payload = {
        "room_type": "deluxe",
        "check_in": ci,
        "check_out": co,
        "num_guests": 2,
    }
    resp = client.post("/rooms/availability", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "is_available" in data
    assert data["success"] is True


def test_semantic_search_endpoint(client):
    resp = client.get("/rooms/search?q=luxury+jacuzzi+skyline")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) > 0
    assert "similarity_score" in results[0]


def test_booking_lifecycle_api(client):
    today = date.today()
    ci = (today + timedelta(days=20)).isoformat()
    co = (today + timedelta(days=22)).isoformat()

    booking_payload = {
        "guest_name": "Sundar Pichai",
        "guest_phone": "9876543210",
        "room_type": "deluxe",
        "check_in": ci,
        "check_out": co,
        "num_guests": 2,
        "language_used": "ta-IN",
    }

    # 1. Create booking
    create_resp = client.post("/bookings/create", json=booking_payload)
    assert create_resp.status_code == 201
    booking_data = create_resp.json()
    code = booking_data["confirmation_code"]
    assert code.startswith("BK-")
    assert booking_data["status"] == "confirmed"

    # 2. Get booking
    get_resp = client.get(f"/bookings/{code}")
    assert get_resp.status_code == 200
    assert get_resp.json()["guest_name"] == "Sundar Pichai"

    # 3. Cancel booking
    del_resp = client.delete(f"/bookings/{code}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True


def test_livekit_token_generation(client):
    resp = client.get("/livekit/token?room=test-room&participant=guest-1")
    assert resp.status_code == 200
    token_data = resp.json()
    assert token_data["success"] is True
    assert "token" in token_data
    assert token_data["room"] == "test-room"
