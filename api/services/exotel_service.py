"""
Exotel Cloud Telephony Service with Strict Duplicate Protection & Call Idempotency.
Initiates real cellular phone calls to Indian mobile numbers via Exotel REST API.
"""
import os
import re
import time
import logging
import asyncio
from typing import Dict, Any, Optional
import httpx
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("exotel_service")


class CallStateManager:
    """
    Thread-safe Call State & Idempotency Tracker.
    Prevents duplicate call initiations, duplicate webhooks, and multiple active legs.
    """
    def __init__(self, cooldown_seconds: float = 30.0):
        self._lock = asyncio.Lock()
        self._active_calls: Dict[str, Dict[str, Any]] = {}
        self._recent_attempts: Dict[str, float] = {}
        self._processed_webhook_sids: Dict[str, float] = {}
        self._cooldown_seconds = cooldown_seconds

    async def can_initiate_call(self, phone: str) -> bool:
        """Check if an outbound call can safely be dispatched without duplicating."""
        async with self._lock:
            now = time.time()
            # Clean expired recent attempts
            expired_attempts = [
                k for k, t in self._recent_attempts.items()
                if now - t > self._cooldown_seconds
            ]
            for k in expired_attempts:
                del self._recent_attempts[k]

            # Check if active call already running
            if phone in self._active_calls:
                logger.warning(f"[DuplicateGuard] Active call already running for {phone}")
                return False

            # Check cooldown window
            if phone in self._recent_attempts:
                logger.warning(f"[DuplicateGuard] Call attempt cooldown active for {phone} ({self._cooldown_seconds}s)")
                return False

            self._recent_attempts[phone] = now
            return True

    async def register_active_call(self, call_sid: str, phone: str, caller_id: str) -> None:
        """Register newly started active call session."""
        async with self._lock:
            self._active_calls[phone] = {
                "call_sid": call_sid,
                "phone": phone,
                "caller_id": caller_id,
                "start_time": time.time(),
                "status": "in-progress",
            }
            logger.info(f"[CallManager] Registered active call {call_sid} for {phone}")

    async def end_active_call(self, call_sid_or_phone: str) -> None:
        """Mark call session as completed and free lock."""
        async with self._lock:
            phone_to_remove = None
            for p, data in self._active_calls.items():
                if p == call_sid_or_phone or data.get("call_sid") == call_sid_or_phone:
                    phone_to_remove = p
                    break
            if phone_to_remove:
                del self._active_calls[phone_to_remove]
                logger.info(f"[CallManager] Released active call for {phone_to_remove}")

    async def is_duplicate_webhook(self, call_sid: str) -> bool:
        """Check if an incoming Exotel webhook for call_sid was already handled."""
        if not call_sid:
            return False
        async with self._lock:
            now = time.time()
            if call_sid in self._processed_webhook_sids:
                logger.warning(f"[DuplicateGuard] Webhook retry detected for CallSid {call_sid}")
                return True
            self._processed_webhook_sids[call_sid] = now
            return False

    def get_active_count(self) -> int:
        return len(self._active_calls)


# Global singleton instance
call_manager = CallStateManager(cooldown_seconds=30.0)


def normalize_exotel_number(v: str) -> str:
    """
    Format phone number for Exotel Indian calling.
    Exotel expects numbers in 0XXXXXXXXXX (11 digits) or XXXXXXXXXX (10 digits) format.
    """
    cleaned = re.sub(r"[^\d]", "", v.strip())
    # Strip leading 91 if 12 digits (+919994388773 -> 9994388773)
    if len(cleaned) == 12 and cleaned.startswith("91"):
        cleaned = cleaned[2:]
    # Prefix 0 for standard Indian landline/mobile dial format (09994388773)
    if len(cleaned) == 10:
        cleaned = "0" + cleaned
    return cleaned


