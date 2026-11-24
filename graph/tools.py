"""
Backend tools executed by LangGraph nodes for availability and booking.
"""
from datetime import date
from typing import Dict, Any, Optional
import api.database as db_module
from api.services.room_service import check_availability
from api.services.booking_service import create_booking
from api.schemas.booking import BookingCreateRequest


def tool_check_availability(
    room_type: Optional[str],
    check_in: str,
    check_out: str,
    num_guests: int = 1,
) -> Dict[str, Any]:
    """Check availability in the database."""
    db = db_module.SessionLocal()
    try:
        ci = date.fromisoformat(check_in)
        co = date.fromisoformat(check_out)
        rooms = check_availability(
            db=db,
            room_type=room_type,
            check_in=ci,
            check_out=co,
            num_guests=num_guests,
        )
        if rooms:
            best_room = rooms[0]
            nights = max((co - ci).days, 1)
            total = float(best_room.price_per_night) * nights
            return {
                "is_available": True,
                "room_id": best_room.id,
                "room_name": best_room.name,
                "room_type": best_room.type,
                "price_per_night": float(best_room.price_per_night),
                "total_price": total,
                "available_count": len(rooms),
            }
        return {"is_available": False, "available_count": 0}
    except Exception as e:
        return {"is_available": False, "error": str(e)}
    finally:
        db.close()


def tool_create_booking(
    guest_name: str,
    guest_phone: str,
    room_type: str,
    check_in: str,
    check_out: str,
    num_guests: int = 1,
    language_used: str = "en-IN",
    raw_conversation: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist booking in the database."""
    db = db_module.SessionLocal()
    try:
        ci = date.fromisoformat(check_in)
        co = date.fromisoformat(check_out)
        rooms = check_availability(
            db=db,
            room_type=room_type,
            check_in=ci,
            check_out=co,
            num_guests=num_guests,
        )
        if not rooms:
            return {"success": False, "error": "No rooms available"}

        assigned = rooms[0]
        req = BookingCreateRequest(
            guest_name=guest_name,
            guest_phone=guest_phone,
            room_type=room_type,
            check_in=ci,
            check_out=co,
            num_guests=num_guests,
            language_used=language_used,
            raw_conversation=raw_conversation,
        )
        booking = create_booking(db=db, booking_in=req, room=assigned)
        return {
            "success": True,
            "confirmation_code": booking.confirmation_code,
            "room_name": assigned.name,
            "total_price": float(booking.total_price),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        db.close()
