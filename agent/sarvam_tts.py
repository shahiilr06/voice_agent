"""
Custom LiveKit TTS plugin for Sarvam AI Bulbul (v3).
Synthesizes natural, low-latency bilingual Tamil and English speech.
"""
from __future__ import annotations
import os
import io
import wave
import base64
import asyncio
import aiohttp
from typing import Optional

try:
    from livekit.agents import tts, utils
    from livekit.agents.utils import AudioBuffer
    HAS_LIVEKIT_AGENTS = True
    _BaseTTS = tts.TTS
    _BaseStream = tts.ChunkedStream
except ImportError:
    HAS_LIVEKIT_AGENTS = False
    class AudioBuffer:
        pass
    class _BaseTTS:
        def __init__(self, capabilities=None, sample_rate=24000, num_channels=1):
            self.capabilities = capabilities
            self.sample_rate = sample_rate
            self.num_channels = num_channels
    class _BaseStream:
        def __init__(self, *args, **kwargs):
            pass
    class tts:
        ChunkedStream = _BaseStream
        SynthesizeStream = _BaseStream
        class SynthesizedAudio:
            def __init__(self, request_id, frame):
                self.request_id = request_id
                self.frame = frame
        class TTSCapabilities:
            def __init__(self, streaming=False):
                self.streaming = streaming


class SarvamTTSCapabilities:
    def __init__(self, streaming: bool = False):
        self.streaming = streaming


from agent.lang_detector import detect_language


class SarvamTTS(_BaseTTS):
    """
    Sarvam AI Text-to-Speech plugin for LiveKit.
    Automatically detects Tamil vs English script and selects optimal voice parameters.
    """
    API_URL = "https://api.sarvam.ai/text-to-speech"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "bulbul:v3",
        speaker: str = "kavitha",
        sample_rate: int = 24000,
        pace: float = 1.0,
    ):
        caps = (
            tts.TTSCapabilities(streaming=False)
            if HAS_LIVEKIT_AGENTS
            else SarvamTTSCapabilities(streaming=False)
        )
        super().__init__(
            capabilities=caps,
            sample_rate=sample_rate,
            num_channels=1,
        )
        self.api_key = api_key or os.getenv("SARVAM_API_KEY")
        self._model = model or os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
        self._speaker = speaker or os.getenv("SARVAM_TTS_SPEAKER", "kavitha")
        self.pace = pace

        if not self.api_key:
            raise ValueError("Sarvam API key must be provided or set in SARVAM_API_KEY environment variable.")

    @property
    def model(self) -> str:
        return self._model

    @property
    def speaker(self) -> str:
        return self._speaker

    def synthesize(self, text: str, *, conn_options=None) -> "SarvamChunkedStream":
        if HAS_LIVEKIT_AGENTS:
            from livekit.agents import DEFAULT_API_CONNECT_OPTIONS
            opts = conn_options or DEFAULT_API_CONNECT_OPTIONS
            return SarvamChunkedStream(tts=self, input_text=text, conn_options=opts)
        return SarvamChunkedStream(tts=self, input_text=text)


class SarvamChunkedStream(tts.ChunkedStream):
    def __init__(self, *, tts: SarvamTTS, input_text: str, conn_options=None):
        if HAS_LIVEKIT_AGENTS:
            try:
                super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
            except RuntimeError as e:
                if "no running event loop" in str(e).lower():
                    self._tts = tts
                    self._input_text = input_text
                else:
                    raise
        self._tts_ref = tts
        self._input_text = input_text

    async def _run(self, output_emitter) -> None:
        if not self._input_text or not self._input_text.strip():
            return

        if not self._tts_ref.api_key or self._tts_ref.api_key.startswith("test_"):
            return

        # Auto-detect language code for natural synthesis (Tamil or English)
        detected_lang, _ = detect_language(self._input_text)
        has_tamil = any('\u0B80' <= c <= '\u0BFF' for c in self._input_text)
        target_lang = "ta-IN" if (has_tamil or detected_lang in ("ta-IN", "tanglish")) else "en-IN"

        payload = {
            "inputs": [self._input_text.strip()],
            "target_language_code": target_lang,
            "speaker": self._tts_ref._speaker,
            "model": self._tts_ref._model,
            "speech_sample_rate": self._tts_ref.sample_rate,
            "audio_codec": "wav",
            "pace": self._tts_ref.pace,
        }

        headers = {
            "api-subscription-key": self._tts_ref.api_key,
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self._tts_ref.API_URL, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    err_msg = await resp.text()
                    raise RuntimeError(f"Sarvam TTS failed ({resp.status}): {err_msg}")

                data = await resp.json()
                audios = data.get("audios", [])
                if not audios:
                    return

                # Decode Base64 audio into WAV buffer and extract raw PCM
                raw_bytes = base64.b64decode(audios[0])
                with wave.open(io.BytesIO(raw_bytes), "rb") as wf:
                    actual_rate = wf.getframerate()
                    actual_channels = wf.getnchannels()
                    pcm_data = wf.readframes(wf.getnframes())

                if HAS_LIVEKIT_AGENTS:
                    output_emitter.initialize(
                        request_id=utils.shortuuid(),
                        sample_rate=actual_rate,
                        num_channels=actual_channels,
                        mime_type="audio/pcm",
                        frame_size_ms=50,
                    )
                    # Stream in smooth 50ms frames to prevent packet drops and buffer overflows
                    chunk_bytes = int(actual_rate * actual_channels * 2 * 0.05)
                    for i in range(0, len(pcm_data), chunk_bytes):
                        output_emitter.push(pcm_data[i:i + chunk_bytes])
                        await asyncio.sleep(0.001)
                    output_emitter.flush()


# Alias for backward-compatibility with tests
SarvamSynthesizeStream = SarvamChunkedStream
