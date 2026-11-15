"""Turn caption text into what a voice should actually say, per language.

Kannada model: Kannada script only (no digits, no Latin). Hindi Piper voice reads Latin badly.
So times, digits, OTP/AI and the mock address are spelled out in each language.
"""
import re

HI_NUM = ["शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ", "दस", "ग्यारह", "बारह"]
KN_NUM = ["ಸೊನ್ನೆ", "ಒಂದು", "ಎರಡು", "ಮೂರು", "ನಾಲ್ಕು", "ಐದು", "ಆರು", "ಏಳು", "ಎಂಟು", "ಒಂಬತ್ತು", "ಹತ್ತು", "ಹನ್ನೊಂದು", "ಹನ್ನೆರಡು"]
EN_NUM = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]

WORDS = {
    "hi": [("SETU", "सेतु"), ("AI", "ए आई"), ("OTP", "ओ टी पी"), ("Demo Layout", "डेमो लेआउट"), ("Block", "ब्लॉक"),
           ("opposite the blue water tank", "नीली पानी की टंकी के सामने"), ("Hello", "हेलो"), ("Ok", "ओके")],
    "kn": [("SETU", "ಸೇತು"), ("AI", "ಎ ಐ"), ("OTP", "ಒ ಟಿ ಪಿ"), ("Demo Layout", "ಡೆಮೊ ಲೇಔಟ್"), ("Block", "ಬ್ಲಾಕ್"),
           ("opposite the blue water tank", "ನೀಲಿ ನೀರಿನ ಟ್ಯಾಂಕ್ ಎದುರು")],
    "en": [("SETU", "Setu"), ("OTP", "O T P")],
}


def _hi_time(h12, m, pm):
    h24 = (h12 % 12) + (12 if pm else 0)
    period = "सुबह" if h24 < 12 else "दोपहर" if h24 < 16 else "शाम" if h24 < 20 else "रात"
    if m == 30:
        word = {1: "डेढ़", 2: "ढाई"}.get(h12, "साढ़े " + HI_NUM[h12])
    elif m == 15:
        word = "सवा " + HI_NUM[h12]
    elif m == 45:
        word = "पौने " + HI_NUM[h12 % 12 + 1]
    elif m:
        return f"{period} {HI_NUM[h12]} बजकर {m} मिनट"
    else:
        word = HI_NUM[h12]
    return f"{period} {word} बजे"


def _kn_time(h12, m, pm):
    h24 = (h12 % 12) + (12 if pm else 0)
    period = "ಬೆಳಿಗ್ಗೆ" if h24 < 12 else "ಮಧ್ಯಾಹ್ನ" if h24 < 16 else "ಸಂಜೆ" if h24 < 20 else "ರಾತ್ರಿ"
    if m == 30:
        half = ["", "ಒಂದೂವರೆ", "ಎರಡೂವರೆ", "ಮೂರೂವರೆ", "ನಾಲ್ಕೂವರೆ", "ಐದೂವರೆ", "ಆರೂವರೆ", "ಏಳೂವರೆ", "ಎಂಟೂವರೆ",
                "ಒಂಬತ್ತೂವರೆ", "ಹತ್ತೂವರೆ", "ಹನ್ನೊಂದೂವರೆ", "ಹನ್ನೆರಡೂವರೆ"][h12]
        return f"{period} {half} ಗಂಟೆ"
    if m:
        return f"{period} {KN_NUM[h12]} ಗಂಟೆ {digits(str(m), 'kn')} ನಿಮಿಷ"
    return f"{period} {KN_NUM[h12]} ಗಂಟೆ"


def _en_time(h12, m, pm):
    return f"{EN_NUM[h12]}{' thirty' if m == 30 else (' ' + str(m)) if m else ''} {'P M' if pm else 'A M'}"


TIME = re.compile(r"(\d{1,2})(?::(\d{2}))?\s?(AM|PM)")


def digits(s, lang):
    table = {"hi": HI_NUM, "kn": KN_NUM, "en": EN_NUM}[lang]
    return " ".join(table[int(d)] for d in s)


def speakable(text: str, lang: str) -> str:
    t = re.sub(r"\s*\((mock|synthetic)\)", "", text)
    fn = {"hi": _hi_time, "kn": _kn_time, "en": _en_time}[lang]
    t = TIME.sub(lambda m: fn(int(m.group(1)), int(m.group(2) or 0), m.group(3) == "PM"), t)
    if lang == "hi":
        t = t.replace(" बजे – ", " बजे से ")
    elif lang == "kn":
        t = t.replace(" ಗಂಟೆ – ", " ಗಂಟೆಯಿಂದ ").replace("ಗಂಟೆಕ್ಕೆ", "ಗಂಟೆಗೆ")
    else:
        t = t.replace(" – ", " to ")
    for a, b in WORDS[lang]:
        t = re.sub(rf"(?<![A-Za-z]){re.escape(a)}(?![A-Za-z])", b, t, flags=re.I)
    if lang != "en":
        t = re.sub(r"\d+", lambda m: digits(m.group(0), lang), t)
    if lang == "kn":
        t = re.sub(r"[A-Za-z_]+", " ", t)  # the Kannada model has no Latin letters
    t = t.replace("‌", "").replace("‍", "") if lang == "kn" else t
    return re.sub(r"\s+", " ", t).strip()


if __name__ == "__main__":
    for s, l in [("The customer prefers delivery between 6 PM – 8 PM. Can you come then?", "en"),
                 ("ग्राहक 6 PM – 8 PM के बीच डिलीवरी चाहते हैं। क्या आप तब आ सकते हैं?", "hi"),
                 ("ಗ್ರಾಹಕರು 6 PM – 8 PM ನಡುವೆ ಡೆಲಿವರಿ ಬಯಸುತ್ತಾರೆ. ಆಗ ಬರಲು ಸಾಧ್ಯವೇ?", "kn"),
                 ("ನೀವು 6:30 PMಕ್ಕೆ ಡೆಲಿವರಿ ಪ್ರಯತ್ನಿಸುತ್ತೀರಿ ಎಂದು ದಾಖಲಿಸಿದ್ದೇನೆ.", "kn"),
                 ("OTP 739214 है, कन्फर्म करो", "hi"), ("ಪ್ರದೇಶ Demo Layout, Block 4 (mock). ಗುರುತು: opposite the blue water tank (mock).", "kn"),
                 ("नमस्ते, मैं ग्राहक की ओर से जवाब देने वाला एक AI सहायक हूँ।", "hi"), ("I'll come at 6:30", "en")]:
        print(l, "|", speakable(s, l))
