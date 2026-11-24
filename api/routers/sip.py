"""
LiveKit SIP Telephony Router.
Provides HTTP endpoints to initiate phone calls, configure SIP trunks, and check status.
"""
import os
from fastapi import APIRouter, HTTPException
from api.schemas.sip import CallRequest, CreateTrunkRequest, CallResponse, TrunkInfo
from api.services.sip_service import dial_phone_number, list_sip_trunks, register_outbound_trunk

router = APIRouter(prefix="/sip", tags=["SIP Telephony"])


@router.post("/call", response_model=CallResponse)
async def make_phone_call(req: CallRequest):
    """
    Trigger an outbound call to the target phone number using LiveKit SIP.
    Defaults to the user's mobile number: +919994388773.
    """
    return await dial_phone_number(
        phone_number=req.phone_number,
        room_name=req.room_name,
        sip_trunk_id=req.sip_trunk_id,
    )


@router.get("/trunks", response_model=list[TrunkInfo])
async def get_sip_trunks():
    """List all registered outbound SIP trunks on LiveKit Cloud."""
    return await list_sip_trunks()


@router.post("/trunks", response_model=TrunkInfo)
async def create_sip_trunk(req: CreateTrunkRequest):
    """Register a new outbound SIP trunk on LiveKit Cloud."""
    try:
        return await register_outbound_trunk(
            name=req.name,
            address=req.address,
            numbers=req.numbers,
            auth_username=req.auth_username,
            auth_password=req.auth_password,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create SIP trunk: {str(e)}")


@router.get("/status")
async def get_sip_status():
    """Check SIP readiness and configuration."""
    target_number = os.getenv("PHONE_CALL_TARGET", "+919994388773")
    configured_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
    auto_call = os.getenv("AUTO_CALL_ON_STARTUP", "false").lower() in ("true", "1", "yes")

    trunks = await list_sip_trunks()
    is_ready = bool(configured_trunk_id or trunks)

    return {
        "status": "ready" if is_ready else "setup_required",
        "target_phone_number": target_number,
        "auto_call_on_startup": auto_call,
        "active_trunk_id": configured_trunk_id or (trunks[0].sip_trunk_id if trunks else None),
        "total_trunks_found": len(trunks),
        "setup_instructions": None if is_ready else (
            "To place outbound phone calls to cellular phones (+919994388773), "
            "an Outbound SIP Trunk is required to link LiveKit with the telecom network (Twilio/Telnyx/Plivo)."
        )
    }
