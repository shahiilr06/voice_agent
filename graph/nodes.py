"""
LangGraph execution nodes for conversation handling, extraction, and booking.
"""
import re
import json
import os
from datetime import date, timedelta
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from graph.state import BookingState
from graph.prompts import SYSTEM_PROMPT, EXTRACTION_PROMPT
from graph.tools import tool_check_availability, tool_create_booking

from agent.lang_detector import detect_language


def detect_language_node(state: BookingState) -> Dict[str, Any]:
    """Classify user utterance into ta-IN (Tamil), tanglish, or en-IN (English)."""
    messages = state.get("messages", [])
    if not messages:
        return {"language": state.get("language") or "en-IN"}

    last_text = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
            last_text = msg.content
            break

    if not last_text:
        return {"language": state.get("language") or "en-IN"}

    lower = last_text.lower().strip()
    # Explicit language preference keywords
    if "tamil" in lower or "தமிழ்" in last_text or "tamizh" in lower:
        return {"language": "ta-IN"}
    if "tanglish" in lower or "தங்கிலீஷ்" in last_text:
        return {"language": "tanglish"}
    if "english" in lower:
        return {"language": "en-IN"}

    detected_lang, _ = detect_language(last_text)
    current_lang = state.get("language")
    if current_lang and current_lang != "en-IN" and detected_lang == "en-IN":
        # Keep existing language preference unless user explicitly switched
        if any(c >= '\u0B80' and c <= '\u0BFF' for c in last_text):
            return {"language": "ta-IN"}
        return {"language": current_lang}

    return {"language": detected_lang}


