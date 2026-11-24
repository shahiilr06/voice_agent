# 🏨 Sunrise International Hotel — Autonomous AI Voice Receptionist

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue.svg?logo=python&logoColor=white" alt="Python 3.11" />
  <img src="https://img.shields.io/badge/FastAPI-2.0.0-009688.svg?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/LiveKit-Cloud_SIP-FF5722.svg?logo=webrtc&logoColor=white" alt="LiveKit Cloud SIP" />
  <img src="https://img.shields.io/badge/Twilio-PSTN_Voice-F22F46.svg?logo=twilio&logoColor=white" alt="Twilio" />
  <img src="https://img.shields.io/badge/Sarvam_AI-Saaras_v4_%2B_Bulbul_v3-7C3AED.svg" alt="Sarvam AI" />
  <img src="https://img.shields.io/badge/LangGraph-StateGraph-1E293B.svg" alt="LangGraph" />
  <img src="https://img.shields.io/badge/Tests-23%20Passed-brightgreen.svg" alt="Tests" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License" />
</p>

An enterprise-grade, real-time conversational AI voice concierge designed for **Sunrise International Hotel**. **Maya** autonomously manages room reservations, verifies live database inventory, calculates stay pricing, and issues confirmed bookings over **standard cellular telephone lines (Twilio + LiveKit SIP)** and **browser WebRTC** with native fluency in **English, Tamil (தமிழ்), and Tanglish**.

---

## 🌟 Key Highlights

- 📞 **Direct Cellular Telephony (PSTN)**: Integrated with Twilio line **`+1 515 758 7590`** bridged via SIP to **LiveKit Cloud**. Guests can call from or receive calls on any landline or mobile phone (**`+91 9994388773`**).
- 🌐 **True Multilingual & Tanglish Understanding**: Greets guests and asks for language preference. Effortlessly understands colloquial mixed Tanglish (*"Enakku deluxe room venum, 4 family members varom"*), pure Tamil script (*"நாளைக்கு ரூம் கிடைக்குமா?"*), and professional English.
- 🎙️ **16kHz HD Telephony Audio Pipeline**: Natively synthesized via **Sarvam Bulbul v3** at 16,000 Hz with 50ms frame pacing and buffer flushing to eliminate downsampling distortion and packet jitter over phone lines.
- 🧠 **Deterministic LangGraph Brain**: 5-node cyclic state graph managing entity extraction (`room_type`, `check_in`, `check_out`, `num_guests`, `guest_name`, `guest_phone`), room capacity validation, payment inquiries, and reservation confirmation guards.
- 💻 **Real-Time WebRTC Dashboard**: Browser interface with live dynamic speech volume meters, OS-level audio device prediction (Bluetooth, Headset, Mic), and real-time conversation transcripts.
- 📚 **Obsidian Documentation Vault**: Complete technical documentation suite located in [`docs/`](docs/Index.md) with interactive Mermaid diagrams and troubleshooting deep-dives.

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph Telecom["1. Cellular Telecom (PSTN)"]
        Phone["Guest Mobile Phone\n(+91 9994388773)"]
        Twilio["Twilio Telephony\n(+1 515 758 7590)"]
    end

    subgraph Web["2. Web Client"]
        Browser["Browser WebRTC Dashboard\n(http://localhost:8004)"]
    end

    subgraph Media["3. LiveKit Cloud Infrastructure"]
        SIPTrunk["Inbound SIP Trunk (ST_FqcE6X4R76nP)"]
        Dispatch["Dispatch Rule (hotel-individual-rule)"]
        SFU["LiveKit Cloud SFU (ai-hotel-5hl7n2nq)"]
        Room["LiveKit Room (hotel-call-{caller})"]
    end

    subgraph VoiceCore["4. Maya AI Agent Core"]
        Worker["LiveKit Agent Worker (worker.py)"]
        VAD["Silero VAD (Speech Endpointing)"]
        STT["Sarvam Saaras v4 STT (Language: Auto)"]
        TTS["Sarvam Bulbul v3 TTS (16kHz Native HD Voice)"]
    end

    subgraph Intelligence["5. State Machine & Inventory"]
        LangGraph["LangGraph Multi-Turn StateGraph"]
        DB[("Database (SQLite / PostgreSQL)")]
    end

    Phone <-->|Cellular Voice Call| Twilio
    Twilio <-->|TwiML / Webhook| Browser
    Twilio <-->|SIP Audio (G.711 / Opus)| SIPTrunk
    SIPTrunk --> Dispatch --> SFU
    Browser <-->|WebRTC Media Stream| SFU
    SFU <--> Room <--> Worker

    Worker --> VAD --> STT
    STT -->|Transcribed Text| LangGraph
    LangGraph <-->|Query Inventory & Commit| DB
    LangGraph -->|Natural Receptionist Reply| TTS
    TTS -->|16kHz Audio Stream| Worker
