import asyncio
import json
import os
import re
from dataclasses import dataclass
from typing import Any

import litellm

try:
    from .hotel_api import ROOM_CATALOG, book_room, cancel_booking, check_room, list_room_details
except ImportError:
    from hotel_api import ROOM_CATALOG, book_room, cancel_booking, check_room, list_room_details


SYSTEM_PROMPT = (
    "You are a fast, voice-first hotel assistant. "
    "Reply briefly, naturally, and clearly. "
    "Always reply in the same language as the latest user message (Tamil or English). "
    "Never output internal reasoning, analysis, or <think> tags. "
    "Use tools whenever booking or availability actions are needed. "
    "Never invent booking confirmations."
)

NO_TOOL_PROMPT = (
    "You are a fast, voice-first hotel assistant for Sunrise Hotel. "
    "Always reply in the same language as the latest user message (Tamil or English). "
    "Keep responses brief and conversational. "
    "Never output internal reasoning, analysis, or <think> tags. "
    "Do not confirm or cancel any reservation yourself. "
    "\n\nBooking flow:\n"
    "1. Collect details in order: check-in date → check-out date → number of guests → room type\n"
    "2. Acknowledge each detail the user provides\n"
    "3. Ask for the NEXT missing detail only\n"
    "4. Remember all previously collected information\n"
    "5. Never ask for the same detail twice\n"
    "6. When all 4 details are collected, check availability and ask for name/phone to confirm\n"
    "\nRoom types: Standard (INR 500), Deluxe (INR 800), Suite (INR 1200), Family (INR 950) per night."
)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_room",
            "description": "Check room availability and pricing for requested dates and guests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "guests": {"type": "integer"},
                    "room_type": {"type": "string"},
                },
                "required": ["start_date", "end_date", "guests", "room_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_room",
            "description": "Create a booking when guest confirms details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "phone": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "guests": {"type": "integer"},
                    "room_type": {"type": "string"},
                },
                "required": [
                    "name",
                    "phone",
                    "start_date",
                    "end_date",
                    "guests",
                    "room_type",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_booking",
            "description": "Cancel an existing booking with a confirmation number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmation_number": {"type": "string"},
                },
                "required": ["confirmation_number"],
            },
        },
    },
]


TOOL_HANDLERS = {
    "check_room": check_room,
    "book_room": book_room,
    "cancel_booking": cancel_booking,
}

_INVALID_KEY_VALUES = {
    "",
    "your_sarvam_api_key_here",
    "replace_with_real_key",
    "changeme",
}

_MODEL_ALIASES = {
    "sarvam-m": "sarvam/sarvam-m",
    "sarvam 30b": "sarvam/sarvam-m",
    "sarvam-30b": "sarvam/sarvam-m",
    "servam 30b": "sarvam/sarvam-m",
    "servam-30b": "sarvam/sarvam-m",
}


@dataclass(frozen=True)
class SarvamRuntimeConfig:
    api_key: str
    model_name: str
    api_base: str
    tools_enabled: bool


_runtime_config: SarvamRuntimeConfig | None = None
_LLM_MESSAGE_WINDOW = int(os.getenv("LLM_MESSAGE_WINDOW", "40"))
_NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "ஒரு": 1,
    "ஒன்று": 1,
    "இரண்டு": 2,
    "ரெண்டு": 2,
    "மூன்று": 3,
    "நான்கு": 4,
    "நாலு": 4,
    "ஐந்து": 5,
    "ஆறு": 6,
    "ஏழு": 7,
    "எட்டு": 8,
    "ഒന്ന്": 1,
    "രണ്ട്": 2,
    "മൂന്ന്": 3,
    "നാല്": 4,
    "നാലു": 4,
    "അഞ്ച്": 5,
    "ആറ്": 6,
    "ഏഴ്": 7,
    "എട്ട്": 8,
}
_BOOKING_CONTEXT_HISTORY_WINDOW = int(os.getenv("BOOKING_CONTEXT_HISTORY_WINDOW", "48"))
_MONTH_ALIASES = {
    "jan": "January",
    "january": "January",
    "feb": "February",
    "february": "February",
    "mar": "March",
    "march": "March",
    "apr": "April",
    "april": "April",
    "may": "May",
    "jun": "June",
    "june": "June",
    "jul": "July",
    "july": "July",
    "aug": "August",
    "august": "August",
    "sep": "September",
    "sept": "September",
    "september": "September",
    "oct": "October",
    "october": "October",
    "nov": "November",
    "november": "November",
    "dec": "December",
    "december": "December",
    "ஜனவரி": "January",
    "பிப்ரவரி": "February",
    "மார்ச்": "March",
    "ஏப்ரல்": "April",
    "மே": "May",
    "ஜூன்": "June",
    "ஜூலை": "July",
    "ஆகஸ்ட்": "August",
    "செப்டம்பர்": "September",
    "அக்டோபர்": "October",
    "நவம்பர்": "November",
    "டிசம்பர்": "December",
}
_MONTH_ORDER = {
    "January": 1,
    "February": 2,
    "March": 3,
    "April": 4,
    "May": 5,
    "June": 6,
    "July": 7,
    "August": 8,
    "September": 9,
    "October": 10,
    "November": 11,
    "December": 12,
}
_MONTH_TOKEN_PATTERN = "|".join(sorted((re.escape(k) for k in _MONTH_ALIASES.keys()), key=len, reverse=True))
_ROOM_TYPE_ALIASES = {
    "standard": ("standard", "basic"),
    "deluxe": ("deluxe",),
    "suite": ("suite",),
    "family": ("family",),
}
_SLOT_ORDER = ("check_in", "check_out", "guests", "room_type")
_FOLLOW_UP_BY_SLOT = {
    "en": {
        "check_in": "What is your check-in date?",
        "check_out": "What is your check-out date?",
        "guests": "How many guests will stay?",
        "room_type": "Which room type do you prefer: standard, deluxe, suite, or family?",
    },
    "ta": {
        "check_in": "உங்கள் check-in தேதி என்ன?",
        "check_out": "உங்கள் check-out தேதி என்ன?",
        "guests": "எத்தனை விருந்தினர்கள் தங்கவுள்ளனர்?",
        "room_type": "எந்த room type வேண்டும்: standard, deluxe, suite, அல்லது family?",
    },
}

_BOOKING_KEYWORDS_TA = (
    "அறை",
    "முன்பதிவு",
    "புக்",
    "ரூம்",
    "செக்-இன்",
    "செக் இன்",
    "செக்கின்",
    "செக்கிங்",
    "செக்-அவுட்",
    "செக் அவுட்",
    "செக்கவுட்",
    "இன்று",
    "நாளை",
    "விருந்தினர்",
    "பேர்",
)

_DETAIL_KEYWORDS_TA = ("விவரம்", "டீடெய்ல்ஸ்", "ரூம் வகை", "அறை வகை", "விருப்பங்கள்")
_PRICE_KEYWORDS_TA = ("விலை", "கட்டணம்", "rate", "price")
_TAMIL_SCRIPT_RE = re.compile(r"[\u0B80-\u0BFF]")


