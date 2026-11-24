"""
Room catalog and date-range availability management.
"""
from typing import List, Optional
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from api.models.room import Room
from api.models.booking import Booking
from api.schemas.room import RoomCreate


def check_availability(
    db: Session,
    room_type: Optional[str],
    check_in: date,
    check_out: date,
    num_guests: int = 1,
) -> List[Room]:
    """
    Find active rooms that are NOT overlapping with confirmed reservations
    during [check_in, check_out) and meet guest count & type constraints.
    """
    # Find room IDs booked in overlapping date window
    overlapping_booked_rooms = (
        db.query(Booking.room_id)
        .filter(
            Booking.status == "confirmed",
            and_(
                Booking.check_in < check_out,
                Booking.check_out > check_in,
            )
        )
        .scalar_subquery()
    )

    query = db.query(Room).filter(
        Room.is_active == True,
        Room.max_guests >= num_guests,
        ~Room.id.in_(overlapping_booked_rooms)
    )

    if room_type and room_type.strip():
        clean_type = room_type.strip().lower()
        query = query.filter(
            or_(
                Room.type.ilike(f"%{clean_type}%"),
                Room.name.ilike(f"%{clean_type}%"),
                Room.description.ilike(f"%{clean_type}%"),
            )
        )

    return query.order_by(Room.price_per_night.asc()).all()


def get_all_rooms(db: Session, active_only: bool = True) -> List[Room]:
    query = db.query(Room)
    if active_only:
        query = query.filter(Room.is_active == True)
    return query.order_by(Room.room_number.asc()).all()


def get_room_by_id(db: Session, room_id: int) -> Optional[Room]:
    return db.query(Room).filter(Room.id == room_id).first()


def create_room(db: Session, room_in: RoomCreate, embedding: Optional[List[float]] = None) -> Room:
    room = Room(
        name=room_in.name,
        room_number=room_in.room_number,
        type=room_in.type.lower(),
        floor=room_in.floor,
        max_guests=room_in.max_guests,
        price_per_night=room_in.price_per_night,
        amenities=room_in.amenities,
        description=room_in.description,
        description_ta=room_in.description_ta,
        description_vector=embedding,
        is_active=room_in.is_active,
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return room
