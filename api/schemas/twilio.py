"""
Pydantic schemas for Twilio telephony integration with LiveKit SIP and Maya AI.
"""
import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator


def normalize_e164_phone(v: str) -> str:
    """Normalize phone number to E.164 international format."""
    cleaned = re.sub(r"[^\d+]", "", v.strip())
    if not cleaned.startswith("+"):
        if len(cleaned) == 10:
            cleaned = "+91" + cleaned
        elif cleaned.startswith("0") and len(cleaned) == 11:
            cleaned = "+91" + cleaned[1:]
        else:
            cleaned = "+" + cleaned
    return cleaned


class TwilioCallRequest(BaseModel):
    to_phone: str = Field(
        default="+919994388773",
        description="Target phone number in E.164 format (e.g. +919994388773)",
    )
    from_phone: Optional[str] = Field(
        default=None,
        description="Twilio caller ID (defaults to TWILIO_PHONE_NUMBER e.g. +15157587590)",
    )
    room_name: Optional[str] = Field(
        default=None,
        description="Optional LiveKit room name for the call session",
    )

    @field_validator("to_phone")
    @classmethod
    def validate_to_phone(cls, v: str) -> str:
        return normalize_e164_phone(v)


class TwilioCallResponse(BaseModel):
    success: bool
    status: str
    call_sid: Optional[str] = None
    to_phone: str
    from_phone: str
    room_name: str
    message: str
    setup_required: bool = False
    instructions: Optional[str] = None


class TwilioStatusCallback(BaseModel):
    call_sid: str
    call_status: str
    from_number: Optional[str] = None
    to_number: Optional[str] = None
    duration: Optional[int] = None
    direction: Optional[str] = None


class TwilioConfigStatus(BaseModel):
    configured: bool
    account_sid_configured: bool
    auth_token_configured: bool
    twilio_phone_number: str
    target_phone_number: str
    livekit_sip_uri: str
    status: str
    instructions: Optional[str] = None
