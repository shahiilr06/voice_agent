"""
Unit and integration tests for LiveKit SIP telephony integration.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from api.schemas.sip import normalize_phone_number, CallRequest
from api.services.sip_service import dial_phone_number, list_sip_trunks
from api.main import app

client = TestClient(app)


def test_normalize_phone_number():
    """Verify phone numbers are correctly normalized to E.164."""
    assert normalize_phone_number("9994388773") == "+919994388773"
    assert normalize_phone_number("+919994388773") == "+919994388773"
    assert normalize_phone_number("999-438-8773") == "+919994388773"
    assert normalize_phone_number("+1 (555) 123-4567") == "+15551234567"


def test_call_request_validation():
    """Verify CallRequest schema automatically normalizes input phone number."""
    req = CallRequest(phone_number="9994388773")
    assert req.phone_number == "+919994388773"


@pytest.mark.asyncio
async def test_dial_phone_without_trunk_returns_setup_required():
    """Verify that attempting to dial without a configured trunk returns actionable guidance."""
    with patch("api.services.sip_service.list_sip_trunks", new=AsyncMock(return_value=[])):
        with patch.dict("os.environ", {"SIP_OUTBOUND_TRUNK_ID": ""}):
            res = await dial_phone_number(phone_number="9994388773")
            assert res.setup_required is True
            assert res.phone_number == "+919994388773"
            assert "Outbound SIP Trunk" in res.message


@pytest.mark.asyncio
async def test_dial_phone_with_trunk_dispatches_call():
    """Verify that dial_phone_number calls create_sip_participant when trunk is available."""
    mock_participant = MagicMock()
    mock_participant.sip_call_id = "SC_12345"

    mock_api = MagicMock()
    mock_api.sip.create_sip_participant = AsyncMock(return_value=mock_participant)
    mock_api.aclose = AsyncMock()

    with patch("api.services.sip_service.get_livekit_api", return_value=mock_api):
        with patch.dict("os.environ", {"SIP_OUTBOUND_TRUNK_ID": "ST_mock_trunk"}):
            res = await dial_phone_number(phone_number="9994388773")
            assert res.status == "dialing"
            assert res.sip_call_id == "SC_12345"
            assert res.trunk_id == "ST_mock_trunk"
            assert res.phone_number == "+919994388773"


def test_sip_status_endpoint():
    """Verify /sip/status HTTP endpoint returns healthy status report."""
    response = client.get("/sip/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["target_phone_number"] == "+919994388773"


def test_sip_call_endpoint():
    """Verify /sip/call HTTP endpoint accepts phone call request."""
    response = client.post("/sip/call", json={"phone_number": "9994388773"})
    assert response.status_code == 200
    data = response.json()
    assert data["phone_number"] == "+919994388773"
    assert "room_name" in data
