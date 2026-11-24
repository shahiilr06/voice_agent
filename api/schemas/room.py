from typing import List, Optional
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, model_validator


class RoomBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., max_length=100)
    room_number: str = Field(..., max_length=20)
    type: str = Field(..., max_length=50)
    floor: int = Field(default=1, ge=1)
    max_guests: int = Field(default=2, ge=1, le=10)
    price_per_night: float = Field(..., gt=0)
    amenities: List[str] = Field(default_factory=list)
    description: str = Field(...)
    description_ta: Optional[str] = None
    is_active: bool = True


class RoomCreate(RoomBase):
    pass


class RoomResponse(RoomBase):
    id: int
    similarity_score: Optional[float] = None


class RoomAvailabilityRequest(BaseModel):
    room_type: Optional[str] = None
    check_in: date
    check_out: date
    num_guests: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.check_out <= self.check_in:
            raise ValueError("check_out must be strictly after check_in")
        return self