```

---

## 💬 Real-World Dialogue Trace

```text
Maya (Receptionist)
"Welcome to Sunrise International Hotel! I am Maya, your virtual receptionist. Which language would you prefer — English, Tamil, or Tanglish? வணக்கம், நீங்கள் எந்த மொழியில் பேச விரும்புகிறீர்கள்?"

Guest (+91 9994388773)
"Tanglish-la pesalam. 4 family members varom, suite room available-aa?"

Maya (Receptionist)
"Sure! Engalukku Executive Luxury Suite available-aa irukku. Check-in date eppo nu solla mudiyuma?"

Guest
"Checking date is 25 December 2025, morning checkout on 26th."

Maya (Receptionist)
"Got it! One-night stay from 25th to 26th December total ₹9,500 aagum. Payment hotel arrival-la front desk-laye pannikalam. Reservation confirm panna unga name solluveengala?"

Guest
"Name Shakil, booking confirm pannidunga."

Maya (Receptionist)
"Thank you Mr. Shakil! Unga reservation confirm aaiduchu. Unga confirmation code BK-7E29A1. Looking forward to welcoming you to Sunrise International Hotel!"
```

---

## 🛠️ Technology Stack

| Layer | Technologies | Purpose |
| :--- | :--- | :--- |
| **Telephony** | Twilio Voice, TwiML, E.164 Normalization | Inbound & Outbound cellular phone calling |
| **SIP & WebRTC** | LiveKit Cloud, LiveKit Agents SDK, Silero VAD | Real-time audio streaming, SIP trunking, & barge-in |
| **Speech-to-Text** | Sarvam AI Saaras v4 (`saaras:v4`) | Acoustic model for Indian English, Tamil, & Tanglish |
| **Text-to-Speech** | Sarvam AI Bulbul v3 (`bulbul:v3`) | Natural speech synthesis (`kavitha`) at 16kHz HD rate |
| **State Machine** | LangGraph, LangChain Core | Cyclic multi-turn dialogue orchestration & entity parsing |
| **Backend API** | FastAPI, Uvicorn, Pydantic v2 | REST endpoints, webhook handlers, & static dashboard |
| **Persistence** | SQLAlchemy 2.0, SQLite (PostgreSQL + pgvector ready) | Atomic room inventory, reservations, & vector search |
| **Testing** | Pytest, Pytest-Asyncio, TestClient | Unit and integration test suite |

---

## 📁 Repository Structure

```
AI_hotel/
├── agent/                          # LiveKit Agent Worker & Voice Plugins
│   ├── lang_detector.py            # Multilingual Classifier (English, Tamil, Tanglish)
│   ├── sarvam_stt.py               # Sarvam Saaras v4 STT Plugin
│   ├── sarvam_tts.py               # Sarvam Bulbul v3 TTS Plugin (16kHz Audio Pacing)
│   └── worker.py                   # LiveKit Worker Entrypoint & SIP Adapter
├── api/                            # FastAPI Application
│   ├── database.py                 # Cross-Dialect Session Manager
│   ├── main.py                     # App Lifecycle, CORS, & Router Mounting
│   ├── models/                     # SQLAlchemy Models (Room, Booking, FAQ)
│   ├── routers/                    # REST Routes (/twilio, /voice, /rooms, /sip)
│   ├── schemas/                    # Pydantic Schemas & E.164 Validators
│   └── services/                   # Twilio, LiveKit SIP, Room, & Booking Services
├── docs/                           # Obsidian Documentation Vault
│   ├── Index.md                    # Main Map of Content (MOC)
│   ├── Architecture.md             # End-to-End System Design
│   ├── Voice_Pipeline.md           # STT, TTS, & 16kHz Audio Engineering
│   ├── Dialogue_State_Machine.md   # LangGraph Dialogue Topology & Rules
│   ├── Telephony_Integration.md    # Twilio & LiveKit SIP Routing Guide
│   ├── Troubleshooting_Guide.md    # Master Error Resolution Knowledge Base
│   └── Operations_And_Execution.md # Step-by-Step Runbooks & Testing Guide
├── frontend/                       # Interactive Receptionist Web Dashboard
│   ├── app.js                      # Client Voice Pipeline & Dynamic Volume Meter
│   └── index.html                  # Responsive Tailwind UI with Twilio Calling
├── graph/                          # LangGraph Conversational Brain
│   ├── edges.py                    # Conditional Routing & Safety Guards
│   ├── graph.py                    # StateGraph Compilation
│   ├── nodes.py                    # Language, Extraction, Availability, & Agent Nodes
│   ├── prompts.py                  # Bilingual Receptionist Prompts
│   └── state.py                    # BookingState Schema
├── scripts/                        # Operational Scripts
│   ├── call_guest.py               # Direct Outbound CLI Dialer
│   └── setup_livekit_sip.py        # LiveKit Cloud SIP Provisioning Script
├── seeds/                          # Database Seed Data (Room Catalog & Pricing)
│   └── seed_data.py
├── tests/                          # Automated Pytest Suite
│   ├── conftest.py                 # Test Database Fixtures
│   ├── test_api.py                 # REST Endpoint Tests
│   ├── test_graph.py               # Dialogue State Machine Tests
│   ├── test_sarvam.py              # STT / TTS Plugin Tests
│   ├── test_sip.py                 # LiveKit SIP Service Tests
│   └── test_twilio.py              # Twilio Webhook, TwiML, & Call Dispatch Tests
├── .env.example                    # Sanitized Environment Variables Template
├── .gitignore                      # Git Ignore (Excludes credentials, DB, caches)
├── pytest.ini                      # Test Configuration
└── requirements.txt                # Python Dependencies
```

---

## ⚡ Quick Start Guide

### 1. Clone & Install Dependencies
```powershell
git clone https://github.com/your-username/AI_hotel.git
cd AI_hotel

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install requirements
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and populate your credentials:
```powershell
copy .env.example .env
```
Fill in your API keys in `.env`:
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- `SARVAM_API_KEY`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`

### 3. Start the AI Receptionist Worker
In Terminal 1:
```powershell
python agent/worker.py dev
```

### 4. Start the FastAPI Server & Web Dashboard
In Terminal 2:
```powershell
python -m uvicorn api.main:app --port 8004 --reload
```
Open [http://localhost:8004](http://localhost:8004) to access the interactive web console.

### 5. Place a Direct Phone Call
In Terminal 3:
```powershell
# Dials the target phone number configured in .env
python scripts/call_guest.py

