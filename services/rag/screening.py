"""Use the dashboard's local screening decisions, independently of LLM ranking."""
import re
from finsight_app.eligibility_engine import find_relevant_schemes
from .assistant import ask
from .repository import load_records


def answer_scheme(question, language="en", profile=None):
    records = load_records()
    query = question.casefold()
    named = [r for r in records if any(a.casefold() in query for a in r["aliases"])]
    discovery = not named and bool(re.search(
        r"\b(schemes?|programmes?|programs?)\b.*\b(eligible|eligibility|qualify|recommend|relevant|apply|help|support|available)\b|"
        r"\b(eligible|eligibility|qualify|recommend)\b.*\b(schemes?|programs?)\b", query))
    personal = discovery or bool(re.search(r"\b(eligible|qualify|eligibility|why|match)\b", query))
    rows = find_relevant_schemes(profile or {}) if discovery or named else []
    if named:
        rows = [row for row in rows if any(
            row["scheme_id"] in record.get("screening_ids", []) for record in named)]
    if discovery:
        message = {
            "en": "Here are the same local screening results as Government Schemes, using your saved profile. Potentially relevant means information is still missing; it does not confirm eligibility. Entries marked Not matched are not recommendations.",
            "hi": "ये Government Schemes वाले ही स्थानीय जाँच परिणाम हैं, आपके सहेजे गए प्रोफ़ाइल के आधार पर। Potentially relevant का मतलब जानकारी अधूरी है, पात्रता की पुष्टि नहीं। Not matched वाली योजनाएँ सुझाव नहीं हैं।",
            "mr": "हे Government Schemes मधील तेच स्थानिक तपासणी निकाल आहेत, जतन केलेल्या प्रोफाइलवर आधारित. Potentially relevant म्हणजे माहिती अपुरी आहे, पात्रतेची खात्री नाही. Not matched योजना शिफारसी नाहीत.",
        }[language]
        if not profile:
            message += {"en": " No saved profile is available. Save your details under Government Schemes first.",
                        "hi": " प्रोफ़ाइल उपलब्ध नहीं है। पहले Government Schemes में जानकारी सहेजें।",
                        "mr": " प्रोफाइल उपलब्ध नाही. आधी Government Schemes मध्ये माहिती जतन करा."}[language]
        result = {"status": "screening", "language": language, "message": message, "recommendations": []}
    else:
        # A mismatch must not prevent the user learning what a named scheme is.
        result = ask(question, language, {})
        for card in result["recommendations"]:
            card["status"] = {"en": "Scheme information — see local screening separately",
                              "hi": "योजना की जानकारी — स्थानीय जाँच अलग देखें",
                              "mr": "योजनेची माहिती — स्थानिक तपासणी स्वतंत्र पहा"}[language]
    if rows and (personal or named):
        result["screening_results"] = sorted(rows, key=lambda r: (
            {"Likely relevant based on supplied information": 0, "Potentially relevant": 1,
             "Not matched based on supplied information": 2}.get(r["relevance"], 9), r["scheme_name"]))
    return result
