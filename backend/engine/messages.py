"""Fixed message templates. No model ever writes or rewrites these.

Rider replies: hi / kn / en. Customer messages: en / kn.
Every Kannada (and Hindi) string is a draft listed in REVIEW.md under NEEDS NATIVE REVIEW.

Customer messages are chosen from the ledger: each template declares the evidence
level it needs. If the ledger does not contain that evidence, the message is
downgraded to a safe "nothing confirmed" template. That is the Never-Lie rule.
"""
from __future__ import annotations

from backend.engine.ledger import EVIDENCE_RANK

LANGS = ("hi", "kn", "en")

RIDER = {
    "greeting": {
        "en": "Hello, this is an AI assistant answering for the customer. This call is simulated. How can I help?",
        "hi": "नमस्ते, मैं ग्राहक की ओर से जवाब देने वाला एक AI सहायक हूँ। यह कॉल सिम्युलेटेड है। बताइए, क्या मदद करूँ?",
        "kn": "ನಮಸ್ಕಾರ, ನಾನು ಗ್ರಾಹಕರ ಪರವಾಗಿ ಉತ್ತರಿಸುತ್ತಿರುವ AI ಸಹಾಯಕ. ಇದು ಸಿಮ್ಯುಲೇಟೆಡ್ ಕರೆ. ಹೇಳಿ, ಏನು ಸಹಾಯ ಬೇಕು?",
    },
    "listening": {
        "en": "Yes, I can hear you. I am an AI assistant answering for the customer. How can I help?",
        "hi": "जी हाँ, मैं सुन रहा हूँ। मैं ग्राहक की ओर से AI सहायक हूँ। बताइए, क्या मदद करूँ?",
        "kn": "ಹೌದು, ಕೇಳಿಸುತ್ತಿದೆ. ನಾನು ಗ್ರಾಹಕರ ಪರವಾಗಿ ಮಾತನಾಡುತ್ತಿರುವ AI ಸಹಾಯಕ. ಹೇಳಿ, ಏನು ಸಹಾಯ ಬೇಕು?",
    },
    "goodbye": {
        "en": "Thank you. This call has been recorded for the customer. Goodbye.",
        "hi": "धन्यवाद। इस कॉल की जानकारी ग्राहक के लिए दर्ज कर ली गई है। नमस्ते।",
        "kn": "ಧನ್ಯವಾದಗಳು. ಈ ಕರೆಯ ವಿವರಗಳನ್ನು ಗ್ರಾಹಕರಿಗಾಗಿ ದಾಖಲಿಸಲಾಗಿದೆ. ನಮಸ್ಕಾರ.",
    },
    "holding": {
        "en": "I am checking with the customer. Please wait briefly.",
        "hi": "मैं ग्राहक से पूछ रहा हूँ। कृपया थोड़ा रुकिए।",
        "kn": "ನಾನು ಗ್ರಾಹಕರನ್ನು ಕೇಳುತ್ತಿದ್ದೇನೆ. ದಯವಿಟ್ಟು ಸ್ವಲ್ಪ ಕಾಯಿರಿ.",
    },
    "ask_repeat": {
        "en": "Sorry, I did not catch that. Please say it once more.",
        "hi": "माफ़ कीजिए, मैं समझ नहीं पाया। कृपया एक बार फिर बोलिए।",
        "kn": "ಕ್ಷಮಿಸಿ, ನನಗೆ ಅರ್ಥವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಇನ್ನೊಮ್ಮೆ ಹೇಳಿ.",
    },
    "choose_language": {
        "en": "Please speak in Hindi, Kannada or English.",
        "hi": "कृपया हिंदी, कन्नड़ या अंग्रेज़ी में बोलिए।",
        "kn": "ದಯವಿಟ್ಟು ಹಿಂದಿ, ಕನ್ನಡ ಅಥವಾ ಇಂಗ್ಲಿಷ್‌ನಲ್ಲಿ ಮಾತನಾಡಿ.",
    },
    "otp_refused": {
        "en": "I cannot share or ask for any OTP. Please do not ask for it.",
        "hi": "मैं कोई भी OTP न बता सकता हूँ, न माँग सकता हूँ। कृपया OTP न माँगें।",
        "kn": "ನಾನು ಯಾವುದೇ OTP ಹೇಳಲು ಅಥವಾ ಕೇಳಲು ಸಾಧ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು OTP ಕೇಳಬೇಡಿ.",
    },
    "customer_unavailable": {
        "en": "The customer is busy right now. I can help. Their preferred time is {window}. What would you like to do?",
        "hi": "ग्राहक अभी व्यस्त हैं। मैं मदद कर सकता हूँ। उनका पसंदीदा समय {window} है। आप क्या करना चाहेंगे?",
        "kn": "ಗ್ರಾಹಕರು ಈಗ ಬ್ಯುಸಿ ಇದ್ದಾರೆ. ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ. ಅವರ ಇಷ್ಟದ ಸಮಯ {window}. ನೀವು ಏನು ಮಾಡಲು ಬಯಸುತ್ತೀರಿ?",
    },
    "availability": {
        "en": "The customer prefers delivery between {window}. Can you come then?",
        "hi": "ग्राहक {window} के बीच डिलीवरी चाहते हैं। क्या आप तब आ सकते हैं?",
        "kn": "ಗ್ರಾಹಕರು {window} ನಡುವೆ ಡೆಲಿವರಿ ಬಯಸುತ್ತಾರೆ. ಆಗ ಬರಲು ಸಾಧ್ಯವೇ?",
    },
    "rider_agreed": {
        "en": "Noted that you will attempt delivery at {time}. This is your commitment; the platform has not confirmed a slot.",
        "hi": "नोट कर लिया कि आप {time} पर डिलीवरी की कोशिश करेंगे। यह आपकी तरफ़ से है; प्लेटफ़ॉर्म ने स्लॉट पक्का नहीं किया है।",
        "kn": "ನೀವು {time}ಕ್ಕೆ ಡೆಲಿವರಿ ಪ್ರಯತ್ನಿಸುತ್ತೀರಿ ಎಂದು ದಾಖಲಿಸಿದ್ದೇನೆ. ಇದು ನಿಮ್ಮ ಮಾತು; ಪ್ಲಾಟ್‌ಫಾರ್ಮ್ ಸ್ಲಾಟ್ ಖಚಿತಪಡಿಸಿಲ್ಲ.",
    },
    "time_approved": {
        "en": "The customer approved {time}. Please attempt delivery then. The platform has not confirmed a slot.",
        "hi": "ग्राहक ने {time} की अनुमति दी है। कृपया तभी डिलीवरी की कोशिश करें। प्लेटफ़ॉर्म ने स्लॉट पक्का नहीं किया है।",
        "kn": "ಗ್ರಾಹಕರು {time}ಕ್ಕೆ ಒಪ್ಪಿದ್ದಾರೆ. ದಯವಿಟ್ಟು ಆಗ ಡೆಲಿವರಿ ಪ್ರಯತ್ನಿಸಿ. ಪ್ಲಾಟ್‌ಫಾರ್ಮ್ ಸ್ಲಾಟ್ ಖಚಿತಪಡಿಸಿಲ್ಲ.",
    },
    "handover_ok": {
        "en": "The customer approved leaving it with the {who}. The request is recorded. Please hand it over.",
        "hi": "ग्राहक ने {who} को देने की अनुमति दी है। रिक्वेस्ट दर्ज हो गई है। कृपया उन्हें दे दीजिए।",
        "kn": "ಗ್ರಾಹಕರು {who} ಅವರಿಗೆ ಕೊಡಲು ಒಪ್ಪಿದ್ದಾರೆ. ವಿನಂತಿ ದಾಖಲಾಗಿದೆ. ದಯವಿಟ್ಟು ಅವರಿಗೆ ಕೊಡಿ.",
    },
    "handover_provider_failed": {
        "en": "The customer approved it, but the delivery system did not accept the request. Please do not hand it over yet. Try again between {window}.",
        "hi": "ग्राहक ने अनुमति दी, लेकिन डिलीवरी सिस्टम ने रिक्वेस्ट स्वीकार नहीं की। अभी किसी को मत दीजिए। कृपया {window} के बीच फिर आइए।",
        "kn": "ಗ್ರಾಹಕರು ಒಪ್ಪಿದರು, ಆದರೆ ಡೆಲಿವರಿ ವ್ಯವಸ್ಥೆ ವಿನಂತಿಯನ್ನು ಸ್ವೀಕರಿಸಲಿಲ್ಲ. ಈಗ ಯಾರಿಗೂ ಕೊಡಬೇಡಿ. ದಯವಿಟ್ಟು {window} ನಡುವೆ ಮತ್ತೆ ಬನ್ನಿ.",
    },
    "handover_refused_verified": {
        "en": "This order needs verification at handover, so it cannot be left with anyone else. Please try again between {window}.",
        "hi": "इस ऑर्डर में डिलीवरी के समय वेरिफिकेशन ज़रूरी है, इसलिए इसे किसी और को नहीं दे सकते। कृपया {window} के बीच फिर आइए।",
        "kn": "ಈ ಆರ್ಡರ್‌ಗೆ ಹಸ್ತಾಂತರದ ವೇಳೆ ಪರಿಶೀಲನೆ ಬೇಕು, ಆದ್ದರಿಂದ ಬೇರೆಯವರಿಗೆ ಕೊಡಲು ಸಾಧ್ಯವಿಲ್ಲ. ದಯವಿಟ್ಟು {window} ನಡುವೆ ಮತ್ತೆ ಬನ್ನಿ.",
    },
    "declined": {
        "en": "The customer did not allow that. Please try again between {window}.",
        "hi": "ग्राहक ने इसकी अनुमति नहीं दी। कृपया {window} के बीच फिर आइए।",
        "kn": "ಗ್ರಾಹಕರು ಇದಕ್ಕೆ ಅನುಮತಿ ನೀಡಿಲ್ಲ. ದಯವಿಟ್ಟು {window} ನಡುವೆ ಮತ್ತೆ ಬನ್ನಿ.",
    },
    "contact_later": {
        "en": "The customer will contact you later. Nothing is confirmed now.",
        "hi": "ग्राहक आपसे बाद में संपर्क करेंगे। अभी कुछ पक्का नहीं है।",
        "kn": "ಗ್ರಾಹಕರು ನಿಮ್ಮನ್ನು ನಂತರ ಸಂಪರ್ಕಿಸುತ್ತಾರೆ. ಈಗ ಏನೂ ಖಚಿತವಾಗಿಲ್ಲ.",
    },
    "unresolved_fallback": {
        "en": "I could not get the customer's answer in time. Their preferred time is {window}. Nothing else is confirmed.",
        "hi": "ग्राहक से समय पर जवाब नहीं मिला। उनका पसंदीदा समय {window} है। इसके अलावा कुछ पक्का नहीं है।",
        "kn": "ಸಮಯಕ್ಕೆ ಗ್ರಾಹಕರಿಂದ ಉತ್ತರ ಸಿಗಲಿಲ್ಲ. ಅವರ ಇಷ್ಟದ ಸಮಯ {window}. ಬೇರೆ ಏನೂ ಖಚಿತವಾಗಿಲ್ಲ.",
    },
    "address": {
        "en": "The area is {area}. Landmark: {landmark}.",
        "hi": "इलाका {area} है। लैंडमार्क: {landmark}।",
        "kn": "ಪ್ರದೇಶ {area}. ಗುರುತು: {landmark}.",
    },
    "address_change_ok": {
        "en": "The customer approved the address change and the request was recorded. Wait until your app shows the new address.",
        "hi": "ग्राहक ने पता बदलने की अनुमति दी और रिक्वेस्ट दर्ज हुई। ऐप में नया पता दिखने तक रुकिए।",
        "kn": "ಗ್ರಾಹಕರು ವಿಳಾಸ ಬದಲಾವಣೆಗೆ ಒಪ್ಪಿದ್ದಾರೆ ಮತ್ತು ವಿನಂತಿ ದಾಖಲಾಗಿದೆ. ಆ್ಯಪ್‌ನಲ್ಲಿ ಹೊಸ ವಿಳಾಸ ಕಾಣುವವರೆಗೆ ಕಾಯಿರಿ.",
    },
    "escalated": {
        "en": "I cannot handle this safely. The customer has been informed. Please contact your support team.",
        "hi": "मैं इसे सुरक्षित तरीके से नहीं संभाल सकता। ग्राहक को बता दिया गया है। कृपया अपनी सपोर्ट टीम से संपर्क करें।",
        "kn": "ಇದನ್ನು ನಾನು ಸುರಕ್ಷಿತವಾಗಿ ನಿರ್ವಹಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ. ಗ್ರಾಹಕರಿಗೆ ತಿಳಿಸಲಾಗಿದೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಸಪೋರ್ಟ್ ತಂಡವನ್ನು ಸಂಪರ್ಕಿಸಿ.",
    },
}

