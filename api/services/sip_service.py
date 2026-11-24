"""
LiveKit SIP telephony service for outbound/inbound phone calls.
Bridges standard phone numbers (PSTN) with the LiveKit AI hotel receptionist.
"""
import os
import uuid
import logging
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

from api.schemas.sip import normalize_phone_number, CallResponse, TrunkInfo

load_dotenv()
logger = logging.getLogger("sip_service")


def get_livekit_api():
    """Instantiate LiveKitAPI using environment credentials."""
    from livekit.api import LiveKitAPI
    url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    if not (url and api_key and api_secret):
        raise ValueError("LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET must be configured in .env")
    return LiveKitAPI(url=url, api_key=api_key, api_secret=api_secret)


async def list_sip_trunks() -> List[TrunkInfo]:
    """Retrieve list of registered outbound SIP trunks from LiveKit Cloud."""
    api = get_livekit_api()
    try:
        from livekit.api import ListSIPOutboundTrunkRequest
        # Support both new and legacy SDK method names
        if hasattr(api.sip, "list_outbound_trunk"):
            res = await api.sip.list_outbound_trunk(ListSIPOutboundTrunkRequest())
        else:
            res = await api.sip.list_sip_outbound_trunk(ListSIPOutboundTrunkRequest())

        trunks = []
        for item in getattr(res, "items", []):
            trunks.append(
                TrunkInfo(
                    sip_trunk_id=getattr(item, "sip_trunk_id", ""),
                    name=getattr(item, "name", "Unnamed Trunk"),
                    address=getattr(item, "address", ""),
                    numbers=list(getattr(item, "numbers", [])),
                )
            )
        return trunks
    except Exception as e:
        logger.error(f"Error querying LiveKit SIP trunks: {e}")
        return []
    finally:
        await api.aclose()


async def register_outbound_trunk(
    name: str,
    address: str,
    numbers: List[str],
    auth_username: Optional[str] = None,
    auth_password: Optional[str] = None,
) -> TrunkInfo:
    """Register a new outbound SIP trunk on LiveKit Cloud."""
    from livekit.api import CreateSIPOutboundTrunkRequest, SIPOutboundTrunkInfo
    api = get_livekit_api()
    try:
        trunk_info = SIPOutboundTrunkInfo(
            name=name,
            address=address,
            numbers=numbers,
            auth_username=auth_username or "",
            auth_password=auth_password or "",
        )
        req = CreateSIPOutboundTrunkRequest(trunk=trunk_info)
        if hasattr(api.sip, "create_outbound_trunk"):
            created = await api.sip.create_outbound_trunk(req)
        else:
            created = await api.sip.create_sip_outbound_trunk(req)

        return TrunkInfo(
            sip_trunk_id=created.sip_trunk_id,
            name=created.name,
            address=created.address,
            numbers=list(created.numbers),
        )
    finally:
        await api.aclose()


async def dial_phone_number(
    phone_number: str = "+919994388773",
    room_name: Optional[str] = None,
    sip_trunk_id: Optional[str] = None,
) -> CallResponse:
    """
    Dial an outbound phone call to the target phone number using LiveKit SIP.
    """
    from livekit.api import CreateSIPParticipantRequest

    phone = normalize_phone_number(phone_number)
    target_room = room_name or f"hotel-call-{phone.replace('+', '')}-{uuid.uuid4().hex[:6]}"

    # 1. Resolve Outbound SIP Trunk
    resolved_trunk_id = sip_trunk_id or os.getenv("SIP_OUTBOUND_TRUNK_ID")
    if not resolved_trunk_id:
        existing_trunks = await list_sip_trunks()
        if existing_trunks:
            resolved_trunk_id = existing_trunks[0].sip_trunk_id

    # 2. If no SIP Trunk is available, inform caller with actionable setup instructions
    if not resolved_trunk_id:
        msg = (
            f"Ready to call {phone}. However, LiveKit Cloud requires an Outbound SIP Trunk "
            "to bridge WebRTC into the physical cellular network (PSTN)."
        )
        instructions = (
            "Steps to enable phone calls to your mobile:\n"
            "1. Create a free SIP Trunk (e.g. on Twilio, Telnyx, or Plivo).\n"
            "2. In LiveKit Cloud Console (https://cloud.livekit.io) -> SIP -> Outbound Trunks -> Add Trunk.\n"
            "3. Add your Trunk ID to .env as `SIP_OUTBOUND_TRUNK_ID=ST_xxxx` or use POST /sip/trunks.\n"
            "In the meantime, you can test full voice conversations via your browser microphone on http://localhost:8000/."
        )
        logger.warning(f"{msg}\n{instructions}")
        return CallResponse(
            status="setup_required",
            room_name=target_room,
            phone_number=phone,
            message=msg,
            trunk_id=None,
            setup_required=True,
            instructions=instructions,
        )

    # 3. Dispatch call via LiveKit SIP API
    api = get_livekit_api()
    try:
        req = CreateSIPParticipantRequest(
            sip_trunk_id=resolved_trunk_id,
            sip_call_to=phone,
            room_name=target_room,
            participant_identity=f"phone-{phone}",
            participant_name=f"Guest ({phone})",
            play_ringtone=True,
        )
        participant = await api.sip.create_sip_participant(req)
        call_id = getattr(participant, "sip_call_id", None) or getattr(participant, "participant_id", None)

        return CallResponse(
            status="dialing",
            sip_call_id=call_id,
            room_name=target_room,
            phone_number=phone,
            trunk_id=resolved_trunk_id,
            message=f"Calling {phone}... Pick up your phone to talk to Maya!",
            setup_required=False,
        )
    except Exception as e:
        error_msg = f"Failed to dispatch SIP call to {phone}: {str(e)}"
        logger.error(error_msg)
        return CallResponse(
            status="error",
            room_name=target_room,
            phone_number=phone,
            trunk_id=resolved_trunk_id,
            message=error_msg,
            setup_required=False,
            instructions=str(e),
        )
    finally:
        await api.aclose()
