"""OTP protection: redact anything that looks like a one-time code.

Applied to every transcript before it is logged, stored, shown, or put in a model
prompt. A run of 4–8 digits (Latin, Devanagari or Kannada numerals) or 4+ spoken
digit words in en/hi/kn is replaced with [REDACTED]. IDs like ORD_1024 are left
alone because the digits are glued to a letter/underscore.
"""
from __future__ import annotations

import re

REDACTED = "[REDACTED]"

_DIGIT = r"[0-9०-९೦-೯]"
_DIGIT_RUN = re.compile(rf"(?<![A-Za-z_0-9०-९೦-೯]){_DIGIT}(?:[\s\-.]?{_DIGIT}){{3,7}}(?![0-9०-९೦-೯])")

_DIGIT_WORDS = [
    # English
    "zero", "oh", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    # Hindi romanized
    "shunya", "ek", "do", "teen", "char", "chaar", "paanch", "panch", "chhe", "che", "chhah",
    "saat", "aath", "nau",
    # Hindi Devanagari
    "शून्य", "एक", "दो", "तीन", "चार", "पांच", "पाँच", "छह", "छः", "छे", "सात", "आठ", "नौ",
    # Kannada romanized
    "sonne", "ondu", "eradu", "mooru", "muru", "naalku", "nalku", "aidu", "aaru", "elu", "yelu",
    "entu", "ombattu",
    # Kannada script
    "ಸೊನ್ನೆ", "ಒಂದು", "ಎರಡು", "ಮೂರು", "ನಾಲ್ಕು", "ಐದು", "ಆರು", "ಏಳು", "ಎಂಟು", "ಒಂಬತ್ತು",
]
_WORD_ALT = "|".join(sorted((re.escape(w) for w in _DIGIT_WORDS), key=len, reverse=True))
_WORD_RUN = re.compile(rf"(?<!\w)(?:{_WORD_ALT})(?:[\s,\-]+(?:{_WORD_ALT})){{3,}}(?!\w)", re.IGNORECASE)


def redact_otp(text: str) -> str:
    if not text:
        return text
    text = _DIGIT_RUN.sub(REDACTED, text)
    text = _WORD_RUN.sub(REDACTED, text)
    return text


def contains_otp_like(text: str) -> bool:
    return bool(text) and redact_otp(text) != text


def redact_free_text(obj):
    """Recursively redact every string value in a dict/list structure."""
    if isinstance(obj, str):
        return redact_otp(obj)
    if isinstance(obj, dict):
        return {k: redact_free_text(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_free_text(v) for v in obj]
    return obj
