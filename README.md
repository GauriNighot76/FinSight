# FinSight

Financial analytics and transaction intelligence for MSMEs.

## Run

```powershell
python -m pip install -r requirements.txt
python -m streamlit run finsight_app/app.py
```

## Government Scheme Assistant

Click **Ask Finny**, the floating FinSight mascot in the bottom-right corner after
selecting a business. Finny stays on screen while you scroll and opens the compact
assistant across workspace pages. Ask in English, Hindi or
Marathi, or override **Auto Detect**. Responses use reviewed official evidence for
PMEGP, MUDRA, CGTMSE, CGSS and Stand-Up India, with visible source links and advisory eligibility wording.
Finny's eligibility answers use the same saved business profile and deterministic
screening engine as Government Schemes, including missing information and failed
rules. Scheme explanations use the separate reviewed official-source catalog;
asking about a scheme does not require a positive screening match. Stand-Up India
information explicitly flags the published scheme term ending in March 2025.
Local rule screening remains on the **Government Schemes** page. General questions
such as “Which government scheme am I eligible for?” are supported; suggestions
remain advisory until full eligibility is confirmed.

Finny uses Groq for conversational help, dashboard terminology, charts, anomalies,
health metrics and recommendations. Auto Detect uses the latest message's language,
so English questions switch back to English after Hindi. Finny understands
Hindi/Hinglish follow-ups and retains six recent turns per business.
Scheme-specific questions go through source-validated retrieval;
missing facts are acknowledged. Recent questions and selected scheme IDs are sent
to Groq for conversational context. Enabled dashboard summaries include calculated
metrics, anomaly counts and recommendation text; raw transactions and credentials
are excluded. Disable this sharing under **Language, profile & privacy** to receive
general explanations only. The multiline composer submits with **Ask Finny**.

Copy `.env.example` to `.env` and set `LLM_API_KEY` (Groq); the existing
`GROQ_API_KEY` name is also supported. `LLM_MODEL` defaults to
`openai/gpt-oss-20b`. Local `.env` edits take effect on the next question without
restarting Streamlit. `GROQ_API_KEY` takes precedence over `LLM_API_KEY` if both
are present. Never commit `.env` or keys. The assistant sends the
question and source passages to Groq; business profiles filter results locally.

Optional multilingual semantic ranking:

```powershell
python -m pip install -r requirements-rag.txt
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"
```

Core FinSight needs neither these packages nor model weights. Without them the
assistant uses conservative multilingual keyword retrieval. This fast path is also
the default when ML packages are installed, so loading Torch cannot stall a normal
chat submission. Set `RAG_USE_EMBEDDINGS=1` only after downloading and benchmarking
the model to explicitly enable semantic ranking. Without an API key,
or during provider outages, it shows an availability message; analytics and reports
remain independent. No separate translation API is required: supported facts have
stored Hindi/Marathi convenience translations. Refer to official sources for
authoritative wording.

Only fresh reviewed HTTPS government records can support assistant results.
URLs and factual claims come from stored metadata, never model-authored text.
Sources expire after 90 days; no matching fresh evidence produces an abstention.
The initial catalog is deliberately small and cannot answer every scheme question.

Troubleshooting: the assistant distinguishes missing/invalid keys, inaccessible
models, rate limits and connection failures. If a model is unavailable, set
`LLM_MODEL` to a model your Groq account can access. Pre-download
model weights for semantic ranking; review expired records for missing results.
Do not reuse the legacy FAISS index. See [implementation and source maintenance](docs/rag_implementation.md).

```powershell
python -m pytest tests/test_rag.py -q
python -m services.rag.evaluate
# Requires downloaded optional model:
python -m services.rag.evaluate --semantic
python -m pytest -q
```
