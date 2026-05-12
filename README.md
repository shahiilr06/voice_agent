# 🏨 Sunrise Hotel Voice Agent

A real-time, bilingual (Tamil/English) voice-based hotel booking assistant powered by LiveKit, Sarvam AI, and FastAPI.

![Voice Agent Demo](Screenshots/Screenshot%20from%202026-05-12%2016-13-03.png)

## ✨ Features

- 🎤 **Real-time Voice Interaction** - Natural conversation using WebRTC
- 🌐 **Bilingual Support** - Seamless Tamil and English conversation
- 🧠 **Intent-Based Architecture** - Deterministic slot extraction and state management
- 📝 **Smart Conversation Flow** - Structured booking process with context retention
- 🔄 **Interruption Handling** - Users can interrupt the agent naturally
- ✅ **Complete Booking Flow** - From inquiry to confirmation number

## 🏗️ Architecture

```
Speech (STT)
    ↓
Intent + Slot Extractor
    ↓
Conversation State Manager
    ↓
Natural Response Generator
    ↓
Text-to-Speech (TTS)
```

### Components

- **Frontend** (`voice_agent/index.html`) - Browser-based voice interface
- **API Server** (`voice_agent/server.py`) - FastAPI server for token management
- **Voice Worker** (`voice_agent/livekit_worker.py`) - Real-time audio processing pipeline
- **Intent Extractor** (`voice_agent/intent_extractor.py`) - Extracts user intent and booking slots
- **State Manager** (`voice_agent/state_manager.py`) - Manages conversation state
- **Orchestrator** (`voice_agent/sarvam_orchestrator.py`) - Generates natural responses
- **Hotel API** (`voice_agent/hotel_api.py`) - Room catalog and booking logic

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- LiveKit account ([livekit.io](https://livekit.io))
- Sarvam AI API key ([sarvam.ai](https://sarvam.ai))

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/shahiilr06/voice_agent.git
cd voice_agent
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables**

Create a `.env` file in the project root:

```env
LIVEKIT_URL=wss://your-livekit-url.livekit.cloud
LIVEKIT_API_KEY=your_api_key
LIVEKIT_API_SECRET=your_api_secret
SARVAM_API_KEY=your_sarvam_api_key

# Optional: STT/TTS tuning
STT_LOW_CONFIDENCE_THRESHOLD=0.2
STT_SPEAK_COOLDOWN_SECONDS=0.3
CONVERSATION_HISTORY_MAX_TURNS=60
```

### Running the Application

**Terminal 1 - Start API Server:**
```bash
python voice_agent/server.py
```

**Terminal 2 - Start Voice Worker:**
```bash
python voice_agent/livekit_worker.py
```

**Open in Browser:**
```
http://localhost:8000
```

## 🎯 Usage

1. Click **"Start Conversation"** and allow microphone access
2. Speak naturally in Tamil or English
3. Provide booking details:
   - Check-in date
   - Check-out date
   - Number of guests
   - Room type (Standard/Deluxe/Suite/Family)
   - Name and phone number
4. Receive booking confirmation

### Example Conversation

```
User: "வணக்கம், எனக்கு ஒரு அறை வேணும்"
Agent: "வணக்கம், Sunrise Hotel-க்கு வரவேற்கிறோம். உங்கள் check-in தேதி என்ன?"

User: "27 April"
Agent: "சரி, check-in April 27. உங்கள் check-out தேதி என்ன?"

User: "30 April"
Agent: "சரி, check-out April 30. எத்தனை பேர் தங்குவார்கள்?"

User: "நாலு பேர்"
Agent: "சரி, 4 பேர். எந்த room type வேண்டும்: Standard, Deluxe, Suite, அல்லது Family?"

User: "Standard"
Agent: "சரி! Standard அறை April 27 முதல் April 30 வரை 4 பேருக்கு கிடைக்கிறது. 
       ஒரு இரவுக்கு ரூபாய் 500. உங்கள் பெயர் மற்றும் தொலைபேசி எண்ணை சொல்லுங்கள்."

User: "My name is Shahil and my mobile number is 9943887733"
Agent: "Your booking is confirmed! Confirmation number: CNF-A1B2C3. Thank you!"
```

## 🛠️ Configuration

### Room Types & Pricing

| Room Type | Price (per night) | Description |
|-----------|-------------------|-------------|
| Standard  | ₹500             | Basic amenities |
| Deluxe    | ₹800             | Enhanced comfort |
| Suite     | ₹1200            | Premium experience |
| Family    | ₹950             | Spacious for families |

### STT/TTS Models

- **STT**: Sarvam Saarika v2.5 (Tamil/English)
- **TTS**: Sarvam Bulbul v2 (Tamil/English)

## 📁 Project Structure

```
voice_agent/
├── voice_agent/
│   ├── index.html              # Frontend UI
│   ├── server.py               # FastAPI server
│   ├── livekit_worker.py       # Voice processing pipeline
│   ├── intent_extractor.py     # Intent & slot extraction
│   ├── state_manager.py        # Conversation state management
│   ├── sarvam_orchestrator.py  # Response generation
│   ├── hotel_api.py            # Booking logic
│   └── static/                 # Static assets
├── requirements.txt
├── .env
└── README.md
```

## 🐛 Troubleshooting

### Microphone Permission Denied
- Use Chrome/Firefox/Edge
- Ensure HTTPS or localhost
- Check browser settings: `chrome://settings/content/microphone`

### Worker Crashes on Startup
- Verify `SARVAM_API_KEY` is valid (not placeholder)
- Check LiveKit credentials

### Poor STT Recognition
- Speak clearly and at moderate pace
- Reduce background noise
- Adjust `STT_LOW_CONFIDENCE_THRESHOLD` in `.env`

### TTS Connection Errors
- Check internet connection
- Verify Sarvam API key is active
- System retries automatically (2 attempts)

## 🔧 Advanced Configuration

### Environment Variables

```env
# Core settings
SARVAM_MODEL=sarvam/sarvam-m
SARVAM_STT_MODEL=saarika:v2.5
SARVAM_TTS_MODEL=bulbul:v2

# STT tuning
STT_FLUSH_DELAY_SECONDS=0.7
STT_END_OF_SPEECH_SETTLE_SECONDS=0.4
STT_DUPLICATE_WINDOW_SECONDS=3.0
STT_ADAPTIVE_LANGUAGE_HINT=true

# Conversation memory
CONVERSATION_HISTORY_MAX_TURNS=60
BOOKING_CONTEXT_HISTORY_WINDOW=60
LLM_MESSAGE_WINDOW=50
```

## 📝 License

MIT License - feel free to use for your projects!

## 🤝 Contributing

Contributions welcome! Please open an issue or submit a pull request.

## 👨‍💻 Author

**Shahil R**
- GitHub: [@shahiilr06](https://github.com/shahiilr06)

## 🙏 Acknowledgments

- [LiveKit](https://livekit.io) - Real-time communication infrastructure
- [Sarvam AI](https://sarvam.ai) - Indic language STT/TTS/LLM
- [FastAPI](https://fastapi.tiangolo.com) - Modern Python web framework

---

**Built with ❤️ for seamless hotel booking experiences**
