"""
Unit and integration tests for Twilio Telephony Integration with LiveKit SIP.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api.schemas.twilio import normalize_e164_phone, TwilioCallRequest
from api.services.twilio_service import (
    build_twiml_sip_dial,
    dial_twilio_call,
    check_twilio_config,
    call_manager,
)
from api.main import app

client = TestClient(app)


def test_normalize_phone_number():
    """Verify phone normalization handles standard Indian & international formats."""
    assert normalize_e164_phone("9994388773") == "+919994388773"
    assert normalize_e164_phone("09994388773") == "+919994388773"
    assert normalize_e164_phone("+919994388773") == "+919994388773"
    assert normalize_e164_phone("+1 515 758 7590") == "+15157587590"


def test_twilio_call_request_validation():
    """Verify TwilioCallRequest automatically normalizes phone numbers."""
    req = TwilioCallRequest(to_phone="9994388773")
    assert req.to_phone == "+919994388773"


def test_build_twiml_sip_dial():
    """Verify generated TwiML contains valid SIP bridge elements."""
    xml = build_twiml_sip_dial("sip:vw9lj499216.sip.livekit.cloud", caller_id="+15157587590")
    assert "<Response>" in xml
    assert "<Dial" in xml
    assert "<Sip>sip:vw9lj499216.sip.livekit.cloud</Sip>" in xml
    assert 'callerId="+15157587590"' in xml


def test_twilio_status_endpoint():
    """Verify /twilio/status returns status structure."""
    resp = client.get("/twilio/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "configured" in data
    assert "twilio_phone_number" in data
    assert data["twilio_phone_number"] == "+15157587590"
    assert "livekit_sip_uri" in data
    assert "vw9lj499216" in data["livekit_sip_uri"]


def test_twilio_inbound_voice_webhook():
    """Verify inbound call webhook returns valid TwiML with SIP bridge."""
    resp = client.post(
        "/twilio/voice",
        data={
            "CallSid": "CA1234567890abcdef",
            "From": "+919994388773",
            "To": "+15157587590",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    content = resp.text
    assert "<Dial" in content
    assert "<Sip>" in content
    assert "vw9lj499216.sip.livekit.cloud" in content


def test_twilio_outbound_twiml_endpoint():
    """Verify outbound twiml endpoint returns SIP bridge XML."""
    resp = client.post("/twilio/outbound_twiml?From=+15157587590")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert "<Sip>" in resp.text


def test_twilio_status_callback():
    """Verify status callback receives completed events without error."""
    call_manager.register_call("CAtest123", {"status": "in-progress"})
    resp = client.post(
        "/twilio/status_callback",
        data={
            "CallSid": "CAtest123",
            "CallStatus": "completed",
            "CallDuration": "45",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert call_manager.get_call("CAtest123") is None


@pytest.mark.asyncio
async def test_dial_twilio_call_without_credentials():
    """Verify that dialing without Twilio credentials returns setup_required notice."""
    with patch.dict("os.environ", {"TWILIO_ACCOUNT_SID": "", "TWILIO_AUTH_TOKEN": ""}):
        res = await dial_twilio_call(to_phone="9994388773")
        assert res.success is False
        assert res.setup_required is True
        assert res.to_phone == "+919994388773"
        assert "TWILIO_ACCOUNT_SID" in res.instructions


@pytest.mark.asyncio
async def test_dial_twilio_call_with_credentials_dispatches():
    """Verify that dialing with Twilio credentials calls Twilio REST API and queues call."""
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "sid": "CAmocked123456",
        "status": "queued",
        "to": "+919994388773",
        "from": "+15157587590",
    }

    with patch.dict(
        "os.environ",
        {
            "TWILIO_ACCOUNT_SID": "AC_mock_account_sid_for_testing",
            "TWILIO_AUTH_TOKEN": "mock_auth_token_secret",
            "TWILIO_PHONE_NUMBER": "+15157587590",
        },
    ):
        with patch("requests.post", return_value=mock_resp) as mock_post:
            res = await dial_twilio_call(to_phone="9994388773")
            assert res.success is True
            assert res.call_sid == "CAmocked123456"
            assert res.status == "queued"
            assert res.to_phone == "+919994388773"
            assert mock_post.called
            args, kwargs = mock_post.call_args
            assert "AC_mock_account_sid_for_testing/Calls.json" in args[0]
            assert kwargs["data"]["To"] == "+919994388773"
            assert kwargs["data"]["From"] == "+15157587590"
            assert "<Sip>" in kwargs["data"]["Twiml"]
