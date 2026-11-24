"""
Reservation lifecycle management and validation.
"""
import random
import string
from typing import Optional
from sqlalchemy.orm import Session
from api.models.booking import Booking
from api.models.room import Room
from api.schemas.booking import BookingCreateRequest


def generate_confirmation_code() -> str:
    """Generate unique hotel reservation code format: BK-XXXXXX."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(random.choices(chars, k=6))
    return f"BK-{suffix}"


def create_booking(
    db: Session,
    booking_in: BookingCreateRequest,
    room: Room,
) -> Booking:
    """
    Calculate duration, total price, and persist confirmed reservation.
    """
    nights = max((booking_in.check_out - booking_in.check_in).days, 1)
    total_price = float(room.price_per_night) * nights

    # Ensure unique confirmation code
    code = generate_confirmation_code()
    while db.query(Booking).filter(Booking.confirmation_code == code).first():
        code = generate_confirmation_code()

    booking = Booking(
        confirmation_code=code,
        room_id=room.id,
        guest_name=booking_in.guest_name.strip(),
        guest_phone=booking_in.guest_phone.strip(),
        guest_email=booking_in.guest_email.strip() if booking_in.guest_email else None,
        check_in=booking_in.check_in,
        check_out=booking_in.check_out,
        num_guests=booking_in.num_guests,
        total_price=total_price,
        status="confirmed",
        language_used=booking_in.language_used or "en-IN",
        raw_conversation=booking_in.raw_conversation,
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def get_booking_by_code(db: Session, confirmation_code: str) -> Optional[Booking]:
    clean_code = confirmation_code.strip().upper()
    return db.query(Booking).filter(Booking.confirmation_code == clean_code).first()


def cancel_booking(db: Session, confirmation_code: str) -> Optional[Booking]:
    booking = get_booking_by_code(db, confirmation_code)
    if not booking:
        return None
    booking.status = "cancelled"
    db.commit()
    db.refresh(booking)
    return booking
