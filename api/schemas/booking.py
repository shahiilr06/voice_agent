from typing import Optional
from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator


class BookingCreateRequest(BaseModel):
    guest_name: str = Field(..., min_length=2, max_length=200)
    guest_phone: str = Field(..., min_length=7, max_length=30)
    guest_email: Optional[str] = None
    room_type: str = Field(..., min_length=2, max_length=50)
    check_in: date
    check_out: date
    num_guests: int = Field(default=1, ge=1, le=10)
    language_used: Optional[str] = Field(default="en-IN")
    raw_conversation: Optional[str] = None

    @model_validator(mode="after")
    def validate_booking(self):
        if self.check_out <= self.check_in:
            raise ValueError("check_out date must be after check_in date")
        return self


class BookingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    confirmation_code: str
    room_id: int
    guest_name: str
    guest_phone: str
    guest_email: Optional[str]
    check_in: date
    check_out: date
    num_guests: int
    total_price: float
    status: str
    language_used: Optional[str]
    created_at: datetime