CUSTOMER = {
    "rider_called": {
        "en": "A rider called about your order. Nothing is confirmed yet.",
        "kn": "ನಿಮ್ಮ ಆರ್ಡರ್ ಬಗ್ಗೆ ರೈಡರ್ ಕರೆ ಮಾಡಿದ್ದಾರೆ. ಇನ್ನೂ ಏನೂ ಖಚಿತವಾಗಿಲ್ಲ.",
    },
    "approval_requested": {
        "en": "The rider is asking: {request}. Choose Approve, Do not allow, or Contact me later. Nothing is confirmed yet.",
        "kn": "ರೈಡರ್ ಕೇಳುತ್ತಿದ್ದಾರೆ: {request}. ಒಪ್ಪಿಗೆ, ಅನುಮತಿಸಬೇಡಿ ಅಥವಾ ನಂತರ ಸಂಪರ್ಕಿಸಿ ಆಯ್ಕೆಮಾಡಿ. ಇನ್ನೂ ಏನೂ ಖಚಿತವಾಗಿಲ್ಲ.",
    },
    "otp_refused": {
        "en": "The rider asked for an OTP. The agent refused. Nothing was shared or confirmed.",
        "kn": "ರೈಡರ್ OTP ಕೇಳಿದರು. ಏಜೆಂಟ್ ನಿರಾಕರಿಸಿತು. ಏನನ್ನೂ ಹಂಚಿಕೊಂಡಿಲ್ಲ ಅಥವಾ ಖಚಿತಪಡಿಸಿಲ್ಲ.",
    },
    "rider_agreed_time": {
        "en": "The rider agreed to attempt delivery at {time}. The delivery platform has not confirmed a new slot.",
        "kn": "ರೈಡರ್ {time}ಕ್ಕೆ ಡೆಲಿವರಿ ಪ್ರಯತ್ನಿಸಲು ಒಪ್ಪಿದ್ದಾರೆ. ಡೆಲಿವರಿ ಪ್ಲಾಟ್‌ಫಾರ್ಮ್ ಹೊಸ ಸ್ಲಾಟ್ ಖಚಿತಪಡಿಸಿಲ್ಲ.",
    },
    "time_approved": {
        "en": "You approved a delivery attempt at {time}. The rider was told. The delivery platform has not confirmed a new slot.",
        "kn": "ನೀವು {time}ಕ್ಕೆ ಡೆಲಿವರಿ ಪ್ರಯತ್ನಕ್ಕೆ ಒಪ್ಪಿಗೆ ನೀಡಿದ್ದೀರಿ. ರೈಡರ್‌ಗೆ ತಿಳಿಸಲಾಗಿದೆ. ಡೆಲಿವರಿ ಪ್ಲಾಟ್‌ಫಾರ್ಮ್ ಹೊಸ ಸ್ಲಾಟ್ ಖಚಿತಪಡಿಸಿಲ್ಲ.",
    },
    "handover_provider_accepted": {
        "en": "Your {who} handover was approved. The simulated delivery provider accepted the request. Delivery completion has not yet been recorded.",
        "kn": "ನಿಮ್ಮ {who} ಹಸ್ತಾಂತರಕ್ಕೆ ಒಪ್ಪಿಗೆ ದೊರೆತಿದೆ. ಸಿಮ್ಯುಲೇಟೆಡ್ ಡೆಲಿವರಿ ಪೂರೈಕೆದಾರರು ವಿನಂತಿಯನ್ನು ಸ್ವೀಕರಿಸಿದ್ದಾರೆ. ಡೆಲಿವರಿ ಪೂರ್ಣಗೊಂಡಿರುವುದು ಇನ್ನೂ ದಾಖಲಾಗಿಲ್ಲ.",
    },
    "handover_provider_failed": {
        "en": "Your {who} handover was approved, but the simulated delivery provider did not accept the request. The rider was told not to hand it over. Nothing was confirmed.",
        "kn": "ನಿಮ್ಮ {who} ಹಸ್ತಾಂತರಕ್ಕೆ ಒಪ್ಪಿಗೆ ದೊರೆತಿದೆ, ಆದರೆ ಸಿಮ್ಯುಲೇಟೆಡ್ ಡೆಲಿವರಿ ಪೂರೈಕೆದಾರರು ವಿನಂತಿಯನ್ನು ಸ್ವೀಕರಿಸಲಿಲ್ಲ. ಹಸ್ತಾಂತರಿಸಬೇಡಿ ಎಂದು ರೈಡರ್‌ಗೆ ತಿಳಿಸಲಾಗಿದೆ. ಏನೂ ಖಚಿತವಾಗಿಲ್ಲ.",
    },
    "handover_refused_verified": {
        "en": "The rider asked to leave your order with a {who}. This order needs verification at handover, so the agent refused. Nothing was handed over or confirmed.",
        "kn": "ರೈಡರ್ ನಿಮ್ಮ ಆರ್ಡರ್ ಅನ್ನು {who} ಅವರಿಗೆ ಕೊಡಲು ಕೇಳಿದರು. ಈ ಆರ್ಡರ್‌ಗೆ ಹಸ್ತಾಂತರದ ವೇಳೆ ಪರಿಶೀಲನೆ ಬೇಕಾಗಿರುವುದರಿಂದ ಏಜೆಂಟ್ ನಿರಾಕರಿಸಿತು. ಏನನ್ನೂ ಹಸ್ತಾಂತರಿಸಿಲ್ಲ ಅಥವಾ ಖಚಿತಪಡಿಸಿಲ್ಲ.",
    },
    "declined": {
        "en": "You did not allow the rider's request. The rider was told. Nothing was confirmed.",
        "kn": "ರೈಡರ್‌ನ ವಿನಂತಿಗೆ ನೀವು ಅನುಮತಿ ನೀಡಲಿಲ್ಲ. ರೈಡರ್‌ಗೆ ತಿಳಿಸಲಾಗಿದೆ. ಏನೂ ಖಚಿತವಾಗಿಲ್ಲ.",
    },
    "contact_later": {
        "en": "You asked to be contacted later. The rider was told. Nothing was confirmed.",
        "kn": "ನಂತರ ಸಂಪರ್ಕಿಸುವಂತೆ ನೀವು ಕೇಳಿದ್ದೀರಿ. ರೈಡರ್‌ಗೆ ತಿಳಿಸಲಾಗಿದೆ. ಏನೂ ಖಚಿತವಾಗಿಲ್ಲ.",
    },
    "unresolved": {
        "en": "The rider's request could not be resolved in time. The rider was told your preferred window ({window}). Nothing was confirmed.",
        "kn": "ರೈಡರ್‌ನ ವಿನಂತಿಯನ್ನು ಸಮಯಕ್ಕೆ ಬಗೆಹರಿಸಲಾಗಲಿಲ್ಲ. ನಿಮ್ಮ ಇಷ್ಟದ ಸಮಯ ({window}) ರೈಡರ್‌ಗೆ ತಿಳಿಸಲಾಗಿದೆ. ಏನೂ ಖಚಿತವಾಗಿಲ್ಲ.",
    },
    "escalated": {
        "en": "The agent could not handle the rider's request safely and escalated it. Nothing was confirmed.",
        "kn": "ಏಜೆಂಟ್ ರೈಡರ್‌ನ ವಿನಂತಿಯನ್ನು ಸುರಕ್ಷಿತವಾಗಿ ನಿರ್ವಹಿಸಲಾಗದೆ ಮುಂದಕ್ಕೆ ಕಳುಹಿಸಿತು. ಏನೂ ಖಚಿತವಾಗಿಲ್ಲ.",
    },
    "availability_shared": {
        "en": "The rider asked when you are available. The agent shared your preferred window ({window}). Nothing else was confirmed.",
        "kn": "ನೀವು ಯಾವಾಗ ಲಭ್ಯ ಎಂದು ರೈಡರ್ ಕೇಳಿದರು. ಏಜೆಂಟ್ ನಿಮ್ಮ ಇಷ್ಟದ ಸಮಯ ({window}) ತಿಳಿಸಿತು. ಬೇರೆ ಏನೂ ಖಚಿತವಾಗಿಲ್ಲ.",
    },
    "address_shared": {
        "en": "The rider asked for directions. The agent shared only your area and landmark.",
        "kn": "ರೈಡರ್ ದಾರಿ ಕೇಳಿದರು. ಏಜೆಂಟ್ ನಿಮ್ಮ ಪ್ರದೇಶ ಮತ್ತು ಗುರುತು ಮಾತ್ರ ಹಂಚಿಕೊಂಡಿತು.",
    },
    "address_change_provider_accepted": {
        "en": "You approved an address change. The simulated delivery provider accepted the request. Delivery completion has not yet been recorded.",
        "kn": "ನೀವು ವಿಳಾಸ ಬದಲಾವಣೆಗೆ ಒಪ್ಪಿಗೆ ನೀಡಿದ್ದೀರಿ. ಸಿಮ್ಯುಲೇಟೆಡ್ ಡೆಲಿವರಿ ಪೂರೈಕೆದಾರರು ವಿನಂತಿಯನ್ನು ಸ್ವೀಕರಿಸಿದ್ದಾರೆ. ಡೆಲಿವರಿ ಪೂರ್ಣಗೊಂಡಿರುವುದು ಇನ್ನೂ ದಾಖಲಾಗಿಲ್ಲ.",
    },
    "call_ended_unresolved": {
        "en": "The rider ended the call before you answered. Nothing was confirmed.",
        "kn": "ನೀವು ಉತ್ತರಿಸುವ ಮೊದಲೇ ರೈಡರ್ ಕರೆ ಮುಗಿಸಿದರು. ಏನೂ ಖಚಿತವಾಗಿಲ್ಲ.",
    },
    "system_failure": {
        "en": "The call hit a technical problem and ended safely. Nothing was confirmed.",
        "kn": "ಕರೆಯಲ್ಲಿ ತಾಂತ್ರಿಕ ತೊಂದರೆ ಉಂಟಾಗಿ ಸುರಕ್ಷಿತವಾಗಿ ಕೊನೆಗೊಂಡಿತು. ಏನೂ ಖಚಿತವಾಗಿಲ್ಲ.",
    },
}

