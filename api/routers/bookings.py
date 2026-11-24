from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from api.database import get_db
from api.schemas.booking import BookingCreateRequest, BookingResponse
from api.services.booking_service import create_booking, get_booking_by_code, cancel_booking
from api.services.room_service import check_availability

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/create", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def make_booking(
    request: BookingCreateRequest,
    db: Session = Depends(get_db),
):
    """
    Atomically verify room availability and persist confirmed hotel reservation.
    """
    # 1. Check availability
    available_rooms = check_availability(
        db=db,
        room_type=request.room_type,
        check_in=request.check_in,
        check_out=request.check_out,
        num_guests=request.num_guests,
    )

    if not available_rooms:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No {request.room_type} room available between {request.check_in} and {request.check_out} for {request.num_guests} guests.",
        )

    # 2. Assign best matching room
    assigned_room = available_rooms[0]

    # 3. Create confirmed reservation
    booking = create_booking(db=db, booking_in=request, room=assigned_room)
    return BookingResponse.model_validate(booking)


@router.get("/{confirmation_code}", response_model=BookingResponse)
def get_reservation(confirmation_code: str, db: Session = Depends(get_db)):
    """Fetch booking details by confirmation code."""
    booking = get_booking_by_code(db, confirmation_code)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No booking found with confirmation code {confirmation_code}",
        )
    return BookingResponse.model_validate(booking)


@router.delete("/{confirmation_code}")
def cancel_reservation(confirmation_code: str, db: Session = Depends(get_db)):
    """Cancel a booking by confirmation code."""
    booking = cancel_booking(db, confirmation_code)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No booking found with confirmation code {confirmation_code}",
        )
    return {"success": True, "message": f"Booking {confirmation_code} has been cancelled."}