async def dial_exotel_call(
    target_phone: Optional[str] = None,
    caller_id: Optional[str] = None,
    app_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Dispatch an outbound phone call with strict duplicate prevention.
    Ensures only ONE active call can exist at any given time.
    """
    api_key = os.getenv("EXOTEL_API_KEY")
    api_token = os.getenv("EXOTEL_API_TOKEN")
    account_sid = os.getenv("EXOTEL_ACCOUNT_SID", "karunya6")
    subdomain = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")
    resolved_caller_id = caller_id or os.getenv("EXOTEL_CALLER_ID", "08047291749")
    resolved_app_url = app_url or os.getenv(
        "EXOTEL_APP_URL", f"http://my.exotel.com/{account_sid}/exoml/start_voice/1395609"
    )

    raw_phone = target_phone or os.getenv("EXOTEL_TARGET_PHONE", "09994388773")
    clean_target = normalize_exotel_number(raw_phone)

    # 1. Duplicate & Idempotency Check
    can_call = await call_manager.can_initiate_call(clean_target)
    if not can_call:
        msg = f"Duplicate call prevented: Active call session already exists or cooldown active for {clean_target}."
        logger.warning(msg)
        return {
            "status": "duplicate_prevented",
            "message": msg,
            "target": clean_target,
        }

    # 2. Credential Check
    if not (api_key and api_token and account_sid):
        msg = "Exotel credentials (EXOTEL_API_KEY, EXOTEL_API_TOKEN, EXOTEL_ACCOUNT_SID) are missing in .env"
        logger.error(msg)
        return {
            "status": "error",
            "message": msg,
            "target": clean_target,
        }

    url = f"https://{subdomain}/v1/Accounts/{account_sid}/Calls/connect.json"
    auth = (api_key, api_token)
    data = {
        "From": clean_target,
        "CallerId": resolved_caller_id,
        "Url": resolved_app_url,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, auth=auth, data=data)

        if resp.status_code == 200:
            call_data = resp.json().get("Call", {})
            call_sid = call_data.get("Sid")
            await call_manager.register_active_call(call_sid, clean_target, resolved_caller_id)
            logger.info(f"Exotel call successfully initiated to {clean_target}. Call SID: {call_sid}")
            return {
                "status": "in-progress",
                "call_sid": call_sid,
                "target": clean_target,
                "caller_id": resolved_caller_id,
                "message": f"Calling {clean_target} from ExoPhone {resolved_caller_id}... Pick up your phone to talk to Maya!",
            }
        else:
            err_msg = f"Exotel API error {resp.status_code}: {resp.text}"
            logger.error(err_msg)
            return {
                "status": "error",
                "status_code": resp.status_code,
                "message": err_msg,
                "target": clean_target,
            }
    except Exception as e:
        logger.error(f"Failed to call Exotel API: {e}")
        return {
            "status": "error",
            "message": str(e),
            "target": clean_target,
        }


async def get_exotel_account_info() -> Dict[str, Any]:
    """Retrieve Exotel account details and verification state."""
    api_key = os.getenv("EXOTEL_API_KEY")
    api_token = os.getenv("EXOTEL_API_TOKEN")
    account_sid = os.getenv("EXOTEL_ACCOUNT_SID", "karunya6")
    subdomain = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")

    if not (api_key and api_token and account_sid):
        return {"status": "not_configured"}

    url = f"https://{subdomain}/v1/Accounts/{account_sid}.json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, auth=(api_key, api_token))
        if resp.status_code == 200:
            acc = resp.json().get("Account", {})
            return {
                "status": "active",
                "account_sid": acc.get("Sid"),
                "friendly_name": acc.get("FriendlyName"),
                "type": acc.get("Type"),
                "caller_id": os.getenv("EXOTEL_CALLER_ID", "08047291749"),
                "target_phone": os.getenv("EXOTEL_TARGET_PHONE", "09994388773"),
                "active_calls_count": call_manager.get_active_count(),
            }
        return {"status": "error", "status_code": resp.status_code, "detail": resp.text}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