# Evidence the ledger MUST contain before a customer template may be shown.
CUSTOMER_REQUIRES = {
    "handover_provider_accepted": "provider_accepted",
    "address_change_provider_accepted": "provider_accepted",
    "time_approved": "customer_approved",
    "rider_agreed_time": "rider_agreed",
}
SAFE_FALLBACK = "rider_called"

WHO = {
    "guard": {"en": "security guard", "hi": "गार्ड", "kn": "ಸೆಕ್ಯುರಿಟಿ ಗಾರ್ಡ್"},
    "neighbor": {"en": "neighbour", "hi": "पड़ोसी", "kn": "ಪಕ್ಕದ ಮನೆಯವರು"},
}
REQUEST_LABEL = {
    "guard_drop_request": {"en": "leave the order with the security guard",
                           "hi": "ऑर्डर गार्ड के पास छोड़ना",
                           "kn": "ಆರ್ಡರ್ ಅನ್ನು ಸೆಕ್ಯುರಿಟಿ ಗಾರ್ಡ್ ಬಳಿ ಬಿಡಲು"},
    "neighbor_drop_request": {"en": "leave the order with a neighbour",
                              "hi": "ऑर्डर पड़ोसी के पास छोड़ना",
                              "kn": "ಆರ್ಡರ್ ಅನ್ನು ಪಕ್ಕದ ಮನೆಯವರ ಬಳಿ ಬಿಡಲು"},
    "change_address": {"en": "deliver to a different address", "hi": "दूसरे पते पर डिलीवरी करना",
                       "kn": "ಬೇರೆ ವಿಳಾಸಕ್ಕೆ ಡೆಲಿವರಿ ಮಾಡಲು"},
    "propose_time": {"en": "deliver at {time}", "hi": "{time} पर डिलीवरी करना", "kn": "{time}ಕ್ಕೆ ಡೆಲಿವರಿ ಮಾಡಲು"},
}


