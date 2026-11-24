"""
LangGraph conversation state schema for hotel booking dialogue.
"""
from typing import Annotated, Optional, Literal, List, Dict, Any
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class BookingState(TypedDict):
    # Live message list with append reducer
    messages: Annotated[List[BaseMessage], add_messages]

    # Language classification: "ta-IN" (Tamil), "en-IN" (English), or "tanglish"
    language: Optional[str]

    # Slot extraction fields
    guest_name: Optional[str]
    guest_phone: Optional[str]
    guest_email: Optional[str]
    room_type: Optional[str]  # "deluxe", "suite", "standard", "family"
    check_in: Optional[str]   # ISO format YYYY-MM-DD
    check_out: Optional[str]  # ISO format YYYY-MM-DD
    num_guests: Optional[int]

    # Availability & validation state
    is_available: bool
    available_room_id: Optional[int]
    available_room_name: Optional[str]
    price_per_night: Optional[float]
    total_price: Optional[float]

    # Confirmation flow
    guest_confirmed: bool  # True when guest verbally agrees to the booking
    booking_confirmed: bool
    confirmation_code: Optional[str]

    # Dialogue stage tracker
    stage: Literal[
        "greeting",
        "collecting_slots",
        "checking_availability",
        "awaiting_guest_confirmation",
        "creating_booking",
        "completed",
        "error",
    ]
