"""Rule-based intent detection. Runs before any model. Deterministic and auditable.

Input should already be OTP-redacted. Rules cover Hindi (Devanagari + romanized),
Kannada (script + romanized) and English, plus common code-mixing.
Priority: request_otp > guard > neighbour > change_address > propose_time
          > ask_availability > ask_address > customer_unavailable > end_call > greeting > unclear
"""
from __future__ import annotations

import re
import unicodedata

from backend.intent.schema import IntentResult

# ---------------------------------------------------------------- language guess
_KN_SCRIPT = re.compile(r"[ಀ-೿]")
_HI_SCRIPT = re.compile(r"[ऀ-ॿ]")
_KN_ROMAN = re.compile(r"\b(illa|beku|ide|idya|mane|maneli|elli|yavaga|yaavaga|sanje|gante|kodli|kodbeka|kodi|"
                       r"helri|heli|banni|barthini|bartini|ondu|eradu|mooru|aaru|ettilla|guru|saar|swalpa|"
                       r"hogi|haaki|kodtini|madi|madbeku|alli|illi)\b")
_HI_ROMAN = re.compile(r"\b(hai|hain|nahi|nahin|kya|kab|baje|ko|de|doon|dun|raha|rahi|bhai|batao|bataiye|"
                       r"karo|kar|aaunga|aaun|aaoon|wala|wali|mein|par|pe|abhi|kaha|kahan|kidhar|ghar|"
                       r"utha|chhod|rakh|saade|sava|paune|shaam)\b")


def guess_language(text: str) -> str:
    if _KN_SCRIPT.search(text):
        return "kn"
    if _HI_SCRIPT.search(text):
        return "hi"
    t = text.lower()
    kn, hi = len(_KN_ROMAN.findall(t)), len(_HI_ROMAN.findall(t))
    if kn > hi and kn > 0:
        return "kn"
    if hi > 0:
        return "hi"
    return "en"


# ---------------------------------------------------------------- time extraction
_NUM_WORDS = {
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    # Hindi romanized + Devanagari
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "che": 6,
    "chhah": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "छे": 6,
    "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12,
    # Kannada romanized + script
    "ondu": 1, "eradu": 2, "mooru": 3, "muru": 3, "naalku": 4, "nalku": 4, "aidu": 5, "aaru": 6,
    "elu": 7, "yelu": 7, "entu": 8, "ombattu": 9, "hattu": 10, "hannondu": 11, "hanneradu": 12,
    "ಒಂದು": 1, "ಎರಡು": 2, "ಮೂರು": 3, "ನಾಲ್ಕು": 4, "ಐದು": 5, "ಆರು": 6, "ಏಳು": 7, "ಎಂಟು": 8,
    "ಒಂಬತ್ತು": 9, "ಹತ್ತು": 10, "ಹನ್ನೊಂದು": 11, "ಹನ್ನೆರಡು": 12,
}
_NUMW = "|".join(sorted((re.escape(w) for w in _NUM_WORDS), key=len, reverse=True))
_HOUR = rf"(\d{{1,2}}|{_NUMW})"
_UNIT = r"(?:baje|बजे|gante|ಗಂಟೆ|ganteg[ae]|ಗಂಟೆಗೆ|o'?\s?clock|pm|am|p\.m\.|a\.m\.)"
_PM = re.compile(r"\b(pm|p\.m\.|evening|night|tonight|shaam|sham|raat)\b|शाम|रात|ಸಂಜೆ|ರಾತ್ರಿ|\bsanje\b|\bratri\b")
_AM = re.compile(r"\b(am|a\.m\.|morning|subah|beligge)\b|सुबह|ಬೆಳಿಗ್ಗೆ")

_P_COLON = re.compile(r"(?<![\d])(\d{1,2})[:.](\d{2})(?!\d)")
_P_HALF_PAST = re.compile(rf"half past {_HOUR}")
_P_SAADE = re.compile(rf"(?:saade|साढ़े|साढे)\s+{_HOUR}")
_P_SAVA = re.compile(rf"(?:sava|सवा)\s+{_HOUR}")
_P_PAUNE = re.compile(rf"(?:paune|पौने)\s+{_HOUR}")
_P_KN_VARE = re.compile(rf"{_HOUR}\s*(?:vare|ವರೆ|ಮುಕ್ಕಾಲು)")
_P_EN_THIRTY = re.compile(rf"{_HOUR}\s+thirty\b")
_P_UNIT = re.compile(rf"{_HOUR}\s*{_UNIT}")
_P_AT = re.compile(rf"\b(?:at|after|by|around|ke baad|के बाद)\s+{_HOUR}\b(?!\s*(?:min|minute|mins|km))")


def _hour(tok: str) -> int | None:
    if tok.isdigit():
        return int(tok)
    return _NUM_WORDS.get(tok)


