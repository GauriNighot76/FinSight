import copy
import json
from datetime import date
from pathlib import Path

import pytest

from services.rag.assistant import ask, validate_answer
from services.rag.language import detect_language
from services.rag.repository import allowed_source, load_records, valid_record
from services.rag.retriever import retrieve


def selected(query, records, language):
    return {"recommendations": [{"scheme_id": r["scheme_id"], "evidence_chunk_ids": [r["scheme_id"] + ":" + f for f in r["facts"]]} for r in records]}


@pytest.mark.parametrize("url", ["https://gov.in.evil.com/x", "http://msme.gov.in/x", "https://msme.gov.in@evil.com/", "https://msme.gov.in:444/x", "file:///etc/passwd", "https://example.com/", "https://evilgov.in/"])
def test_reject_untrusted_urls(url):
    assert not allowed_source(url)


def test_catalog_freshness_hash_and_metadata():
    records = load_records(today=date(2026, 9, 24))
    assert len(records) == 3
    for r in records:
        assert valid_record(r, date(2026, 9, 24))
        assert not valid_record(r, date(2027, 1, 1))
        changed = copy.deepcopy(r)
        changed["facts"]["benefits"]["en"] = "Invented grant"
        assert not valid_record(changed, date(2026, 9, 24))
        assert "?" not in r["facts"]["reason"]["mr"]


@pytest.mark.parametrize("query,lang", [("small manufacturing business", "en"), ("मेरे छोटे विनिर्माण कारोबार के लिए ऋण", "hi"), ("माझ्या उत्पादन व्यवसायासाठी कर्ज", "mr")])
def test_multilingual(query, lang):
    assert detect_language(query) == lang
    result = ask(query, generator=selected, use_embeddings=False)
    assert result["status"] == "ok"
    assert {c["scheme_id"] for c in result["recommendations"]} == {"pmegp", "mudra", "cgtmse"}
    for card in result["recommendations"]:
        assert allowed_source(card["source_url"])
        assert all(claim["source_url"] == card["source_url"] for claim in card["claims"])


@pytest.mark.parametrize("output", [None, {}, {"recommendations": [{"scheme_id": "fake", "evidence_chunk_ids": ["fake:benefits"]}]}, {"recommendations": [{"scheme_id": "mudra", "evidence_chunk_ids": ["pmegp:benefits"]}]}, {"recommendations": [{"scheme_id": "mudra", "evidence_chunk_ids": ["mudra:benefits"], "source_url": "https://example.com"}]}])
def test_invalid_generation_fails_closed(output):
    result = ask("mudra", generator=lambda *args: output, use_embeddings=False)
    assert result["status"] == "unavailable"
    assert not result["recommendations"]


def test_missing_key_and_provider_failure(monkeypatch):
    from services.rag import generator
    monkeypatch.setattr(generator, "settings", lambda: {"api_key": "", "model": "test"})
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert ask("mudra", use_embeddings=False)["status"] == "unavailable"
    def failed(*args):
        raise TimeoutError("private details must never surface")
    result = ask("mudra", generator=failed, use_embeddings=False)
    assert "private details" not in str(result)


def test_eligibility_cannot_be_overridden():
    result = ask("pmegp", profile={"owner_age": 16}, generator=selected, use_embeddings=False)
    assert not result["recommendations"]


def test_optional_embeddings_failure(monkeypatch):
    from services.rag import retriever
    def unavailable():
        raise ImportError("Optional dependencies unavailable")
    monkeypatch.setattr(retriever, "embedding_model", unavailable)
    retriever.document_vectors.cache_clear()
    assert retrieve("manufacturing business", load_records())


def test_catalog_unavailable(monkeypatch):
    from services.rag import assistant
    def unavailable():
        raise FileNotFoundError("internal/path")
    monkeypatch.setattr(assistant, "load_records", unavailable)
    result = ask("mudra")
    assert result["status"] == "unavailable"
    assert "internal/path" not in str(result)


def test_business_profile_not_sent_to_generator():
    def provider(query, records, language):
        assert "secret-account" not in json.dumps(records)
        assert query == "mudra"
        return selected(query, records, language)
    assert ask("mudra", profile={"bank_account": "secret-account"}, generator=provider, use_embeddings=False)["status"] == "ok"


def test_unknown_acronym_not_confused_with_general_business_discovery():
    assert not retrieve("Tell me about ABCDEF business subsidy", load_records(), False)


def test_language_override_and_hindi_business():
    assert detect_language("मेरे व्यवसाय के लिए ऋण") == "hi"
    assert detect_language("मुद्रा", "mr") == "mr"


@pytest.mark.parametrize("query", [
    "Which government scheme am i eligible for ?",
    "Which government schemes can help me?",
    "Am I eligible for any schemes?",
    "What government loan schemes support my manufacturing business?”",
    "मैं किन सरकारी योजनाओं के लिए पात्र हूँ?",
    "मी कोणत्या सरकारी योजनांसाठी पात्र आहे?",
])
def test_general_eligibility_reaches_provider(query):
    calls = []
    def provider(question, records, language):
        calls.append(question)
        return selected(question, records, language)
    result = ask(query, generator=provider, use_embeddings=False)
    assert calls == [query]
    assert result["status"] == "ok"
    assert {c["scheme_id"] for c in result["recommendations"]} == {
        r["scheme_id"] for r in retrieve(query, load_records(), use_embeddings=False)
    }


def test_general_eligibility_still_filters_profile():
    result = ask("Which government scheme am I eligible for?", profile={"owner_age": 16},
                 generator=selected, use_embeddings=False)
    assert "pmegp" not in {r["scheme_id"] for r in result["recommendations"]}


def test_default_chat_does_not_load_optional_ml(monkeypatch):
    from services.rag import assistant, retriever
    monkeypatch.setattr(assistant, "semantic_enabled", lambda: False)
    def should_not_load(*args):
        pytest.fail("Default chat must not load the ML model")
    monkeypatch.setattr(retriever, "document_vectors", should_not_load)
    result = ask("Which government scheme am I eligible for?", generator=selected)
    assert result["status"] == "ok"


def test_greeting_and_romanized_hindi_documents():
    def no_provider(*args):
        pytest.fail("Greetings and clarification must not call Groq")
    greeting = ask("hello", generator=no_provider)
    assert greeting["status"] == "conversation"
    assert "Finny" in greeting["message"]
    question = ask("mujhe kaunse documents chaiye", generator=no_provider)
    assert question["status"] == "clarification"
    assert question["language"] == "hi"
    assert "MUDRA" in question["message"]
    followup = ask(question["followup_question"] + " MUDRA", generator=no_provider)
    assert followup["status"] == "source_guidance"
    assert all(allowed_source(s["url"]) for s in followup["sources"])
    assert not followup["recommendations"]


def test_eval_dataset():
    cases = json.loads((Path(__file__).parent / "fixtures/rag_eval.json").read_text(encoding="utf-8"))
    records = load_records()
    for case in cases:
        actual = {r["scheme_id"] for r in retrieve(case["query"], records, False)}
        assert actual == set(case["expected"]), case["query"]
