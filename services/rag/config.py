"""Read local configuration each request without polluting process environment."""
import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
DEFAULT_MODEL = "openai/gpt-oss-20b"


def semantic_enabled():
    """Heavy local ML is an explicit deployment choice, never a chat cold start."""
    from dotenv import dotenv_values
    local = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    value = local.get("RAG_USE_EMBEDDINGS") or os.getenv("RAG_USE_EMBEDDINGS", "0")
    return value.strip().lower() in {"1", "true", "yes"}


def settings():
    from dotenv import dotenv_values
    local = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    # Local edits take effect immediately in an already-running Streamlit process.
    def value(name):
        return (local.get(name) or os.getenv(name) or "").strip()
    return {"api_key": value("GROQ_API_KEY") or value("LLM_API_KEY"),
            "model": value("LLM_MODEL") or DEFAULT_MODEL}