def extract_time(text: str) -> str | None:
    """Return 'HH:MM' (24h) or None. Unmarked 1–7 are read as PM (delivery hours)."""
    t = text.lower()
    hour = minute = None
    m = _P_COLON.search(t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
    else:
        for pat, mins, delta in ((_P_HALF_PAST, 30, 0), (_P_SAADE, 30, 0), (_P_SAVA, 15, 0),
                                 (_P_PAUNE, 45, -1), (_P_KN_VARE, 30, 0), (_P_EN_THIRTY, 30, 0)):
            m = pat.search(t)
            if m and _hour(m.group(1)) is not None:
                hour, minute = _hour(m.group(1)) + delta, mins
                break
        if hour is None:
            for pat in (_P_UNIT, _P_AT):
                m = pat.search(t)
                if m and _hour(m.group(1)) is not None:
                    hour, minute = _hour(m.group(1)), 0
                    break
    if hour is None or not (0 <= hour <= 23) or not (0 <= minute <= 59):
        return None
    if hour <= 12:
        if _PM.search(t) and hour < 12:
            hour += 12
        elif _AM.search(t):
            hour = 0 if hour == 12 else hour
        elif 1 <= hour <= 7:
            hour += 12
    return f"{hour:02d}:{minute:02d}"


# ---------------------------------------------------------------- intent rules
RULES: list[tuple[str, re.Pattern]] = [
    ("request_otp", re.compile(
        r"\botp\b|o\.\s?t\.\s?p|\bo t p\b|ओटीपी|ओ\.?\s?टी\.?\s?पी|ಒಟಿಪಿ|ಓಟಿಪಿ|ಓ ಟಿ ಪಿ|one.?time.?pass|"
        r"verification code|delivery code|secret code|security code|\bcode\b.{0,15}\b(bata|bolo|do|de|heli|helri|kodi|send|share|tell|give)|"
        r"(bata|bolo|tell|give|share|send|heli).{0,15}\bcode\b|कोड|ಕೋಡ್|\[redacted\]")),
    ("guard_drop_request", re.compile(
        r"guard|security|watchman|gate ?keeper|chowkidar|chaukidar|darwan|reception|चौकीदार|गार्ड|"
        r"सिक्योरिटी|सेक्युरिटी|दरबान|वॉचमैन|वाचमैन|वॉचमेन|ವಾಚ್ ?ಮನ್|ವಾಚ್ ?ಮೆನ್|ಗಾರ್ಡ್|ಸೆಕ್ಯುರಿಟಿ|ಸೆಕ್ಯೂರಿಟಿ")),
    ("neighbor_drop_request", re.compile(
        r"neighbou?r|next door|padosi|padosan|padosi|पड़ोस|पडोस|ಪಕ್ಕದ ?ಮನೆ|pakkad?a ?mane|nerehore|ನೆರೆಹೊರೆ")),
    ("change_address", re.compile(
        r"\b(change|different|new|another|other) (the )?address|address (change|badal|bere)|pata badal|"
        r"पता बदल|दूसरे पते|दूसरा पता|ವಿಳಾಸ ಬದಲ|vilasa badal|ಬೇರೆ ವಿಳಾಸ|bere vilasa|"
        r"deliver (it )?to (my |the )?office|office (pe|par|me|mein|ge) (de|deliver|bhej|kodi)")),
    ("ask_availability", re.compile(
        r"when (will|is|can|are)|what time|(?<!not )\bavailable\b|kab (aa|mil|ghar|free|ho|rah|tak|lo|le)|"
        r"कब|ಯಾವಾಗ|yaa?vaga|free (kab|time)|ಎಷ್ಟು ಗಂಟೆಗೆ|eshtu gantege|kitne baje")),
    ("ask_address", re.compile(
        r"address|location|landmark|where (is|exactly|do)|which (building|floor|gate|block|tower)|"
        r"\bkahan\b|\bkahaan\b|\bkaha\b|\bkidhar\b|किधर|कहाँ|कहां|पता (क्या|बताओ|बताइए|भेजो)|"
        r"pata (kya|batao|bhejo|bataiye)|ಎಲ್ಲಿ|\belli\b|ವಿಳಾಸ|\bvilasa\b|लोकेशन|ಲೊಕೇಶನ್|lokeshan")),
    ("customer_unavailable", re.compile(
        r"not (picking|answering|responding|reachable|available|home)|no(t)? answer|switch(ed)? ?off|"
        r"स्विच ऑफ|ಸ್ವಿಚ್ ಆಫ್|"
        r"(phone|call) (nahi|nahin|nai) (utha|lag|le)|nahi utha|nahin utha|फ़ोन नहीं|फोन नहीं|"
        r"कॉल नहीं|नहीं उठा|ಫೋನ್ (ತೆಗೆಯುತ್ತಿಲ್ಲ|ಎತ್ತುತ್ತಿಲ್ಲ|ಎತ್ತಿಲ್ಲ|ತೆಗೆದಿಲ್ಲ)|"
        r"phone (ettilla|ettuttilla|etthilla|tegeyuttilla|tegithilla|tagolta illa)|"
        r"ghar (pe|par) (koi )?nahi|ಮನೆಯಲ್ಲಿ ಯಾರೂ ಇಲ್ಲ|maneli yaaru? illa|door (nahi|not) open|"
        r"darwaza (nahi|nahin) khol|nobody (is )?(home|there)|"
        # rider has arrived and is waiting
        r"(at|outside|near) the (gate|door|building)|i'?m (here|outside|downstairs)|i have (arrived|reached)|"
        r"\b(gate|ghar|building) (pe|par|ke bahar|ke paas) (hoon|hu|khada|aa gaya)|bahar khada|pahunch gaya|"
        r"गेट (पे|पर)|बाहर खड़ा|पहुँच गया|पहुंच गया|ಗೇಟ್ (ಹತ್ತಿರ|ಬಳಿ)|ಬಂದಿದ್ದೀನಿ|ಬಂದಿದ್ದೇನೆ|"
        r"gate hathra|bandidini|bandiddini")),
    ("greeting", re.compile(
        r"\b(hello|hallo|helo|hi|hey|namaste|namaskar|namaskara)\b|\bhaan ?ji\b|who is (this|speaking)|"
        r"can you hear me|kaun bol|ಹಲೋ|हेलो|हैलो|नमस्ते|ನಮಸ್ಕಾರ|ಯಾರು ಮಾತಾಡ|कौन बोल|yaaru matad")),
    ("end_call", re.compile(
        r"\b(thank ?you|thanks|thank u|bye|goodbye|dhanyavaad|dhanyavad|dhanyawad|shukriya|thanku)\b|"
        r"धन्यवाद|शुक्रिया|थैंक|बाय|ಧನ್ಯವಾದ|ಥ್ಯಾಂಕ್|ಬೈ|\b(rakhta|rakhti) (hoon|hu)\b|फ़ोन रखता|फोन रखता|"
        r"ಫೋನ್ ಇಡ್ತೀನಿ|phone idtini")),
]

_INJECTION = re.compile(
    r"ignore (your|all|the|previous|any)? ?(rules|instructions|policy|prompt)|you are now|"
    r"system prompt|developer mode|override|pretend (you|to)|act as|forget (your|the) (rules|instructions)|"
    r"नियम (भूल|छोड़|तोड़)|rules (bhool|chhod|tod)|ನಿಯಮ (ಮರೆ|ಬಿಡಿ)")


def _normalize(text: str) -> str:
    t = unicodedata.normalize("NFC", text or "").lower()
    t = t.replace("\u200c", "").replace("\u200d", "")  # ZWNJ / ZWJ: invisible joiners common in Kannada
    t = re.sub(r"[“”\"!?,;()]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def classify(text: str, language_hint: str | None = None) -> tuple[IntentResult, dict]:
    """Return (IntentResult, flags). flags: injection (bool), otp_rule (bool)."""
    t = _normalize(text)
    lang = language_hint if language_hint in ("hi", "kn", "en") else guess_language(t)
    flags = {"injection": bool(_INJECTION.search(t)), "otp_rule": False}
    if not t:
        return IntentResult("unclear", None, lang, "fast_path", []), flags

    fired = [name for name, pat in RULES if pat.search(t)]
    time = extract_time(t)

    if "request_otp" in fired:
        flags["otp_rule"] = True
        return IntentResult("request_otp", None, lang, "fast_path", fired), flags
    for name in ("guard_drop_request", "neighbor_drop_request", "change_address"):
        if name in fired:
            return IntentResult(name, None, lang, "fast_path", fired), flags
    if time:
        return IntentResult("propose_time", time, lang, "fast_path", fired + ["time"]), flags
    for name in ("ask_availability", "ask_address", "customer_unavailable", "end_call", "greeting"):
        if name in fired:
            return IntentResult(name, None, lang, "fast_path", fired), flags
    return IntentResult("unclear", None, lang, "fast_path", fired), flags


# Speech engines differ in how they encode Indic letters (e.g. ड़ as one code point or two).
# Text is NFC-normalised in classify(); normalise every pattern the same way.
def _nfc(p: re.Pattern) -> re.Pattern:
    return re.compile(unicodedata.normalize("NFC", p.pattern), p.flags)


RULES = [(n, _nfc(p)) for n, p in RULES]
_INJECTION = _nfc(_INJECTION)
_PM, _AM = _nfc(_PM), _nfc(_AM)
_P_HALF_PAST, _P_SAADE, _P_SAVA, _P_PAUNE = map(_nfc, (_P_HALF_PAST, _P_SAADE, _P_SAVA, _P_PAUNE))
_P_KN_VARE, _P_EN_THIRTY, _P_UNIT, _P_AT = map(_nfc, (_P_KN_VARE, _P_EN_THIRTY, _P_UNIT, _P_AT))
