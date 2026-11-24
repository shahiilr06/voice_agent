import pytest
import io
import base64
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import date, timedelta
from langchain_core.messages import HumanMessage, AIMessage
from graph.tools import tool_check_availability, tool_create_booking
from graph.nodes import check_availability_node, create_booking_node, receptionist_agent_node, extract_slots_node
from graph.edges import route_after_extract
from api.services.vector_service import semantic_faq_search
from api.services.room_service import create_room, get_room_by_id
from api.schemas.room import RoomCreate
from api.database import SessionLocal, init_db, CompatibleVector
from api.main import app
from fastapi.testclient import TestClient
from seeds.seed_data import seed_database
from agent.sarvam_stt import SarvamSTT, SarvamSTTStream
from agent.sarvam_tts import SarvamTTS, SarvamSynthesizeStream


@pytest.fixture(autouse=True)
def setup_db():
    init_db()
    seed_database()


def test_tools_execution():
    today = date.today()
    ci = (today + timedelta(days=60)).isoformat()
    co = (today + timedelta(days=62)).isoformat()

    # Tool check availability
    res = tool_check_availability("deluxe", ci, co, num_guests=2)
    assert res["is_available"] is True
    assert res["total_price"] > 0

    # Tool check availability for invalid dates
    bad_res = tool_check_availability("deluxe", "invalid-date", "invalid-date", num_guests=2)
    assert bad_res["is_available"] is False

    # Tool create booking
    book_res = tool_create_booking(
        guest_name="Anand",
        guest_phone="9988776655",
        room_type="deluxe",
        check_in=ci,
        check_out=co,
        num_guests=2,
        language_used="ta-IN",
    )
    assert book_res["success"] is True
    assert book_res["confirmation_code"].startswith("BK-")

    # Tool create booking with unavailable room
    fail_res = tool_create_booking(
        guest_name="Anand",
        guest_phone="9988776655",
        room_type="non-existent-room-type",
        check_in=ci,
        check_out=co,
    )
    assert fail_res["success"] is False


def test_graph_nodes_and_edges():
    today = date.today()
    ci = (today + timedelta(days=70)).isoformat()
    co = (today + timedelta(days=72)).isoformat()

    # Test check_availability_node with missing dates
    assert check_availability_node({"check_in": None})["stage"] == "collecting_slots"

    # Test check_availability_node
    state = {
        "room_type": "deluxe",
        "check_in": ci,
        "check_out": co,
        "num_guests": 2,
    }
    avail_update = check_availability_node(state)
    assert avail_update["is_available"] is True
    assert avail_update["stage"] == "awaiting_guest_confirmation"

    # Test route_after_extract
    state_to_route = {
        "guest_confirmed": True,
        "is_available": True,
        "booking_confirmed": False,
    }
    assert route_after_extract(state_to_route) == "create_booking"

    state_need_avail = {
        "room_type": "deluxe",
        "check_in": ci,
        "check_out": co,
        "is_available": False,
    }
    assert route_after_extract(state_need_avail) == "check_availability"

    state_need_slots = {
        "room_type": None,
        "check_in": None,
        "is_available": False,
    }
    assert route_after_extract(state_need_slots) == "receptionist_agent"

    # Test create_booking_node
    full_state = {
        "guest_name": "Meenakshi",
        "guest_phone": "9840123456",
        "room_type": "deluxe",
        "check_in": ci,
        "check_out": co,
        "num_guests": 2,
        "language": "ta-IN",
        "messages": [HumanMessage(content="ஆம் உறுதி செய்கிறேன்")],
    }
    booking_res = create_booking_node(full_state)
    assert booking_res["booking_confirmed"] is True
    assert booking_res["confirmation_code"].startswith("BK-")

    # Test create_booking_node failure
    fail_state = {
        "guest_name": "Ghost",
        "room_type": "underwater-cabin",
        "check_in": ci,
        "check_out": co,
    }
    fail_booking = create_booking_node(fail_state)
    assert fail_booking["booking_confirmed"] is False
    assert fail_booking["stage"] == "error"

    # Test receptionist_agent_node fallback responses across languages
    agent_confirmed_ta = receptionist_agent_node({
        "language": "ta-IN",
        "confirmation_code": "BK-123456",
        "total_price": 9000.0,
        "messages": [],
    })
    assert "BK-123456" in agent_confirmed_ta["messages"][0].content

    agent_confirmed_tanglish = receptionist_agent_node({
        "language": "tanglish",
        "confirmation_code": "BK-123456",
        "total_price": 9000.0,
        "messages": [],
    })
    assert "BK-123456" in agent_confirmed_tanglish["messages"][0].content

    agent_await_en = receptionist_agent_node({
        "language": "en-IN",
        "stage": "awaiting_guest_confirmation",
        "room_type": "deluxe",
        "total_price": 9000.0,
        "messages": [],
    })
    assert "confirm" in agent_await_en["messages"][0].content.lower()

    # Test unavailable room response turns in Tamil & English
    unavail_ta = receptionist_agent_node({
        "language": "ta-IN",
        "is_available": False,
        "check_in": ci,
        "check_out": co,
        "room_type": "suite",
        "messages": [],
    })
    assert len(unavail_ta["messages"]) == 1

    unavail_en = receptionist_agent_node({
        "language": "en-IN",
        "is_available": False,
        "check_in": ci,
        "check_out": co,
        "room_type": "suite",
        "messages": [],
    })
    assert len(unavail_en["messages"]) == 1


