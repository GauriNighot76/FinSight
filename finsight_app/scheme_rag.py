import os
from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_groq import ChatGroq

SCHEME_DOCS_FOLDER = "scheme_docs"
FAISS_INDEX_PATH = "faiss_scheme_index"

# maps the scheme_name shown in the UI to its source file, so retrieval
# only searches the ONE scheme the user clicked -- not all schemes mixed together
SCHEME_FILE_MAP = {
    "PMEGP (Service/Business)": "pmegp.txt",
    "CGTMSE Collateral-Free Loan": "cgtmse.txt",
    "Mudra Loan - Kishor": "mudra_kishor.txt",
}


def get_embeddings():
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


def build_index():
    embeddings = get_embeddings()
    all_chunks = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    for scheme_name, filename in SCHEME_FILE_MAP.items():
        loader = TextLoader(f"{SCHEME_DOCS_FOLDER}/{filename}")
        doc = loader.load()[0]
        doc.metadata["scheme_name"] = scheme_name  # tags every chunk with its scheme
        chunks = splitter.split_documents([doc])
        all_chunks.extend(chunks)

    vectorstore = FAISS.from_documents(all_chunks, embeddings)
    vectorstore.save_local(FAISS_INDEX_PATH)
    print(f"[RAG] Indexed {len(all_chunks)} chunks from {len(SCHEME_FILE_MAP)} schemes")
    return vectorstore


def load_index():
    if not os.path.exists(FAISS_INDEX_PATH):
        return build_index()
    embeddings = get_embeddings()
    return FAISS.load_local(FAISS_INDEX_PATH, embeddings, allow_dangerous_deserialization=True)


def get_llm():
    return ChatGroq(model="llama-3.1-8b-instant", api_key=os.environ.get("GROQ_API_KEY"), temperature=0.2)


def ask_scheme_question(scheme_name, question, vectorstore):
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
    llm = get_llm()
    response = llm.invoke(prompt)
    return response.content
