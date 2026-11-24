"""
Twilio Telephony Router.
Endpoints for inbound Twilio voice webhooks, outbound call dispatch,
TwiML generation, and LiveKit SIP routing.
"""
import logging
from fastapi import APIRouter, Request, Response
from typing import Optional

from api.schemas.twilio import (
    TwilioCallRequest,
    TwilioCallResponse,
    TwilioConfigStatus,
)
from api.services.twilio_service import (
    dial_twilio_call,
    check_twilio_config,
    build_twiml_sip_dial,
    get_livekit_sip_uri,
    call_manager,
)

logger = logging.getLogger("twilio_router")
router = APIRouter(prefix="/twilio", tags=["Twilio Telephony"])


@router.post("/call", response_model=TwilioCallResponse)
async def trigger_outbound_call(req: Optional[TwilioCallRequest] = None):
    """
    Trigger an outbound cellular phone call to the customer via Twilio.
    Defaults to target number +919994388773 from Twilio number +15157587590.
    """
    to_phone = req.to_phone if req else None
    from_phone = req.from_phone if req else None
    room_name = req.room_name if req else None
    return await dial_twilio_call(to_phone=to_phone, from_phone=from_phone, room_name=room_name)


@router.get("/status", response_model=TwilioConfigStatus)
async def get_twilio_status():
    """
    Get Twilio telephony readiness and configuration details.
    """
    return check_twilio_config()


@router.api_route("/voice", methods=["GET", "POST"])
async def twilio_inbound_voice(request: Request):
    """
    Webhook executed by Twilio when an incoming call arrives at +1 515 758 7590.
    Bridges the caller directly to the LiveKit SIP trunk (sip:vw9lj499216.sip.livekit.cloud)
    where Maya AI receptionist is waiting to assist them.
    """
    params = dict(request.query_params)
    form_data = {}
    if request.method == "POST":
        try:
            form_data = dict(await request.form())
        except Exception:
            pass

    data = {**params, **form_data}
    call_sid = data.get("CallSid", "unknown_sid")
    caller = data.get("From", "unknown_caller")
    called = data.get("To", "unknown_destination")

    logger.info(f"📞 [Twilio Inbound Call] Sid={call_sid}, From={caller}, To={called}")

    sip_uri = get_livekit_sip_uri()
    twiml = build_twiml_sip_dial(sip_uri=sip_uri, caller_id=called)
    return Response(content=twiml, media_type="application/xml")


@router.api_route("/outbound_twiml", methods=["GET", "POST"])
async def twilio_outbound_twiml(request: Request):
    """
    Returns TwiML bridging an answered outbound call to LiveKit SIP trunk.
    """
    params = dict(request.query_params)
    caller_id = params.get("From")
    sip_uri = get_livekit_sip_uri()
    twiml = build_twiml_sip_dial(sip_uri=sip_uri, caller_id=caller_id)
    return Response(content=twiml, media_type="application/xml")


@router.api_route("/status_callback", methods=["GET", "POST"])
async def twilio_status_callback(request: Request):
    """
    Webhook executed by Twilio when call lifecycle events occur (completed, busy, failed).
    """
    params = dict(request.query_params)
    form_data = {}
    if request.method == "POST":
        try:
            form_data = dict(await request.form())
        except Exception:
            pass

    data = {**params, **form_data}
    call_sid = data.get("CallSid", "unknown")
    call_status = data.get("CallStatus", "unknown")
    duration = data.get("CallDuration", "0")

    logger.info(f"📋 [Twilio Callback] CallSid={call_sid}, Status={call_status}, Duration={duration}s")
    if call_status in ("completed", "failed", "busy", "no-answer", "canceled"):
        call_manager.end_call(call_sid)

    return Response(content="<Response/>", media_type="application/xml")
