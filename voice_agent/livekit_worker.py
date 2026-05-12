import asyncio
import inspect
import json
import os
import re
import secrets
from dataclasses import dataclass, field

import aiohttp
import litellm
from dotenv import load_dotenv
from livekit import api, rtc
from livekit.agents import stt as lk_stt
from livekit.plugins import sarvam

try:
    from .sarvam_orchestrator import configure_runtime, generate_agent_reply, validate_sarvam_config
except ImportError:
    from sarvam_orchestrator import configure_runtime, generate_agent_reply, validate_sarvam_config

load_dotenv()


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_float(name: str, default: float) -> float:
    value = (os.getenv(name) or "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = (os.getenv(name) or "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = (os.getenv(name) or "").strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


LIVEKIT_URL = _required_env("LIVEKIT_URL")
LIVEKIT_API_KEY = _required_env("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = _required_env("LIVEKIT_API_SECRET")
SARVAM_API_KEY = _required_env("SARVAM_API_KEY")
ROOM_NAME = os.getenv("LIVEKIT_ROOM", "hotel-assistant-room")

SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saarika:v2.5")
SARVAM_STT_LANGUAGE = os.getenv("SARVAM_STT_LANGUAGE", "unknown")
SARVAM_STT_PROMPT = (
    os.getenv("SARVAM_STT_PROMPT", "").strip()
    or (
        "Transcribe hotel booking calls in Tamil and English with high accuracy. "
        "Important terms: Sunrise Hotel, room, check-in, check-out, guests, standard, deluxe, suite, family, "
        "இன்று, நாளை, விலை, அறை, முன்பதிவு."
    )
)
SARVAM_STT_LANGUAGE_EN = os.getenv("SARVAM_STT_LANGUAGE_EN", "en-IN")
SARVAM_STT_LANGUAGE_TA = os.getenv("SARVAM_STT_LANGUAGE_TA", "ta-IN")
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v2")
SARVAM_TTS_SPEAKER_DEFAULT = os.getenv("SARVAM_TTS_SPEAKER", "anushka")
SARVAM_TTS_LANGUAGE_EN = os.getenv("SARVAM_TTS_LANGUAGE_EN", os.getenv("SARVAM_TTS_LANGUAGE", "en-IN"))
SARVAM_TTS_LANGUAGE_TA = os.getenv("SARVAM_TTS_LANGUAGE_TA", "ta-IN")
SARVAM_TTS_SPEAKER_EN = os.getenv("SARVAM_TTS_SPEAKER_EN", SARVAM_TTS_SPEAKER_DEFAULT)
SARVAM_TTS_SPEAKER_TA = os.getenv("SARVAM_TTS_SPEAKER_TA", SARVAM_TTS_SPEAKER_DEFAULT)
SARVAM_TTS_SAMPLE_RATE = int(os.getenv("SARVAM_TTS_SAMPLE_RATE", "16000"))
STT_FLUSH_DELAY_SECONDS = _env_float("STT_FLUSH_DELAY_SECONDS", 0.9)
STT_SPEAK_COOLDOWN_SECONDS = _env_float("STT_SPEAK_COOLDOWN_SECONDS", 0.55)
STT_MIN_TRANSCRIPT_CHARS = _env_int("STT_MIN_TRANSCRIPT_CHARS", 2)
STT_END_OF_SPEECH_SETTLE_SECONDS = _env_float("STT_END_OF_SPEECH_SETTLE_SECONDS", 0.2)
STT_ADAPTIVE_LANGUAGE_HINT = _env_bool("STT_ADAPTIVE_LANGUAGE_HINT", False)
STT_DUPLICATE_WINDOW_SECONDS = _env_float("STT_DUPLICATE_WINDOW_SECONDS", 2.2)
STT_LOW_CONFIDENCE_THRESHOLD = _env_float("STT_LOW_CONFIDENCE_THRESHOLD", 0.35)
STT_LOW_CONFIDENCE_MAX_WORDS = _env_int("STT_LOW_CONFIDENCE_MAX_WORDS", 1)
CONVERSATION_HISTORY_MAX_TURNS = _env_int("CONVERSATION_HISTORY_MAX_TURNS", 40)
_TAMIL_SCRIPT_RE = re.compile(r"[\u0B80-\u0BFF]")


def create_worker_token(room_name: str, worker_identity: str) -> str:
    grants = api.VideoGrants(
        room_join=True,
        room=room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
        agent=True,
    )
    return (
        api.AccessToken(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
        .with_identity(worker_identity)
        .with_name("Hotel Agent Worker")
        .with_grants(grants)
        .to_jwt()
    )


@dataclass
class ParticipantSession:
    identity: str
    participant: rtc.RemoteParticipant
    audio_track: rtc.RemoteAudioTrack | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    greeted: bool = False
    pending_segments: list[str] = field(default_factory=list)
    last_interim: str = ""
    utterance_queue: asyncio.Queue[str | None] = field(default_factory=asyncio.Queue)
    flush_task: asyncio.Task | None = None
    active: bool = True
    done_event: asyncio.Event = field(default_factory=asyncio.Event)
    run_task: asyncio.Task | None = None
    agent_speaking: bool = False
    speak_cooldown_until: float = 0.0
    stt_language_hint: str = SARVAM_STT_LANGUAGE
    last_utterance_key: str = ""
    last_utterance_at: float = 0.0


class LiveKitHotelWorker:
    def __init__(self):
        self.room: rtc.Room | None = None
        self.http_session: aiohttp.ClientSession | None = None
        self.stt_client: sarvam.STT | None = None
        self.tts_clients: dict[str, sarvam.TTS] = {}
        self.audio_source: rtc.AudioSource | None = None
        self.assistant_track: rtc.LocalAudioTrack | None = None
        self.session: ParticipantSession | None = None
        self.tasks: set[asyncio.Task] = set()
        self.tts_lock = asyncio.Lock()

    @staticmethod
    def _disconnect_reason_name(reason: object) -> str:
        try:
            return rtc.DisconnectReason.Name(int(reason))
        except Exception:
            return str(reason)

    def _reset_room_resources(self) -> None:
        self.room = rtc.Room()
        self.audio_source = rtc.AudioSource(
            sample_rate=SARVAM_TTS_SAMPLE_RATE,
            num_channels=1,
        )
        self.assistant_track = rtc.LocalAudioTrack.create_audio_track("hotel-assistant", self.audio_source)

    @staticmethod
    def _is_worker_identity(identity: str) -> bool:
        return identity.startswith("hotel-agent-worker")

    @staticmethod
    def _is_tamil_text(text: str) -> bool:
        return bool(_TAMIL_SCRIPT_RE.search(text or ""))

    @staticmethod
    def _sanitize_agent_reply_text(text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
        if "<think>" in cleaned.lower():
            cleaned = re.split(r"<think>", cleaned, flags=re.IGNORECASE)[0].strip()
        return cleaned

    def _select_tts_client(self, text: str) -> sarvam.TTS | None:
        if self._is_tamil_text(text):
            return self.tts_clients.get(SARVAM_TTS_LANGUAGE_TA) or self.tts_clients.get(SARVAM_TTS_LANGUAGE_EN)
        return self.tts_clients.get(SARVAM_TTS_LANGUAGE_EN) or self.tts_clients.get(SARVAM_TTS_LANGUAGE_TA)

    @staticmethod
    def _speech_language(event: lk_stt.SpeechEvent) -> str:
        alternatives = getattr(event, "alternatives", None) or []
        if not alternatives:
            return ""
        return (getattr(alternatives[0], "language", "") or "").strip()

    @staticmethod
    def _speech_confidence(event: lk_stt.SpeechEvent) -> float | None:
        alternatives = getattr(event, "alternatives", None) or []
        if not alternatives:
            return None
        confidence = getattr(alternatives[0], "confidence", None)
        if confidence is None:
            return None
        try:
            return float(confidence)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _is_filler_only(text: str) -> bool:
        lowered = text.lower().strip()
        return lowered in {"uh", "um", "hmm", "mm", "ah", "eh", "ஐயோ", "அம்"}

    def _postprocess_transcript_text(self, text: str) -> str:
        normalized = self._normalize_transcript_text(text)
        if not normalized:
            return ""

        replacements = (
            (r"\brome\b", "room"),
            (r"\brum\b", "room"),
            (r"\bdelux\b", "deluxe"),
            (r"\bchek[- ]?in\b", "check-in"),
            (r"\bchecking[- ]?date\b", "check-in date"),
            (r"\bchek[- ]?out\b", "check-out"),
            (r"\bto\s?day\b", "today"),
            (r"\btomoro+w?\b", "tomorrow"),
            (r"\bsun\s?rise\b", "sunrise"),
            (r"செக் இன்", "செக்-இன்"),
            (r"செக்கின்", "செக்-இன்"),
            (r"செக்கிங்", "செக்-இன்"),
            (r"செக் அவுட்", "செக்-அவுட்"),
            (r"செக்கவுட்", "செக்-அவுட்"),
        )
        for pattern, replacement in replacements:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

        return self._normalize_transcript_text(normalized)

    def _detect_language_hint(self, text: str, event_language: str) -> str | None:
        if event_language in {SARVAM_STT_LANGUAGE_EN, SARVAM_STT_LANGUAGE_TA}:
            return event_language
        lowered = text.lower()
        if self._is_tamil_text(text) or re.search(r"\b(vanakkam|nandri)\b", lowered):
            return SARVAM_STT_LANGUAGE_TA
        if re.search(r"[a-zA-Z]", text):
            return SARVAM_STT_LANGUAGE_EN
        return None

    def _build_stt_prompt_for_language(self, language_hint: str) -> str:
        base = (
            "Hotel booking conversation in Tamil and English. "
            "Key terms: Sunrise Hotel, room, check-in, check-out, guests, standard, deluxe, suite, family, "
            "வணக்கம், அறை, முன்பதிவு, செக்-இன், செக்-அவுட், விருந்தினர், இன்று, நாளை, பேர், நம்பர்."
        )
        if language_hint == SARVAM_STT_LANGUAGE_TA:
            return base + " Prioritize Tamil transcription for Tamil speech."
        if language_hint == SARVAM_STT_LANGUAGE_EN:
            return base + " Prioritize English transcription for English speech."
        return base

    def _stt_stream_candidates(self, session: ParticipantSession) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []

        def add_candidate(model: str, language: str, prompt: str):
            entry = {"model": model, "language": language, "prompt": prompt}
            if entry not in candidates:
                candidates.append(entry)

        base_prompt = self._build_stt_prompt_for_language(session.stt_language_hint)
        add_candidate(SARVAM_STT_MODEL, SARVAM_STT_LANGUAGE, base_prompt)

        if SARVAM_STT_MODEL.startswith("saaras"):
            add_candidate("saarika:v2.5", session.stt_language_hint, SARVAM_STT_PROMPT)
            add_candidate("saarika:v2.5", SARVAM_STT_LANGUAGE_EN, SARVAM_STT_PROMPT)
            add_candidate("saarika:v2.5", "unknown", SARVAM_STT_PROMPT)
        else:
            add_candidate(SARVAM_STT_MODEL, SARVAM_STT_LANGUAGE_EN, SARVAM_STT_PROMPT)
            add_candidate("saarika:v2.5", SARVAM_STT_LANGUAGE_EN, SARVAM_STT_PROMPT)

        return candidates

    def _maybe_update_stt_language_hint(self, session: ParticipantSession, stt_stream, text: str, event_language: str):
        if not STT_ADAPTIVE_LANGUAGE_HINT:
            return
        if not SARVAM_STT_MODEL.startswith("saaras"):
            return
        language_hint = self._detect_language_hint(text, event_language)
        if not language_hint or language_hint == session.stt_language_hint:
            return

        try:
            session.stt_language_hint = language_hint
            stt_stream.update_options(
                language=language_hint,
                model=SARVAM_STT_MODEL,
                prompt=self._build_stt_prompt_for_language(language_hint),
            )
            print(f"[STT] Updated language hint to {language_hint}")
        except Exception as e:
            print(f"[STT] Could not update language hint: {e}")

    async def _ensure_sarvam_clients(self) -> None:
        if self.http_session is None or self.http_session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
            self.http_session = aiohttp.ClientSession(timeout=timeout)

        # Sarvam plugins need an explicit aiohttp session when running outside livekit-agents job context.
        stt_kwargs = {
            "language": SARVAM_STT_LANGUAGE,
            "model": SARVAM_STT_MODEL,
            "api_key": SARVAM_API_KEY,
            "http_session": self.http_session,
            "prompt": SARVAM_STT_PROMPT,
        }
        stt_signature = inspect.signature(sarvam.STT.__init__).parameters
        if "flush_signal" in stt_signature:
            stt_kwargs["flush_signal"] = True
        if "mode" in stt_signature:
            stt_kwargs["mode"] = "transcribe"
        
        try:
            self.stt_client = sarvam.STT(**stt_kwargs)
            print("[WORKER] STT client initialized")
        except Exception as e:
            print(f"[WORKER ERROR] Failed to initialize STT: {e}")
            raise

        self.tts_clients.clear()
        tts_configs = (
            (SARVAM_TTS_LANGUAGE_EN, SARVAM_TTS_SPEAKER_EN),
            (SARVAM_TTS_LANGUAGE_TA, SARVAM_TTS_SPEAKER_TA),
        )
        for language_code, speaker in tts_configs:
            if language_code in self.tts_clients:
                continue
            try:
                self.tts_clients[language_code] = sarvam.TTS(
                    target_language_code=language_code,
                    model=SARVAM_TTS_MODEL,
                    speaker=speaker,
                    speech_sample_rate=SARVAM_TTS_SAMPLE_RATE,
                    api_key=SARVAM_API_KEY,
                    http_session=self.http_session,
                )
                print(f"[WORKER] TTS client initialized for {language_code}")
            except Exception as e:
                print(f"[WORKER ERROR] Failed to initialize TTS for {language_code}: {e}")

    def _track_task(self, task: asyncio.Task):
        self.tasks.add(task)

        def _cleanup(done_task: asyncio.Task):
            self.tasks.discard(done_task)
            try:
                done_task.result()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"[WORKER ERROR] Background task failed: {e}")

        task.add_done_callback(_cleanup)

    async def _publish_event(self, event_type: str, text: str):
        if self.room is None:
            return
        payload = json.dumps({"type": event_type, "text": text})
        try:
            await self.room.local_participant.publish_data(payload, reliable=True, topic="agent-events")
        except Exception:
            pass

    async def _speak(self, text: str, session: ParticipantSession | None = None):
        tts_client = self._select_tts_client(text)
        if not text.strip() or self.audio_source is None or tts_client is None:
            return

        await self._publish_event("agent", text)
        await self._publish_event("status", "Speaking...")
        if session is not None:
            session.agent_speaking = True
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                async with self.tts_lock:
                    async with tts_client.stream() as tts_stream:
                        tts_stream.push_text(text)
                        tts_stream.end_input()

                        async for synthesized in tts_stream:
                            if self.audio_source is None:
                                break
                            await self.audio_source.capture_frame(synthesized.frame)
                        
                        # Add small buffer to ensure complete playback
                        await asyncio.sleep(0.15)
                
                # Success - break retry loop
                break
                
            except Exception as e:
                error_msg = str(e).lower()
                print(f"[TTS ERROR] Attempt {attempt + 1}/{max_retries}: {e}")
                
                # Don't retry on certain errors
                if "api key" in error_msg or "authentication" in error_msg:
                    await self._publish_event("status", "TTS authentication failed.")
                    break
                
                # Retry on connection errors
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)
                    continue
                else:
                    # Final failure - publish text only
                    await self._publish_event("status", "TTS unavailable. Text shown.")
                    break
        
        if session is not None:
            session.agent_speaking = False
            session.speak_cooldown_until = asyncio.get_running_loop().time() + STT_SPEAK_COOLDOWN_SECONDS

        await self._publish_event("status", "Listening...")

    async def _flush_session_segments(self, session: ParticipantSession):
        if not session.pending_segments:
            return
        utterance = " ".join(session.pending_segments).strip()
        session.pending_segments.clear()
        session.last_interim = ""
        await self._publish_event("user_interim", "")
        if utterance and len(utterance) >= STT_MIN_TRANSCRIPT_CHARS and not self._is_filler_only(utterance):
            canonical = self._canonical_utterance(utterance)
            now = asyncio.get_running_loop().time()
            if (
                canonical
                and canonical == session.last_utterance_key
                and (now - session.last_utterance_at) < STT_DUPLICATE_WINDOW_SECONDS
            ):
                print(f"[STT] Dropping duplicate utterance: {utterance}")
                return
            session.last_utterance_key = canonical
            session.last_utterance_at = now
            await session.utterance_queue.put(utterance)

    def _schedule_flush(self, session: ParticipantSession, delay: float = STT_FLUSH_DELAY_SECONDS):
        if session.flush_task and not session.flush_task.done():
            session.flush_task.cancel()

        async def delayed_flush():
            try:
                await asyncio.sleep(delay)
                await self._flush_session_segments(session)
            except asyncio.CancelledError:
                return

        session.flush_task = asyncio.create_task(delayed_flush())
        self._track_task(session.flush_task)

    @staticmethod
    def _speech_text(event: lk_stt.SpeechEvent) -> str:
        alternatives = getattr(event, "alternatives", None) or []
        if not alternatives:
            return ""
        return (alternatives[0].text or "").strip()

    @staticmethod
    def _normalize_transcript_text(text: str) -> str:
        return " ".join(text.split()).strip()

    @staticmethod
    def _canonical_utterance(text: str) -> str:
        lowered = re.sub(r"[^a-z0-9\u0B80-\u0BFF\s-]", "", text.lower())
        return " ".join(lowered.split()).strip()

    @staticmethod
    def _is_low_confidence_noise(transcript: str, confidence: float | None) -> bool:
        if confidence is None:
            return False
        if confidence >= STT_LOW_CONFIDENCE_THRESHOLD:
            return False
        return len(transcript.split()) <= STT_LOW_CONFIDENCE_MAX_WORDS

    def _append_pending_segment(self, session: ParticipantSession, transcript: str) -> None:
        normalized = self._normalize_transcript_text(transcript)
        if len(normalized) < STT_MIN_TRANSCRIPT_CHARS:
            return

        if not session.pending_segments:
            session.pending_segments.append(normalized)
            return

        last = session.pending_segments[-1]
        if normalized == last or last.startswith(normalized):
            return
        if normalized.startswith(last):
            session.pending_segments[-1] = normalized
            return
        session.pending_segments.append(normalized)

    async def _handle_stt_message(self, session: ParticipantSession, event: lk_stt.SpeechEvent, stt_stream):
        if event.type == lk_stt.SpeechEventType.INTERIM_TRANSCRIPT:
            interim = self._postprocess_transcript_text(self._speech_text(event))
            if interim and interim != session.last_interim:
                session.last_interim = interim
                await self._publish_event("user_interim", interim)
            return

        if event.type == lk_stt.SpeechEventType.FINAL_TRANSCRIPT:
            transcript = self._postprocess_transcript_text(self._speech_text(event))
            if transcript:
                confidence = self._speech_confidence(event)
                if self._is_low_confidence_noise(transcript, confidence):
                    conf_text = f"{confidence:.2f}" if confidence is not None else "n/a"
                    print(f"[STT] Dropping low-confidence: '{transcript}' (conf={conf_text})")
                    return
                
                conf_str = f"{confidence:.2f}" if confidence is not None else "n/a"
                print(f"[STT] Final transcript: '{transcript}' (conf={conf_str})")
                self._maybe_update_stt_language_hint(session, stt_stream, transcript, self._speech_language(event))
                self._append_pending_segment(session, transcript)
                
                # Schedule flush with appropriate delay
                if session.pending_segments:
                    self._schedule_flush(session, STT_FLUSH_DELAY_SECONDS)
            return

        if event.type == lk_stt.SpeechEventType.END_OF_SPEECH:
            print(f"[STT] End of speech detected")
            if session.flush_task and not session.flush_task.done():
                session.flush_task.cancel()
            if STT_END_OF_SPEECH_SETTLE_SECONDS > 0:
                await asyncio.sleep(STT_END_OF_SPEECH_SETTLE_SECONDS)
            await self._flush_session_segments(session)

    async def _stt_reader(self, session: ParticipantSession, stt_stream):
        try:
            async for event in stt_stream:
                if not session.active:
                    break
                await self._handle_stt_message(session, event, stt_stream)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[STT ERROR] Reader failed: {e}")
        finally:
            session.done_event.set()

    async def _stream_track_to_stt(self, session: ParticipantSession, stt_stream):
        audio_stream = None
        try:
            audio_stream = rtc.AudioStream.from_participant(
                participant=session.participant,
                track_source=rtc.TrackSource.SOURCE_MICROPHONE,
                sample_rate=16000,
                num_channels=1,
            )
        except Exception as e:
            print(f"[WORKER] from_participant stream fallback: {e}")
            if session.audio_track is not None:
                audio_stream = rtc.AudioStream.from_track(
                    track=session.audio_track,
                    sample_rate=16000,
                    num_channels=1,
                )
            else:
                raise
        try:
            async for event in audio_stream:
                if not session.active:
                    break
                now = asyncio.get_running_loop().time()
                
                # Allow interruption - only skip during cooldown, not while speaking
                if now < session.speak_cooldown_until:
                    continue
                
                stt_stream.push_frame(event.frame)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[STT ERROR] Audio stream send failed: {e}")
        finally:
            try:
                stt_stream.end_input()
            except Exception:
                pass
            await audio_stream.aclose()
            session.done_event.set()

    async def _conversation_loop(self, session: ParticipantSession):
        await self._publish_event("status", "Listening...")
        try:
            while session.active:
                user_text = await session.utterance_queue.get()
                if user_text is None or not session.active:
                    break

                await self._publish_event("user", user_text)
                session.history.append({"role": "user", "content": user_text})
                session.history = session.history[-CONVERSATION_HISTORY_MAX_TURNS:]
                session.greeted = True

                await self._publish_event("status", "Thinking...")
                try:
                    reply = await asyncio.wait_for(generate_agent_reply(session.history, user_text), timeout=35)
                except asyncio.TimeoutError:
                    reply = "Sorry, that took too long. Please repeat your request."
                except litellm.AuthenticationError as e:
                    print(f"[LLM AUTH ERROR] {e}")
                    await self._publish_event(
                        "status",
                        "LLM authentication failed. Set a valid SARVAM_API_KEY and restart the worker.",
                    )
                    reply = (
                        "I cannot access the language model right now because the API key is invalid. "
                        "Please update the Sarvam API key and restart the worker."
                    )
                except ValueError as e:
                    config_error = str(e)
                    print(f"[LLM CONFIG ERROR] {config_error}")
                    await self._publish_event("status", f"LLM configuration error: {config_error}")
                    reply = (
                        f"I have a configuration issue: {config_error} "
                        "Please update the setting and restart the worker."
                    )
                except Exception as e:
                    print(f"[LLM ERROR] {e}")
                    reply = "Sorry, I ran into a problem while processing that. Please try again."

                reply = self._sanitize_agent_reply_text(reply)
                if not reply:
                    reply = "Could you please repeat that?"
                session.history.append({"role": "assistant", "content": reply})
                session.history = session.history[-CONVERSATION_HISTORY_MAX_TURNS:]
                await self._speak(reply, session)
        finally:
            session.done_event.set()

    async def _run_session(self, session: ParticipantSession):
        if self.stt_client is None:
            raise RuntimeError("Sarvam STT client is not initialized")
        try:
            stream_errors: list[str] = []
            for candidate in self._stt_stream_candidates(session):
                try:
                    session.stt_language_hint = candidate["language"]
                    stream_kwargs = {
                        "language": candidate["language"],
                        "model": candidate["model"],
                    }
                    if candidate["prompt"]:
                        stream_kwargs["prompt"] = candidate["prompt"]

                    print(
                        f"[STT] Opening stream model={candidate['model']} language={candidate['language']}"
                    )
                    async with self.stt_client.stream(**stream_kwargs) as stt_stream:
                        stt_reader_task = asyncio.create_task(self._stt_reader(session, stt_stream))
                        stream_task = asyncio.create_task(self._stream_track_to_stt(session, stt_stream))
                        convo_task = asyncio.create_task(self._conversation_loop(session))

                        self._track_task(stt_reader_task)
                        self._track_task(stream_task)
                        self._track_task(convo_task)

                        await session.done_event.wait()

                        for t in (stt_reader_task, stream_task, convo_task):
                            t.cancel()
                        await asyncio.gather(stt_reader_task, stream_task, convo_task, return_exceptions=True)
                        return
                except Exception as e:
                    stream_errors.append(f"{candidate['model']}/{candidate['language']}: {e}")
                    print(f"[STT ERROR] Stream candidate failed: {candidate['model']}/{candidate['language']} -> {e}")
                    if not session.active:
                        break

            if session.active:
                joined = " | ".join(stream_errors[-3:]) if stream_errors else "unknown error"
                print(f"[STT ERROR] Failed to open Sarvam STT stream: {joined}")
                await self._publish_event("status", "Speech recognition connection failed.")
                await self._speak("I'm having trouble with speech recognition right now. Please try again.")
        finally:
            session.active = False

    async def _attach_participant_session(
        self,
        participant: rtc.RemoteParticipant,
        track: rtc.RemoteAudioTrack | None = None,
    ):
        if self._is_worker_identity(participant.identity):
            return
        if self.session and self.session.active:
            if participant.identity == self.session.identity:
                return
            print(f"[WORKER] Session already active for {self.session.identity}, ignoring {participant.identity}")
            return

        session = ParticipantSession(identity=participant.identity, participant=participant, audio_track=track)
        self.session = session
        print(f"[WORKER] Starting session for participant: {participant.identity}")
        session.run_task = asyncio.create_task(self._run_session(session))
        self._track_task(session.run_task)

    def _is_audio_publication(self, publication: rtc.RemoteTrackPublication) -> bool:
        try:
            return publication.kind == rtc.TrackKind.KIND_AUDIO or int(publication.kind) == int(
                rtc.TrackKind.KIND_AUDIO
            )
        except Exception:
            return False

    async def _bootstrap_existing_audio_tracks(self):
        if self.room is None:
            return
        for participant in list(self.room.remote_participants.values()):
            if self._is_worker_identity(participant.identity):
                continue
            print(f"[WORKER] Found participant in room: {participant.identity}")
            for publication in list(participant.track_publications.values()):
                if not self._is_audio_publication(publication):
                    continue
                publication.set_subscribed(True)
                track = publication.track
                if isinstance(track, rtc.RemoteAudioTrack):
                    print(f"[WORKER] Bootstrapping existing audio track for {participant.identity}")
                    await self._attach_participant_session(participant, track)
                    break

    async def _stop_session(self):
        if not self.session:
            return
        session = self.session
        session.active = False
        if session.flush_task and not session.flush_task.done():
            session.flush_task.cancel()
        session.done_event.set()
        await session.utterance_queue.put(None)
        if session.run_task and not session.run_task.done():
            session.run_task.cancel()
            await asyncio.gather(session.run_task, return_exceptions=True)
        self.session = None

    async def run(self):
        model_name, api_base = validate_sarvam_config()
        configure_runtime(api_key=SARVAM_API_KEY, model_name=model_name, api_base=api_base)
        await self._ensure_sarvam_clients()
        print(f"[WORKER] Sarvam LLM configured with model={model_name} api_base={api_base}")
        print(
            f"[WORKER] Sarvam voice configured with STT={SARVAM_STT_MODEL}/{SARVAM_STT_LANGUAGE} "
            f"(adaptive_hint={STT_ADAPTIVE_LANGUAGE_HINT}) "
            f"TTS={SARVAM_TTS_MODEL} "
            f"EN={SARVAM_TTS_LANGUAGE_EN}/{SARVAM_TTS_SPEAKER_EN} "
            f"TA={SARVAM_TTS_LANGUAGE_TA}/{SARVAM_TTS_SPEAKER_TA}"
        )
        retry_delay = 2.0
        try:
            while True:
                self._reset_room_resources()
                if self.room is None or self.assistant_track is None:
                    raise RuntimeError("Failed to initialize LiveKit room resources")
                room = self.room
                disconnect_info: dict[str, object | None] = {"reason": None}
                stop_event = asyncio.Event()

                @room.on("participant_connected")
                def _on_participant_connected(participant):
                    if self._is_worker_identity(participant.identity):
                        return
                    print(f"[WORKER] Participant connected: {participant.identity}")

                @room.on("track_published")
                def _on_track_published(publication, participant):
                    if participant.identity == room.local_participant.identity:
                        return
                    if self._is_worker_identity(participant.identity):
                        return
                    if self._is_audio_publication(publication):
                        print(f"[WORKER] Audio track published by {participant.identity}; subscribing")
                        publication.set_subscribed(True)

                @room.on("track_subscribed")
                def _on_track_subscribed(track, publication, participant):
                    if participant.identity == room.local_participant.identity:
                        return
                    if self._is_worker_identity(participant.identity):
                        return
                    if not self._is_audio_publication(publication):
                        return
                    if not isinstance(track, rtc.RemoteAudioTrack):
                        return
                    print(f"[WORKER] Audio track subscribed for {participant.identity}")
                    self._track_task(asyncio.create_task(self._attach_participant_session(participant, track)))

                @room.on("participant_disconnected")
                def _on_participant_disconnected(participant):
                    if self._is_worker_identity(participant.identity):
                        return
                    print(f"[WORKER] Participant disconnected: {participant.identity}")
                    if self.session and participant.identity == self.session.identity:
                        self._track_task(asyncio.create_task(self._stop_session()))

                @room.on("disconnected")
                def _on_disconnected(reason):
                    disconnect_info["reason"] = reason
                    print(f"[WORKER] Room disconnected: {self._disconnect_reason_name(reason)} ({reason})")
                    stop_event.set()

                try:
                    worker_identity = f"hotel-agent-worker-{secrets.token_hex(4)}"
                    publish_options = rtc.TrackPublishOptions()
                    publish_options.source = rtc.TrackSource.SOURCE_MICROPHONE

                    token = create_worker_token(ROOM_NAME, worker_identity)
                    await room.connect(LIVEKIT_URL, token)
                    await room.local_participant.publish_track(self.assistant_track, publish_options)
                    print(
                        f"[WORKER] Connected to {ROOM_NAME} as {worker_identity} "
                        "and published assistant audio track"
                    )
                    await self._bootstrap_existing_audio_tracks()
                    retry_delay = 2.0
                    await stop_event.wait()
                finally:
                    await self._stop_session()
                    for task in list(self.tasks):
                        task.cancel()
                    if self.tasks:
                        await asyncio.gather(*self.tasks, return_exceptions=True)
                    if room.isconnected():
                        await room.disconnect()

                reason_name = self._disconnect_reason_name(disconnect_info["reason"])
                print(f"[WORKER] Reconnecting after disconnect reason={reason_name} in {retry_delay:.1f}s")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 10.0)
        finally:
            if self.stt_client is not None:
                await self.stt_client.aclose()
            for tts_client in self.tts_clients.values():
                await tts_client.aclose()
            self.tts_clients.clear()
            if self.http_session is not None and not self.http_session.closed:
                await self.http_session.close()


async def main():
    worker = LiveKitHotelWorker()
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