def fmt_time(hhmm: str | None) -> str:
    if not hhmm:
        return ""
    h, m = (int(x) for x in hhmm.split(":"))
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" if m else f"{h12} {suffix}"


def fmt_window(start: str, end: str) -> str:
    return f"{fmt_time(start)} – {fmt_time(end)}"


def _localize(slots: dict, lang: str) -> dict:
    out = dict(slots)
    if "who" in out and out["who"] in WHO:
        out["who"] = WHO[out["who"]][lang if lang in WHO[out["who"]] else "en"]
    if "request_intent" in out:
        out["request"] = request_label(out.pop("request_intent"), out.get("time"), lang)
    if "time" in out and out["time"] and ":" in out["time"] and len(out["time"]) == 5:
        out["time"] = fmt_time(out["time"])
    return out


def rider_reply(key: str, lang: str, **slots) -> str:
    lang = lang if lang in LANGS else "en"
    return RIDER[key][lang].format(**_localize(slots, lang))


def customer_message(key: str, **slots) -> dict:
    return {lang: CUSTOMER[key][lang].format(**_localize(slots, lang)) for lang in ("en", "kn")}


def request_label(intent: str, time: str | None = None, lang: str = "en") -> str:
    labels = REQUEST_LABEL.get(intent)
    if not labels:
        return {"en": "a request", "hi": "एक अनुरोध", "kn": "ಒಂದು ವಿನಂತಿ"}.get(lang, "a request")
    return labels.get(lang, labels["en"]).format(time=fmt_time(time))


