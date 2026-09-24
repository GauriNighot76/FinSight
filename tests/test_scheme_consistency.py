from finsight_app.eligibility_engine import find_relevant_schemes
from services.rag.screening import answer_scheme
from services.rag.repository import load_records
from services.rag.assistant import ask


def selected(query, records, language):
    return {"recommendations": [{"scheme_id": r["scheme_id"],
        "evidence_chunk_ids": [r["scheme_id"] + ":" + f for f in r["facts"]]} for r in records]}


def test_discovery_matches_every_dashboard_decision():
    profile = {"business_category": "Micro", "owner_age": 25,
               "startup_recognized": False, "annual_turnover": 400000,
               "sector": "Service", "new_or_greenfield": False}
    result = answer_scheme("Which government schemes am I eligible for?", profile=profile)
    expected = {r["scheme_id"]: r for r in find_relevant_schemes(profile)}
    assert {r["scheme_id"]: r for r in result["screening_results"]} == expected
    assert len(result["screening_results"]) == 10
    assert result["recommendations"] == []


def test_every_dashboard_scheme_has_official_explanation():
    covered = {sid for record in load_records() for sid in record.get("screening_ids", [])}
    assert {r["scheme_id"] for r in find_relevant_schemes({})} <= covered


def test_cgss_explanation_even_when_profile_does_not_match(monkeypatch):
    from services.rag import screening
    monkeypatch.setattr(screening, "ask", lambda q, lang, p: ask(q, lang, p, generator=selected, use_embeddings=False))
    answer = answer_scheme("Tell me more about CGSS for DPIIT startups", profile={"startup_recognized": False})
    assert answer["status"] == "ok"
    assert answer["recommendations"][0]["scheme_id"] == "cgss"
    assert answer["screening_results"][0]["failed_reasons"]


def test_missing_profile_is_not_confirmed_eligibility():
    result = answer_scheme("what schemes am I eligible for?")
    assert "No saved profile" in result["message"]
    assert all(not r["eligible"] for r in result["screening_results"])
