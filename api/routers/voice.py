"""
Direct Local Voice & Dialogue Router.
Processes voice audio or text input through:
Sarvam Saaras v4 STT (English en-IN) -> LangGraph Dialogue State Machine -> Sarvam Bulbul v3 TTS.
Serves real-time responses directly over HTTP port 8004 without requiring WebRTC ports.
"""
import os
import io
import wave
import base64
import asyncio
import requests
import av
from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from langchain_core.messages import HumanMessage, AIMessage

from graph.graph import build_hotel_graph

router = APIRouter(prefix="/voice", tags=["Local Voice Pipeline"])

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v4")
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
SARVAM_TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "kavitha")
SARVAM_TTS_PACE = float(os.getenv("SARVAM_TTS_PACE", "1.15"))


def convert_to_wav_16k(audio_bytes: bytes) -> bytes:
    """
    Standardize any audio format (WebM, Opus, Ogg, MP4, AAC, WAV) into
    16kHz mono 16-bit PCM WAV for Sarvam Saaras v4 STT.
    """
    inp = io.BytesIO(audio_bytes)
    out = io.BytesIO()
    with av.open(inp) as container:
        audio_stream = next((s for s in container.streams if s.type == "audio"), None)
        if not audio_stream:
            raise ValueError("No audio stream found in audio container")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        with wave.open(out, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            for frame in container.decode(audio_stream):
                for resampled_frame in resampler.resample(frame):
                    wf.writeframes(bytes(resampled_frame.planes[0]))
    return out.getvalue()


# Global conversation state for active session
_active_state = {
    "messages": [],
    "language": "en-IN",
    "guest_name": None,
    "guest_phone": None,
    "guest_email": None,
    "room_type": None,
    "check_in": None,
    "check_out": None,
    "num_guests": None,
    "is_available": False,
    "available_room_id": None,
    "available_room_name": None,
    "price_per_night": None,
    "total_price": None,
    "guest_confirmed": False,
    "booking_confirmed": False,
    "confirmation_code": None,
    "stage": "greeting",
}

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_hotel_graph()
    return _graph


@router.get("/status")
def get_voice_status():
    """Returns the status of the local voice listening port and STT/TTS pipeline."""
    return {
        "status": "online",
        "port": int(os.getenv("API_PORT", 8004)),
        "listen_ready": bool(SARVAM_API_KEY),
        "stt_model": SARVAM_STT_MODEL,
        "tts_model": SARVAM_TTS_MODEL,
        "language_support": ["en-IN", "ta-IN", "tanglish"],
        "pace": SARVAM_TTS_PACE,
        "message": "Listen port active and ready for multilingual voice interaction (English, Tamil, Tanglish).",
    }


@router.get("/greeting")
async def get_initial_greeting():
    """Returns the initial bilingual greeting asking for language preference and synthesized audio."""
    greeting_text = (
        "Welcome to Sunrise International Hotel! I am Maya, your virtual receptionist. "
        "Which language would you prefer — English, Tamil, or Tanglish? "
        "வணக்கம், நீங்கள் எந்த மொழியில் பேச விரும்புகிறீர்கள்?"
    )
    audio_base64 = ""
    if SARVAM_API_KEY:
        tts_payload = {
            "inputs": [greeting_text],
            "target_language_code": "ta-IN",
            "speaker": SARVAM_TTS_SPEAKER,
            "model": SARVAM_TTS_MODEL,
            "speech_sample_rate": 24000,
            "audio_codec": "wav",
            "pace": SARVAM_TTS_PACE,
        }
        tts_headers = {
            "api-subscription-key": SARVAM_API_KEY,
            "Content-Type": "application/json",
        }
        try:
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: requests.post(SARVAM_TTS_URL, json=tts_payload, headers=tts_headers, timeout=10),
            )
            if resp.status_code == 200:
                audios = resp.json().get("audios", [])
                if audios:
                    audio_base64 = audios[0]
        except Exception as e:
            print(f"[Greeting TTS Error]: {e}")

    return {
        "text": greeting_text,
        "audio_base64": audio_base64,
    }


