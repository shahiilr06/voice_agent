# Sunrise Hotel Voice Agent - Project Documentation

## 1. Project overview

This project is a **voice-based hotel assistant** built with:

- **LiveKit** for real-time audio transport (WebRTC room)
- **Sarvam STT/TTS** for speech recognition and speech synthesis
- **Sarvam LLM via LiteLLM** for conversation and booking assistance
- **FastAPI** for token/API serving and web UI hosting

The assistant supports bilingual interaction (Tamil/English), real-time transcript updates, and hotel booking conversation flow.

---

## 2. Current architecture

### Runtime components

1. **Frontend UI** (`voice_agent/index.html`)
   - Browser mic capture
   - LiveKit room join
   - Transcript and status rendering
   - Agent audio playback

2. **API server** (`voice_agent/server.py`)
   - Serves UI and static assets
   - Issues LiveKit JWT tokens

3. **Voice worker** (`voice_agent/livekit_worker.py`)
   - Connects to LiveKit room as worker participant
   - Subscribes guest audio tracks
   - Streams audio to Sarvam STT
   - Calls orchestrator for LLM reply generation
   - Streams Sarvam TTS audio back to room

4. **LLM orchestrator** (`voice_agent/sarvam_orchestrator.py`)
   - Builds LLM messages/history
   - Handles tool-calling mode when enabled
   - Handles no-tool LLM mode with memory prompt injection and guardrails

5. **Hotel tool layer** (`voice_agent/hotel_api.py`)
   - Room catalog and deterministic pricing
   - check/book/cancel booking functions

---

## 3. Processing pipeline (end-to-end)

1. User clicks **Start Conversation** in browser.
2. Frontend validates mic access (`getUserMedia`) and secure context.
3. Frontend calls `POST /livekit/token`.
4. Frontend joins LiveKit room and publishes microphone audio.
5. Worker subscribes to guest audio track.
6. Worker opens Sarvam STT stream (`saarika:v2.5` default, with fallbacks).
7. STT events are processed:
   - interim transcript publishing
   - final transcript post-processing
   - low-confidence/noise filtering
   - duplicate utterance suppression
8. Final user utterance is sent to LLM orchestrator.
9. Orchestrator generates reply (LLM-first flow).
10. Worker sanitizes reply (removes `<think>` leakage), publishes transcript event.
11. Worker streams reply via Sarvam TTS back to LiveKit.
12. Browser plays agent audio and updates transcript/status.

---

## 4. API endpoints

### HTTP endpoints (FastAPI)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Serves web client (`index.html`) |
| `POST` | `/livekit/token` | Returns room token + websocket URL |
| `GET` | `/healthz` | Health check (`{"status":"ok","transport":"livekit-only"}`) |

### Internal tool functions (LLM callable when tools are enabled)

- `check_room(start_date, end_date, guests, room_type)`
- `book_room(name, phone, start_date, end_date, guests, room_type)`
- `cancel_booking(confirmation_number)`

---

## 5. Configuration

Set these in `.env` (project root):

### Required

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `SARVAM_API_KEY`

### Core model settings

- `SARVAM_MODEL` (default: `sarvam/sarvam-m`)
- `SARVAM_ENABLE_TOOL_CALLING` (`true|false|auto`)
- `SARVAM_STT_MODEL` (default: `saarika:v2.5`)
- `SARVAM_STT_LANGUAGE` (`unknown` recommended for auto-detect)
- `SARVAM_TTS_MODEL` (default: `bulbul:v2`)

### STT/Turn tuning

- `STT_FLUSH_DELAY_SECONDS`
- `STT_SPEAK_COOLDOWN_SECONDS`
- `STT_END_OF_SPEECH_SETTLE_SECONDS`
- `STT_DUPLICATE_WINDOW_SECONDS`
- `STT_LOW_CONFIDENCE_THRESHOLD`
- `STT_LOW_CONFIDENCE_MAX_WORDS`

### Conversation memory tuning

- `CONVERSATION_HISTORY_MAX_TURNS`
- `BOOKING_CONTEXT_HISTORY_WINDOW`
- `LLM_MESSAGE_WINDOW`

---

## 6. How to run

From project root:

```bash
pip install -r requirements.txt
```

Terminal 1:

```bash
python voice_agent/server.py
```

Terminal 2:

```bash
python voice_agent/livekit_worker.py
```

Open:

```text
http://localhost:8000
```

---

## 7. Conversation mode (current)

- Primary mode is **LLM-only conversation** in no-tool mode (as requested).
- Deterministic rule-based flow is **not** used as primary response engine.
- Guardrails still enforce safety and fallback prompting when needed:
  - strips `<think>`/reasoning tags
  - avoids fake booking confirmations
  - asks next missing booking detail when reply is unsafe/empty

---

## 8. Errors faced and fixes applied

| Problem observed | Root cause | Fix applied |
|---|---|---|
| `Invalid placeholder API key detected` | `.env` still had placeholder key | Require real `SARVAM_API_KEY`; startup validation retained |
| Browser error: `Cannot read properties of undefined (reading 'getUserMedia')` | Missing/unsupported mic API path or insecure origin | Added mic preflight, secure-context check, legacy fallback, clearer UX errors |
| STT startup crash (syntax issue in worker) | Misplaced `finally` block in `_run_session` | Corrected `try/finally` structure |
| Repeated/echo-like transcript loops | Rapid duplicate finals and self-capture timing | Added duplicate suppression + speak cooldown gating |
| Poor multilingual parsing (Tamil mixed inputs) | Limited slot/date/guest extraction patterns | Added Tamil/English/Malayalam parsing improvements and month/day normalization |
| Memory resets in long calls | Short history windows | Increased history windows and injected LLM memory context |
| Agent showing `<think> ...` in replies | Model output leakage | Added output sanitization in orchestrator + worker |

---

## 9. Troubleshooting checklist

1. **Worker exits on startup**
   - Check `SARVAM_API_KEY` is real (not placeholder).

2. **Mic not working**
   - Use Chrome/Edge/Firefox.
   - Use `localhost` or HTTPS.
   - Grant microphone permission.

3. **Cannot connect to room**
   - Verify `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`.
   - Confirm `/livekit/token` returns `token` and `ws_url`.

4. **No STT events**
   - Check worker logs for `[STT] Opening stream...` and `[STT ERROR]`.
   - Validate STT model/language config.

5. **Conversation quality issues**
   - Increase memory window env values.
   - Keep `SARVAM_ENABLE_TOOL_CALLING=false` for pure LLM conversational mode (current setting).

---

## 10. Important files

- `voice_agent/server.py` - API server and token issuance
- `voice_agent/index.html` - browser client (mic, LiveKit, transcript UI)
- `voice_agent/livekit_worker.py` - realtime worker pipeline
- `voice_agent/sarvam_orchestrator.py` - LLM orchestration and reply guards
- `voice_agent/hotel_api.py` - room catalog + booking helpers
- `requirements.txt` - runtime dependencies

