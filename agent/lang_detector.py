"""
Language detection utility for English, Tamil (தமிழ்), and Tanglish.
Detects user language preference and conversational script.
"""
import re
from typing import Tuple

# Unicode range for Tamil script: U+0B80 to U+0BFF
TAMIL_CHAR_RE = re.compile(r"[\u0B80-\u0BFF]")

TANGLISH_MARKERS = {
    "vanakkam", "enna", "irukku", "venum", "kedaikkuma", "romba",
    "mudiyuma", "eppadi", "ungalukku", "nalla", "eppo", "kaala",
    "neram", "evvalavu", "panradhu", "theva", "aama", "seri", "illai",
    "solunga", "pannalam", "irukkaa", "panna", "la", "nu", "inga",
    "vara", "poren", "tanglish"
}


def detect_language(text: str) -> Tuple[str, float]:
    """
    Detect whether text is Tamil (ta-IN), Tanglish, or English (en-IN).
    Returns (language_code, confidence).
    """
    if not text or not text.strip():
        return "en-IN", 1.0

    clean_text = text.strip()
    lower_text = clean_text.lower()

    # 1. Check explicit language choice keywords
    if any(w in lower_text.split() for w in ["tamil", "tamizh"]) or "தமிழ்" in clean_text:
        return "ta-IN", 1.0

    if "tanglish" in lower_text or "தங்கிலீஷ்" in clean_text:
        return "tanglish", 1.0

    if "english" in lower_text and not any(m in lower_text for m in ["tanglish", "tamil"]):
        return "en-IN", 1.0

    # 2. Check for Tamil script presence
    tamil_chars = len(TAMIL_CHAR_RE.findall(clean_text))
    total_chars = max(len(re.findall(r"\w", clean_text)), 1)
    tamil_ratio = tamil_chars / total_chars

    if tamil_chars >= 2 or tamil_ratio > 0.15:
        return "ta-IN", min(0.7 + tamil_ratio, 1.0)

    # 3. Check for Tanglish romanized words
    words = re.findall(r"[a-zA-Z]+", lower_text)
    if not words:
        return "en-IN", 1.0

    tanglish_matches = sum(1 for w in words if w in TANGLISH_MARKERS)
    tanglish_ratio = tanglish_matches / len(words)

    if tanglish_matches >= 2 or tanglish_ratio >= 0.25 or (tanglish_matches >= 1 and len(words) <= 3):
        return "tanglish", min(0.6 + tanglish_ratio, 1.0)

    return "en-IN", 0.95

