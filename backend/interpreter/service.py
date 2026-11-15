"""SETU AI translation service: one sentence from one speaker, into the listener's language.

Order (TRANSLATE_MODE=both, default):
  1. mask OTP-like numbers (never translated, never stored)
  2. doorstep phrases: exact, reviewed sentences for what riders and customers say at a delivery
  3. if nothing matched: the IndicTrans2 model, when installed on this machine
  4. otherwise: say so honestly; the listener sees the original words
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from backend.engine.otp_guard import contains_otp_like, redact_otp
from backend.intent.fast_path import guess_language
from backend.interpreter import phrases
from backend.interpreter.model import IndicTrans2

UNTRANSLATED = {"en": "(SETU could not translate this sentence. Original words shown.)",
                "hi": "(SETU इस वाक्य का अनुवाद नहीं कर सका। मूल शब्द दिखाए गए हैं।)",
                "kn": "(SETU ಈ ವಾಕ್ಯವನ್ನು ಅನುವಾದಿಸಲು ಆಗಲಿಲ್ಲ. ಮೂಲ ಪದಗಳನ್ನು ತೋರಿಸಲಾಗಿದೆ.)"}


@dataclass
class Translation:
    original: str                 # what was said, OTP-masked
    src_lang: str
    tgt_lang: str
    text: str                     # what the listener hears / reads ("" when untranslated)
    method: str                   # same_language | phrases | model | untranslated
    meanings: list[str] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)       # spoken one by one (each fixed sentence has a recording)
    notes: list[str] = field(default_factory=list)      # SETU's own safety notes, in the listener's language
    masked_number: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class Translator:
    def __init__(self, settings):
        self.s = settings
        self.model = IndicTrans2(settings)

    def status(self) -> dict:
        avail = self.model.available()
        return {"mode": self.s.translate_mode, "phrases": self.s.translate_mode != "model",
                "model_available": avail, "model_error": None if avail else self.model.error,
                "languages": list(phrases.LANGS)}

    def translate(self, text: str, speaker: str, src: str | None, tgt: str, gender: str = "m") -> Translation:
        masked = contains_otp_like(text or "")
        original = redact_otp((text or "").strip())[:500]
        src = src if src in phrases.LANGS else guess_language(original.lower())
        tgt = tgt if tgt in phrases.LANGS else "en"
        notes: list[str] = []
        if masked:
            notes.append(phrases.NOTES["number_hidden"][tgt])

        if src == tgt:
            out = Translation(original, src, tgt, original, "same_language", parts=[original], notes=notes,
                              masked_number=masked)
        else:
            out = None
            if self.s.translate_mode in ("phrases", "both"):
                r = phrases.translate(original, speaker, tgt, gender)
                if r.ok:
                    out = Translation(original, src, tgt, r.text, "phrases", r.meanings, r.parts, notes, masked)
            if out is None and self.s.translate_mode in ("model", "both"):
                t = self.model.translate(original, src, tgt)
                if t:
                    out = Translation(original, src, tgt, t, "model", [], [t], notes, masked)
            if out is None:
                notes.append(UNTRANSLATED[tgt])
                out = Translation(original, src, tgt, "", "untranslated", [], [], notes, masked)

        # The OTP rule holds in every mode: whoever mentions it, the customer is reminded.
        if "otp" in out.meanings or phrases._RX["otp"].search(original.lower()):
            if "otp" not in out.meanings:
                out.meanings.append("otp")
            note = phrases.NOTES["otp_to_customer"][tgt]
            if speaker == "rider" and note not in out.notes:
                out.notes.append(note)
        return out
