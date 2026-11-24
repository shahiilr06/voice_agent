"""
Twilio Telephony Service for LiveKit SIP Bridge.
Connects standard telephone calls (PSTN) with the LiveKit AI hotel receptionist (Maya).
"""
import os
import uuid
import logging
import requests
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from api.schemas.twilio import (
    normalize_e164_phone,
    TwilioCallResponse,
    TwilioConfigStatus,
)

load_dotenv()
logger = logging.getLogger("twilio_service")

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"


class TwilioCallManager:
    """Manages active Twilio call states and deduplication."""
    def __init__(self):
        self._active_calls: Dict[str, Dict[str, Any]] = {}

    def register_call(self, call_sid: str, meta: Dict[str, Any]):
        self._active_calls[call_sid] = meta

    def get_call(self, call_sid: str) -> Optional[Dict[str, Any]]:
        return self._active_calls.get(call_sid)

    def end_call(self, call_sid: str):
        if call_sid in self._active_calls:
            del self._active_calls[call_sid]


call_manager = TwilioCallManager()


def get_livekit_sip_uri() -> str:
    """Return the SIP URI for LiveKit Cloud SIP trunk (clean user@domain format)."""
    uri = os.getenv("LIVEKIT_SIP_URI") or os.getenv("LIVEKIT_SIP_FORWARD_URI") or "sip:hotel@vw9lj499216.sip.livekit.cloud"
    uri = uri.strip()
    if not uri.startswith("sip:"):
        uri = f"sip:{uri}"

    # Strip any obsolete password component like sip:user:pass@domain -> sip:user@domain
    if "@" in uri:
        prefix, domain = uri.split("@", 1)
        if ":" in prefix.replace("sip:", ""):
            user = prefix.replace("sip:", "").split(":")[0]
            uri = f"sip:{user}@{domain}"
    else:
        # If no user specified (e.g. sip:vw9lj499216.sip.livekit.cloud), route to hotel@
        domain = uri.replace("sip:", "")
        uri = f"sip:hotel@{domain}"

    return uri


def build_twiml_sip_dial(sip_uri: str, caller_id: Optional[str] = None) -> str:
    """
    Generate TwiML XML to bridge a telephone call directly to LiveKit SIP URI.
    """
    caller_attr = f' callerId="{caller_id}"' if caller_id else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial answerOnBridge="true"{caller_attr} timeout="30">
        <Sip>{sip_uri}</Sip>
    </Dial>
</Response>"""


def get_twilio_credentials() -> Dict[str, str]:
    """Retrieve Twilio credentials and phone configuration from environment."""
    return {
        "account_sid": (os.getenv("TWILIO_ACCOUNT_SID") or "").strip(),
        "auth_token": (os.getenv("TWILIO_AUTH_TOKEN") or "").strip(),
        "from_phone": os.getenv("TWILIO_PHONE_NUMBER", "+15157587590").strip(),
        "target_phone": os.getenv("TWILIO_TARGET_PHONE", "+919994388773").strip(),
        "sip_uri": get_livekit_sip_uri(),
    }


def check_twilio_config() -> TwilioConfigStatus:
    """Check Twilio integration readiness."""
    cfg = get_twilio_credentials()
    has_sid = bool(cfg["account_sid"] and cfg["account_sid"].startswith("AC"))
    has_token = bool(cfg["auth_token"])
    configured = has_sid and has_token

    instructions = None
    if not configured:
        instructions = (
            "To place live telephone calls, configure TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env. "
            "You can find these in your Twilio Console dashboard: https://console.twilio.com"
        )

    return TwilioConfigStatus(
        configured=configured,
        account_sid_configured=has_sid,
        auth_token_configured=has_token,
        twilio_phone_number=cfg["from_phone"],
        target_phone_number=cfg["target_phone"],
        livekit_sip_uri=cfg["sip_uri"],
        status="ready" if configured else "setup_required",
        instructions=instructions,
    )


async def dial_twilio_call(
    to_phone: Optional[str] = None,
    from_phone: Optional[str] = None,
    room_name: Optional[str] = None,
) -> TwilioCallResponse:
    """
    Place an outbound call via Twilio REST API to the destination phone number.
    When answered, connects the call directly to LiveKit SIP trunk.
    """
    cfg = get_twilio_credentials()
    target_num = normalize_e164_phone(to_phone or cfg["target_phone"])
    caller_id = normalize_e164_phone(from_phone or cfg["from_phone"])
    sip_uri = cfg["sip_uri"]

    room = room_name or f"hotel-call-{target_num.replace('+', '')}-{uuid.uuid4().hex[:6]}"

    # Validate Twilio credentials
    if not (cfg["account_sid"] and cfg["auth_token"]):
        msg = (
            f"Ready to call {target_num} from {caller_id}. "
            "Twilio Account SID or Auth Token is not set in .env."
        )
        instructions = (
            "Please provide your TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN "
            "to place live outbound cellular phone calls."
        )
        logger.warning(msg)
        return TwilioCallResponse(
            success=False,
            status="setup_required",
            to_phone=target_num,
            from_phone=caller_id,
            room_name=room,
            message=msg,
            setup_required=True,
            instructions=instructions,
        )

    # Inline TwiML to bridge answered call to LiveKit SIP
    twiml_content = build_twiml_sip_dial(sip_uri=sip_uri, caller_id=caller_id)

    url = f"{TWILIO_API_BASE}/Accounts/{cfg['account_sid']}/Calls.json"
    payload = {
        "To": target_num,
        "From": caller_id,
        "Twiml": twiml_content,
    }

    try:
        resp = requests.post(
            url,
            data=payload,
            auth=(cfg["account_sid"], cfg["auth_token"]),
            timeout=10,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            call_sid = data.get("sid", "unknown_sid")
            status = data.get("status", "queued")
            call_manager.register_call(call_sid, {
                "to": target_num,
                "from": caller_id,
                "room": room,
                "status": status,
            })
            return TwilioCallResponse(
                success=True,
                status=status,
                call_sid=call_sid,
                to_phone=target_num,
                from_phone=caller_id,
                room_name=room,
                message=f"Outbound call successfully queued via Twilio to {target_num}. CallSid: {call_sid}",
            )
        else:
            err_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = err_data.get("message") or f"Twilio API Error HTTP {resp.status_code}: {resp.text}"
            logger.error(f"[Twilio Call Failed]: {err_msg}")
            return TwilioCallResponse(
                success=False,
                status="failed",
                to_phone=target_num,
                from_phone=caller_id,
                room_name=room,
                message=f"Failed to place Twilio call: {err_msg}",
            )
    except Exception as e:
        logger.exception(f"Unexpected error in Twilio call: {e}")
        return TwilioCallResponse(
            success=False,
            status="error",
            to_phone=target_num,
            from_phone=caller_id,
            room_name=room,
            message=f"Call dispatch exception: {str(e)}",
        )
