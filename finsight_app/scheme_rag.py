"""Optional scheme-document RAG adapter.

Deterministic scheme screening does not depend on these optional packages.
This module imports the heavy RAG stack lazily so the core FinSight app still
starts when FAISS, sentence-transformers or Groq dependencies are unavailable.
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent
SCHEME_DOCS_FOLDER = BASE_DIR / "scheme_docs"
FAISS_INDEX_PATH = BASE_DIR / "faiss_scheme_index"

SCHEME_FILE_MAP = {
    "PMEGP (Service/Business)": "pmegp.txt",
    "CGTMSE Collateral-Free Loan": "cgtmse.txt",
    "Mudra Loan - Kishor": "mudra_kishor.txt",
}


class SchemeRAGUnavailable(RuntimeError):
    pass


def _deps():
    try:
        from langchain_community.document_loaders import TextLoader
        from langchain.text_splitter import RecursiveCharacterTextSplitter
        from langchain_huggingface import HuggingFaceEmbeddings
        from langchain_community.vectorstores import FAISS
        from langchain_groq import ChatGroq
    except Exception as error:
        raise SchemeRAGUnavailable(
            "Scheme document Q&A dependencies are not installed."
        ) from error
    return TextLoader, RecursiveCharacterTextSplitter, HuggingFaceEmbeddings, FAISS, ChatGroq


def supports_scheme(scheme_name: str) -> bool:
    return scheme_name in SCHEME_FILE_MAP


def rag_status() -> dict[str, object]:
    try:
        _deps()
        dependencies = True
    except SchemeRAGUnavailable:
        dependencies = False
    return {
        "dependencies_available": dependencies,
        "api_key_configured": bool(os.environ.get("GROQ_API_KEY")),
    }


def get_embeddings():
    _TextLoader, _Splitter, HuggingFaceEmbeddings, _FAISS, _ChatGroq = _deps()
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


def build_index():
    TextLoader, RecursiveCharacterTextSplitter, _Embeddings, FAISS, _ChatGroq = _deps()
    embeddings = get_embeddings()
    all_chunks = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    for scheme_name, filename in SCHEME_FILE_MAP.items():
        path = SCHEME_DOCS_FOLDER / filename
        if not path.exists():
            continue
        doc = TextLoader(str(path), encoding="utf-8").load()[0]
        doc.metadata["scheme_name"] = scheme_name
        all_chunks.extend(splitter.split_documents([doc]))
    if not all_chunks:
        raise SchemeRAGUnavailable("No scheme documents are available for Q&A.")
    vectorstore = FAISS.from_documents(all_chunks, embeddings)
    vectorstore.save_local(str(FAISS_INDEX_PATH))
    return vectorstore


def load_index():
    _TextLoader, _Splitter, _Embeddings, FAISS, _ChatGroq = _deps()
    if not FAISS_INDEX_PATH.exists():
        return build_index()
    return FAISS.load_local(
        str(FAISS_INDEX_PATH),
        get_embeddings(),
        allow_dangerous_deserialization=True,
    )


def get_llm():
    _TextLoader, _Splitter, _Embeddings, _FAISS, ChatGroq = _deps()
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise SchemeRAGUnavailable("GROQ_API_KEY is not configured for scheme Q&A.")
    return ChatGroq(model="llama-3.1-8b-instant", api_key=api_key, temperature=0.2)


def ask_scheme_question(scheme_name, question, vectorstore=None):
    if not supports_scheme(scheme_name):
        raise SchemeRAGUnavailable("A local RAG document is not available for this scheme.")
    vectorstore = vectorstore or load_index()
    retriever = vectorstore.as_retriever(
        search_kwargs={"k": 4, "filter": {"scheme_name": scheme_name}}
    )
    chunks = retriever.invoke(question)
    if not chunks:
        return "I don't have enough information in the local scheme documents to answer that."
    context = "\n\n".join(chunk.page_content for chunk in chunks)
    prompt = f"""Answer using ONLY the scheme context below. If the answer is not present, say that the local scheme documents do not contain enough information. Do not invent eligibility.

Context:
{context}

Question: {question}
"""
    return get_llm().invoke(prompt).content


__all__ = [
    "SchemeRAGUnavailable",
    "SCHEME_FILE_MAP",
    "ask_scheme_question",
    "build_index",
    "load_index",
    "rag_status",
    "supports_scheme",
]