def _resolve_api_key() -> str:
    api_key = (os.getenv("SARVAM_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("Missing SARVAM_API_KEY in your environment.")
    if api_key.lower() in _INVALID_KEY_VALUES:
        raise ValueError(
            "Invalid placeholder API key detected. Replace SARVAM_API_KEY with a real Sarvam key."
        )
    return api_key


def _resolve_model() -> str:
    configured = (os.getenv("SARVAM_MODEL") or "").strip()
    if not configured:
        return "sarvam/sarvam-m"
    return _MODEL_ALIASES.get(configured.lower(), configured)


def _tools_enabled_for_model(model_name: str) -> bool:
    mode = (os.getenv("SARVAM_ENABLE_TOOL_CALLING", "auto") or "auto").strip().lower()
    if mode in {"0", "false", "off", "disabled", "no"}:
        return False
    if mode in {"1", "true", "on", "enabled", "yes"}:
        return True
    # Auto mode: Sarvam-m does not support tool-calling.
    return model_name.lower() not in {"sarvam/sarvam-m"}


def _is_tool_call_not_supported_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "tool calling is not supported" in text or "tool-calling is not supported" in text


def configure_runtime(
    *,
    api_key: str | None = None,
    model_name: str | None = None,
    api_base: str | None = None,
    tools_enabled: bool | None = None,
) -> SarvamRuntimeConfig:
    global _runtime_config
    resolved_model = model_name or _resolve_model()
    resolved_api_key = api_key or _resolve_api_key()
    resolved_api_base = api_base or os.getenv("SARVAM_API_BASE", "https://api.sarvam.ai/v1")
    resolved_tools_enabled = _tools_enabled_for_model(resolved_model) if tools_enabled is None else tools_enabled
    _runtime_config = SarvamRuntimeConfig(
        api_key=resolved_api_key,
        model_name=resolved_model,
        api_base=resolved_api_base,
        tools_enabled=resolved_tools_enabled,
    )
    return _runtime_config


def _get_runtime_config() -> SarvamRuntimeConfig:
    if _runtime_config is not None:
        return _runtime_config
    return configure_runtime()


def _contains_tamil_script(text: str) -> bool:
    return bool(_TAMIL_SCRIPT_RE.search(text or ""))


def _detect_language_from_text(text: str) -> str:
    lowered = (text or "").lower()
    if _contains_tamil_script(text):
        return "ta"
    if re.search(r"\b(speak tamil|tamil please|தமிழ்)\b", lowered):
        return "ta"
    if re.search(r"\b(vanakkam|nandri)\b", lowered):
        return "ta"
    return "en"


def _detect_preferred_language(history: list[dict[str, str]], user_text: str) -> str:
    explicit = _detect_language_from_text(user_text)
    if explicit == "ta":
        return "ta"

    lowered = (user_text or "").lower()
    if re.search(r"\b(speak english|english please|ஆங்கிலம்)\b", lowered):
        return "en"

    for turn in reversed(history[-8:]):
        if (turn.get("role") or "").lower() != "user":
            continue
        content = turn.get("content", "")
        if _detect_language_from_text(content) == "ta":
            return "ta"
        if re.search(r"\b(speak english|english please|ஆங்கிலம்)\b", content.lower()):
            return "en"

    return "en"


def _follow_up(slot: str, language: str) -> str:
    return _FOLLOW_UP_BY_SLOT.get(language, _FOLLOW_UP_BY_SLOT["en"]).get(slot, "")


def _is_greeting(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\b(hello|hi|hey|good morning|good evening|vanakkam)\b", lowered):
        return True
    return "வணக்கம்" in text


def _language_preference(text: str) -> str | None:
    lowered = text.lower()
    if re.search(r"\b(can you speak tamil|speak tamil|tamil please|தமிழில் பேச|தமிழ் பேச)\b", lowered):
        return "ta"
    if re.search(r"\b(speak english|english please|ஆங்கிலத்தில் பேச|ஆங்கிலம் பேச)\b", lowered):
        return "en"
    return None


def _is_unclear_input(text: str) -> bool:
    if not text.strip():
        return True
    return re.search(r"[A-Za-z0-9\u0B80-\u0BFF\u0900-\u097F\u0D00-\u0D7F]", text) is None


def _extract_room_type(text: str) -> str | None:
    lowered = text.lower()
    
    # Tamil room type patterns
    tamil_patterns = {
        "standard": r"(ஸ்டாண்டர்ட்|ஸ்டான்டர்ட்|ஸ்டாண்டர்ட|ஸ்டான்டர்ட|standard)",
        "deluxe": r"(டீலக்ஸ்|டெலக்ஸ்|டீலக்ஸ|டெலக்ஸ|deluxe|delux)",
        "suite": r"(சூட்|சூட்டு|suite)",
        "family": r"(ஃபேமிலி|பேமிலி|ஃபேமிலீ|பேமிலீ|family)",
    }
    
    for room_type, pattern in tamil_patterns.items():
        if re.search(pattern, lowered):
            return room_type
    
    # English patterns
    for room_type, aliases in _ROOM_TYPE_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", lowered):
                return room_type
    
    return None


def _extract_guests(text: str) -> int | None:
    lowered = text.lower()

    def parse_number_token(token: str) -> int | None:
        normalized = (token or "").strip().lower()
        if not normalized:
            return None
        if normalized.isdigit():
            return int(normalized)
        return _NUMBER_WORDS.get(normalized)

    # Explicit guest patterns
    explicit = re.search(
        r"\b(\d+)\s*(guest|guests|people|person|persons|adult|adults|member|members|pax|விருந்தினர்|பேர்|பேரு)\b",
        lowered,
    )
    if explicit:
        return int(explicit.group(1))

    # Number word patterns
    for word, value in _NUMBER_WORDS.items():
        if re.search(
            rf"(?<!\w){re.escape(word)}\s*(guest|guests|people|person|persons|adult|adults|member|members|pax|விருந்தினர்|பேர்|பேரு)",
            lowered,
        ):
            return value

    # Pair matches (e.g., "2 ladies 2 gents")
    pair_matches = re.findall(
        r"(\d+|[a-z]+|[\u0B80-\u0BFF]+|[\u0D00-\u0D7F]+)\s*"
        r"(?:ladies|lady|gents|gent|women|men|"
        r"லேடீஸ்|லேடிஸ்|ஜெண்ட்ஸ்|ஜென்ட்ஸ்|பெண்கள்|ஆண்கள்|"
        r"ലേഡീസ്|ലേഡീസും|ജെൻറ്|ജെന്റ്|ജെന്റും|ജെന്റ്സ്|സ്ത്രീകൾ|പുരുഷൻമാർ)",
        lowered,
    )
    if pair_matches:
        total = 0
        for token in pair_matches:
            value = parse_number_token(token)
            if value is not None:
                total += value
        if total > 0:
            return total

    # Tamil compact pattern
    compact_tamil = re.search(r"([a-z0-9\u0B80-\u0BFF]+)\s*(?:பேர்|பேரு)", lowered)
    if compact_tamil:
        value = parse_number_token(compact_tamil.group(1))
        if value is not None:
            return value

    return None


def _extract_slot_signal(text: str) -> str | None:
    lowered = text.lower()
    if (
        re.search(r"\bcheck[- ]?in\b", lowered)
        or re.search(r"\bchecking(?:[- ]?date)?\b", lowered)
        or "செக்-இன்" in lowered
        or "செக் இன்" in lowered
        or "செக்கின்" in lowered
        or "செக்கிங்" in lowered
        or "செக்கிங் டேட்" in lowered
        or "புகும் தேதி" in lowered
        or "வரவு தேதி" in lowered
        or "चेकिंग" in lowered
    ):
        return "check_in"
    if (
        re.search(r"\bcheck[- ]?out\b", lowered)
        or re.search(r"\bcheckout(?:[- ]?date)?\b", lowered)
        or "செக்-அவுட்" in lowered
        or "செக் அவுட்" in lowered
        or "செக்கவுட்" in lowered
        or "வெளியேறும் தேதி" in lowered
        or "புறப்படும் தேதி" in lowered
        or "चेकआउट" in lowered
    ):
        return "check_out"
    if "வரை" in lowered:
        return "check_out"
    return None


def _extract_month_day_value(text: str) -> str | None:
    lowered = text.lower()
    month_first = re.search(
        rf"({_MONTH_TOKEN_PATTERN})\s*[-/,\s]\s*([0-3]?\d)(?:st|nd|rd|th|ஆம்|ம்)?\b",
        lowered,
        flags=re.IGNORECASE,
    )
    day_first = re.search(
        rf"\b([0-3]?\d)(?:st|nd|rd|th|ஆம்|ம்)?\s*[-/,\s]\s*({_MONTH_TOKEN_PATTERN})",
        lowered,
        flags=re.IGNORECASE,
    )

    month_token = ""
    day_token = ""
    if month_first:
        month_token = month_first.group(1)
        day_token = month_first.group(2)
    elif day_first:
        day_token = day_first.group(1)
        month_token = day_first.group(2)
    else:
        return None

    try:
        day = int(day_token)
    except ValueError:
        return None
    if day < 1 or day > 31:
        return None

    canonical_month = _MONTH_ALIASES.get(month_token.lower()) or _MONTH_ALIASES.get(month_token)
    if not canonical_month:
        return None
    return f"{canonical_month} {day}"


def _parse_month_day(value: str | None) -> tuple[int | None, int] | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    day_only = re.fullmatch(r"([0-3]?\d)", text)
    if day_only:
        day = int(day_only.group(1))
        if 1 <= day <= 31:
            return (None, day)
        return None
    month_day = re.fullmatch(r"([A-Za-z]+)\s+([0-3]?\d)", text)
    if not month_day:
        return None
    month_name = month_day.group(1).title()
    month_num = _MONTH_ORDER.get(month_name)
    if month_num is None:
        return None
    day = int(month_day.group(2))
    if day < 1 or day > 31:
        return None
    return (month_num, day)


def _is_checkout_before_checkin(check_in: str | None, check_out: str | None) -> bool:
    parsed_in = _parse_month_day(check_in)
    parsed_out = _parse_month_day(check_out)
    if not parsed_in or not parsed_out:
        return False
    in_month, in_day = parsed_in
    out_month, out_day = parsed_out

    if in_month is None and out_month is None:
        return out_day <= in_day
    if in_month is not None and out_month is not None:
        if out_month < in_month:
            return True
        if out_month == in_month and out_day <= in_day:
            return True
    return False


def _extract_dates(text: str) -> dict[str, str]:
    lowered = text.lower()
    result: dict[str, str] = {}
    slot_signal = _extract_slot_signal(lowered)
    month_day_range = re.search(
        rf"({_MONTH_TOKEN_PATTERN})\s*([0-3]?\d)\s*(?:,|and|to|-|/)\s*([0-3]?\d)\b",
        lowered,
        flags=re.IGNORECASE,
    )
    month_day_value = _extract_month_day_value(lowered)
    date_matches = re.findall(r"\b\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?\b", lowered)
    ordinal_day = re.search(r"\b([0-3]?\d)\s*(?:ஆம்|ம்)\s*(?:தேதி|நாள்)?\b", lowered)
    tamil_date_day = re.search(r"\b([0-3]?\d)\s*(?:தேதி|நாள்)\b", lowered)

    if len(date_matches) >= 2:
        result["check_in"] = date_matches[0]
        result["check_out"] = date_matches[1]
        return result

    if len(date_matches) == 1:
        date_value = date_matches[0]
        # Strong check-out signal
        if slot_signal == "check_out" or re.search(r"\b(check[- ]?out|checkout|out date|வெளியேறும்|செக்[- ]?அவுட்)\b", lowered):
            result["check_out"] = date_value
        else:
            result["check_in"] = date_value

    if month_day_range:
        month_token = month_day_range.group(1)
        day1 = int(month_day_range.group(2))
        day2 = int(month_day_range.group(3))
        if 1 <= day1 <= 31 and 1 <= day2 <= 31:
            canonical_month = _MONTH_ALIASES.get(month_token.lower()) or _MONTH_ALIASES.get(month_token)
            if canonical_month:
                first_date = f"{canonical_month} {day1}"
                second_date = f"{canonical_month} {day2}"
                if slot_signal == "check_out":
                    result.setdefault("check_out", first_date)
                elif slot_signal == "check_in":
                    result.setdefault("check_in", first_date)
                    result.setdefault("check_out", second_date)
                else:
                    result.setdefault("check_in", first_date)
                    result.setdefault("check_out", second_date)

    if month_day_value:
        # Strong check-out signal
        if slot_signal == "check_out" or re.search(r"\b(check[- ]?out|checkout|out date|வெளியேறும்|செக்[- ]?அவுட்)\b", lowered):
            result.setdefault("check_out", month_day_value)
        elif slot_signal == "check_in" or re.search(r"\b(check[- ]?in|checkin|in date|வரவு|செக்[- ]?இன்)\b", lowered):
            result.setdefault("check_in", month_day_value)
        else:
            # Default to check-in if no signal
            result.setdefault("check_in", month_day_value)

    spoken_day = None
    if ordinal_day:
        spoken_day = ordinal_day.group(1)
    elif tamil_date_day:
        spoken_day = tamil_date_day.group(1)
    if spoken_day:
        # Strong check-out signal
        if slot_signal == "check_out" or re.search(r"\b(check[- ]?out|out date|வெளியேறும்|செக்[- ]?அவுட்)\b", lowered):
            result.setdefault("check_out", spoken_day)
        elif slot_signal == "check_in" or re.search(r"\b(check[- ]?in|in date|வரவு|செக்[- ]?இன்)\b", lowered):
            result.setdefault("check_in", spoken_day)
        else:
            result.setdefault("check_in", spoken_day)

    if "today" in lowered or "இன்று" in lowered:
        if slot_signal == "check_out" or re.search(r"\b(check[- ]?out|out|வெளியேறும்)\s+(today|இன்று)\b", lowered):
            result["check_out"] = "today"
        elif slot_signal == "check_in":
            result["check_in"] = "today"
        else:
            result.setdefault("check_in", "today")

    if "tomorrow" in lowered or "நாளை" in lowered:
        if slot_signal == "check_out" or re.search(r"\b(check[- ]?out|out|வெளியேறும்)\s+(tomorrow|நாளை)\b", lowered):
            result["check_out"] = "tomorrow"
        elif slot_signal == "check_in":
            result["check_in"] = "tomorrow"
        elif "check_in" not in result:
            result["check_in"] = "tomorrow"

    return result


def _extract_simple_date_value(text: str) -> str | None:
    lowered = text.strip().lower()
    if re.fullmatch(r"(today|tomorrow|இன்று|நாளை)", lowered):
        if lowered in {"today", "இன்று"}:
            return "today"
        return "tomorrow"
    month_day_value = _extract_month_day_value(lowered)
    if month_day_value:
        return month_day_value
    explicit = re.fullmatch(r"\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?", lowered)
    if explicit:
        return explicit.group(0)
    tamil_day = re.fullmatch(r"([0-3]?\d)\s*(?:ஆம்|ம்)?\s*(?:தேதி|நாள்)?", lowered)
    if tamil_day:
        return tamil_day.group(1)
    return None


def _extract_name_phone(text: str) -> dict[str, str]:
    """Extract name and phone number from text"""
    result = {}
    lowered = text.lower()
    
    # Extract phone number - more flexible patterns
    phone_patterns = [
        r"\b(\d{10})\b",  # 10 digits
        r"\b(\d{4}[-\s]?\d{6})\b",  # 4-6 format
        r"\b(\d{5}[-\s]?\d{5})\b",  # 5-5 format
        r"\b(\d{3}[-\s]?\d{3}[-\s]?\d{4})\b",  # 3-3-4 format
        r"(?:number|mobile|phone|நம்பர்|மொபைல்)[:\s]+(\d{8,12})",  # After keywords
    ]
    
    for pattern in phone_patterns:
        phone_match = re.search(pattern, text)
        if phone_match:
            phone = phone_match.group(1).replace("-", "").replace(" ", "")
            if len(phone) >= 8:  # Valid phone number
                result["phone"] = phone
                break
    
    # Extract name - improved patterns
    name_patterns = [
        r"(?:my name is|name is|i am|i'm|this is|என் பேரு|என்னோட பேரு|பேரு)\s+([A-Za-z][A-Za-z\s]{1,30})",
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*(?:here|speaking|இங்கே)?\.?$",  # Capitalized name
    ]
    
    for pattern in name_patterns:
        name_match = re.search(pattern, text, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip()
            # Filter out common non-name words
            exclude_words = r"\b(number|phone|mobile|email|provide|already|will|நம்பர்|மொபைல்|room|அறை|hotel|check)\b"
            if name and not re.search(exclude_words, name.lower()):
                # Clean up extra words
                name_words = name.split()
                clean_name = " ".join([w for w in name_words if len(w) > 1 and w[0].isupper()])
                if clean_name:
                    result["name"] = clean_name
                    break
    
    return result


def _extract_booking_fields(text: str) -> dict[str, Any]:
    extracted = _extract_dates(text)
    guests = _extract_guests(text)
    room_type = _extract_room_type(text)
    name_phone = _extract_name_phone(text)
    
    if guests is not None:
        extracted["guests"] = guests
    if room_type is not None:
        extracted["room_type"] = room_type
    if name_phone:
        extracted.update(name_phone)
    
    return extracted


def _update_context_from_text(context: dict[str, Any], text: str) -> None:
    existing_check_in = context.get("check_in")
    existing_check_out = context.get("check_out")
    extracted = _extract_booking_fields(text)
    next_slot = _next_missing_slot(context)
    simple_date = _extract_simple_date_value(text)
    slot_signal = _extract_slot_signal(text)

    if slot_signal == "check_out" and "check_in" in extracted and "check_out" not in extracted:
        extracted["check_out"] = extracted.pop("check_in")
    if slot_signal == "check_in" and "check_out" in extracted and "check_in" not in extracted:
        extracted["check_in"] = extracted.pop("check_out")

    if (
        existing_check_in is not None
        and existing_check_out is None
        and slot_signal is None
        and "check_in" in extracted
        and "check_out" not in extracted
    ):
        extracted["check_out"] = extracted.pop("check_in")

    if (
        existing_check_in is not None
        and existing_check_out is not None
        and slot_signal is None
        and next_slot not in {"check_in", "check_out"}
    ):
        extracted.pop("check_in", None)
        extracted.pop("check_out", None)

    target_slot = None
    if simple_date:
        if slot_signal in {"check_in", "check_out"}:
            target_slot = slot_signal
        elif next_slot in {"check_in", "check_out"}:
            target_slot = next_slot
        elif existing_check_in is not None and existing_check_out is None:
            target_slot = "check_out"
        elif existing_check_out is not None and existing_check_in is None:
            target_slot = "check_in"

    if simple_date and target_slot:
        context[target_slot] = simple_date
        if target_slot == "check_out":
            extracted.pop("check_in", None)
        elif target_slot == "check_in":
            extracted.pop("check_out", None)

    context.update(extracted)
    if _is_checkout_before_checkin(str(context.get("check_in") or ""), str(context.get("check_out") or "")):
        context.pop("check_out", None)


def _collect_booking_context(history: list[dict[str, str]], user_text: str) -> dict[str, Any]:
    context: dict[str, Any] = {}
    
    # Process entire history to build complete context
    for turn in history[-_BOOKING_CONTEXT_HISTORY_WINDOW:]:
        if (turn.get("role") or "").lower() != "user":
            continue
        _update_context_from_text(context, turn.get("content", ""))
    
    # Process current user text
    _update_context_from_text(context, user_text)
    
    # Validate context integrity
    if "check_in" in context and "check_out" in context:
        if _is_checkout_before_checkin(str(context.get("check_in")), str(context.get("check_out"))):
            context.pop("check_out", None)
    
    return context


def _next_missing_slot(context: dict[str, Any]) -> str | None:
    for slot in _SLOT_ORDER:
        if slot not in context:
            return slot
    return None


def _room_catalog_text(language: str) -> str:
    details = list_room_details()
    entries = [
        f"{item['room_type'].title()}: INR {item['price']} per night ({item['description']})" for item in details
    ]
    if language == "ta":
        return "எங்கள் அறை விருப்பங்கள்: " + " ".join(entries)
    return "Here are our room options: " + " ".join(entries)


def _is_booking_intent(text: str) -> bool:
    lowered = text.lower()
    # Don't treat name/phone as booking restart
    if re.search(r"\b(my name|என் பேரு|என்னோட|நம்பர்|number|phone|mobile|மொபைல்)\b", lowered):
        return False
    if re.search(
        r"\b(room|book|booking|reserve|reservation|availability|stay|check[- ]?in|check[- ]?out|checking|checkout|today|tomorrow|tonight|guest|guests|people|single|double|standard|deluxe|suite|family)\b",
        lowered,
    ):
        return True
    return any(keyword in lowered for keyword in _BOOKING_KEYWORDS_TA)


def _is_details_intent(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\b(detail|details|room type|room options|available rooms)\b", lowered):
        return True
    return any(keyword in lowered for keyword in _DETAIL_KEYWORDS_TA)


def _is_pricing_intent(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\b(price|pricing|cost|rate|charges|tariff)\b", lowered):
        return True
    return any(keyword in lowered for keyword in _PRICE_KEYWORDS_TA)


def _is_short_ack(text: str) -> bool:
    return bool(re.fullmatch(r"\s*(yes|yeah|yep|ok|okay|sure|fine|ஆம்|சரி|ஓகே)\s*[.!]?\s*", text.lower()))


def _slot_prompt_label(slot: str, language: str) -> str:
    labels = {
        "en": {
            "check_in": "check-in date",
            "check_out": "check-out date",
            "guests": "guest count",
            "room_type": "room type",
        },
        "ta": {
            "check_in": "check-in தேதி",
            "check_out": "check-out தேதி",
            "guests": "விருந்தினர் எண்ணிக்கை",
            "room_type": "room type",
        },
    }
    return labels.get(language, labels["en"]).get(slot, slot)


def _ack_slot_value(slot: str, value: Any, language: str) -> str:
    if value is None:
        return ""
    if language == "ta":
        return f"சரி, உங்கள் {_slot_prompt_label(slot, language)} {value} என்று பதிவு செய்தேன்."
    return f"Got it, I noted your {_slot_prompt_label(slot, language)} as {value}."


def _rule_based_no_tool_reply(history: list[dict[str, str]], user_text: str) -> str:
    text = user_text.strip()
    lowered = text.lower()
    language = _detect_preferred_language(history, text)
    previous_context = _collect_booking_context(history, "")
    context = _collect_booking_context(history, text)
    extracted_now = _extract_booking_fields(text)
    has_booking_update = bool(extracted_now) or _extract_simple_date_value(text) is not None
    preferred_language = _language_preference(text)
    slot_signal = _extract_slot_signal(text)
    updated_slots = [
        slot for slot in _SLOT_ORDER if slot in context and context.get(slot) != previous_context.get(slot)
    ]
    
    # Validate check-out after check-in
    if (
        slot_signal == "check_out"
        and "check_in" in previous_context
        and isinstance(extracted_now.get("check_out"), str)
        and _is_checkout_before_checkin(str(previous_context.get("check_in")), str(extracted_now.get("check_out")))
    ):
        if language == "ta":
            return "check-out தேதி, check-in தேதிக்குப் பிறகு இருக்க வேண்டும். சரியான check-out தேதியை மீண்டும் சொல்லுங்கள்."
        return "Your check-out date must be after your check-in date. Please tell me a valid check-out date."

    # Handle greetings
    if _is_greeting(lowered):
        if language == "ta":
            return "வணக்கம், Sunrise Hotel-க்கு வரவேற்கிறோம். இன்று உங்கள் அறை முன்பதிவுக்கு எப்படி உதவலாம்?"
        return "Hello and welcome to Sunrise Hotel. How can I help you with your room booking today?"

    # Handle language preference
    if preferred_language == "ta":
        return "நிச்சயம், நான் தமிழில் பேச முடியும். உங்கள் check-in தேதி என்ன?"
    if preferred_language == "en":
        return "Sure, I can continue in English. What is your check-in date?"

    # Handle unclear input
    if _is_unclear_input(text) and not has_booking_update:
        if language == "ta":
            return "மன்னிக்கவும், உங்கள் குரல் தெளிவாக கேட்கவில்லை. தயவுசெய்து தமிழ் அல்லது ஆங்கிலத்தில் மீண்டும் சொல்லுங்கள்."
        return "Sorry, I could not catch that clearly. Please repeat in Tamil or English."

    # Handle room details inquiry
    if _is_details_intent(lowered):
        next_slot = _next_missing_slot(context)
        if next_slot:
            return f"{_room_catalog_text(language)} {_follow_up(next_slot, language)}"
        return _room_catalog_text(language)

    # Handle pricing inquiry
    if _is_pricing_intent(lowered):
        room_type = context.get("room_type")
        if isinstance(room_type, str) and room_type in ROOM_CATALOG:
            price = ROOM_CATALOG[room_type]["price"]
            next_slot = _next_missing_slot(context)
            if next_slot:
                if language == "ta":
                    return f"{room_type} room-க்கு ஒரு இரவுக்கான கட்டணம் INR {price}. {_follow_up(next_slot, language)}"
                return f"The {room_type} room is INR {price} per night. {_follow_up(next_slot, language)}"
            if language == "ta":
                return f"{room_type} room-க்கு ஒரு இரவுக்கான கட்டணம் INR {price}. முன்பதிவை தொடரவா?"
            return f"The {room_type} room is INR {price} per night. Would you like me to continue with booking?"
        if language == "ta":
            return (
                "இயல்புநிலை அறை விலை: Standard INR 500, Deluxe INR 800, Suite INR 1200, "
                "Family INR 950 (ஒரு இரவு). எந்த room type வேண்டும்?"
            )
        return (
            "Default room pricing is: Standard INR 500, Deluxe INR 800, Suite INR 1200, "
            "Family INR 950 per night. Which room type do you prefer?"
        )

    # Handle booking flow with structured follow-ups
    if _is_booking_intent(lowered) or _is_short_ack(lowered) or has_booking_update:
        next_slot = _next_missing_slot(context)
        
        # Still collecting information
        if next_slot:
            # Acknowledge newly captured slot with better formatting
            if updated_slots:
                latest_slot = updated_slots[-1]
                value = context.get(latest_slot)
                if value is not None:
                    if language == "ta":
                        if latest_slot == "room_type":
                            ack = f"சரி, {value} அறை."
                        else:
                            ack = f"சரி, {_slot_prompt_label(latest_slot, language)} {value}."
                    else:
                        if latest_slot == "room_type":
                            ack = f"Got it, {value} room."
                        else:
                            ack = f"Got it, {_slot_prompt_label(latest_slot, language)} is {value}."
                    return f"{ack} {_follow_up(next_slot, language)}"
            
            # Acknowledge slot from signal
            if slot_signal in {"check_in", "check_out"} and slot_signal in context and slot_signal != next_slot:
                value = context.get(slot_signal)
                if value is not None:
                    if language == "ta":
                        ack = f"சரி, {_slot_prompt_label(slot_signal, language)} {value}."
                    else:
                        ack = f"Got it, {_slot_prompt_label(slot_signal, language)} is {value}."
                    return f"{ack} {_follow_up(next_slot, language)}"
            
            # Just ask for next missing slot
            return _follow_up(next_slot, language)
        
        # All slots collected - check availability or complete booking
        if "name" in context and "phone" in context:
            # Complete booking
            result = book_room(
                name=str(context["name"]),
                phone=str(context["phone"]),
                start_date=str(context["check_in"]),
                end_date=str(context["check_out"]),
                guests=int(context["guests"]),
                room_type=str(context["room_type"]),
            )
            if result.get("status") == "confirmed":
                conf_num = result.get("confirmation_number", "")
                if language == "ta":
                    return (
                        f"உங்கள் முன்பதிவு உறுதி செய்யப்பட்டது! "
                        f"உறுதிப்படுத்தல் எண்: {conf_num}. "
                        f"நன்றி!"
                    )
                return (
                    f"Your booking is confirmed! "
                    f"Confirmation number: {conf_num}. "
                    f"Thank you!"
                )
            else:
                if language == "ta":
                    return "மன்னிக்கவும், முன்பதிவில் சிக்கல். மீண்டும் முயற்சிக்கவும்."
                return "Sorry, there was an issue with booking. Please try again."
        
        # Check availability
        result = check_room(
            start_date=str(context["check_in"]),
            end_date=str(context["check_out"]),
            guests=int(context["guests"]),
            room_type=str(context["room_type"]),
        )
        if result.get("status") == "available":
            room_name = str(result['room_type']).title()
            price = result['price']
            if language == "ta":
                return (
                    f"சரி! {room_name} அறை {result['start_date']} முதல் {result['end_date']} வரை "
                    f"{result['guests']} விருந்தினருக்கு கிடைக்கிறது. "
                    f"ஒரு இரவுக்கு ரூபாய் {price}. "
                    "உங்கள் பெயர் மற்றும் தொலைபேசி எண்ணை சொல்லுங்கள்."
                )
            return (
                f"Great! {room_name} room is available from {result['start_date']} to {result['end_date']} "
                f"for {result['guests']} guests. "
                f"Price is rupees {price} per night. "
                "Please provide your name and phone number."
            )
        if language == "ta":
            return str(result.get("message") or "தேர்ந்தெடுத்த தேதிகளில் அந்த அறை கிடைக்கவில்லை. வேறு தேதிகளை முயற்சிக்கவா?")
        return str(result.get("message") or "That room is not available for the selected dates. Would you like to try different dates?")

    # Continue conversation if partial context exists
    remembered_next_slot = _next_missing_slot(context)
    if remembered_next_slot and any(slot in context for slot in _SLOT_ORDER):
        # Build summary of what we have
        collected = []
        for slot in _SLOT_ORDER:
            if slot in context:
                collected.append(f"{_slot_prompt_label(slot, language)}: {context[slot]}")
        
        if collected:
            summary = ", ".join(collected)
            if language == "ta":
                return f"இதுவரை நான் பதிவு செய்தது: {summary}. {_follow_up(remembered_next_slot, language)}"
            return f"So far I have: {summary}. {_follow_up(remembered_next_slot, language)}"
        
        return _follow_up(remembered_next_slot, language)

    # Default fallback
    if language == "ta":
        return "அறை விவரம், விலை, மற்றும் முன்பதிவில் உதவலாம். உங்கள் check-in தேதியை சொல்லுங்கள்."
    return "I can help with room details, pricing, and booking. Please tell me your check-in date."


def _normalize_messages(
    history: list[dict[str, str]],
    user_text: str,
    prompt_text: str,
) -> list[dict[str, str]]:
    turns: list[dict[str, str]] = []
    for item in history[-_LLM_MESSAGE_WINDOW:]:
        role = (item.get("role") or "").strip().lower()
        content = (item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        turns.append({"role": role, "content": content})

    current_user = user_text.strip()
    if current_user:
        if not turns or turns[-1]["role"] != "user" or turns[-1]["content"] != current_user:
            turns.append({"role": "user", "content": current_user})

    while turns and turns[0]["role"] != "user":
        turns.pop(0)

    normalized: list[dict[str, str]] = []
    for turn in turns:
        if not normalized:
            normalized.append(turn)
            continue
        if normalized[-1]["role"] == turn["role"]:
            normalized[-1]["content"] = turn["content"]
        else:
            normalized.append(turn)

    if not normalized:
        normalized = [{"role": "user", "content": current_user or "Hello"}]

    # Sarvam chat requires a user-first alternation; inject instructions into the first user turn.
    normalized[0] = {
        "role": "user",
        "content": f"{prompt_text}\n\nUser: {normalized[0]['content']}",
    }
    return normalized


def _llm_memory_prompt(history: list[dict[str, str]], user_text: str) -> str:
    context = _collect_booking_context(history, user_text)
    if not context:
        return ""
    
    # Build collected details summary
    collected = []
    for slot in _SLOT_ORDER:
        value = context.get(slot)
        if value is not None:
            collected.append(f"{slot}: {value}")
    
    # Add name/phone if present
    if "name" in context:
        collected.append(f"name: {context['name']}")
    if "phone" in context:
        collected.append(f"phone: {context['phone']}")
    
    next_slot = _next_missing_slot(context)
    
    if not collected:
        return ""
    
    memory = "[INTERNAL STATE - Never reveal to user]\n"
    memory += "Already collected: " + ", ".join(collected) + "\n"
    
    if next_slot:
        memory += f"Next required: {next_slot}\n"
        memory += f"Action: Acknowledge latest input, ask ONLY for {next_slot}. Do NOT ask for already collected details.\n"
    elif "name" not in context or "phone" not in context:
        memory += "Next required: name and phone number\n"
        memory += "Action: Ask for name and phone number to complete booking.\n"
    else:
        memory += "All details collected. Action: Complete the booking now.\n"
    
    return memory


def validate_sarvam_config(api_key: str | None = None) -> tuple[str, str]:
    if api_key is None:
        _resolve_api_key()
    model_name = _resolve_model()
    api_base = os.getenv("SARVAM_API_BASE", "https://api.sarvam.ai/v1")
    return model_name, api_base


def _needs_confirmation_guard(reply_text: str) -> bool:
    text = reply_text.lower()
    if not text:
        return False
    risky_phrases = (
        "booking confirmed",
        "reservation confirmed",
        "booked successfully",
        "your booking is confirmed",
        "cancellation confirmed",
        "cancelled successfully",
        "confirmation number",
        "reservation number",
    )
    if any(phrase in text for phrase in risky_phrases):
        return True
    return bool(re.search(r"\b(?:cnf|conf|ref)[-_ ]?[a-z0-9]{4,}\b", text))


def _build_missing_details_prompt(user_text: str, history: list[dict[str, str]] | None = None) -> str:
    history = history or []
    text = user_text.lower()
    language = _detect_preferred_language(history, user_text)
    context = _collect_booking_context(history, user_text)
    next_slot = _next_missing_slot(context)
    if next_slot:
        return _follow_up(next_slot, language)

    has_checkin = bool(
        re.search(r"\b(today|tonight|tomorrow|இன்று|நாளை)\b", text)
        or re.search(r"\b\d{1,2}[-/]\d{1,2}(?:[-/]\d{2,4})?\b", text)
    )
    has_checkout = bool(re.search(r"\b(check[- ]?out|until|till|வரை)\b", text))
    has_guests = bool(re.search(r"\b\d+\s*(guest|guests|people|person|adult|adults|விருந்தினர்|பேர்)\b", text))
    has_room_type = bool(re.search(r"\b(single|double|deluxe|suite|standard|family)\b", text))

    missing: list[str] = []
    if not has_checkin:
        missing.append("check-in date")
    if not has_checkout:
        missing.append("check-out date")
    if not has_guests:
        missing.append("number of guests")
    if not has_room_type:
        missing.append("room type")

    if len(missing) == 4:
        if language == "ta":
            return "சரி. check-in தேதி, check-out தேதி, விருந்தினர் எண்ணிக்கை, மற்றும் room type-ஐ சொல்லுங்கள்."
        return (
            "Got it. Please share your check-in date, check-out date, number of guests, "
            "and preferred room type."
        )

    if language == "ta":
        return "நன்றி. தொடர உங்கள் " + ", ".join(missing) + " தகவலை சொல்லுங்கள்."
    return "Thanks. Please share your " + ", ".join(missing) + " so I can continue."


def _sanitize_agent_reply(reply_text: str) -> str:
    text = (reply_text or "").strip()
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    if "<think>" in text.lower():
        text = re.split(r"<think>", text, flags=re.IGNORECASE)[0]
    text = re.sub(r"</?analysis>", "", text, flags=re.IGNORECASE)
    return text.strip()


def _guard_agent_reply(
    reply_text: str,
    *,
    tool_used: bool,
    user_text: str,
    history: list[dict[str, str]],
) -> str:
    sanitized = _sanitize_agent_reply(reply_text)
    if not sanitized:
        return _build_missing_details_prompt(user_text, history)
    if tool_used:
        return sanitized
    if _needs_confirmation_guard(sanitized):
        return _build_missing_details_prompt(user_text, history)
    return sanitized


def _to_dict(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return value.__dict__
    return value


def _message_content(message: Any) -> str:
    msg = _to_dict(message)
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(text)
            return " ".join(parts).strip()
        return (content or "").strip() if isinstance(content, str) else ""
    return ""


def _extract_tool_calls(message: Any) -> list[dict[str, Any]]:
    msg = _to_dict(message)
    if not isinstance(msg, dict):
        return []

    tool_calls = msg.get("tool_calls") or []
    normalized = []
    for call in tool_calls:
        c = _to_dict(call)
        if not isinstance(c, dict):
            continue
        function = _to_dict(c.get("function")) or {}
        name = function.get("name")
        arguments_raw = function.get("arguments") or "{}"
        if not name:
            continue
        try:
            arguments = json.loads(arguments_raw) if isinstance(arguments_raw, str) else arguments_raw
        except json.JSONDecodeError:
            arguments = {}
        normalized.append(
            {
                "id": c.get("id") or f"call_{name}",
                "name": name,
                "arguments": arguments if isinstance(arguments, dict) else {},
            }
        )
    return normalized


def _choice_message(choice: Any) -> Any:
    choice_dict = _to_dict(choice)
    if isinstance(choice_dict, dict):
        return choice_dict.get("message")
    return getattr(choice, "message", None)


def _serialize_assistant_tool_call(message: Any) -> dict[str, Any]:
    msg = _to_dict(message)
    if not isinstance(msg, dict):
        return {"role": "assistant", "content": ""}
    tool_calls = msg.get("tool_calls") or []
    serialized = []
    for call in tool_calls:
        c = _to_dict(call)
        if not isinstance(c, dict):
            continue
        function = _to_dict(c.get("function")) or {}
        serialized.append(
            {
                "id": c.get("id"),
                "type": "function",
                "function": {
                    "name": function.get("name"),
                    "arguments": function.get("arguments", "{}"),
                },
            }
        )
    return {
        "role": "assistant",
        "content": _message_content(msg),
        "tool_calls": serialized,
    }


def _generate_natural_response(action: Any, language: str) -> str:
    """Generate natural language response based on action"""
    try:
        from .hotel_api import check_room, book_room, list_room_details, ROOM_CATALOG
    except ImportError:
        from hotel_api import check_room, book_room, list_room_details, ROOM_CATALOG
    
    if action.action_type == "greet":
        if language == "ta":
            return "வணக்கம், Sunrise Hotel-க்கு வரவேற்கிறோம். உங்கள் check-in தேதி என்ன?"
        return "Hello and welcome to Sunrise Hotel. What is your check-in date?"
    
    if action.action_type == "clarify":
        if language == "ta":
            return "மன்னிக்கவும், தெளிவாக கேட்கவில்லை. மீண்டும் சொல்லுங்கள்."
        return "Sorry, I didn't catch that. Please repeat."
    
    if action.action_type == "ask_slot":
        response = ""
        
        # Acknowledge what was just provided (but not if it's a room type or number being asked for name)
        if action.acknowledged_slot and action.acknowledged_value:
            slot_name = action.acknowledged_slot
            value = action.acknowledged_value
            
            # Don't acknowledge room_type or guests as name
            if slot_name in ["room_type", "guests"] and action.slot_to_ask in ["name", "phone"]:
                pass  # Skip acknowledgment
            elif language == "ta":
                if slot_name == "room_type":
                    response = f"சரி, {value} அறை. "
                elif slot_name == "check_in":
                    response = f"சரி, check-in {value}. "
                elif slot_name == "check_out":
                    response = f"சரி, check-out {value}. "
                elif slot_name == "guests":
                    response = f"சரி, {value} பேர். "
                elif slot_name == "name":
                    response = f"நன்றி {value}. "
                elif slot_name == "phone":
                    response = f"நன்றி, தொலைபேசி எண் பதிவு செய்யப்பட்டது. "
            else:
                if slot_name == "room_type":
                    response = f"Got it, {value} room. "
                elif slot_name == "check_in":
                    response = f"Got it, check-in {value}. "
                elif slot_name == "check_out":
                    response = f"Got it, check-out {value}. "
                elif slot_name == "guests":
                    response = f"Got it, {value} guests. "
                elif slot_name == "name":
                    response = f"Thank you {value}. "
                elif slot_name == "phone":
                    response = f"Thank you, phone number recorded. "
        
        # Ask for next slot
        next_slot = action.slot_to_ask
        if language == "ta":
            if next_slot == "check_in":
                response += "உங்கள் check-in தேதி என்ன?"
            elif next_slot == "check_out":
                response += "உங்கள் check-out தேதி என்ன?"
            elif next_slot == "guests":
                response += "எத்தனை பேர் தங்குவார்கள்?"
            elif next_slot == "room_type":
                response += "எந்த room type வேண்டும்: Standard, Deluxe, Suite, அல்லது Family?"
            elif next_slot == "name":
                response += "உங்கள் பெயர் என்ன?"
            elif next_slot == "phone":
                response += "உங்கள் தொலைபேசி எண்?"
        else:
            if next_slot == "check_in":
                response += "What is your check-in date?"
            elif next_slot == "check_out":
                response += "What is your check-out date?"
            elif next_slot == "guests":
                response += "How many guests?"
            elif next_slot == "room_type":
                response += "Which room type: Standard, Deluxe, Suite, or Family?"
            elif next_slot == "name":
                response += "What is your name?"
            elif next_slot == "phone":
                response += "What is your phone number?"
        
        return response.strip()
    
    if action.action_type == "check_availability":
        state = action.state_summary
        
        # If we already have name and phone, book directly
        if state.get("name") and state.get("phone"):
            result = book_room(
                name=str(state["name"]),
                phone=str(state["phone"]),
                start_date=str(state["check_in"]),
                end_date=str(state["check_out"]),
                guests=int(state["guests"]),
                room_type=str(state["room_type"]),
            )
            
            if result.get("status") == "confirmed":
                conf_num = result.get("confirmation_number", "")
                if language == "ta":
                    return f"உங்கள் முன்பதிவு உறுதி செய்யப்பட்டது! உறுதிப்படுத்தல் எண்: {conf_num}. நன்றி!"
                return f"Your booking is confirmed! Confirmation number: {conf_num}. Thank you!"
            else:
                if language == "ta":
                    return "மன்னிக்கவும், முன்பதிவில் சிக்கல். மீண்டும் முயற்சிக்கவும்."
                return "Sorry, there was an issue with booking. Please try again."
        
        # Check availability first time
        result = check_room(
            start_date=str(state["check_in"]),
            end_date=str(state["check_out"]),
            guests=int(state["guests"]),
            room_type=str(state["room_type"]),
        )
        
        if result.get("status") == "available":
            room_name = str(result['room_type']).title()
            price = result['price']
            if language == "ta":
                return (
                    f"சரி! {room_name} அறை {result['start_date']} முதல் {result['end_date']} வரை "
                    f"{result['guests']} பேருக்கு கிடைக்கிறது. "
                    f"ஒரு இரவுக்கு ரூபாய் {price}. "
                    "உங்கள் பெயர் மற்றும் தொலைபேசி எண்ணை சொல்லுங்கள்."
                )
            return (
                f"Great! {room_name} room is available from {result['start_date']} to {result['end_date']} "
                f"for {result['guests']} guests. "
                f"Price is rupees {price} per night. "
                "Please provide your name and phone number."
            )
        else:
            if language == "ta":
                return "மன்னிக்கவும், அந்த தேதிகளில் கிடைக்கவில்லை. வேறு தேதிகளை முயற்சிக்கவா?"
            return "Sorry, not available for those dates. Would you like to try different dates?"
    
    if action.action_type == "book_room":
        state = action.state_summary
        result = book_room(
            name=str(state["name"]),
            phone=str(state["phone"]),
            start_date=str(state["check_in"]),
            end_date=str(state["check_out"]),
            guests=int(state["guests"]),
            room_type=str(state["room_type"]),
        )
        
        if result.get("status") == "confirmed":
            conf_num = result.get("confirmation_number", "")
            if language == "ta":
                return f"உங்கள் முன்பதிவு உறுதி செய்யப்பட்டது! உறுதிப்படுத்தல் எண்: {conf_num}. நன்றி!"
            return f"Your booking is confirmed! Confirmation number: {conf_num}. Thank you!"
        else:
            if language == "ta":
                return "மன்னிக்கவும், முன்பதிவில் சிக்கல். மீண்டும் முயற்சிக்கவும்."
            return "Sorry, there was an issue with booking. Please try again."
    
    return "How can I help you?"


async def generate_agent_reply(history: list[dict[str, str]], user_text: str) -> str:
    """
    NEW ARCHITECTURE:
    1. Extract intent and slots
    2. Update conversation state
    3. Determine action
    4. Generate natural response (rule-based or LLM-enhanced)
    """
    try:
        from .intent_extractor import IntentSlotExtractor
        from .state_manager import ConversationStateManager
    except ImportError:
        from intent_extractor import IntentSlotExtractor
        from state_manager import ConversationStateManager
    
    # Use global state manager (in production, use session-based)
    if not hasattr(generate_agent_reply, 'state_manager'):
        generate_agent_reply.state_manager = ConversationStateManager()
    
    state_mgr = generate_agent_reply.state_manager
    
    # Step 1: Extract intent and slots
    intent, slots = IntentSlotExtractor.extract(user_text, history)
    print(f"[INTENT] {intent}, SLOTS: {slots}")
    
    # Step 2 & 3: Update state and determine action
    action = state_mgr.process_turn(intent, slots, user_text)
    print(f"[ACTION] {action.action_type}, next_slot: {action.slot_to_ask}")
    
    # Step 4: Generate natural response
    language = slots.get("language", "en")
    response = _generate_natural_response(action, language)
    
    # Reset state after successful booking
    if action.action_type == "book_room":
        state_mgr.reset()
    
    return response


async def generate_agent_reply_llm_fallback(history: list[dict[str, str]], user_text: str) -> str:
    """Fallback to LLM-based generation if needed"""
    runtime = _get_runtime_config()
    api_key = runtime.api_key
    model_name = runtime.model_name
    api_base = runtime.api_base
    tools_enabled = runtime.tools_enabled

    prompt_text = SYSTEM_PROMPT if tools_enabled else NO_TOOL_PROMPT
    if not tools_enabled:
        memory_prompt = _llm_memory_prompt(history, user_text)
        if memory_prompt:
            prompt_text = f"{prompt_text}\n\n{memory_prompt}"
    messages: list[dict[str, Any]] = _normalize_messages(history, user_text, prompt_text)
    tool_used = False

    for _ in range(4):
        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "api_key": api_key,
            "api_base": api_base,
            "temperature": 0.2,
            "max_tokens": 250,
        }
        if tools_enabled:
            payload["tools"] = TOOLS
            payload["tool_choice"] = "auto"

        try:
            response = await asyncio.to_thread(litellm.completion, **payload)
        except litellm.APIConnectionError as e:
            if tools_enabled and _is_tool_call_not_supported_error(e):
                tools_enabled = False
                continue
            raise

        choice = response.choices[0]
        message = _to_dict(_choice_message(choice))
        tool_calls = _extract_tool_calls(message)
        text = _message_content(message)

        if not tools_enabled or not tool_calls:
            final_text = text or "Could you please repeat that?"
            return _guard_agent_reply(final_text, tool_used=tool_used, user_text=user_text, history=history)

        messages.append(_serialize_assistant_tool_call(message))

        for call in tool_calls:
            handler = TOOL_HANDLERS.get(call["name"])
            if handler is None:
                result = {"status": "error", "message": f"Unknown tool: {call['name']}"}
            else:
                try:
                    result = handler(**call["arguments"])
                    tool_used = True
                except Exception as e:
                    result = {"status": "error", "message": str(e)}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "name": call["name"],
                    "content": json.dumps(result),
                }
            )

    return "I could not complete that request yet. Please try once more."
