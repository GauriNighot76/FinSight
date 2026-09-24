from types import SimpleNamespace
from services.rag.conversation import chat
from services.rag.dashboard_context import remember


def test_english_after_hindi_uses_current_language_and_general_chat():
    def planner(system, data):
        assert data["response_language"] == "en"
        assert "anomalies" in data["dashboard_guide"].lower()
        return {"intent": "chat", "query": "", "language": "en",
                "message": "Anomalies are unusual patterns to review, not proof of fraud."}
    def no_rag(*args):
        raise AssertionError("Dashboard explanations must not invoke scheme RAG")
    result = chat("what are the anomalies?", history=[{"question": "mujhe madad chahiye", "language": "hi"}], planner=planner, answerer=no_rag)
    assert result["language"] == "en"
    assert result["status"] == "conversation"
    assert "Anomalies" in result["message"]


def test_dashboard_figures_are_allowed_in_conversation():
    def planner(system, data):
        assert data["dashboard_summary"]["anomaly_count"] == 3
        return {"intent": "chat", "query": "", "language": "en", "message": "The dashboard summary contains 3 anomalies."}
    result = chat("How many anomalies are shown?", dashboard={"anomaly_count": 3}, planner=planner)
    assert result["status"] == "conversation"
    assert "3" in result["message"]


def test_snapshot_excludes_raw_rows_and_scopes_by_business():
    st = SimpleNamespace(session_state={})
    remember(st, "one", analysis={"kpis": {"transaction_count": 4, "total_income_minor": 12300},
             "transactions": [{"description": "private", "account_number": "secret"}]},
             health={"metrics": {}, "anomalies": [{"type": "Expense spike", "severity": "HIGH", "affected_transaction": {"description": "private"}}]})
    snapshot = st.session_state["scheme_dashboard_context_one"]
    assert snapshot["anomaly_count"] == 1
    assert "private" not in str(snapshot)
    assert "secret" not in str(snapshot)
    assert "scheme_dashboard_context_two" not in st.session_state
