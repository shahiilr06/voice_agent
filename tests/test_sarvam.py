import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from agent.lang_detector import detect_language
from agent.sarvam_stt import SarvamSTT
from agent.sarvam_tts import SarvamTTS
from agent.worker import LangGraphLLMAdapter
from graph.graph import build_hotel_graph


def test_lang_detector_cases():
    # English utterances
    lang, conf = detect_language("I want to book a room for tomorrow")
    assert lang == "en-IN"
    assert conf > 0.5

    lang, conf = detect_language("Good morning, what are the checkout times?")
    assert lang == "en-IN"

    # Empty text defaults to English
    lang_empty, _ = detect_language("")
    assert lang_empty == "en-IN"


def test_sarvam_stt_instantiation(monkeypatch):
    stt = SarvamSTT(api_key="test_key", model="saaras:v4", language_code="en-IN", streaming=True)
    assert stt.model == "saaras:v4"
    assert stt.capabilities.streaming is True
    assert stt.capabilities.interim_results is True

    # Test error when api_key is missing from both arg and env
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    with pytest.raises(ValueError):
        SarvamSTT(api_key=None)


def test_sarvam_tts_instantiation(monkeypatch):
    tts = SarvamTTS(api_key="test_key", model="bulbul:v3", speaker="kavitha")
    assert tts.model == "bulbul:v3"
    assert tts.speaker == "kavitha"
    assert tts.sample_rate == 24000

    # Test error when api_key is missing from both arg and env
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    with pytest.raises(ValueError):
        SarvamTTS(api_key=None)


@pytest.mark.asyncio
async def test_langgraph_llm_adapter():
    graph = build_hotel_graph()
    adapter = LangGraphLLMAdapter(graph)
    reply = await adapter.ainvoke("Hi, do you have a deluxe room available for tomorrow?")
    assert isinstance(reply, str)
    assert len(reply) > 0
    assert len(adapter.state["messages"]) >= 2
