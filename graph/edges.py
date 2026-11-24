"""
LangGraph conditional edge routers.
"""
from typing import Literal
from graph.state import BookingState


def route_after_extract(state: BookingState) -> Literal["check_availability", "create_booking", "receptionist_agent"]:
    """
    Determine the next node based on collected booking parameters:
    1. If guest explicitly agreed and room is available -> create_booking
    2. If dates and room type are filled and availability not yet checked -> check_availability
    3. Otherwise -> receptionist_agent to ask for next detail
    """
    guest_confirmed = state.get("guest_confirmed", False)
    is_available = state.get("is_available", False)
    booking_confirmed = state.get("booking_confirmed", False)

    if guest_confirmed and is_available and not booking_confirmed:
        return "create_booking"

    check_in = state.get("check_in")
    check_out = state.get("check_out")
    room_type = state.get("room_type")

    # If critical booking parameters are ready but availability hasn't been checked yet
    if check_in and check_out and room_type and not is_available:
        return "check_availability"

    return "receptionist_agent"
