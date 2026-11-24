---
title: Operations & Execution Guide
tags:
  - operations
  - runbook
  - cli
  - deployment
  - testing
created: 2026-11-24
status: production-ready
---

# 🚀 Operations & Execution Guide
> Related: [[Index]] • [[Architecture]] • [[Telephony_Integration]] • [[Troubleshooting_Guide]]

This document provides step-by-step instructions for running, operating, testing, and managing the **Sunrise International Hotel AI Voice System**.

---

## 1. Environment Configuration (`.env`)

Ensure the following variables are defined in your [`.env`](file:///C:/Users/shahiil/Desktop/AI_hotel/.env) file:

```env
# ==============================================================================
# LiveKit Cloud
# ==============================================================================
LIVEKIT_URL=wss://your_project.livekit.cloud
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
LIVEKIT_SIP_URI=sip:hotel@your_project.sip.livekit.cloud

# ==============================================================================
# Sarvam AI
# ==============================================================================
SARVAM_API_KEY=your_sarvam_api_key
SARVAM_STT_MODEL=saaras:v4
SARVAM_TTS_MODEL=bulbul:v3
SARVAM_TTS_SPEAKER=kavitha
LLM_MODEL=sarvam-105b-conversations

# ==============================================================================
# Twilio Telephony
# ==============================================================================
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+15157587590
TWILIO_TARGET_PHONE=+919994388773

# ==============================================================================
# Application Server & Database
# ==============================================================================
API_HOST=0.0.0.0
API_PORT=8004
DATABASE_URL=sqlite:///./hotel_booking.db
HOTEL_NAME=Sunrise International Hotel
```

---

## 2. Daily Operations & Runbook

### Step 1: Start the Voice Agent Worker
The agent worker connects Maya to LiveKit Cloud, waiting to enter rooms when phone calls or web users connect:

```powershell
# From the project root:
python agent/worker.py dev

# Or from inside the agent folder:
cd agent
python worker.py dev
```

---

### Step 2: Launch the FastAPI Backend & Web Dashboard
Starts the REST API and the browser-based receptionist console on port **8004**:

```powershell
python -m uvicorn api.main:app --port 8004 --reload
```
- Open [http://localhost:8004](http://localhost:8004) in Chrome or Edge.

---

### Step 3: Placing Telephone Calls

#### Option A: Quick CLI Call
To immediately trigger a call to the verified mobile number (**`+91 9994388773`**):

```powershell
python scripts/call_guest.py
```

To call any other verified phone number:
```powershell
python scripts/call_guest.py +91XXXXXXXXXX
```

#### Option B: Web UI One-Click Call
1. Navigate to [http://localhost:8004](http://localhost:8004).
2. Click the purple **"Call My Phone"** button.

---

## 3. Configuring Inbound Calls (Twilio Console)

To receive incoming phone calls when guests dial **`+1 515 758 7590`**:

1. Start your local server (`uvicorn api.main:app --port 8004`).
2. Expose port 8004 to the internet using a secure tunnel:
   ```powershell
   ngrok http 8004
   ```
3. Copy your HTTPS forwarding URL (e.g. `https://abc-123.ngrok-free.app`).
4. In your [Twilio Console](https://console.twilio.com/us1/develop/phone-numbers/manage/incoming), select **`+1 515 758 7590`**:
   - Under **Voice Configuration** -> **A call comes in**:
     - Select: **Webhook**
     - URL: `https://abc-123.ngrok-free.app/twilio/voice`
     - HTTP Method: `POST`
   - Click **Save configuration**.
5. Dial `+1 515 758 7590` from any mobile phone — Maya will answer directly.

---

## 4. Automated Testing & Verification

Run the complete test suite across telephony, state machine, voice synthesis, and database operations:

```powershell
# Run all tests
python -m pytest -v

# Run targeted telephony & voice tests
python -m pytest tests/test_twilio.py tests/test_sip.py tests/test_sarvam.py -v
```

---

## 5. API Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/twilio/call` | Triggers an outbound cellular phone call via Twilio. |
| `GET` | `/twilio/status` | Returns Twilio configuration status and phone numbers. |
| `POST` | `/twilio/voice` | Inbound call webhook from Twilio returning TwiML `<Dial><Sip>`. |
| `POST` | `/twilio/outbound_twiml` | Returns TwiML bridging answered outbound calls to LiveKit. |
| `POST` | `/voice/chat` | Direct browser voice/text endpoint (STT -> LangGraph -> TTS). |
| `GET` | `/voice/greeting` | Returns initial multilingual greeting text and synthesized audio. |
| `GET` | `/rooms` | Retrieves available room categories and pricing. |
| `GET` | `/bookings` | Lists active and confirmed reservations. |
| `GET` | `/health` | Service health check. |
