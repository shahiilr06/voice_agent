---
title: Twilio & LiveKit SIP Telephony Integration
tags:
  - telephony
  - twilio
  - livekit-sip
  - pstn
  - voip
created: 2026-11-24
status: production-ready
---

# 📞 Twilio & LiveKit SIP Telephony Integration
> Related: [[Index]] • [[Architecture]] • [[Troubleshooting_Guide]] • [[Operations_And_Execution]]

This document details the configuration, network routing, and telephony protocols connecting cellular phone lines with LiveKit Cloud and Maya.

---

## 1. Telephony Topology

```mermaid
flowchart LR
    subgraph PSTN["Cellular Telecom Network"]
        Phone["Guest Mobile\n(+91 9994388773)"]
    end

    subgraph TwilioCloud["Twilio Telephony Platform"]
        TwilioNum["Twilio Line\n(+1 515 758 7590)"]
        VoiceEngine["Twilio Voice Engine\n(TwiML Interpreter)"]
    end

    subgraph LiveKitSIP["LiveKit Cloud SIP Ingress"]
        SIPURI["SIP Trunk\n(sip:hotel@vw9lj499216.sip.livekit.cloud)"]
        InboundTrunk["Inbound Trunk\n(ST_FqcE6X4R76nP)"]
        DispatchRule["Dispatch Rule\n(SDR_jgQdHoSebpLv)"]
    end

    subgraph LiveKitRoom["LiveKit Media Room"]
        Room["hotel-call-+919994388773\n(Audio Tracks)"]
        Maya["Maya Agent Worker"]
    end

    Phone <-->|Cellular Voice Call| TwilioNum
    TwilioNum --> VoiceEngine
    VoiceEngine -->|SIP INVITE\n(TwiML Dial)| SIPURI
    SIPURI --> InboundTrunk --> DispatchRule --> Room
    Room <--> Maya
```

---

## 2. Infrastructure Configuration

### LiveKit Cloud SIP Settings
| Setting | Value | Description |
| :--- | :--- | :--- |
| **Project Name** | `AI_hotel` | Project name on LiveKit Cloud |
| **Project ID** | `p_vw9lj499216` | Unique project identifier |
| **SIP Inbound URI** | `sip:hotel@vw9lj499216.sip.livekit.cloud` | Public SIP entrypoint |
| **Inbound Trunk ID** | `ST_FqcE6X4R76nP` | Associated with numbers `+15157587590`, `+919994388773`, `hotel` |
| **SIP Dispatch Rule** | `SDR_jgQdHoSebpLv` | Maps calls to dynamic rooms matching `hotel-call-*` |
| **Digest Authentication** | Disabled (Empty) | Allows clean carrier SIP INVITEs without password rejection |

### Twilio Account Configuration
| Setting | Value | Description |
| :--- | :--- | :--- |
| **Twilio Phone Number** | `+1 515 758 7590` | Active purchased telephone line |
| **Target Guest Mobile** | `+91 9994388773` | Customer mobile phone number |
| **Account SID** | `your_twilio_account_sid` (in `.env`) | Twilio Account identifier |
| **Auth Token** | `your_twilio_auth_token` (in `.env`) | Twilio REST API secret |

---

## 3. Call Flows

### A. Inbound Calling (Guest calls +1 515 758 7590)
1. Guest dials `+1 515 758 7590` from any landline or mobile.
2. Twilio receives the incoming call and fires an HTTP POST webhook to `/twilio/voice`.
3. FastAPI responds with TwiML:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <Response>
       <Dial answerOnBridge="true" callerId="+15157587590" timeout="30">
           <Sip>sip:hotel@vw9lj499216.sip.livekit.cloud</Sip>
       </Dial>
   </Response>
   ```
4. Twilio sends a SIP INVITE to LiveKit Cloud.
5. LiveKit's Inbound Trunk accepts the call and routes it to room `hotel-call-+919994388773`.
6. Maya answers and speaks the initial greeting.

### B. Outbound Calling (Maya calls Guest +91 9994388773)
1. Triggered via CLI (`python scripts/call_guest.py`) or Web UI.
2. Backend calls Twilio's REST API (`POST /2010-04-01/Accounts/{SID}/Calls.json`):
   ```python
   payload = {
       "To": "+919994388773",
       "From": "+15157587590",
       "Twiml": """<Response>
           <Dial answerOnBridge="true" callerId="+15157587590" timeout="30">
               <Sip>sip:hotel@vw9lj499216.sip.livekit.cloud</Sip>
           </Dial>
       </Response>"""
   }
   ```
3. Twilio rings `+919994388773`.
4. As soon as the guest answers (and completes the Twilio trial keypress prompt), Twilio bridges the audio directly into LiveKit SIP.

---

## 4. Phone Number Normalization Engine

Implemented in [`api/schemas/twilio.py`](file:///C:/Users/shahiil/Desktop/AI_hotel/api/schemas/twilio.py):
- Automatically standardizes user inputs into canonical **E.164 international format**:
  - `9994388773` -> `+919994388773`
  - `09994388773` -> `+919994388773`
  - `+91 9994388773` -> `+919994388773`
  - `+1 (515) 758-7590` -> `+15157587590`
