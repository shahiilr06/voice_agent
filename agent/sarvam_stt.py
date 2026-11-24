"""
Custom LiveKit STT plugin for Sarvam AI Saaras v4 with VAD chunked REST recognition
and real-time streaming capability.
"""
from __future__ import annotations
import os
import io
import sys
import wave
import json
import base64
import asyncio
import aiohttp
import websockets
from typing import Optional, List

try:
    from livekit import rtc
    from livekit.agents import stt, utils
    from livekit.agents.utils import AudioBuffer
    HAS_LIVEKIT_AGENTS = True
    _BaseSTT = stt.STT
    _BaseStream = stt.SpeechStream
except ImportError:
    HAS_LIVEKIT_AGENTS = False
    rtc = None
    utils = None
    class AudioBuffer:
        pass
    class _BaseSTT:
        def __init__(self, capabilities=None):
            self.capabilities = capabilities
    class _BaseStream:
        def __init__(self, stt_instance, *args, **kwargs):
            self._stt = stt_instance
    class stt:
        SpeechStream = _BaseStream
        class SpeechEvent:
            def __init__(self, type=None, alternatives=None):
                self.type = type
                self.alternatives = alternatives or []
        class SpeechData:
            def __init__(self, text="", language="en-IN", confidence=1.0):
                self.text = text
                self.language = language
                self.confidence = confidence
        class SpeechEventType:
            FINAL_TRANSCRIPT = "final"
            INTERIM_TRANSCRIPT = "interim"
            END_OF_SPEECH = "end"
        class STTCapabilities:
            def __init__(self, streaming=False, interim_results=False):
                self.streaming = streaming
                self.interim_results = interim_results


class SarvamSTTCapabilities:
    def __init__(self, streaming: bool = False, interim_results: bool = False):
        self.streaming = streaming
        self.interim_results = interim_results


class SarvamSTT(_BaseSTT):
    """
    Sarvam AI Saaras v4 Speech-To-Text implementation for LiveKit.
    Integrates seamlessly with LiveKit VAD to capture and transcribe
    bilingual Indian English, Tamil, and Tanglish speech.
    """
    WS_URL = "wss://api.sarvam.ai/speech-to-text/ws"
    REST_URL = "https://api.sarvam.ai/speech-to-text"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "saaras:v4",
        language_code: str = "auto",
        sample_rate: int = 16000,
        streaming: bool = False,
    ):
        # streaming=False enables robust Silero VAD segmenting with Sarvam Saaras v4
        caps = (
            stt.STTCapabilities(streaming=streaming, interim_results=streaming)
            if HAS_LIVEKIT_AGENTS
            else SarvamSTTCapabilities(streaming=streaming, interim_results=streaming)
        )
        super().__init__(capabilities=caps)
        self.api_key = api_key or os.getenv("SARVAM_API_KEY")
        self._model = model or os.getenv("SARVAM_STT_MODEL", "saaras:v4")
        self.language_code = language_code
        self.sample_rate = sample_rate
        self.streaming = streaming

        if not self.api_key:
            raise ValueError("Sarvam API key must be provided or set in SARVAM_API_KEY environment variable.")

    @property
    def model(self) -> str:
        return self._model

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: Optional[str] = None,
        conn_options=None,
    ) -> stt.SpeechEvent:
        """
        Transcribe an audio buffer captured by LiveKit VAD using Sarvam Saaras v4 REST API.
        """
        if not buffer:
            return stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT, alternatives=[])

        # 1. Convert LiveKit AudioBuffer (list of AudioFrames or AudioFrame) to WAV
        pcm_data = b""
        sample_rate = self.sample_rate
        num_channels = 1

        try:
            if isinstance(buffer, list):
                if utils and hasattr(utils, "merge_frames") and len(buffer) > 0:
                    frame = utils.merge_frames(buffer)
                    pcm_data = bytes(frame.data)
                    sample_rate = frame.sample_rate
                    num_channels = frame.num_channels
                elif len(buffer) > 0:
                    sample_rate = getattr(buffer[0], "sample_rate", 16000)
                    num_channels = getattr(buffer[0], "num_channels", 1)
                    pcm_data = b"".join(bytes(getattr(f, "data", b"")) for f in buffer)
            elif hasattr(buffer, "data"):
                pcm_data = bytes(buffer.data)
                sample_rate = getattr(buffer, "sample_rate", 16000)
                num_channels = getattr(buffer, "num_channels", 1)
        except Exception as e:
            print(f"[Sarvam STT] Error parsing audio buffer: {e}", file=sys.stderr)
            return stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT, alternatives=[])

        if not pcm_data or len(pcm_data) < 320:
            # Too short (< 10ms of audio), skip
            return stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT, alternatives=[])

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(num_channels)
            wf.setsampwidth(2)  # 16-bit PCM
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_data)
        wav_io.seek(0)

        # 2. Build multipart form-data payload for Sarvam REST API
        lang = language or self.language_code
        data = aiohttp.FormData()
        data.add_field("file", wav_io, filename="audio.wav", content_type="audio/wav")
        data.add_field("model", self._model)
        data.add_field("mode", "transcribe")
        if lang and lang != "auto":
            data.add_field("language-code", lang)

        headers = {"api-subscription-key": self.api_key}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.REST_URL, data=data, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        res_json = await resp.json()
                        transcript = res_json.get("transcript", "").strip()
                        detected = res_json.get("language_code", "en-IN")
                        if transcript:
                            print(f"🎤 [Sarvam ASR] Captured speech: \"{transcript}\" ({detected})")
                            return stt.SpeechEvent(
                                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                                alternatives=[stt.SpeechData(text=transcript, language=detected, confidence=1.0)],
                            )
                        else:
                            return stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT, alternatives=[])
                    else:
                        err = await resp.text()
                        print(f"[Sarvam STT Error] HTTP {resp.status}: {err}", file=sys.stderr)
                        return stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT, alternatives=[])
        except Exception as e:
            print(f"[Sarvam STT] Request exception: {e}", file=sys.stderr)
            return stt.SpeechEvent(type=stt.SpeechEventType.FINAL_TRANSCRIPT, alternatives=[])

    def stream(self, *, language: Optional[str] = None, conn_options=None) -> "SarvamSTTStream":
        return SarvamSTTStream(self, language=language, conn_options=conn_options)


