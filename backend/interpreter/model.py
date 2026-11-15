"""Optional free (word-for-word) translation with AI4Bharat IndicTrans2, run locally on your laptop.

Used only for sentences the doorstep phrases don't recognise (TRANSLATE_MODE=both, the default), or for
everything (TRANSLATE_MODE=model). If the libraries or the model weights are missing, available() is False
and SETU AI keeps working with phrases only.

Install once (about 1-2 GB download on first use, runs on CPU):
    pip install -r requirements-translate.txt
Models (Hugging Face): ai4bharat/indictrans2-en-indic-dist-200M, ai4bharat/indictrans2-indic-en-dist-200M,
ai4bharat/indictrans2-indic-indic-dist-320M.

Limits: IndicTrans2 expects Hindi in Devanagari and Kannada in Kannada script. Hinglish typed in English
letters ("guard ko de do") is handled by the phrases, not by this model.
"""
from __future__ import annotations

import logging
import re
import threading

log = logging.getLogger("setu.translate")

CODES = {"en": "eng_Latn", "hi": "hin_Deva", "kn": "kan_Knda"}
_LATIN = re.compile(r"[A-Za-z]")
_INDIC = re.compile(r"[ऀ-ॿಀ-೿]")


class IndicTrans2:
    def __init__(self, settings):
        self.s = settings
        self._lock = threading.Lock()
        self._loaded: dict[str, tuple] = {}
        self._proc = None
        self.error: str | None = None
        self._libs_ok: bool | None = None

    # -------------------------------------------------- availability
    def available(self) -> bool:
        if self.s.translate_mode == "phrases":
            return False
        if self._libs_ok is None:
            try:
                import torch  # noqa: F401
                import transformers  # noqa: F401
                self._processor_cls()
                self._libs_ok = True
            except Exception as e:  # not installed: phrases only
                self._libs_ok, self.error = False, f"translation model not installed ({type(e).__name__})"
        return bool(self._libs_ok)

    @staticmethod
    def _processor_cls():
        try:
            from IndicTransToolkit.processor import IndicProcessor   # IndicTransToolkit >= 1.0.3
        except ImportError:
            from IndicTransToolkit import IndicProcessor              # older releases
        return IndicProcessor

    def _model_name(self, src: str, tgt: str) -> str:
        if src == "en":
            return self.s.translate_model_en_indic
        if tgt == "en":
            return self.s.translate_model_indic_en
        return self.s.translate_model_indic_indic

    def _load(self, name: str):
        if name not in self._loaded:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            log.info("loading %s (first use downloads it)", name)
            tok = AutoTokenizer.from_pretrained(name, trust_remote_code=True)
            model = AutoModelForSeq2SeqLM.from_pretrained(name, trust_remote_code=True)
            model.eval()
            self._loaded[name] = (tok, model)
        if self._proc is None:
            self._proc = self._processor_cls()(inference=True)
        return self._loaded[name]

    def warm(self) -> None:
        """Load the models in the background at startup so the first call isn't slow."""
        if not self.available():
            return
        try:
            with self._lock:
                for src, tgt in (("en", "kn"), ("kn", "en"), ("hi", "kn")):
                    self._load(self._model_name(src, tgt))
        except Exception as e:
            self.error = f"could not load translation model: {e}"
            log.warning(self.error)

    # -------------------------------------------------- translate
    def supports(self, text: str, src: str) -> bool:
        if src in ("hi", "kn"):
            return bool(_INDIC.search(text))      # romanised Hindi/Kannada: not for this model
        return bool(_LATIN.search(text))

    def translate(self, text: str, src: str, tgt: str) -> str | None:
        if src == tgt or src not in CODES or tgt not in CODES or not self.available() or not self.supports(text, src):
            return None
        try:
            import torch
            with self._lock:
                tok, model = self._load(self._model_name(src, tgt))
                batch = self._proc.preprocess_batch([text], src_lang=CODES[src], tgt_lang=CODES[tgt])
                inputs = tok(batch, truncation=True, padding="longest", return_tensors="pt",
                             return_attention_mask=True)
                with torch.no_grad():
                    out = model.generate(**inputs, use_cache=True, min_length=0, max_length=256, num_beams=5,
                                         num_return_sequences=1)
                dec = tok.batch_decode(out, skip_special_tokens=True, clean_up_tokenization_spaces=True)
                res = self._proc.postprocess_batch(dec, lang=CODES[tgt])
            return (res[0] if res else "").strip() or None
        except Exception as e:
            self.error = f"translation failed: {e}"
            log.warning(self.error)
            return None