def extract_slots_node(state: BookingState, llm=None) -> Dict[str, Any]:
    """
    Extract structured hotel booking slots from conversation.
    Uses regex rules + LLM extraction for high reliability.
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    updates: Dict[str, Any] = {}

    # Extract all conversation text for rule-based heuristics
    full_text = " ".join([m.content for m in messages if hasattr(m, "content")])
    last_user_msg = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage) or getattr(m, "type", None) == "human":
            last_user_msg = m.content
            break

    # 1. Phone number heuristic: 10 consecutive digits or +91 pattern
    phone_match = re.search(r"(\+91[\-\s]?)?[6-9]\d{9}", full_text)
    if phone_match and not state.get("guest_phone"):
        updates["guest_phone"] = phone_match.group(0).replace(" ", "").replace("-", "")

    # 2. Room type heuristic
    lower_text = full_text.lower()
    if not state.get("room_type"):
        if "suite" in lower_text or "சூட்" in lower_text:
            updates["room_type"] = "suite"
        elif "deluxe" in lower_text or "டீலக்ஸ்" in lower_text:
            updates["room_type"] = "deluxe"
        elif "family" in lower_text or "குடும்ப" in lower_text:
            updates["room_type"] = "family"
        elif "standard" in lower_text or "ஸ்டாண்டர்ட்" in lower_text:
            updates["room_type"] = "standard"

    # 3. Guest count heuristic
    if not state.get("num_guests"):
        guest_match = re.search(r"(\d+)\s*(guests?|people|persons?|members?|family members?|பேர்|நபர்கள்)", lower_text)
        if guest_match:
            try:
                updates["num_guests"] = int(guest_match.group(1))
            except ValueError:
                pass
        elif "one person" in lower_text or "single person" in lower_text or "ஒரு நபர்" in lower_text:
            updates["num_guests"] = 1
        elif "two people" in lower_text or "two members" in lower_text or "இரண்டு பேர்" in lower_text:
            updates["num_guests"] = 2
        elif "four" in lower_text or "4" in lower_text:
            if "family" in lower_text or "guests" in lower_text or "members" in lower_text or "பேர்" in lower_text:
                updates["num_guests"] = 4

    # 4. Dates heuristic: Check relative dates e.g. tomorrow, 2 nights
    today = date.today()
    if not state.get("check_in"):
        if "tomorrow" in lower_text or "நாளை" in lower_text:
            updates["check_in"] = (today + timedelta(days=1)).isoformat()
            if not state.get("check_out"):
                updates["check_out"] = (today + timedelta(days=2)).isoformat()
        elif "today" in lower_text or "இன்று" in lower_text:
            updates["check_in"] = today.isoformat()
            if not state.get("check_out"):
                updates["check_out"] = (today + timedelta(days=1)).isoformat()

    # Explicit date regex e.g. 2026-11-25 or December 25
    date_matches = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", full_text)
    if date_matches:
        if not state.get("check_in") and len(date_matches) >= 1:
            updates["check_in"] = date_matches[0]
        if not state.get("check_out") and len(date_matches) >= 2:
            updates["check_out"] = date_matches[1]

    # Month name dates (e.g. 25 December 2025)
    month_match = re.search(r"(\d{1,2})\s*(?:st|nd|rd|th)?\s*(january|february|march|april|may|june|july|august|september|october|november|december)\s*(\d{4})?", lower_text)
    if month_match and not state.get("check_in"):
        day = int(month_match.group(1))
        months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
        m_idx = months.index(month_match.group(2)) + 1
        year = int(month_match.group(3)) if month_match.group(3) else today.year
        try:
            updates["check_in"] = f"{year:04d}-{m_idx:02d}-{day:02d}"
        except Exception:
            pass

    # 5. Verbal confirmation check
    last_lower = last_user_msg.lower()
    confirm_words = {"yes", "confirm", "proceed", "sure", "book it", "okay", "ok", "aama", "seri", "ஆம்", "சரி"}
    if any(w in last_lower.split() for w in confirm_words) and state.get("stage") == "awaiting_guest_confirmation":
        updates["guest_confirmed"] = True

    # 6. Optional LLM-assisted extraction if LLM is provided and slots are still missing
    if llm and (not state.get("guest_name") or not state.get("check_in") or not state.get("check_out")):
        try:
            summary = "\n".join([f"{getattr(m, 'type', 'user')}: {m.content}" for m in messages[-6:]])
            resp = llm.invoke([
                SystemMessage(content=EXTRACTION_PROMPT),
                HumanMessage(content=f"Conversation:\n{summary}")
            ])
            content = resp.content.strip()
            # Clean possible markdown block
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
            parsed = json.loads(content)
            for k in ["guest_name", "guest_phone", "room_type", "check_in", "check_out", "num_guests"]:
                if parsed.get(k) and not state.get(k) and k not in updates:
                    updates[k] = parsed[k]
            if parsed.get("guest_confirmed") and not state.get("guest_confirmed"):
                updates["guest_confirmed"] = True
        except Exception:
            pass

    return updates


def check_availability_node(state: BookingState) -> Dict[str, Any]:
    """Execute availability check when dates and room type are available."""
    check_in = state.get("check_in")
    check_out = state.get("check_out")
    room_type = state.get("room_type")
    num_guests = state.get("num_guests") or 1

    if not (check_in and check_out):
        return {"stage": "collecting_slots"}

    avail_info = tool_check_availability(
        room_type=room_type,
        check_in=check_in,
        check_out=check_out,
        num_guests=num_guests,
    )

    if avail_info.get("is_available"):
        return {
            "is_available": True,
            "available_room_id": avail_info.get("room_id"),
            "available_room_name": avail_info.get("room_name"),
            "price_per_night": avail_info.get("price_per_night"),
            "total_price": avail_info.get("total_price"),
            "stage": "awaiting_guest_confirmation",
        }
    else:
        return {
            "is_available": False,
            "stage": "collecting_slots",
        }


def create_booking_node(state: BookingState) -> Dict[str, Any]:
    """Execute confirmed booking persistence."""
    res = tool_create_booking(
        guest_name=state.get("guest_name") or "Valued Guest",
        guest_phone=state.get("guest_phone") or "N/A",
        room_type=state.get("room_type") or "deluxe",
        check_in=state.get("check_in"),
        check_out=state.get("check_out"),
        num_guests=state.get("num_guests") or 1,
        language_used=state.get("language") or "en-IN",
        raw_conversation=" | ".join([m.content for m in state.get("messages", [])]),
    )

    if res.get("success"):
        return {
            "booking_confirmed": True,
            "confirmation_code": res.get("confirmation_code"),
            "stage": "completed",
        }
    else:
        return {
            "booking_confirmed": False,
            "stage": "error",
        }


def receptionist_agent_node(state: BookingState, llm=None) -> Dict[str, Any]:
    """
    Generate Maya's voice response matching language and dialogue stage.
    """
    lang = state.get("language") or "en-IN"
    stage = state.get("stage") or "greeting"
    name = state.get("guest_name")
    phone = state.get("guest_phone")
    room_type = state.get("room_type")
    check_in = state.get("check_in")
    check_out = state.get("check_out")
    num_guests = state.get("num_guests")
    is_avail = state.get("is_available")
    total_price = state.get("total_price")
    conf_code = state.get("confirmation_code")

    # Injected context summary for prompt steering
    context_str = f"""
CURRENT BOOKING STATE:
- Language: {lang}
- Stage: {stage}
- Guest Name: {name or 'Missing'}
- Phone: {phone or 'Missing'}
- Room Type: {room_type or 'Missing'}
- Check-in: {check_in or 'Missing'}
- Check-out: {check_out or 'Missing'}
- Guests: {num_guests or 'Missing'}
- Room Available: {is_avail}
- Total Price: ₹{total_price if total_price else 'N/A'}
- Booking Confirmed: {state.get('booking_confirmed')}
- Confirmation Code: {conf_code or 'Not created yet'}

