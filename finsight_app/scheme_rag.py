"""Compatibility entry point for the isolated assistant; no eager ML imports."""
from services.rag.assistant import ask
from services.rag.config import settings

class SchemeRAGUnavailable(RuntimeError):
    pass

def rag_status():
    return {"dependencies_available": True, "api_key_configured": bool(settings()["api_key"])}

def supports_scheme(scheme_name):
    return any(word in scheme_name.casefold() for word in ("pmegp", "mudra", "cgtmse"))

def ask_scheme_question(scheme_name, question, vectorstore=None):
    return ask(f"{scheme_name}: {question}")
