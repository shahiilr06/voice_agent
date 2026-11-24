"""
Exotel Cloud Telephony Router with Strict Duplicate Protection & Webhook Idempotency.
Provides HTTP endpoints for call initiation, status checks, ExoML callbacks, and SIP routing.
"""
import logging
from fastapi import APIRouter, Response, Request
from pydantic import BaseModel, Field
from typing import Optional
from api.services.exotel_service import (
    dial_exotel_call,
    get_exotel_account_info,
    call_manager,
)

logger = logging.getLogger("exotel_router")
router = APIRouter(prefix="/exotel", tags=["Exotel Telephony"])


class ExotelCallRequest(BaseModel):
    target_phone: Optional[str] = Field(
        default=None, description="Target phone number (e.g. 09994388773 or 9994388773)"
    )


@router.post("/call")
async def trigger_call(req: Optional[ExotelCallRequest] = None):
    """
    Trigger an outbound cellular phone call to the mobile number using Exotel.
    Guarded by CallStateManager to prevent duplicate call legs.
    """
    target = req.target_phone if req else None
    return await dial_exotel_call(target_phone=target)


@router.get("/status")
async def get_status():
    """Check Exotel account configuration and active call state."""
    return await get_exotel_account_info()


@router.api_route("/voice", methods=["GET", "POST"])
async def exotel_voice_callback(request: Request):
    """
    ExoML callback executed when an incoming or connected call arrives.
    Includes Call SID deduplication to prevent re-processing retries.
    Routes the caller to LiveKit Inbound SIP Trunk or answers directly with Maya.
    """
    params = dict(request.query_params)
    form_data = {}
    if request.method == "POST":
        try:
            form_data = dict(await request.form())
        except Exception:
            pass

    combined_params = {**params, **form_data}
    call_sid = combined_params.get("CallSid") or combined_params.get("Sid") or "unknown_sid"
    caller = combined_params.get("From") or combined_params.get("CallFrom") or "unknown"

    logger.info(f"[ExotelVoice] Call received: Sid={call_sid}, From={caller}")

    # Check for duplicate webhook delivery from Exotel
    if await call_manager.is_duplicate_webhook(call_sid):
        logger.warning(f"[DuplicateGuard] Ignoring duplicate webhook for CallSid: {call_sid}")
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="en-IN">Connecting to Sunrise Hotel.</Say>
</Response>"""
        return Response(content=xml_content, media_type="application/xml")

    # Bridge incoming call to LiveKit Inbound SIP Trunk
    livekit_sip_uri = os.getenv("LIVEKIT_SIP_URI", "sip:hotel@vw9lj499216.sip.livekit.cloud")
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial timeout="30" action="/exotel/status_callback">
        <Sip>{livekit_sip_uri}</Sip>
    </Dial>
</Response>"""
    return Response(content=xml_content, media_type="application/xml")


@router.api_route("/status_callback", methods=["GET", "POST"])
async def exotel_status_callback(request: Request):
    """
    Receives Exotel call lifecycle events (completed, busy, no-answer, failed).
    Cleans up the active call session in CallStateManager.
    """
    params = dict(request.query_params)
    form_data = {}
    if request.method == "POST":
        try:
            form_data = dict(await request.form())
        except Exception:
            pass

    combined = {**params, **form_data}
    call_sid = combined.get("CallSid") or combined.get("Sid") or "unknown"
    call_status = combined.get("CallStatus") or combined.get("Status") or "completed"

    logger.info(f"[ExotelCallback] Call {call_sid} status update: {call_status}")
    await call_manager.end_active_call(call_sid)

    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Hangup />
</Response>"""
    return Response(content=xml_content, media_type="application/xml")
