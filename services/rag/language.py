"""Separate response language from the English evidence language."""
import re

LANGUAGES = {"Auto Detect": "auto", "English": "en", "हिन्दी": "hi", "मराठी": "mr"}
TEXT = {
    "en": {"none": "I couldn't find enough verified government information for this question.", "intro": "These schemes may be relevant. Confirm final eligibility on the official website.", "status": "Potentially relevant — final eligibility is unconfirmed", "eligibility": "Eligibility", "benefits": "Benefits", "missing": "Information still required", "source": "Official source", "reason": "Why this may be relevant", "review": "Full eligibility and lender assessment must be confirmed on the official source."},
    "hi": {"none": "इस प्रश्न के लिए पर्याप्त सत्यापित सरकारी जानकारी नहीं मिली।", "intro": "ये योजनाएँ उपयोगी हो सकती हैं। अंतिम पात्रता आधिकारिक वेबसाइट पर जाँचें।", "status": "संभावित रूप से उपयोगी — अंतिम पात्रता की पुष्टि बाकी है", "eligibility": "पात्रता", "benefits": "लाभ", "missing": "अभी आवश्यक जानकारी", "source": "आधिकारिक स्रोत", "reason": "यह योजना क्यों उपयोगी हो सकती है", "review": "सभी पात्रता शर्तों और ऋणदाता के मूल्यांकन की पुष्टि आधिकारिक स्रोत से करें।"},
    "mr": {"none": "या प्रश्नासाठी पुरेशी पडताळलेली सरकारी माहिती सापडली नाही.", "intro": "या योजना संबंधित असू शकतात. अंतिम पात्रता अधिकृत संकेतस्थळावर तपासा.", "status": "संभाव्य संबंधित योजना — अंतिम पात्रता अद्याप निश्चित नाही", "eligibility": "पात्रता", "benefits": "लाभ", "missing": "अजून आवश्यक माहिती", "source": "अधिकृत स्रोत", "reason": "ही योजना का संबंधित असू शकते", "review": "सर्व पात्रता अटी आणि कर्जदात्याचे मूल्यांकन अधिकृत स्रोतावर तपासा."},
}


def detect_language(query, selected="auto"):
    if selected in TEXT:
        return selected
    if re.search(r"\b(?:mujhe|kaunse|konse|chahiye|chaiye|kaise|kya|namaste|iske|uske|lagenge|batao|samjhao|sakti|sakta|mera|meri|matlab)\b", query.casefold()):
        return "hi"
    if re.search(r"[\u0900-\u097f]", query):
        return "mr" if any(w in query for w in ("माझ", "कोण", "आहे", "साठी", "कर्ज", "योजना कोणत्या")) else "hi"
    return "en"