INSTRUCTIONS FOR THIS TURN:
"""
    if conf_code:
        if lang == "ta-IN":
            context_str += f"முன்பதிவு உறுதியானது! உறுதிப்படுத்தல் எண் {conf_code}, மொத்த தொகை ₹{total_price} கூறி நன்றி சொல்லுங்கள்."
        elif lang == "tanglish":
            context_str += f"Booking confirm aaiduchu! Code {conf_code}, total ₹{total_price}. Nandri solli welcome pannunga."
        else:
            context_str += f"Booking is confirmed! Announce confirmation code {conf_code} and total price ₹{total_price}, and warmly welcome them to Sunrise Hotel."
    elif stage == "awaiting_guest_confirmation":
        if lang == "ta-IN":
            context_str += f"{room_type} அறை {check_in} முதல் {check_out} வரை ₹{total_price}-க்கு தயாராக உள்ளது. முன்பதிவை உறுதிப்படுத்தலாமா என்று கேட்கவும்."
        elif lang == "tanglish":
            context_str += f"{room_type} room ready-aa irukku, total ₹{total_price}. Booking confirm pannattumaa nu kelunga."
        else:
            context_str += f"The {room_type} room is available from {check_in} to {check_out} for ₹{total_price}. Summarize details and ask if they would like to confirm."
    elif is_avail is False and check_in and check_out:
        if lang == "ta-IN":
            context_str += f"மன்னிக்கவும், அந்த தேதிகளில் {room_type or 'அறை'} கிடைக்கவில்லை. மாற்று தேதிகளை பரிந்துரைக்கவும்."
        elif lang == "tanglish":
            context_str += f"Sorry, andha dates-la {room_type or 'room'} available illa. Vera date parkalaamaa nu kelunga."
        else:
            context_str += f"Unfortunately, the {room_type or 'requested'} room is not available for those dates. Politely suggest alternate dates or another room type."
    else:
        # Prompt for next missing slot
        missing = []
        if not room_type: missing.append("room type (Deluxe/Suite/Standard)")
        if not check_in: missing.append("check-in date")
        if not check_out: missing.append("check-out date")
        if not num_guests: missing.append("number of guests")
        if not name: missing.append("guest name")
        if not phone: missing.append("phone number")
        next_slot = missing[0] if missing else "confirmation"
        context_str += f"Ask politely in {lang} for: {next_slot}."

    sys_msg = SystemMessage(content=f"{SYSTEM_PROMPT}\n\n{context_str}")
    conversation = [sys_msg] + [m for m in state.get("messages", []) if not isinstance(m, SystemMessage)]

    if llm:
        try:
            ai_msg = llm.invoke(conversation)
            if ai_msg and getattr(ai_msg, "content", None):
                clean_text = ai_msg.content.strip().replace("\n", " ").replace("**", "")
                return {"messages": [AIMessage(content=clean_text)]}
        except Exception as e:
            pass

    # High quality natural conversational voice fallback responses
    fallback_text = "Welcome to Sunrise Hotel! Which language would you prefer — English, Tamil, or Tanglish?"
    if lang == "ta-IN":
        fallback_text = "வணக்கம்! சன்ரைஸ் ஹோட்டலுக்கு நல்வரவு. அறை முன்பதிவு செய்ய நான் எவ்வாறு உதவலாம்?"
    elif lang == "tanglish":
        fallback_text = "Vanakkam! Sunrise Hotel-ku welcome. Room booking-ku eppadi help pannalam?"

    if conf_code:
        if lang == "ta-IN":
            fallback_text = f"உங்கள் முன்பதிவு உறுதி செய்யப்பட்டது! உங்கள் உறுதிப்படுத்தல் எண் {conf_code}. சன்ரைஸ் ஹோட்டலை தேர்ந்தெடுத்ததற்கு நன்றி!"
        elif lang == "tanglish":
            fallback_text = f"Ungaloda booking confirm aaiduchu! Confirmation code {conf_code}. Sunrise Hotel-la sandhikka aavaludan irukkom!"
        else:
            fallback_text = f"Your reservation is confirmed! Your booking confirmation code is {conf_code}. We look forward to welcoming you to Sunrise Hotel!"
    elif stage == "awaiting_guest_confirmation":
        if lang == "ta-IN":
            fallback_text = f"{room_type} அறை தயாராக உள்ளது, மொத்த தொகை ₹{total_price}. முன்பதிவை உறுதி செய்யலாமா?"
        elif lang == "tanglish":
            fallback_text = f"{room_type} room available-aa irukku, total ₹{total_price}. Booking confirm pannattumaa?"
        else:
            fallback_text = f"The {room_type} room is available for ₹{total_price}. Shall I go ahead and confirm this reservation for you?"

    return {"messages": [AIMessage(content=fallback_text)]}
