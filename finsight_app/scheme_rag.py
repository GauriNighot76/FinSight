"""Optional, safely degraded RAG for the bundled scheme documents."""

import os
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
ENV_PATH = MODULE_DIR.parent / ".env"
SCHEME_DOCS_FOLDER = MODULE_DIR / "scheme_docs"

# maps the scheme_name shown in the UI to its source file, so retrieval
# only searches the ONE scheme the user clicked -- not all schemes mixed together
SCHEME_FILE_MAP = {
    "PMEGP (Service/Business)": "pmegp.txt",
    "CGTMSE Collateral-Free Loan": "cgtmse.txt",
    "Mudra Loan - Kishor": "mudra_kishor.txt",
}


class RAGUnavailableError(RuntimeError):
    """Safe error for missing optional dependencies, documents, or configuration."""


def _dependencies():
    try:
        from langchain_community.document_loaders import TextLoader
        from langchain_community.vectorstores import FAISS
        from langchain_groq import ChatGroq
        from langchain_huggingface import HuggingFaceEmbeddings
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as error:
        raise RAGUnavailableError(
            "Optional RAG packages are not installed. Core FinSight features remain available."
        ) from error
    return TextLoader, FAISS, ChatGroq, HuggingFaceEmbeddings, RecursiveCharacterTextSplitter


def build_index():
    """Build in memory from trusted local text; never deserialize a pickle index."""
    TextLoader, FAISS, _chat, HuggingFaceEmbeddings, RecursiveCharacterTextSplitter = _dependencies()
    missing = [name for name in SCHEME_FILE_MAP.values() if not (SCHEME_DOCS_FOLDER / name).is_file()]
    if missing:
        raise RAGUnavailableError("Bundled scheme documents are unavailable.")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    all_chunks = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    for scheme_name, filename in SCHEME_FILE_MAP.items():
        loader = TextLoader(str(SCHEME_DOCS_FOLDER / filename), encoding="utf-8")
        doc = loader.load()[0]
        doc.metadata["scheme_name"] = scheme_name  # tags every chunk with its scheme
        chunks = splitter.split_documents([doc])
        all_chunks.extend(chunks)

    return FAISS.from_documents(all_chunks, embeddings)


def load_index():
    return build_index()


def get_llm():
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH, override=False)
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RAGUnavailableError("Set GROQ_API_KEY to enable optional scheme questions.")
    _loader, _faiss, ChatGroq, _embeddings, _splitter = _dependencies()
    return ChatGroq(model="llama-3.1-8b-instant", api_key=key, temperature=0.2)


def ask_scheme_question(scheme_name, question, vectorstore, llm=None):
    if scheme_name not in SCHEME_FILE_MAP:
        return "I don't have enough information to answer that about this scheme."
    if not isinstance(question, str) or not question.strip():
        return "Enter a question about the selected scheme."
    # metadata filter -- only retrieve chunks belonging to THIS scheme,
    # so a question about PMEGP can't accidentally pull CGTMSE text
    retriever = vectorstore.as_retriever(
        search_kwargs={"k": 4, "filter": {"scheme_name": scheme_name}}
    )
    chunks = retriever.invoke(question)

    if not chunks:
        return "I don't have enough information to answer that about this scheme."

    context = "\n\n".join(c.page_content for c in chunks)
    prompt = f"""Answer the question using ONLY the context below. If the context doesn't contain the answer, say "I don't have that information in the scheme documents" instead of guessing.

Context:
{context}

Question: {question}
"""
    llm = llm or get_llm()
    try:
        response = llm.invoke(prompt)
    except RAGUnavailableError:
        raise
    except Exception as error:
        raise RAGUnavailableError(
            "The scheme question service is temporarily unavailable."
        ) from error
    return response.content
