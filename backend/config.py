"""Central configuration. Everything tunable lives in .env (see .env.example)."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _bool(name: str, default: str = "0") -> bool:
    return _env(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    mock_voice: bool = field(default_factory=lambda: _bool("MOCK_VOICE", "1"))
    gnani_api_key: str = field(default_factory=lambda: _env("GNANI_API_KEY"))
    gnani_base_url: str = field(default_factory=lambda: _env("GNANI_BASE_URL", "https://api.vachana.ai"))

    prisma_path: str = field(default_factory=lambda: _env("PRISMA_PATH", "/stt/v3"))
    prisma_model: str = field(default_factory=lambda: _env("PRISMA_MODEL", "prisma-v3.0"))
    prisma_language_code: str = field(default_factory=lambda: _env("PRISMA_LANGUAGE_CODE", "hi-IN,kn-IN,en-IN"))
    prisma_format: str = field(default_factory=lambda: _env("PRISMA_FORMAT", "codemix"))
    prisma_use_keyterms: bool = field(default_factory=lambda: _bool("PRISMA_USE_KEYTERMS", "1"))
    prisma_timeout_s: float = field(default_factory=lambda: float(_env("PRISMA_TIMEOUT_S", "15")))

    timbre_path: str = field(default_factory=lambda: _env("TIMBRE_PATH", "/api/v1/tts/inference"))
    timbre_model: str = field(default_factory=lambda: _env("TIMBRE_MODEL", "timbre-v2.5"))
    timbre_voices: dict = field(default_factory=lambda: {
        "hi": _env("TIMBRE_VOICE_HI", "Nalini"),
        "kn": _env("TIMBRE_VOICE_KN", "Saanvi"),
        "en": _env("TIMBRE_VOICE_EN", "Kaveri"),
    })
    # A second set of voices for the rider in demo playback (Pipecat's timbre-v2.5 voice list).
    timbre_rider_voices: dict = field(default_factory=lambda: {
        "hi": _env("TIMBRE_RIDER_VOICE_HI", "Deepak"),
        "kn": _env("TIMBRE_RIDER_VOICE_KN", "Kavin"),
        "en": _env("TIMBRE_RIDER_VOICE_EN", "Pranav"),
    })
    timbre_sample_rate: int = field(default_factory=lambda: int(_env("TIMBRE_SAMPLE_RATE", "16000")))
    timbre_timeout_s: float = field(default_factory=lambda: float(_env("TIMBRE_TIMEOUT_S", "20")))

    evon_mode: str = field(default_factory=lambda: _env("EVON_MODE", "off").lower())
    evon_local_url: str = field(default_factory=lambda: _env("EVON_LOCAL_URL", "http://127.0.0.1:8001/v1/chat/completions"))
    evon_model_name: str = field(default_factory=lambda: _env("EVON_MODEL_NAME", "gnani/gnani-evon-v3.3-30B-A3B"))
    evon_timeout_s: float = field(default_factory=lambda: float(_env("EVON_TIMEOUT_S", "4")))

    # ---- Real phone calls through Gnani Inya (see docs/phone_call.md) ----
    inya_api_key: str = field(default_factory=lambda: _env("INYA_API_KEY"))
    inya_base_url: str = field(default_factory=lambda: _env("INYA_BASE_URL", "https://api.inya.ai/platform/v1"))
    inya_bot_id: str = field(default_factory=lambda: _env("INYA_BOT_ID"))
    inya_environment: str = field(default_factory=lambda: _env("INYA_ENVIRONMENT", "development"))
    inya_bridge_token: str = field(default_factory=lambda: _env("INYA_BRIDGE_TOKEN"))
    inya_order_id: str = field(default_factory=lambda: _env("INYA_ORDER_ID", "ORD_1024"))
    inya_wait_s: float = field(default_factory=lambda: float(_env("INYA_WAIT_S", "25")))
    call_to_number: str = field(default_factory=lambda: _env("CALL_TO_NUMBER"))
    call_country_code: str = field(default_factory=lambda: _env("CALL_COUNTRY_CODE", "+91"))

    # ---- Live translation between rider and customer (SETU AI interpreter) ----
    # phrases = doorstep phrases only · model = IndicTrans2 only · both = phrases, then the model for the rest
    translate_mode: str = field(default_factory=lambda: _env("TRANSLATE_MODE", "both"))
    translate_model_en_indic: str = field(default_factory=lambda: _env("TRANSLATE_MODEL_EN_INDIC", "ai4bharat/indictrans2-en-indic-dist-200M"))
    translate_model_indic_en: str = field(default_factory=lambda: _env("TRANSLATE_MODEL_INDIC_EN", "ai4bharat/indictrans2-indic-en-dist-200M"))
    translate_model_indic_indic: str = field(default_factory=lambda: _env("TRANSLATE_MODEL_INDIC_INDIC", "ai4bharat/indictrans2-indic-indic-dist-320M"))
    interpret_ring_s: int = field(default_factory=lambda: int(_env("INTERPRET_RING_S", "20")))

    approval_secret: str = field(default_factory=lambda: _env("APPROVAL_SECRET", "dev-only-secret-change-me"))
    approval_ttl_s: int = field(default_factory=lambda: int(_env("APPROVAL_TTL_S", "30")))
    db_path: str = field(default_factory=lambda: str(ROOT / _env("DB_PATH", "data/deliverysaathi.db")))
    phrase_cache_dir: str = field(default_factory=lambda: str(ROOT / _env("PHRASE_CACHE_DIR", "data/phrase_cache")))

    @property
    def voice_live(self) -> bool:
        return (not self.mock_voice) and bool(self.gnani_api_key)


settings = Settings()


class FFmpegMissing(RuntimeError):
    pass


def check_ffmpeg() -> str:
    """Fail loudly and clearly if ffmpeg is not installed."""
    exe = shutil.which("ffmpeg")
    if not exe:
        raise FFmpegMissing(
            "ffmpeg not found on PATH. Install it (Ubuntu: sudo apt install ffmpeg | "
            "macOS: brew install ffmpeg | Windows: winget install ffmpeg) and retry."
        )
    out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=10)
    return out.stdout.splitlines()[0] if out.stdout else "ffmpeg (unknown version)"