def test_extract_slots_more_cases():
    # Test suite room and guest count parsing
    state = {
        "messages": [
            HumanMessage(content="We need a royal suite for 4 members from 2026-12-01 to 2026-12-05")
        ]
    }
    res = extract_slots_node(state)
    assert res.get("room_type") == "suite"
    assert res.get("num_guests") == 4
    assert res.get("check_in") == "2026-12-01"
    assert res.get("check_out") == "2026-12-05"

    # Test single person and today
    state_today = {
        "messages": [HumanMessage(content="Single person room for today")]
    }
    res_today = extract_slots_node(state_today)
    assert res_today.get("num_guests") == 1
    assert res_today.get("check_in") == date.today().isoformat()


def test_room_service_and_vector_column():
    import random
    db = SessionLocal()
    try:
        rand_num = f"T{random.randint(1000, 9999)}"
        new_room = create_room(
            db,
            RoomCreate(
                name="Test Penthouse",
                room_number=rand_num,
                type="suite",
                floor=9,
                max_guests=4,
                price_per_night=15000.0,
                amenities=["Terrace"],
                description="Top floor penthouse with private terrace",
            ),
            embedding=[0.1] * 384,
        )
        assert new_room.id is not None
        fetched = get_room_by_id(db, new_room.id)
        assert fetched.room_number == rand_num
    finally:
        db.close()


def test_compatible_vector_type():
    cv = CompatibleVector(dimensions=384)
    # process_bind_param
    assert cv.process_bind_param(None, None) is None
    assert isinstance(cv.process_bind_param([1.0, 2.0], None), str)

    # process_result_value
    assert cv.process_result_value(None, None) is None
    assert cv.process_result_value("[1.0, 2.0]", None) == [1.0, 2.0]
    assert cv.process_result_value([1.0, 2.0], None) == [1.0, 2.0]


def test_api_error_routes():
    with TestClient(app) as client:
        # 404 Room Details
        r404 = client.get("/rooms/999999")
        assert r404.status_code == 404

        # 404 Booking Get
        b404 = client.get("/bookings/BK-NONEXISTENT")
        assert b404.status_code == 404

        # 404 Booking Cancel
        c404 = client.delete("/bookings/BK-NONEXISTENT")
        assert c404.status_code == 404


