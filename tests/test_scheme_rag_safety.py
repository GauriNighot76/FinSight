import importlib

import pytest


def test_scheme_rag_imports_without_optional_packages_or_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    module = importlib.import_module("finsight_app.scheme_rag")
    assert module.SCHEME_DOCS_FOLDER.is_absolute()
    with pytest.raises(module.RAGUnavailableError, match="GROQ_API_KEY"):
        module.get_llm()


def test_unknown_scheme_and_empty_question_fail_honestly():
    from finsight_app import scheme_rag

    assert "enough information" in scheme_rag.ask_scheme_question(
        "Unknown Scheme", "What is covered?", object()
    )
    assert "Enter a question" in scheme_rag.ask_scheme_question(
        "PMEGP (Service/Business)", "   ", object()
    )


def test_unsafe_faiss_deserialization_is_not_enabled():
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "finsight_app" / "scheme_rag.py").read_text(
        encoding="utf-8"
    )
    assert "allow_dangerous_deserialization" not in source


def test_missing_documents_fail_with_safe_message(tmp_path, monkeypatch):
    from finsight_app import scheme_rag

    monkeypatch.setattr(scheme_rag, "SCHEME_DOCS_FOLDER", tmp_path)
    monkeypatch.setattr(
        scheme_rag,
        "_dependencies",
        lambda: (object(), object(), object(), object(), object()),
    )

    with pytest.raises(scheme_rag.RAGUnavailableError, match="documents"):
        scheme_rag.build_index()


def test_selected_scheme_filter_and_api_failure_are_sanitized():
    from finsight_app import scheme_rag

    class Retriever:
        def invoke(self, _question):
            return [type("Document", (), {"page_content": "Synthetic context"})()]

    class VectorStore:
        def as_retriever(self, search_kwargs):
            assert search_kwargs["filter"] == {
                "scheme_name": "PMEGP (Service/Business)"
            }
            return Retriever()

    class FailingLLM:
        def invoke(self, _prompt):
            raise RuntimeError("private upstream detail")

    with pytest.raises(
        scheme_rag.RAGUnavailableError, match="temporarily unavailable"
    ) as captured:
        scheme_rag.ask_scheme_question(
            "PMEGP (Service/Business)",
            "What is covered?",
            VectorStore(),
            llm=FailingLLM(),
        )
    assert "private upstream detail" not in str(captured.value)
