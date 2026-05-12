_BOOKINGS: dict[str, dict] = {}
_BOOKING_COUNTER = 1000

ROOM_CATALOG = {
    "standard": {
        "price": 500,
        "description": "Comfortable room with queen bed, Wi-Fi, and city view.",
    },
    "deluxe": {
        "price": 800,
        "description": "Larger room with king bed, work desk, and complimentary breakfast.",
    },
    "suite": {
        "price": 1200,
        "description": "Premium suite with living area, king bed, and priority service.",
    },
    "family": {
        "price": 950,
        "description": "Spacious room for families with extra bedding and kid-friendly setup.",
    },
}


def _normalize_room_type(room_type: str) -> str:
    return (room_type or "").strip().lower()


def list_room_details() -> list[dict]:
    details = []
    for room_type, room_data in ROOM_CATALOG.items():
        details.append(
            {
                "room_type": room_type,
                "price": room_data["price"],
                "description": room_data["description"],
            }
        )
    return details


def check_room(start_date: str, end_date: str, guests: int, room_type: str):
    """
    Check room availability and default nightly pricing for selected room type.
    """
    normalized_room = _normalize_room_type(room_type)
    if normalized_room not in ROOM_CATALOG:
        return {
            "status": "invalid_room_type",
            "message": "Invalid room type. Available types are standard, deluxe, suite, and family.",
            "available_room_types": list(ROOM_CATALOG.keys()),
        }

    room_data = ROOM_CATALOG[normalized_room]
    return {
        "status": "available",
        "room_type": normalized_room,
        "start_date": start_date,
        "end_date": end_date,
        "guests": guests,
        "price": room_data["price"],
        "description": room_data["description"],
    }


def book_room(name: str, phone: str, start_date: str, end_date: str, guests: int, room_type: str):
    """
    Create a booking and return a confirmation number.
    """
    global _BOOKING_COUNTER

    normalized_room = _normalize_room_type(room_type)
    if normalized_room not in ROOM_CATALOG:
        return {"status": "error", "message": "Invalid room type selected for booking."}

    _BOOKING_COUNTER += 1
    confirmation_number = f"CONF-{_BOOKING_COUNTER}"
    _BOOKINGS[confirmation_number] = {
        "name": name,
        "phone": phone,
        "start_date": start_date,
        "end_date": end_date,
        "guests": guests,
        "room_type": normalized_room,
        "price": ROOM_CATALOG[normalized_room]["price"],
        "status": "booked",
    }
    return {
        "status": "success",
        "confirmation_number": confirmation_number,
        "room_type": normalized_room,
        "price": ROOM_CATALOG[normalized_room]["price"],
    }


def cancel_booking(confirmation_number: str):
    """
    Cancel an existing booking by confirmation number.
    """
    booking = _BOOKINGS.get(confirmation_number)
    if not booking:
        return {"status": "not_found", "message": "No booking found with that confirmation number."}
    if booking["status"] == "cancelled":
        return {"status": "already_cancelled", "confirmation_number": confirmation_number}
    booking["status"] = "cancelled"
    return {"status": "cancelled", "confirmation_number": confirmation_number}


# Backward-compatible names for old flow.
def check_availability(start_date: str, end_date: str, guests: int, room_type: str):
    """
    Backward-compatible alias for check_room.
    """
    return check_room(start_date, end_date, guests, room_type)
