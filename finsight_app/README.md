# FinSight Scheme Matcher - Demo App

## Setup (on your machine, in this folder)

1. Create a `.env` file in this folder with your Groq key (same key you used in rag_support_bot):
```
GROQ_API_KEY=your_key_here
```

2. Install dependencies:
```
pip install -r requirements.txt
```

3. Run the app:
```
streamlit run app.py
```

## What each file does

- `kpi_engine.py` - reads the 4 transaction CSVs, computes revenue/expenses/profit (no AI)
- `eligibility_engine.py` - checks the business against schemes.csv, returns matches + reasons (no AI)
- `scheme_rag.py` - the AI part. Chunks scheme_docs/*.txt, embeds with MiniLM, stores in FAISS,
  answers questions using ONLY retrieved chunks via Groq/Llama
- `pdf_generator.py` - builds the downloadable PDF report
- `app.py` - the Streamlit page tying all of the above together

## First run note

The first time you click "Ask a question", it will build the FAISS index from the
scheme_docs folder (takes a few seconds) and cache it to disk as faiss_scheme_index/.
Every run after that loads instantly from the cached index.

## If the RAG chat doesn't work in the demo

The KPIs, eligibility matching, and PDF download all work completely independently of
the RAG/API piece -- if the API has an issue on demo day, everything except the chat
still works and is worth showing.
