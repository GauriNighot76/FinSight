# Government Scheme Assistant

## Audit before modification

The router in `finsight_app/app.py` called `schemes_ui.render_government_schemes`.
That page ran the CSV eligibility engine, then offered per-scheme Q&A through
`scheme_rag.py`. The adapter imported five LangChain integrations lazily, used
English-only MiniLM embeddings, loaded FAISS with dangerous deserialization,
and rendered free-form Groq output. Chunks retained a name but no validated
official URL, source freshness, or claim provenance. Two source notes included
commercial bank/finance summaries. No `dashboard_ui.py` exists in this checkout.
The root dependencies were already independent of RAG; the nested requirements
still installed unpinned LangChain, FAISS and transformer packages.

## New boundary

UI → language selection → reviewed catalog → conservative multilingual hybrid
retrieval → deterministic profile filtering → Groq structured evidence selection
→ ID/citation validation → localized catalog facts → one result with source links.

The assistant opens from the fixed bottom-right **Ask Finny** mascot on every
authenticated business workspace page. Its compact panel keeps the last question
and source-backed answer across open/close actions; answers are scoped by business.
The launcher is fixed to the main viewport's right edge and remains available
with the sidebar collapsed. A native Streamlit popover portals the chat panel
above the mascot; its portal layer is raised above the sidebar. No empty footer
band is created.
Finny uses a local SVG asset, supports keyboard focus and reduced motion, and has
a smaller layout on narrow or short screens.
The original local CSV screening remains a separate, explicitly labelled tool;
its historical data is not used as verified assistant evidence. Financial services,
database schemas, reports and analytics are unchanged. Profiles only filter locally.
No raw profile, transaction, authentication or session data is sent to Groq.

The model selects fact IDs rather than writing factual prose. Unknown IDs, cross-
scheme citations, URLs or additional generated fields invalidate the response.
This intentionally conservative implementation can answer only catalog-supported
facts; it is not unrestricted conversational advice. Hindi/Marathi are convenience
translations stored with the same source records, not authoritative government text.
Automatic Devanagari language detection is heuristic; manual override is available.

## Sources and maintenance

The initial three records were checked on 2026-09-24 against:

- https://www.pib.gov.in/newsite/archiveContent.aspx?lang=2&reg=48&relid=286631
- https://financialservices.gov.in/pradhan-mantri-mudra-yojana-pmmy

Records expire after 90 days and fail closed on hash or metadata mismatches.
To refresh, a maintainer must review the linked official page, edit supported facts
and translations, update source/verification dates, and recalculate `content_hash`
using `services.rag.repository.content_hash`. Do not advance verification dates
without reviewing the source. Updated passages automatically change the vector
cache key. There is no user URL crawler, automatic refresh job, or pickle index.

## Evaluation limits

`tests/fixtures/rag_eval.json` contains 32 direct-name, discovery, multilingual,
negative and adversarial retrieval cases. The lexical gate accepts a recognized
name, supported discovery concepts, or an explicit government-scheme/eligibility
question in English, Hindi or Marathi. General eligibility questions retrieve the
reviewed catalog before profile filtering; they do not assert personal eligibility.
Semantic ranking cannot bypass the gate. The rules are evaluated by expected-ID
and provider-invocation tests. They do not
establish production recall on the entire Indian government scheme catalog.

Optional multilingual E5 ranks the gated candidates with normalized embeddings;
the model uses `query:`/`passage:` prefixes and must be downloaded before requests.
No claim is made that this model outperforms alternatives until an actual model
benchmark is run. Offline tests verify multilingual lexical fallback, not semantic
embedding quality or live provider response latency. Python 3.12 installation
remains unverified.

## Groq failure correction (2026-09-24)

Live reproduction returned HTTP 403 with urllib's default request headers and
`model_not_found` for the previous `llama-3.3-70b-versatile` configuration after
setting an application User-Agent. The account's model-list endpoint confirmed
`openai/gpt-oss-20b` is accessible. It is now the default, and a live call with
“Which government scheme am I eligible for?” returned validated scheme IDs.

Requests identify the application, bound output sizes and timeouts, and reject
truncated JSON. Safe error categories distinguish authentication, model access,
quota and connectivity issues without logging keys or provider response bodies.
Configuration is read directly from `.env` on each request, so correcting it does
not leave old dotenv values cached in the Streamlit process environment.
