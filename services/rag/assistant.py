"""One validated answer path, with failure isolation and minimal API disclosure."""
import logging
import time
import re
from .generator import generate, ProviderError
from .config import semantic_enabled
from .language import TEXT, detect_language
from .repository import eligibility, load_records, valid_record
from .retriever import retrieve

LOG = logging.getLogger(__name__)
UNAVAILABLE = "The Scheme Assistant is temporarily unavailable. Your FinSight analytics and reports are unaffected."
PROVIDER_MESSAGES = {
    "missing_key": "Add GROQ_API_KEY to the project's .env file to enable the assistant.",
    "invalid_key": "Groq rejected the API key. Check GROQ_API_KEY in your .env file.",
    "access_denied": "Groq denied this request. Check your account's model permissions and network access.",
    "model_unavailable": "The configured Groq model is unavailable to your account. Update LLM_MODEL in .env to an accessible model.",
    "rate_limit": "Groq's usage limit was reached. Wait a moment and try again, or check your Groq quota.",
    "network_error": "Could not reach Groq. Check your connection and try again.",
    "invalid_response": "Groq returned an incomplete answer. Please try again.",
    "provider_error": "Groq could not complete the request. Please try again shortly.",
}


def validate_answer(output, records, language, profile):
    if not isinstance(output, dict) or not isinstance(output.get("recommendations"), list):
        raise ValueError("Invalid structured answer")
    trusted = {r["scheme_id"]: r for r in records}
    cards, seen = [], set()
    for item in output["recommendations"]:
        if not isinstance(item, dict) or set(item) != {"scheme_id", "evidence_chunk_ids"}:
            raise ValueError("Unexpected generated fields")
        sid = item["scheme_id"]
        if not isinstance(sid, str) or sid not in trusted:
            raise ValueError("Unknown scheme")
        record = trusted[sid]
        ids = item["evidence_chunk_ids"]
        allowed = {sid + ":" + field for field in record["facts"]}
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in allowed for i in ids):
            raise ValueError("Unknown evidence")
        if not valid_record(record):
            raise ValueError("Source failed validation")
        missing, failed = eligibility(record, profile)
        if failed or sid in seen:
            continue
        seen.add(sid)
        claims = [{"claim": record["facts"][i.split(":", 1)[1]].get(language, record["facts"][i.split(":", 1)[1]]["en"]),
                   "field": i.split(":", 1)[1], "source_chunk": i, "source_url": record["official_url"]} for i in ids]
        cards.append({"scheme_id": sid, "scheme_name": record["scheme_name"], "claims": claims,
                      "source_url": record["official_url"], "last_checked_at": record["last_checked_at"],
                      "missing_information": missing, "status": TEXT[language]["status"]})
    return cards


def ask(question, language="auto", profile=None, *, records=None, generator=generate, use_embeddings=None):
    started = time.monotonic()
    lang = detect_language(question, language)
    result = {"language": lang, "message": TEXT[lang]["none"], "recommendations": [], "status": "no_evidence"}
    if not question.strip() or len(question) > 2000:
        return result
    normalized = question.casefold().strip(" .!?।")
    if re.fullmatch(r"(?:hello|hi|hey|namaste|namaskar|नमस्ते|नमस्कार|हैलो)(?:\s+finny)?", normalized):
        message = {
            "en": "Hi, I'm Finny! I can help you explore government schemes, eligibility and official sources. Tell me about your business, or ask about PMEGP, MUDRA or CGTMSE.",
            "hi": "नमस्ते! मैं Finny हूँ। मैं सरकारी योजनाओं, पात्रता और आधिकारिक स्रोतों में मदद कर सकता हूँ। अपने व्यवसाय के बारे में बताइए या PMEGP, MUDRA या CGTMSE के बारे में पूछिए।",
            "mr": "नमस्कार! मी Finny आहे. सरकारी योजना, पात्रता आणि अधिकृत स्रोत शोधण्यात मदत करू शकतो. तुमच्या व्यवसायाबद्दल सांगा किंवा PMEGP, MUDRA किंवा CGTMSE बद्दल विचारा.",
        }[lang]
        return dict(result, status="conversation", message=message)
    documents_question = any(word in normalized for word in (
        "document", "paperwork", "checklist", "dastavez", "kagaz", "दस्तावेज", "कागदपत्र"))
    try:
        if use_embeddings is None:
            use_embeddings = semantic_enabled()
        catalog = load_records() if records is None else [r for r in records if valid_record(r)]
        if documents_question:
            named = [r for r in catalog if any(a.casefold() in normalized for a in r["aliases"])]
            if not named:
                message = {
                    "en": "Which scheme do you need documents for—PMEGP, MUDRA or CGTMSE? Tell me the scheme name so I can point you to its official requirements.",
                    "hi": "आपको किस योजना के लिए दस्तावेज़ चाहिए—PMEGP, MUDRA या CGTMSE? योजना का नाम बताइए, ताकि मैं उसके आधिकारिक स्रोत तक पहुँचने में मदद कर सकूँ।",
                    "mr": "तुम्हाला कोणत्या योजनेसाठी कागदपत्रे हवी आहेत—PMEGP, MUDRA की CGTMSE? योजनेचे नाव सांगा म्हणजे मी अधिकृत स्रोत शोधण्यात मदत करू शकेन.",
                }[lang]
                return dict(result, status="clarification", message=message, followup_question=question)
            # The reviewed catalog does not yet include document checklists.
            # Be specific about that limit and provide trusted source links.
            message = {
                "en": "I don't yet have a verified document checklist for this scheme in my catalog. Please check the official source below for current requirements; I won't guess which documents are mandatory.",
                "hi": "मेरी जानकारी में इस योजना की सत्यापित दस्तावेज़ सूची अभी उपलब्ध नहीं है। वर्तमान आवश्यकताओं के लिए नीचे आधिकारिक स्रोत देखें; मैं अनिवार्य दस्तावेज़ों का अनुमान नहीं लगाऊँगा।",
                "mr": "माझ्या माहितीत या योजनेची पडताळलेली कागदपत्रांची यादी सध्या उपलब्ध नाही. सध्याच्या आवश्यकतांसाठी खालील अधिकृत स्रोत पाहा; अनिवार्य कागदपत्रांचा अंदाज देणार नाही.",
            }[lang]
            return dict(result, status="source_guidance", message=message,
                        sources=[{"name": r["scheme_name"], "url": r["official_url"]} for r in named])
        candidates = retrieve(question, catalog, use_embeddings)
        candidates = [r for r in candidates if not eligibility(r, profile or {})[1]]
        if not candidates:
            return result
        output = generator(question, candidates, lang)
        cards = validate_answer(output, candidates, lang, profile or {})
        if cards:
            result.update(message=TEXT[lang]["intro"], recommendations=cards, status="ok")
        LOG.info("rag language=%s sources=%s cards=%d duration=%.3f", lang,
                 [r["scheme_id"] for r in candidates], len(cards), time.monotonic() - started)
    except ProviderError as error:
        LOG.warning("rag provider_failure=%s http_status=%s", error.code, error.status)
        result.update(message=PROVIDER_MESSAGES[error.code], status="unavailable", error_code=error.code)
    except Exception as error:
        LOG.warning("rag fallback=%s", type(error).__name__)
        result.update(message=UNAVAILABLE, status="unavailable")
    return result