@router.post("/chat")
async def voice_chat_endpoint(
    text: Optional[str] = Form(default=None),
    audio_file: Optional[UploadFile] = File(default=None),
):
    """
    Process user voice audio or text message through the complete AI pipeline.
    Supports English, Tamil, and Tanglish with natural conversational speed.
    """
    global _active_state

    user_text = ""

    # 1. If audio file provided, transcribe using Sarvam Saaras v4 STT
    if audio_file:
        audio_bytes = await audio_file.read()
        if len(audio_bytes) > 0:
            if not SARVAM_API_KEY:
                raise HTTPException(status_code=500, detail="SARVAM_API_KEY not configured.")

            # Convert browser audio (WebM Opus / etc.) to clean 16kHz mono WAV
            try:
                wav_bytes = convert_to_wav_16k(audio_bytes)
            except Exception as cvt_err:
                print(f"[Audio Conversion Note]: {cvt_err}, using original bytes.")
                wav_bytes = audio_bytes

            if len(wav_bytes) < 320:
                return {
                    "success": False,
                    "error": "Audio snippet too short. Please speak clearly.",
                }

            headers = {"api-subscription-key": SARVAM_API_KEY}
            files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
            data = {
                "model": SARVAM_STT_MODEL,
                "mode": "transcribe",
            }
            # If language is already established, pass hint, otherwise auto-detect
            active_lang = _active_state.get("language")
            if active_lang in ("ta-IN", "en-IN"):
                data["language_code"] = active_lang

            try:
                loop = asyncio.get_running_loop()
                resp = await loop.run_in_executor(
                    None,
                    lambda: requests.post(SARVAM_STT_URL, files=files, data=data, headers=headers, timeout=15),
                )
                if resp.status_code == 200:
                    user_text = resp.json().get("transcript", "").strip()
                    print(f"🎤 [Sarvam STT Captured]: \"{user_text}\"")
                else:
                    err_msg = resp.text
                    print(f"[Sarvam STT Error] HTTP {resp.status_code}: {err_msg}")
                    return {
                        "success": False,
                        "error": "Could not recognize audio. Please speak clearly into your microphone.",
                    }
            except Exception as req_err:
                print(f"[Sarvam STT Connection Error]: {req_err}")
                return {
                    "success": False,
                    "error": f"Speech-to-Text service error: {req_err}",
                }

    # Fallback to provided text
    if not user_text and text:
        user_text = text.strip()

    if not user_text:
        return {
            "success": False,
            "error": "No speech detected. Please speak or type your request.",
        }

    # 2. Process through LangGraph State Machine
    graph = get_graph()
    _active_state["messages"].append(HumanMessage(content=user_text))
    new_state = graph.invoke(_active_state)
    _active_state = new_state

    # Extract Maya's reply
    reply_text = "How may I assist with your room reservation today?"
    for m in reversed(new_state.get("messages", [])):
        if isinstance(m, AIMessage) or getattr(m, "type", None) == "ai":
            reply_text = m.content
            break

    # 3. Synthesize speech using Sarvam Bulbul v3 TTS (Natural pace 1.15)
    audio_base64 = ""
    current_lang = new_state.get("language") or "en-IN"
    if SARVAM_API_KEY and reply_text:
        # Detect if reply contains Tamil script or is Tanglish
        has_tamil_chars = any('\u0B80' <= c <= '\u0BFF' for c in reply_text)
        target_lang = "ta-IN" if (has_tamil_chars or current_lang in ("ta-IN", "tanglish")) else "en-IN"

        tts_payload = {
            "inputs": [reply_text[:500]],
            "target_language_code": target_lang,
            "speaker": SARVAM_TTS_SPEAKER,
            "model": SARVAM_TTS_MODEL,
            "speech_sample_rate": 24000,
            "audio_codec": "wav",
            "pace": SARVAM_TTS_PACE,
        }
        tts_headers = {
            "api-subscription-key": SARVAM_API_KEY,
            "Content-Type": "application/json",
        }
        try:
            loop = asyncio.get_running_loop()
            tts_resp = await loop.run_in_executor(
                None,
                lambda: requests.post(SARVAM_TTS_URL, json=tts_payload, headers=tts_headers, timeout=10),
            )
            if tts_resp.status_code == 200:
                tts_data = tts_resp.json()
                audios = tts_data.get("audios", [])
                if audios:
                    audio_base64 = audios[0]
        except Exception as e:
            print(f"[TTS Error in Voice Router]: {e}")

    # 4. Return complete response
    return {
        "success": True,
        "user_text": user_text,
        "reply_text": reply_text,
        "audio_base64": audio_base64,
        "language": current_lang,
        "slots": {
            "room_type": _active_state.get("room_type"),
            "check_in": _active_state.get("check_in"),
            "check_out": _active_state.get("check_out"),
            "num_guests": _active_state.get("num_guests"),
            "guest_name": _active_state.get("guest_name"),
            "is_available": _active_state.get("is_available"),
            "total_price": _active_state.get("total_price"),
            "booking_confirmed": _active_state.get("booking_confirmed"),
            "confirmation_code": _active_state.get("confirmation_code"),
        },
    }


@router.post("/reset")
def reset_conversation():
    """Reset the active conversation state."""
    global _active_state
    _active_state = {
        "messages": [],
        "language": "en-IN",
        "guest_name": None,
        "guest_phone": None,
        "guest_email": None,
        "room_type": None,
        "check_in": None,
        "check_out": None,
        "num_guests": None,
        "is_available": False,
        "available_room_id": None,
        "available_room_name": None,
        "price_per_night": None,
        "total_price": None,
        "guest_confirmed": False,
        "booking_confirmed": False,
        "confirmation_code": None,
        "stage": "greeting",
    }
    return {"success": True, "message": "Conversation state reset."}
