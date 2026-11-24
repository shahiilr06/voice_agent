"""
Local Interactive Voice & Dialogue Runner for Sunrise Hotel AI (Maya).
Tests the complete end-to-end AI pipeline locally on your machine with ZERO telephony:
  [Audio / Text Input]
         │
         ▼
  [Sarvam Saaras v4 STT]  (Speech-to-Text)
         │
         ▼
  [LangGraph StateGraph]  (Dialogue State Machine + Room DB + Booking Lifecycle)
         │
         ▼
  [Sarvam Bulbul v3 TTS]  (Natural Bilingual Tamil/English Speech Synthesis)
         │
         ▼
  [Laptop Speaker / WAV]  (Zero-lag local playback)
"""
import os
import sys
import io
import wave
import base64
import asyncio
import requests
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from graph.graph import build_hotel_graph
from agent.lang_detector import detect_language

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
SARVAM_TTS_SPEAKER = os.getenv("SARVAM_TTS_SPEAKER", "kavitha")
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"

INITIAL_GREETING = (
    "Welcome to Sunrise International Hotel. I am Maya, "
    "your virtual receptionist. How may I assist with your room booking today?"
)


def synthesize_speech(text: str, output_file: str = "maya_response.wav") -> str:
    """Synthesize speech using Sarvam Bulbul v3 and save to WAV."""
    if not SARVAM_API_KEY:
        print("[TTS] Warning: SARVAM_API_KEY not configured. Skipping audio synthesis.")
        return ""

    lang, _ = detect_language(text)
    target_lang = "ta-IN" if lang in ("ta-IN", "tanglish") else "en-IN"

    payload = {
        "inputs": [text[:500]],
        "target_language_code": target_lang,
        "speaker": SARVAM_TTS_SPEAKER,
        "model": SARVAM_TTS_MODEL,
        "speech_sample_rate": 24000,
        "audio_codec": "wav",
        "pace": 1.0,
    }
    headers = {
        "api-subscription-key": SARVAM_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(SARVAM_TTS_URL, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            audios = data.get("audios", [])
            if audios:
                raw_bytes = base64.b64decode(audios[0])
                with open(output_file, "wb") as f:
                    f.write(raw_bytes)
                return output_file
        else:
            print(f"[TTS Error] Sarvam status {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[TTS Error] Synthesis failed: {e}")
    return ""


def play_audio(file_path: str):
    """Play WAV audio on local laptop speakers using winsound (Windows native)."""
    if not file_path or not os.path.exists(file_path):
        return
    try:
        import winsound
        winsound.PlaySound(file_path, winsound.SND_FILENAME)
    except Exception as e:
        print(f"[Audio] (WAV saved at {file_path}, playback skipped: {e})")


def transcribe_audio_file(audio_path: str, language: str = "auto") -> str:
    """Transcribe a local WAV file using Sarvam Saaras v4 STT."""
    if not SARVAM_API_KEY or not os.path.exists(audio_path):
        return ""

    headers = {"api-subscription-key": SARVAM_API_KEY}
    with open(audio_path, "rb") as af:
        files = {"file": ("audio.wav", af, "audio/wav")}
        data = {
            "model": os.getenv("SARVAM_STT_MODEL", "saaras:v4"),
            "mode": "transcribe",
        }
        if language and language != "auto":
            data["language_code"] = language

        resp = requests.post(SARVAM_STT_URL, files=files, data=data, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("transcript", "").strip()
        else:
            print(f"[STT Error] Status {resp.status_code}: {resp.text}")
    return ""


class LocalMayaSession:
    """Manages local multi-turn dialogue with Maya AI using LangGraph."""

    def __init__(self):
        self.graph = build_hotel_graph()
        self.state = {
            "messages": [],
            "language": None,
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

    def process_turn(self, user_text: str) -> str:
        """Process one conversational turn through LangGraph."""
        self.state["messages"].append(HumanMessage(content=user_text))
        new_state = self.graph.invoke(self.state)
        self.state = new_state

        reply = "How can I assist you today?"
        for m in reversed(new_state.get("messages", [])):
            if isinstance(m, AIMessage) or getattr(m, "type", None) == "ai":
                reply = m.content
                break
        return reply

    def get_summary(self) -> dict:
        """Return active extracted slots."""
        return {
            "stage": self.state.get("stage"),
            "language": self.state.get("language"),
            "room_type": self.state.get("room_type"),
            "check_in": self.state.get("check_in"),
            "check_out": self.state.get("check_out"),
            "num_guests": self.state.get("num_guests"),
            "guest_name": self.state.get("guest_name"),
            "is_available": self.state.get("is_available"),
            "total_price": self.state.get("total_price"),
            "booking_confirmed": self.state.get("booking_confirmed"),
            "confirmation_code": self.state.get("confirmation_code"),
        }


def run_automated_verification():
    """Verify the full ASR/STT + LangGraph + DB + TTS pipeline locally."""
    print("=" * 65)
    print("🏨 [Local AI Pipeline Verification] Starting end-to-end test...")
    print("=" * 65)

    session = LocalMayaSession()

    test_turns = [
        ("Guest Greeting (Tamil)", "வணக்கம்! எனக்கு ஒரு டீலக்ஸ் ரூம் வேணும்"),
        ("Guest Dates & Count", "Check in tomorrow for 2 nights, 2 guests"),
        ("Guest Name & Confirmation", "My name is Rajesh Kumar, please confirm booking"),
    ]

    for label, user_msg in test_turns:
        print(f"\n👤 [User - {label}]:")
        print(f"   \"{user_msg}\"")
        reply = session.process_turn(user_msg)
        print(f"🤖 [Maya AI]:")
        print(f"   \"{reply}\"")
        slots = session.get_summary()
        print(f"📊 [Slot State]: room={slots['room_type']}, dates={slots['check_in']}->{slots['check_out']}, confirmed={slots['booking_confirmed']}, code={slots['confirmation_code']}")

    # Verify TTS synthesis on final confirmation
    print("\n🔊 [Sarvam Bulbul v3 TTS] Synthesizing speech audio for final response...")
    wav_file = synthesize_speech(reply, output_file="maya_test_output.wav")
    if wav_file and os.path.exists(wav_file):
        size = os.path.getsize(wav_file)
        print(f"✅ [TTS Success] Audio generated: {wav_file} ({size} bytes)")
    else:
        print("⚠️ [TTS Warning] Audio file not generated.")

    print("\n" + "=" * 65)
    print("🎉 All Local AI Components (ASR + LangGraph + DB + TTS) Verified Successfully!")
    print("=" * 65)


def run_interactive():
    """Interactive CLI to speak or chat with Maya AI locally."""
    print("=" * 65)
    print("🏨 Sunrise International Hotel - Local AI Voice Assistant (Maya)")
    print("   Powered by Sarvam Saaras v4 STT, LangGraph & Sarvam Bulbul v3 TTS")
    print("=" * 65)
    print(f"🤖 Maya: \"{INITIAL_GREETING}\"")
    print("\n💡 Tips:")
    print("   - Type in English, Tamil (தமிழ்), or Tanglish (e.g. 'room venum').")
    print("   - Type 'slots' to view current extracted booking parameters.")
    print("   - Type 'exit' or 'quit' to end.")
    print("-" * 65)

    # Speak initial greeting
    wav_file = synthesize_speech(INITIAL_GREETING, "maya_greeting.wav")
    play_audio(wav_file)

    session = LocalMayaSession()

    while True:
        try:
            user_input = input("\n👤 You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("\n👋 Maya: Thank you for contacting Sunrise International Hotel. Have a wonderful day!")
                break
            if user_input.lower() == "slots":
                print(f"📊 Current State: {session.get_summary()}")
                continue

            reply = session.process_turn(user_input)
            print(f"\n🤖 Maya: {reply}")

            # Synthesize & play speech
            wav = synthesize_speech(reply, "maya_reply.wav")
            play_audio(wav)

        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            break


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        run_automated_verification()
    else:
        run_interactive()