# Or dial a specific phone number
python scripts/call_guest.py +91XXXXXXXXXX
```
When your phone rings, answer and speak with Maya!

---

## 🧪 Verification & Automated Testing

The project includes unit and integration tests covering telephony, dialogue routing, and audio synthesis:

```powershell
# Run the complete test suite
python -m pytest -v

# Run targeted telephony & voice tests
python -m pytest tests/test_twilio.py tests/test_sip.py tests/test_sarvam.py -v
```

```text
============================= test session starts =============================
collected 23 items

tests/test_twilio.py .........                                           [ 39%]
tests/test_sip.py ......                                                 [ 65%]
tests/test_graph.py ....                                                 [ 82%]
tests/test_services.py ....                                              [100%]

============================= 23 passed in 3.21s ==============================
```

---

## 📖 In-Depth Documentation

For detailed architectural breakdowns, telephony protocols, and debugging notes, explore the Obsidian documentation vault in [`docs/`](docs/Index.md):
- **[[docs/Architecture.md|System Architecture]]**: Media bridges, WebRTC SFU, and call lifecycles.
- **[[docs/Voice_Pipeline.md|Voice Pipeline]]**: 16kHz audio calibration and bilingual routing.
- **[[docs/Dialogue_State_Machine.md|Dialogue State Machine]]**: LangGraph entity parsing and confirmation logic.
- **[[docs/Telephony_Integration.md|Telephony Integration]]**: Twilio PSTN and LiveKit SIP routing.
- **[[docs/Troubleshooting_Guide.md|Troubleshooting Guide]]**: Detailed post-mortem analyses of all resolved bugs.
- **[[docs/Operations_And_Execution.md|Operations Guide]]**: Step-by-step deployment and operational runbooks.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
