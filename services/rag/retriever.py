"""Conservative multilingual hybrid retrieval, with cached optional embeddings."""
import re
import unicodedata
from functools import lru_cache

ALIASES = {
    "manufacturing": ("manufacturing", "विनिर्माण", "उत्पादन"),
    "business": ("business", "msme", "enterprise", "व्यवसाय", "उद्योग", "कारोबार"),
    "loan": ("loan", "credit", "कर्ज", "ऋण", "लोन"),
    "subsidy": ("subsidy", "अनुदान", "सब्सिडी"),
    "collateral": ("collateral", "तारण", "जमानत"),
}


@lru_cache(maxsize=1)
def embedding_model():
    from sentence_transformers import SentenceTransformer
    # Deployment downloads the model explicitly; a web request never downloads weights.
    return SentenceTransformer("intfloat/multilingual-e5-small", local_files_only=True)


@lru_cache(maxsize=4)
def document_vectors(passages):
    return embedding_model().encode(["passage: " + p for p in passages], normalize_embeddings=True)


def retrieve(query, records, use_embeddings=True):
    unknown_acronym = any(token not in {"MSME", "MSE", "INR", "PMEGP", "PMMY", "CGTMSE", "AM", "I"}
                          for token in re.findall(r"\b[A-Z]{2,}\b", query))
    query = unicodedata.normalize("NFKC", query).casefold().strip()
    # Require a known scheme or a supported discovery intent before semantic ranking.
    direct = [r for r in records if any(a.casefold() in query for a in r["aliases"])]
    concepts = {k for k, values in ALIASES.items() if any(v in query for v in values)}
    specific = bool(re.search(r"\d|₹|https?://|\.com\b", query))
    discovery = "business" in concepts and bool(concepts & {"manufacturing", "loan", "subsidy", "collateral"})
    general_eligibility = bool(re.search(
        r"\b(?:government|govt)\s+(?:\w+\s+){0,2}schemes?\b|"
        r"\bschemes?\b.*\b(?:eligible|eligibility|qualify|relevant|recommend)\b|"
        r"\b(?:eligible|eligibility|qualify)\b.*\bschemes?\b|"
        r"(?:सरकारी|शासकीय).*योजना|योजना.*पात्र|पात्र.*योजना", query))
    discovery = discovery or general_eligibility
    if (unknown_acronym and not direct) or (not direct and (not discovery or specific)):
        return []
    candidates = direct or records
    passages = tuple(" ".join(f["en"] for f in r["facts"].values()) for r in candidates)
    semantic = [0.0] * len(candidates)
    if use_embeddings:
        try:
            vectors = document_vectors(passages)
            q = embedding_model().encode(["query: " + query], normalize_embeddings=True)[0]
            semantic = (vectors @ q).tolist()
        except Exception:
            pass  # Small curated catalog retains conservative lexical discovery.
    ranked = []
    for r, score in zip(candidates, semantic):
        lexical = len(concepts.intersection(r["tags"]))
        if direct or general_eligibility or lexical >= 2:
            ranked.append((lexical + float(score) * 0.25, r))
    return [r for _, r in sorted(ranked, key=lambda x: x[0], reverse=True)[:4]]
