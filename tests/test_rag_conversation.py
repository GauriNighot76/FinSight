import pytest
from services.rag.conversation import chat


def test_hinglish_query_is_normalized_before_retrieval():
    def planner(system, data):
        assert data["question"] == "mai kaunse schemes ke liye apply kar sakti hu?"
        return {"intent": "search", "query": "Which government schemes am I eligible for?", "language": "hi", "message": ""}
    def answerer(query, lang, profile):
        assert query == "Which government schemes am I eligible for?"
        assert lang == "hi"
        return {"status": "ok"}
    assert chat("mai kaunse schemes ke liye apply kar sakti hu?", planner=planner, answerer=answerer)["status"] == "ok"


def test_followup_context_is_bounded_and_profile_private():
    history = [{"question": "MUDRA", "scheme_ids": ["mudra"], "status": "ok", "language": "hi", "bank_account": "private"}] * 9
    def planner(system, data):
        assert len(data["recent_conversation"]) == 6
        assert "private" not in str(data)
        return {"intent": "search", "query": "What documents are needed for MUDRA?", "language": "hi", "message": ""}
    def answerer(query, language, profile):
        assert "MUDRA" in query
        assert profile["bank_account"] == "private"
        return {"status": "source_guidance"}
    assert chat("iske liye kya kagaz lagenge?", profile={"bank_account": "private"}, history=history, planner=planner, answerer=answerer)["status"] == "source_guidance"


@pytest.mark.parametrize("plan", [None, {}, {"intent": "search", "query": "", "language": "hi", "message": ""},
    {"intent": "chat", "query": "", "language": "hi", "message": "https://fake.example"}])
def test_invalid_plan_does_not_render_or_retrieve(plan):
    def answerer(*args):
        pytest.fail("Invalid plans must not reach retrieval")
    assert chat("hello", planner=lambda *args: plan, answerer=answerer)["status"] == "unavailable"
