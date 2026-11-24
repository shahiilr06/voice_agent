"""
Pydantic schemas for LiveKit SIP Outbound & Inbound telephony.
"""
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
import re


def normalize_phone_number(v: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", v.strip())
    if not cleaned.startswith("+"):
        # Default to Indian country code +91 if 10-digit number
        if len(cleaned) == 10:
            cleaned = "+91" + cleaned
        else:
            cleaned = "+" + cleaned
    return cleaned


class CallRequest(BaseModel):
    phone_number: str = Field(default="+919994388773", description="Target phone number (E.164 format)")
    room_name: Optional[str] = Field(default=None, description="LiveKit room name for the call")
    sip_trunk_id: Optional[str] = Field(default=None, description="Optional explicit LiveKit SIP trunk ID")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone_number(v)


class CreateTrunkRequest(BaseModel):
    name: str = Field(..., description="Friendly name for the SIP trunk")
    address: str = Field(..., description="SIP Provider Host/URI (e.g., sip.twilio.com or sip.telnyx.com)")
    numbers: List[str] = Field(default_factory=list, description="Outbound caller ID phone numbers in E.164")
    auth_username: Optional[str] = Field(default=None, description="SIP authentication username")
    auth_password: Optional[str] = Field(default=None, description="SIP authentication password")


class CallResponse(BaseModel):
    status: str
    sip_call_id: Optional[str] = None
    room_name: str
    phone_number: str
    message: str
    trunk_id: Optional[str] = None
    setup_required: bool = False
    instructions: Optional[str] = None


class TrunkInfo(BaseModel):
    sip_trunk_id: str
    name: str
    address: str
    numbers: List[str]