class SarvamSTTStream(stt.SpeechStream):
    """
    WebSocket streaming pipeline communicating with Sarvam's realtime STT socket.
    """
    def __init__(self, stt_instance: SarvamSTT, language: Optional[str] = None, conn_options=None):
        if HAS_LIVEKIT_AGENTS:
            try:
                from livekit.agents import DEFAULT_API_CONNECT_OPTIONS
                opts = conn_options or DEFAULT_API_CONNECT_OPTIONS
                super().__init__(stt=stt_instance, conn_options=opts)
            except RuntimeError as e:
                if "no running event loop" in str(e).lower():
                    self._stt = stt_instance
                    self._conn_options = conn_options
                else:
                    raise
        else:
            super().__init__(stt_instance)
        self._stt = stt_instance
        self._language = language or stt_instance.language_code

    async def _run(self) -> None:
        if not self._stt.api_key or self._stt.api_key.startswith("test_"):
            return

        lang_param = "unknown" if self._language in ("auto", None) else self._language
        url = (
            f"{self._stt.WS_URL}?"
            f"model={self._stt._model}&"
            f"language-code={lang_param}&"
            f"sample_rate={self._stt.sample_rate}"
        )
        headers = {"Api-Subscription-Key": self._stt.api_key}

        try:
            async with websockets.connect(url, additional_headers=headers) as ws:
                async def sender():
                    async for frame in self._input_ch:
                        if hasattr(frame, "data"):
                            pcm_b64 = base64.b64encode(bytes(frame.data)).decode("utf-8")
                            payload = {
                                "audio": {
                                    "data": pcm_b64,
                                    "sample_rate": str(getattr(frame, "sample_rate", self._stt.sample_rate)),
                                    "encoding": "audio/wav",
                                }
                            }
                            await ws.send(json.dumps(payload))

                async def receiver():
                    async for raw_msg in ws:
                        try:
                            msg = json.loads(raw_msg)
                            data_obj = msg.get("data", {}) if isinstance(msg.get("data"), dict) else {}
                            text = (
                                msg.get("transcript")
                                or data_obj.get("transcript")
                                or msg.get("text", "")
                            )
                            lang = (
                                msg.get("language_code")
                                or data_obj.get("language_code")
                                or "en-IN"
                            )
                            is_final = msg.get("is_final", False) or (msg.get("type") in ("final", "data"))

                            if text and text.strip():
                                print(f"🎤 [Sarvam ASR Stream]: \"{text.strip()}\" ({lang})")
                                evt_type = (
                                    stt.SpeechEventType.FINAL_TRANSCRIPT
                                    if is_final
                                    else stt.SpeechEventType.INTERIM_TRANSCRIPT
                                )
                                self._event_ch.send_nowait(
                                    stt.SpeechEvent(
                                        type=evt_type,
                                        alternatives=[stt.SpeechData(text=text.strip(), language=lang, confidence=1.0)],
                                    )
                                )
                        except Exception:
                            continue

                await asyncio.gather(sender(), receiver())
        except Exception as e:
            print(f"[Sarvam STT Stream] Connection ended: {e}", file=sys.stderr)
