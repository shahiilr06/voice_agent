"""
Intent and Slot Extractor - Extracts intent and slots from user speech
"""
import re
from typing import Any

# Import extraction functions
try:
    from .sarvam_orchestrator import (
        _extract_dates,
        _extract_guests,
        _extract_room_type,
        _extract_name_phone,
        _detect_preferred_language,
        _is_greeting,
        _is_unclear_input,
        _is_details_intent,
        _is_pricing_intent,
    )
except ImportError:
    from sarvam_orchestrator import (
        _extract_dates,
        _extract_guests,
        _extract_room_type,
        _extract_name_phone,
        _detect_preferred_language,
        _is_greeting,
        _is_unclear_input,
        _is_details_intent,
        _is_pricing_intent,
    )


class IntentSlotExtractor:
    """Extracts intent and slots from user utterance"""
    
    @staticmethod
    def extract(user_text: str, history: list[dict[str, str]] = None) -> tuple[str, dict[str, Any]]:
        """
        Extract intent and slots from user text
        
        Returns:
            (intent, slots_dict)
            
        Intents: greeting, booking, info_request, unclear
        """
        history = history or []
        text = user_text.strip()
        lowered = text.lower()
        
        # Detect language
        language = _detect_preferred_language(history, text)
        
        # Extract all possible slots
        slots = {
            "language": language
        }
        
        # Check for greeting
        if _is_greeting(lowered):
            return ("greeting", slots)
        
        # Check for unclear input
        if _is_unclear_input(text):
            return ("unclear", slots)
        
        # Check for info requests
        if _is_details_intent(lowered):
            return ("info_request", {"type": "room_details", "language": language})
        
        if _is_pricing_intent(lowered):
            return ("info_request", {"type": "pricing", "language": language})
        
        # Extract booking-related slots
        dates = _extract_dates(text)
        slots.update(dates)
        
        guests = _extract_guests(text)
        if guests is not None:
            slots["guests"] = guests
        
        room_type = _extract_room_type(text)
        if room_type is not None:
            slots["room_type"] = room_type
        
        name_phone = _extract_name_phone(text)
        slots.update(name_phone)
        
        # Determine intent based on extracted slots
        has_booking_slots = any(k in slots for k in ["check_in", "check_out", "guests", "room_type"])
        has_contact_info = any(k in slots for k in ["name", "phone"])
        
        if has_booking_slots or has_contact_info:
            return ("booking", slots)
        
        # Default to booking intent if user is engaged
        return ("booking", slots)