def select_customer_message(events: list[dict]) -> dict:
    """Pick the message for the latest outcome, but only if the ledger proves it."""
    have = {e["evidence_level"] for e in events}
    chosen = None
    for e in reversed(events):
        if e["detail"].get("customer_message"):
            chosen = e
            break
    if not chosen:
        msg = customer_message(SAFE_FALLBACK)
        return {"key": SAFE_FALLBACK, **msg, "downgraded": False}
    key = chosen["detail"]["customer_message"]
    slots = chosen["detail"].get("slots", {})
    need = CUSTOMER_REQUIRES.get(key)
    if need and need not in have:
        return {"key": SAFE_FALLBACK, **customer_message(SAFE_FALLBACK), "downgraded": True}
    return {"key": key, **customer_message(key, **slots), "downgraded": False}


def all_fixed_rider_phrases(window: str, area: str, landmark: str) -> list[tuple[str, str, str]]:
    """(key, lang, text) for every reply that can be pre-rendered (no free slots)."""
    out = []
    for key, by_lang in RIDER.items():
        for lang in LANGS:
            tmpl = by_lang[lang]
            if "{time}" in tmpl:
                continue  # time varies per call -> rendered live
            if "{who}" in tmpl:
                for who in WHO:
                    out.append((f"{key}:{who}", lang, tmpl.format(**_localize(
                        {"who": who, "window": window}, lang))))
                continue
            out.append((key, lang, tmpl.format(window=window, area=area, landmark=landmark)))
    return out


assert set(EVIDENCE_RANK) >= set(CUSTOMER_REQUIRES.values())
