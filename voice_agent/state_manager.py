"""
Conversation State Manager - Tracks booking state and determines next action
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BookingState:
    """Tracks the current booking conversation state"""
    check_in: str | None = None
    check_out: str | None = None
    guests: int | None = None
    room_type: str | None = None
    name: str | None = None
    phone: str | None = None
    language: str = "en"
    
    def get_missing_slots(self) -> list[str]:
        """Return list of missing required slots in order"""
        missing = []
        if self.check_in is None:
            missing.append("check_in")
        if self.check_out is None:
            missing.append("check_out")
        if self.guests is None:
            missing.append("guests")
        if self.room_type is None:
            missing.append("room_type")
        return missing
    
    def get_next_required_slot(self) -> str | None:
        """Get the next slot that needs to be filled"""
        missing = self.get_missing_slots()
        if missing:
            return missing[0]
        # All booking slots filled, check for name/phone
        if self.name is None:
            return "name"
        if self.phone is None:
            return "phone"
        return None
    
    def is_booking_complete(self) -> bool:
        """Check if all required information is collected"""
        return (
            self.check_in is not None
            and self.check_out is not None
            and self.guests is not None
            and self.room_type is not None
        )
    
    def is_ready_to_book(self) -> bool:
        """Check if ready to make final booking"""
        return self.is_booking_complete() and self.name is not None and self.phone is not None
    
    def update(self, extracted: dict[str, Any]) -> list[str]:
        """Update state with extracted slots, return list of updated slots"""
        updated = []
        
        if "check_in" in extracted and extracted["check_in"] != self.check_in:
            self.check_in = extracted["check_in"]
            updated.append("check_in")
        
        if "check_out" in extracted and extracted["check_out"] != self.check_out:
            self.check_out = extracted["check_out"]
            updated.append("check_out")
        
        if "guests" in extracted and extracted["guests"] != self.guests:
            self.guests = extracted["guests"]
            updated.append("guests")
        
        if "room_type" in extracted and extracted["room_type"] != self.room_type:
            self.room_type = extracted["room_type"]
            updated.append("room_type")
        
        if "name" in extracted and extracted["name"] != self.name:
            self.name = extracted["name"]
            updated.append("name")
        
        if "phone" in extracted and extracted["phone"] != self.phone:
            self.phone = extracted["phone"]
            updated.append("phone")
        
        if "language" in extracted:
            self.language = extracted["language"]
        
        return updated
    
    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary"""
        return {
            "check_in": self.check_in,
            "check_out": self.check_out,
            "guests": self.guests,
            "room_type": self.room_type,
            "name": self.name,
            "phone": self.phone,
            "language": self.language,
        }


@dataclass
class ConversationAction:
    """Represents the action to take based on current state"""
    action_type: str  # "ask_slot", "check_availability", "book_room", "greet", "clarify"
    slot_to_ask: str | None = None
    acknowledged_slot: str | None = None
    acknowledged_value: Any = None
    state_summary: dict[str, Any] = field(default_factory=dict)
    
    def get_prompt_context(self) -> str:
        """Generate context for LLM to create natural response"""
        if self.action_type == "greet":
            return "User greeted. Welcome them and ask for check-in date."
        
        if self.action_type == "ask_slot":
            context = ""
            if self.acknowledged_slot and self.acknowledged_value:
                context = f"Acknowledge: {self.acknowledged_slot} = {self.acknowledged_value}. "
            context += f"Ask for: {self.slot_to_ask}"
            return context
        
        if self.action_type == "check_availability":
            return f"All booking details collected: {self.state_summary}. Check availability and ask for name/phone."
        
        if self.action_type == "book_room":
            return f"Complete booking with: {self.state_summary}"
        
        if self.action_type == "clarify":
            return "User input unclear. Ask them to repeat."
        
        return ""


class ConversationStateManager:
    """Manages conversation state and determines next actions"""
    
    def __init__(self):
        self.state = BookingState()
    
    def process_turn(self, intent: str, extracted_slots: dict[str, Any], user_text: str) -> ConversationAction:
        """
        Process a conversation turn and determine next action
        
        Args:
            intent: Detected intent (greeting, booking, info_request, etc.)
            extracted_slots: Extracted slot values
            user_text: Original user text
        
        Returns:
            ConversationAction with next step
        """
        # Update state with extracted slots
        updated_slots = self.state.update(extracted_slots)
        
        # Log state for debugging
        print(f"[STATE] Updated: {updated_slots}, Current: {self.state.to_dict()}")
        
        # Handle greeting intent
        if intent == "greeting" and not any([self.state.check_in, self.state.check_out, self.state.guests, self.state.room_type]):
            return ConversationAction(action_type="greet")
        
        # Handle unclear input
        if intent == "unclear":
            return ConversationAction(action_type="clarify")
        
        # Check if ready to book
        if self.state.is_ready_to_book():
            return ConversationAction(
                action_type="book_room",
                state_summary=self.state.to_dict()
            )
        
        # Check if booking details complete (need name/phone)
        if self.state.is_booking_complete():
            # If we just got name or phone, acknowledge it
            if updated_slots and any(s in updated_slots for s in ["name", "phone"]):
                ack_slot = updated_slots[-1]
                ack_value = getattr(self.state, ack_slot)
                
                # Check what's still missing
                if self.state.name and not self.state.phone:
                    return ConversationAction(
                        action_type="ask_slot",
                        slot_to_ask="phone",
                        acknowledged_slot=ack_slot,
                        acknowledged_value=ack_value,
                        state_summary=self.state.to_dict()
                    )
                elif self.state.phone and not self.state.name:
                    return ConversationAction(
                        action_type="ask_slot",
                        slot_to_ask="name",
                        acknowledged_slot=ack_slot,
                        acknowledged_value=ack_value,
                        state_summary=self.state.to_dict()
                    )
            
            # First time asking for name/phone
            return ConversationAction(
                action_type="check_availability",
                state_summary=self.state.to_dict()
            )
        
        # Need to collect more booking slots
        next_slot = self.state.get_next_required_slot()
        
        # Determine what was just acknowledged
        ack_slot = updated_slots[-1] if updated_slots else None
        ack_value = getattr(self.state, ack_slot) if ack_slot else None
        
        return ConversationAction(
            action_type="ask_slot",
            slot_to_ask=next_slot,
            acknowledged_slot=ack_slot,
            acknowledged_value=ack_value,
            state_summary=self.state.to_dict()
        )
    
    def reset(self):
        """Reset conversation state"""
        self.state = BookingState()
