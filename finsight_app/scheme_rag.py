"""Dependable local-first RAG assistant for government-scheme guides."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SCHEME_DOCS_FOLDER = Path(__file__).resolve().parent / "scheme_docs"
SCHEME_FILE_MAP = {
    "PMEGP (Manufacturing)": "pmegp.txt",
    "PMEGP (Service/Business)": "pmegp.txt",
    "CGTMSE Collateral-Free Loan": "cgtmse.txt",
    "Mudra Loan - Shishu": "mudra_kishor.txt",
    "Mudra Loan - Kishor": "mudra_kishor.txt",
    "Mudra Loan - Tarun": "mudra_kishor.txt",
    "Mudra Loan - Tarun Plus": "mudra_kishor.txt",
}
_STOP_WORDS = {
    "a", "about", "an", "and", "are", "can", "do", "for", "how", "i",
    "in", "is", "it", "me", "my", "of", "on", "the", "this", "to", "what",
    "where", "which", "who", "with",
}


class SchemeAssistantError(RuntimeError):
    pass


@dataclass(frozen=True)
class RetrievedPassage:
    heading: str
    text: str
    score: int


@dataclass(frozen=True)
class SchemeAnswer:
    answer: str
    passages: tuple[RetrievedPassage, ...]
    mode: str


def _tokens(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) > 1 and token not in _STOP_WORDS
    }


def _sections(text: str) -> Iterable[tuple[str, str]]:
    for block in re.split(r"\n\s*\n", text.strip()):
        block = " ".join(block.split())
        if block:
            heading, separator, body = block.partition(":")
            yield (heading.strip() if separator else "Scheme guide",
                   body.strip() if separator else block)


def retrieve_scheme_passages(
    scheme_name: str, question: str, limit: int = 3
) -> tuple[RetrievedPassage, ...]:
    filename = SCHEME_FILE_MAP.get(scheme_name)
    if not filename:
        raise SchemeAssistantError("A detailed guide is not available for this scheme yet.")
    path = SCHEME_DOCS_FOLDER / filename
    if not path.is_file():
        raise SchemeAssistantError("The scheme guide could not be found.")

    query = _tokens(question)
    lowered = question.lower()
    if any(word in lowered for word in ("apply", "application", "document")):
        query |= {"apply", "applications", "documents", "required"}
    if any(word in lowered for word in ("eligible", "qualify", "qualification")):
        query |= {"qualifies", "eligible", "eligibility"}
    if any(word in lowered for word in ("benefit", "loan", "amount", "subsidy")):
        query |= {"benefit", "loan", "amount", "subsidy"}

    ranked = []
    for heading, body in _sections(path.read_text(encoding="utf-8")):
        score = len(query & _tokens(body)) + 3 * len(query & _tokens(heading))
        ranked.append(RetrievedPassage(heading, body, score))
    ranked.sort(key=lambda item: item.score, reverse=True)
    matched = [item for item in ranked if item.score > 0][:limit]
    return tuple(matched or ranked[:1])


def _local_answer(scheme_name: str, passages: tuple[RetrievedPassage, ...]) -> str:
    details = "\n\n".join(
        f"**{item.heading}:** {item.text}" for item in passages
    )
    return f"Here is what the verified {scheme_name} guide says:\n\n{details}"


def answer_scheme_question(scheme_name: str, question: str) -> SchemeAnswer:
    question = " ".join(str(question).split())
    if len(question) < 3:
        raise SchemeAssistantError("Enter a complete question.")
    passages = retrieve_scheme_passages(scheme_name, question)
    fallback = _local_answer(scheme_name, passages)
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return SchemeAnswer(fallback, passages, "local")

    try:
        from langchain_groq import ChatGroq

        context = "\n\n".join(f"{p.heading}: {p.text}" for p in passages)
        prompt = (
            "You are FinSight's government-scheme guide. Answer in plain language "
            "using only the context. Give practical steps when asked how to apply. "
            "If context is insufficient, say so. Never invent requirements, amounts, "
            "dates, links, or approval guarantees. End by asking the user to verify "
            "final details on the official scheme website.\n\n"
            f"Scheme: {scheme_name}\nContext:\n{context}\n\nQuestion: {question}"
        )
        response = ChatGroq(
            model="llama-3.1-8b-instant", api_key=api_key, temperature=0
        ).invoke(prompt)
        answer = str(getattr(response, "content", "")).strip()
        if answer:
            return SchemeAnswer(answer, passages, "ai")
    except Exception:
        pass
    return SchemeAnswer(fallback, passages, "local")


def load_index() -> None:
    """Compatibility shim: local retrieval needs no generated index."""
    return None


def has_scheme_guide(scheme_name: str) -> bool:
    """Whether FinSight has a local guide for assistant answers."""
    filename = SCHEME_FILE_MAP.get(scheme_name)
    return bool(filename and (SCHEME_DOCS_FOLDER / filename).is_file())


def ask_scheme_question(scheme_name: str, question: str, _index=None) -> str:
    return answer_scheme_question(scheme_name, question).answer


__all__ = [
    "SchemeAnswer", "SchemeAssistantError", "answer_scheme_question",
    "ask_scheme_question", "has_scheme_guide", "load_index", "retrieve_scheme_passages",
]
