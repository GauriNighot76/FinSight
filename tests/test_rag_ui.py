from streamlit.testing.v1 import AppTest


def test_assistant_is_usable_without_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from finsight_app import scheme_assistant_ui
    from services.rag.assistant import ask
    monkeypatch.setattr(scheme_assistant_ui, "chat", lambda q, lang, profile, **kw: ask(q, lang, profile, use_embeddings=False))
    app = AppTest.from_string('''
import streamlit as st
from finsight_app.scheme_assistant_ui import render_assistant
render_assistant(st, 42)
''').run()
    assert not app.exception
    assert app.selectbox[0].value == "Auto Detect"
    app.text_area[0].set_value("unknown scheme called Golden Rocket")
    app.button[0].click().run()
    assert not app.exception
    assert "verified government information" in app.info[0].value


def test_localized_cards_and_persistent_single_answer(monkeypatch):
    from finsight_app import scheme_assistant_ui
    from services.rag.assistant import ask
    def provider(query, records, language):
        return {"recommendations": [{"scheme_id": "mudra", "evidence_chunk_ids": ["mudra:eligibility", "mudra:benefits"]}]}
    monkeypatch.setattr(scheme_assistant_ui, "chat", lambda q, lang, profile, **kw: ask(q, lang, profile, generator=provider, use_embeddings=False))
    app = AppTest.from_string('''
import streamlit as st
from finsight_app.scheme_assistant_ui import render_assistant
render_assistant(st, 42)
''').run()
    app.selectbox[0].select("मराठी")
    app.text_area[0].set_value("मुद्रा योजना")
    app.button[0].click().run()
    assert not app.exception
    assert len(app.session_state["scheme_answer_42"]["recommendations"]) == 1
    assert app.session_state["scheme_answer_42"]["language"] == "mr"
    app.run()
    assert not app.exception
    assert len(app.info) == 1


def test_mascot_uses_main_popover_and_scopes_results(monkeypatch):
    from finsight_app import scheme_assistant_ui
    calls = []
    def answer(q, lang, profile, **kw):
        calls.append(q)
        return {"status": "no_evidence", "language": "en", "message": "No matching evidence", "recommendations": []}
    monkeypatch.setattr(scheme_assistant_ui, "chat", answer)
    app = AppTest.from_string('''
import streamlit as st
from finsight_app.scheme_assistant_ui import render_help_assistant
business = st.selectbox("Test business", [42, 43])
render_help_assistant(st, business)
''').run()
    assert not app.exception
    # The right-edge launcher stays available when the sidebar is collapsed.
    assert len(app.main.get("popover")) == 1
    assert app.main.get("popover")[0].proto.popover.label == "Ask Finny"
    assert not app.sidebar.get("popover")
    assert not calls
    assert app.text_area
    app.text_area[0].set_value("Which government scheme am I eligible for?")
    app.button[0].click().run()
    assert calls == ["Which government scheme am I eligible for?"]
    assert len(app.chat_message) == 2
    app.run()
    assert len(app.chat_message) == 2
    app.selectbox[0].select(43).run()
    assert not app.chat_message


def test_documents_clarification_retained_for_scheme_reply(monkeypatch):
    from finsight_app import scheme_assistant_ui
    from services.rag.conversation import chat
    def planner(system, data):
        query = "MUDRA documents" if data["question"] == "MUDRA" else "Which documents do I need?"
        return {"intent": "search", "query": query, "language": "hi", "message": ""}
    monkeypatch.setattr(scheme_assistant_ui, "chat", lambda q, lang, profile, **kw: chat(q, lang, profile, planner=planner, **kw))
    app = AppTest.from_string('''
import streamlit as st
from finsight_app.scheme_assistant_ui import render_help_assistant
render_help_assistant(st, 42)
''').run()
    app.text_area[0].set_value("mujhe kaunse documents chaiye")
    app.button[0].click().run()
    assert app.session_state["scheme_answer_42"]["status"] == "clarification"
    app.text_area[0].set_value("MUDRA")
    app.button[0].click().run()
    answer = app.session_state["scheme_answer_42"]
    assert answer["status"] == "source_guidance"
    assert answer["language"] == "hi"
    assert answer["sources"]
    assert not app.exception