def test_faq_vector_search():
    db = SessionLocal()
    try:
        faqs = semantic_faq_search(db, "What is the checkout time?", limit=2)
        assert len(faqs) >= 1
        top_faq, score = faqs[0]
        assert "check-out" in top_faq.question_en.lower() or "check-out" in top_faq.answer_en.lower()

        # Empty search
        empty_faqs = semantic_faq_search(db, "", limit=1)
        assert len(empty_faqs) == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_sarvam_tts_stream_run(monkeypatch):
    import wave
    # Create valid dummy WAV bytes
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(b"\x00\x00" * 2400)
    fake_wav_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    class MockResp:
        status = 200
        async def json(self):
            return {"audios": [fake_wav_b64]}
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class MockSession:
        def post(self, *args, **kwargs):
            return MockResp()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", MockSession)

    tts = SarvamTTS(api_key="valid_key")
    stream = tts.synthesize("Hello")
    mock_emitter = MagicMock()
    await stream._run(mock_emitter)
    assert mock_emitter.initialize.called
    assert mock_emitter.push.called

    # Empty text case
    empty_stream = tts.synthesize("")
    await empty_stream._run(mock_emitter)


@pytest.mark.asyncio
async def test_sarvam_stt_rest_recognize(monkeypatch):
    class MockResp:
        status = 200
        async def json(self):
            return {"transcript": "வணக்கம்", "language_code": "ta-IN"}
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    class MockSession:
        def post(self, *args, **kwargs):
            return MockResp()
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass

    import aiohttp
    monkeypatch.setattr(aiohttp, "ClientSession", MockSession)

    stt = SarvamSTT(api_key="valid_key")
    mock_buffer = MagicMock()
    mock_buffer.write_wav = lambda f: f.write(b"RIFFdummyWAVdata")
    evt = await stt._recognize_impl(mock_buffer)
    assert evt is not None
    assert evt.alternatives[0].text == "வணக்கம்"


def test_sarvam_chat_model_mock(monkeypatch):
    from graph.graph import SarvamChatModel, get_llm
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

    class MockPostResp:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": "Vanakkam, welcome!"}}]}

    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **kw: MockPostResp())

    model = SarvamChatModel(api_key="test_key")
    res = model.invoke([
        SystemMessage(content="You are helpful."),
        HumanMessage(content="Hello"),
        AIMessage(content="Hi"),
    ])
    assert res is not None
    assert "Vanakkam" in res.content

    # Error case
    def mock_err(*a, **kw):
        raise ConnectionError("Timeout")
    monkeypatch.setattr(requests, "post", mock_err)
    assert model.invoke([HumanMessage(content="test")]) is None

    # Test get_llm
    monkeypatch.setenv("SARVAM_API_KEY", "test_key")
    llm = get_llm()
    assert llm is not None


@pytest.mark.asyncio
async def test_worker_adapter_and_entrypoint_mock(monkeypatch):
    from agent.worker import LangGraphLLMAdapter, entrypoint
    from unittest.mock import MagicMock
    monkeypatch.setenv("SARVAM_API_KEY", "test_key")

    # Adapter tests
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "messages": [AIMessage(content="How may I help you?")]
    }
    adapter = LangGraphLLMAdapter(mock_graph)
    reply = await adapter.ainvoke("Need a room")
    assert reply == "How may I help you?"

    # Entrypoint mock test
    mock_ctx = MagicMock()
    mock_ctx.room.name = "test-room"
    mock_ctx.connect = AsyncMock()

    with patch("agent.worker.silero.VAD.load") as mock_vad, \
         patch("agent.worker.Agent") as mock_agent, \
         patch("agent.worker.AgentSession") as mock_session:

        sess_instance = MagicMock()
        sess_instance.start = AsyncMock()
        sess_instance.say = MagicMock()
        sess_instance.on = MagicMock()
        mock_session.return_value = sess_instance

        await entrypoint(mock_ctx)
        assert mock_ctx.connect.called
        assert sess_instance.start.called
        assert sess_instance.say.called

    # Test start_worker
    from agent.worker import start_worker
    with patch("agent.worker.cli.run_app") as mock_run:
        start_worker()
        assert mock_run.called


def test_livekit_missing_credentials(monkeypatch):
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    with TestClient(app) as client:
        res = client.get("/livekit/token")
        assert res.status_code == 500


def test_embedding_and_vector_service_fallbacks():
    from api.services.embedding_service import embed_text, cosine_similarity
    from api.services.vector_service import semantic_room_search
    assert embed_text("") == [0.0] * 384
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0], [0.0]) == 0.0

    db = SessionLocal()
    try:
        results = semantic_room_search(db, "", limit=2)
        assert isinstance(results, list)
    finally:
        db.close()



