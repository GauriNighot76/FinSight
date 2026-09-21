# FinSight Streamlit application

Use the repository-root [README](../README.md) for Python 3.12 installation, tests, and the examination flow. Run from the repository root:

```powershell
python -m streamlit run finsight_app\app.py
```

Core authentication, business/account setup, CSV ingestion, analytics, rule-based health/recommendations, and PDF summaries work without optional RAG packages. New businesses receive active internal ledger mappings automatically; no administrator approval is required.

The scheme-matching demonstration uses bundled synthetic coffee-shop data, separately labeled from authenticated business analytics. RAG builds its index in memory from trusted bundled scheme documents; it does not load a saved pickle index. Set `GROQ_API_KEY` in the environment or repository-root `.env` and install the root `requirements-rag.txt` only if demonstrating scheme questions. Live RAG depends on network/model availability.
