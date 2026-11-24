"""
LiveKit Voice Agent Worker.
Wires WebRTC transport, Voice Activity Detection, Sarvam Saaras v4 STT,
LangGraph dialogue state machine, and Sarvam Bulbul TTS.
"""
import os
import sys
import asyncio

# Ensure project root is in sys.path regardless of where worker.py is invoked
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

try:
    from livekit.agents import (
        AutoSubscribe,
        JobContext,
        WorkerOptions,
        cli,
    )
    from livekit.agents.voice import Agent, AgentSession
    from livekit.agents.voice.events import UserInputTranscribedEvent
    from livekit.plugins import silero
    HAS_LIVEKIT_AGENTS = True
except ImportError:
    HAS_LIVEKIT_AGENTS = False
    AutoSubscribe = None
    JobContext = None
    WorkerOptions = None
    cli = None
    Agent = None
    AgentSession = None
    silero = None
    UserInputTranscribedEvent = None

from agent.sarvam_stt import SarvamSTT
from agent.sarvam_tts import SarvamTTS
from graph.graph import build_hotel_graph
from langchain_core.messages import HumanMessage, AIMessage

load_dotenv()

GREETING_MESSAGE = (
    "Welcome to Sunrise International Hotel! I am Maya, your virtual receptionist. "
    "Which language would you prefer — English, Tamil, or Tanglish? "
    "வணக்கம், நீங்கள் எந்த மொழியில் பேச விரும்புகிறீர்கள்?"
)


class LangGraphLLMAdapter:
    """
    Adapter bridging compiled LangGraph StateGraph with LiveKit Voice AgentSession.
    """
    def __init__(self, compiled_graph):
        self.graph = compiled_graph
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

    async def ainvoke(self, user_transcript: str) -> str:
        """Process incoming speech transcript through LangGraph."""
        # Append human message to state
        self.state["messages"].append(HumanMessage(content=user_transcript))

        # Run state graph in executor to prevent blocking asyncio loop
        loop = asyncio.get_running_loop()
        new_state = await loop.run_in_executor(None, self.graph.invoke, self.state)
        self.state = new_state

        # Retrieve the latest receptionist voice response
        latest_reply = "How can I assist you today?"
        for m in reversed(new_state.get("messages", [])):
            if isinstance(m, AIMessage) or getattr(m, "type", None) == "ai":
                latest_reply = m.content
                break

        return latest_reply


async def entrypoint(ctx: JobContext):
    """LiveKit agent worker room lifecycle entrypoint."""
    print(f"Connecting agent worker to room: {ctx.room.name}...")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # 1. Compile LangGraph
    hotel_graph = build_hotel_graph()
    agent_adapter = LangGraphLLMAdapter(hotel_graph)

    # 2. Initialize VAD, STT, and TTS (16kHz HD Telephony pace=1.0 for crystal clear phone audio)
    vad_plugin = silero.VAD.load()
    stt_plugin = SarvamSTT()
    tts_plugin = SarvamTTS(sample_rate=16000, pace=1.0)

    print(f"Agent worker connected successfully to {ctx.room.name} with Sarvam Saaras v4 STT & Bulbul TTS (16kHz).")

    # 3. Create Voice Agent and Session
    agent = Agent(
        instructions="You are Maya, receptionist at Sunrise International Hotel.",
        stt=stt_plugin,
        tts=tts_plugin,
        vad=vad_plugin,
    )

    session = AgentSession(
        stt=stt_plugin,
        tts=tts_plugin,
        vad=vad_plugin,
    )

    # 4. Start session in the LiveKit room
    await session.start(agent, room=ctx.room)

    # 5. Broadcast initial bilingual greeting EXACTLY ONCE after caller connects
    has_greeted = False

    async def send_greeting_after_connect():
        nonlocal has_greeted
        if not has_greeted:
            has_greeted = True
            # Short 0.8s pause to ensure the caller has answered and audio path is fully open
            await asyncio.sleep(0.8)
            if ctx.room.isconnected:
                print("📢 [Maya Initial Greeting]: Starting greeting...")
                session.say(GREETING_MESSAGE)

    @ctx.room.on("participant_connected")
    def on_participant_connected(participant):
        identity = getattr(participant, "identity", "") or ""
        import re
        digits = re.findall(r"\d{10,12}", identity)
        if digits and not agent_adapter.state.get("guest_phone"):
            agent_adapter.state["guest_phone"] = digits[0]
            print(f"📞 [Caller Phone Detected from SIP Identity]: {digits[0]}")
        asyncio.create_task(send_greeting_after_connect())

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track, publication, participant):
        print(f"🎙️ [Audio Track Subscribed] Receiving audio from: {participant.identity} ({track.kind})")
        asyncio.create_task(send_greeting_after_connect())

    # If caller is already in room when agent worker joins
    if ctx.room.remote_participants:
        asyncio.create_task(send_greeting_after_connect())

    last_processed_text = ""
    last_processed_time = 0.0
    is_processing_turn = False

    async def handle_turn(text: str):
        nonlocal last_processed_text, last_processed_time, is_processing_turn
        import time
        now = time.time()
        if is_processing_turn:
            return
        if text.strip().lower() == last_processed_text.strip().lower() and (now - last_processed_time) < 2.5:
            return

        is_processing_turn = True
        last_processed_text = text
        last_processed_time = now

        if not ctx.room.isconnected:
            is_processing_turn = False
            return

        print(f"\n👤 [Guest Voice]: \"{text}\"")
        try:
            reply = await agent_adapter.ainvoke(text)
            print(f"🤖 [Maya Reply]: \"{reply}\"\n")
            if ctx.room.isconnected:
                session.say(reply)
        except Exception as e:
            print(f"Error processing dialogue turn: {e}", file=sys.stderr)
            if ctx.room.isconnected:
                session.say("Could you please repeat that?")
        finally:
            is_processing_turn = False

    # Handle incoming user speech transcripts cleanly without double-triggering
    @session.on("user_input_transcribed")
    def on_user_input(evt):
        if not ctx.room.isconnected:
            return
        text = evt.transcript if hasattr(evt, "transcript") else str(evt)
        is_final = getattr(evt, "is_final", True)
        if not is_final or not text or not text.strip():
            return
        asyncio.create_task(handle_turn(text.strip()))


def start_worker():
    """Start the LiveKit agent worker."""
    if cli is None:
        raise RuntimeError("livekit-agents CLI is not installed or available.")
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    start_worker()
