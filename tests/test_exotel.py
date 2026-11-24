"""
Unit and integration tests for Exotel Cloud Telephony with Duplicate Protection & Idempotency.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from api.services.exotel_service import (
    normalize_exotel_number,
    dial_exotel_call,
    call_manager,
)
from api.main import app

client = TestClient(app)


def test_normalize_exotel_number():
    """Verify phone numbers are correctly normalized to Exotel 11-digit 0XXXXXXXXXX format."""
    assert normalize_exotel_number("9994388773") == "09994388773"
    assert normalize_exotel_number("09994388773") == "09994388773"
    assert normalize_exotel_number("+919994388773") == "09994388773"
    assert normalize_exotel_number("919994388773") == "09994388773"
    assert normalize_exotel_number("+91 999-438-8773") == "09994388773"


@pytest.mark.asyncio
async def test_duplicate_call_prevention():
    """Verify that attempting to call the same number twice triggers DuplicateGuard."""
    test_number = "09876543210"
    await call_manager.end_active_call(test_number)

    # First attempt: allowed
    can_call_1 = await call_manager.can_initiate_call(test_number)
    assert can_call_1 is True
    await call_manager.register_active_call("SID_001", test_number, "08047291749")

    # Immediate second attempt: BLOCKED
    can_call_2 = await call_manager.can_initiate_call(test_number)
    assert can_call_2 is False

    res = await dial_exotel_call(target_phone=test_number)
    assert res["status"] == "duplicate_prevented"

    # Cleanup
    await call_manager.end_active_call(test_number)


@pytest.mark.asyncio
async def test_webhook_idempotency():
    """Verify that duplicate Exotel webhooks for the same CallSid are detected."""
    call_sid = "CALL_TEST_IDEMPOTENCY_999"
    # First delivery: new
    is_dup_1 = await call_manager.is_duplicate_webhook(call_sid)
    assert is_dup_1 is False

    # Second delivery (retry): duplicate detected
    is_dup_2 = await call_manager.is_duplicate_webhook(call_sid)
    assert is_dup_2 is True


@pytest.mark.asyncio
async def test_dial_exotel_call_missing_credentials():
    """Verify dial_exotel_call handles missing credentials safely."""
    test_num = "09111222333"
    await call_manager.end_active_call(test_num)
    with patch.dict("os.environ", {"EXOTEL_API_KEY": ""}):
        res = await dial_exotel_call(target_phone=test_num)
        assert res["status"] == "error"
        assert "missing" in res["message"]
    await call_manager.end_active_call(test_num)


@pytest.mark.asyncio
async def test_dial_exotel_call_success():
    """Verify dial_exotel_call dispatches properly with valid credentials."""
    test_num = "09555666777"
    await call_manager.end_active_call(test_num)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "Call": {
            "Sid": "test_call_sid_12345",
            "Status": "in-progress",
            "PhoneNumberSid": "08047291749",
        }
    }

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await dial_exotel_call(target_phone=test_num)
        assert res["status"] == "in-progress"
        assert res["call_sid"] == "test_call_sid_12345"
        assert res["target"] == test_num

    await call_manager.end_active_call(test_num)


def test_exotel_status_endpoint():
    """Verify /exotel/status endpoint returns account details."""
    response = client.get("/exotel/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_exotel_voice_xml_sip_bridge():
    """Verify /exotel/voice returns valid ExoML XML bridging to LiveKit SIP."""
    response = client.post("/exotel/voice?CallSid=CALL_MOCK_101")
    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]
    assert "<Response>" in response.text
    assert "<Dial" in response.text
    assert "<Sip>" in response.text
    assert "vw9lj499216.sip.livekit.cloud" in response.text


def test_exotel_status_callback():
    """Verify /exotel/status_callback cleans up call session and hangs up."""
    response = client.post("/exotel/status_callback?CallSid=CALL_MOCK_101&CallStatus=completed")
    assert response.status_code == 200
    assert "<Hangup" in response.text
