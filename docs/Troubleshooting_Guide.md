---
title: Troubleshooting & Error Resolution Guide
tags:
  - troubleshooting
  - debugging
  - error-resolution
  - telephony
  - audio
created: 2026-11-24
status: production-ready
---

# 🛠️ Troubleshooting & Error Resolution Guide
> Related: [[Index]] • [[Architecture]] • [[Voice_Pipeline]] • [[Telephony_Integration]]

This document serves as an exhaustive engineering reference detailing every real-world bug encountered during the development of **Maya**, along with root-cause analyses and exact solutions.

---

## 1. Summary of Resolved Issues

| # | Error / Symptom | Component | Root Cause | Solution |
| :--- | :--- | :--- | :--- | :--- |
| **1** | `NameError: name 'asyncio' is not defined` | `agent/sarvam_tts.py` | Missing `import asyncio` in TTS module. | Added `import asyncio` at the top of `sarvam_tts.py`. |
| **2** | Call drops immediately upon pressing key | Twilio SIP Bridge | Outdated `hotel:password123@...` URI caused LiveKit 401 auth rejection. | Cleared trunk auth in LiveKit Cloud and updated URI to `sip:hotel@vw9lj499216.sip.livekit.cloud`. |
| **3** | AI voice unclear / robotic / muffled over phone | `agent/sarvam_tts.py` | 24kHz audio suffered aliasing downsampling to 8kHz/16kHz telephone codecs; pace 1.15 was rushed. | Switched to native **16kHz HD Telephony** rate and calibrated **pace to 1.0**. |
| **4** | `ModuleNotFoundError: No module named 'agent'` | `agent/worker.py` | Invoking from `agent/` folder excluded project root from `sys.path`. | Added dynamic `PROJECT_ROOT` insertion into `sys.path[0]`. |
| **5** | Double overlapping AI voices | `agent/worker.py` | Subscribed to both `user_input_transcribed` and `user_speech_committed`. | Removed duplicate event and introduced an atomic turn lock (`is_processing_turn`). |
| **6** | Caller misses first half of greeting | `agent/worker.py` | Greeting was sent on room entry before SIP audio track handshake completed. | Delayed greeting until `track_subscribed` with a 0.8s stabilization pause. |
| **7** | Web mic volume meter stuck at 0% | `frontend/app.js` | Chrome auto-suspends Web Audio `AudioContext` until explicit user gesture. | Added `audioContext.resume()` hooks on user clicks and start call action. |
| **8** | Sarvam STT HTTP 400 on audio upload | `api/routers/voice.py` | Browser MediaRecorder sent WebM Opus format unsupported by raw STT. | Implemented PyAV (`av`) stream transcoder to 16kHz mono WAV. |

---

## 2. Deep Dives & Fix Details

---

### Incident 1: `NameError: name 'asyncio' is not defined`

#### Symptoms
The agent worker connects, accurately captures the user saying *"Hello"*, LangGraph drafts Maya's reply, but then crashes during audio synthesis:
```
File "C:\Users\shahiil\Desktop\AI_hotel\agent\sarvam_tts.py", line 171, in _run
    await asyncio.sleep(0.001)
NameError: name 'asyncio' is not defined
```

#### Root Cause
In [`agent/sarvam_tts.py`](file:///C:/Users/shahiil/Desktop/AI_hotel/agent/sarvam_tts.py), the `asyncio` module was referenced in `_run()` but omitted from the file header imports.

#### Fix
Added `import asyncio` to the module imports:
```python
from __future__ import annotations
import os
import io
import wave
import base64
import asyncio
import aiohttp
from typing import Optional
```

---

### Incident 2: Twilio Trial Account Auto-Hangup on Keypress

#### Symptoms
When an outbound call is answered, Twilio plays the trial message: *"You have a trial account. Press any key to execute the call."* When the user presses `1`, the call abruptly disconnects.

#### Root Cause
Twilio call logs revealed an immediate `failed` status for the SIP leg:
```
Call SID: CAfaa775046b187e2d75e141a7a36e816b
To: sip:hotel:password123@vw9lj499216.sip.livekit.cloud
Status: failed
```
LiveKit Cloud's Inbound Trunk rejected `hotel:password123` with a SIP 401/404 error because the trunk credentials didn't match.

#### Fix
1. Cleared the digest credentials on LiveKit Cloud Inbound Trunk `ST_FqcE6X4R76nP` using `update_inbound_trunk_fields(auth_username='', auth_password='')`.
2. Updated [`.env`](file:///C:/Users/shahiil/Desktop/AI_hotel/.env) and [`api/services/twilio_service.py`](file:///C:/Users/shahiil/Desktop/AI_hotel/api/services/twilio_service.py) to use the clean SIP URI:
   ```
   LIVEKIT_SIP_URI=sip:hotel@vw9lj499216.sip.livekit.cloud
   ```

---

### Incident 3: Unclear / Muffled Telephony Audio

#### Symptoms
The phone call stays connected, but Maya's voice sounds robotic, garbled, or rushed.

#### Root Cause
1. **Sample Rate Mismatch**: Telephony networks (PSTN) use **16kHz (Wideband HD Voice)** or **8kHz (Narrowband)**. Synthesizing at 24kHz forced LiveKit's WebRTC engine to downsample on the fly, producing aliasing distortion.
2. **Buffer Overflows**: Slicing multi-second PCM data in one huge block without frame pacing caused packet jitter over SIP.
3. **Pacing**: `pace: 1.15` was too fast for cellular phone speakers.

#### Fix
1. Updated `SarvamTTS` initialization in [`agent/worker.py`](file:///C:/Users/shahiil/Desktop/AI_hotel/agent/worker.py):
   ```python
   tts_plugin = SarvamTTS(sample_rate=16000, pace=1.0)
   ```
2. In `SarvamChunkedStream._run()`, sliced PCM data into **50ms frames** and called `output_emitter.flush()`.

---

### Incident 4: `ModuleNotFoundError: No module named 'agent'`

#### Symptoms
Running `python worker.py dev` from `C:\Users\shahiil\Desktop\AI_hotel\agent` failed with:
```
ModuleNotFoundError: No module named 'agent'
```

#### Root Cause
When executing from inside the subfolder, `sys.path[0]` defaults to `AI_hotel/agent`. Python could not find the top-level `agent` package.

#### Fix
Added automatic project-root discovery at the top of [`agent/worker.py`](file:///C:/Users/shahiil/Desktop/AI_hotel/agent/worker.py):
```python
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
```

---

### Incident 5: Dual Overlapping Voices (Chaotic Echo)

#### Symptoms
Maya seemed to speak two sentences at the same time over the phone line.

#### Root Cause
Both `@session.on("user_input_transcribed")` and `@session.on("user_speech_committed")` were active in `agent/worker.py`. A single guest utterance triggered two parallel asynchronous tasks executing `session.say()`.

#### Fix
1. Removed `@session.on("user_speech_committed")`.
2. Wrapped `handle_turn()` with an atomic boolean lock:
   ```python
   if is_processing_turn:
       return
   is_processing_turn = True
   try:
       ...
   finally:
       is_processing_turn = False
   ```
