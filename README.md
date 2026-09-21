# FinSight

FinSight is an academic financial analytics and transaction-intelligence application for small businesses. The verified core uses Python, Streamlit, SQLite, Pandas, integer minor units for canonical transaction amounts, deterministic duplicate detection, and rule-based business-health recommendations.

The application is an examination-ready MVP, not a production banking system.

## Implemented features

- Local registration, bcrypt password hashing, sign-in, sign-out, and revocable sessions.
- Business memberships and active financial accounts with backend authorization.
- Owner-proposed, independently administrator-approved registry relationships.
- CSV and canonical JSON normalization, validation, atomic ingestion, and duplicate detection.
- Account-scoped income, expense, cash-flow, trend, category, and payment-mode analytics.
- Deterministic rule-based health metrics, anomalies, and recommendations.
- Authenticated selected-business PDF reporting.
- A clearly separated synthetic government-scheme demonstration.
- Optional scheme-document question answering through Groq and local embeddings.

## Requirements and supported Python

- Windows 10 or 11
- Git
- Python **3.12** (verified in the final development environment)

Python 3.14 has **not** been verified. If `py --version` reports 3.14, install Python 3.12 and use `py -3.12` in the commands below. Do not assume optional FAISS, Torch, or sentence-transformers packages support an untested Python version.

## Windows installation

```powershell
git clone https://github.com/GauriNighot76/FinSight.git
cd FinSight
git switch submission-fix
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The root `requirements.txt` is the authoritative core dependency list.

### Optional RAG installation

The main application works without RAG packages and without a Groq key.

```powershell
python -m pip install -r requirements-rag.txt
Copy-Item .env.example .env
```

Set `GROQ_API_KEY` in your environment or `.env` only on your own machine. Never commit `.env`.

## Database initialization

FinSight creates `data/finsight.db` and applies the schema automatically when the app starts. Initialization is idempotent and foreign keys are enabled for every application connection.

To initialize explicitly:

```powershell
python -m database.db
```

Set `FINSIGHT_DATABASE_PATH` to use a different SQLite file. Project paths are resolved independently of the current working directory.

## Synthetic demonstration data

Seed only a new or demo-only database:

```powershell
python scripts\seed_demo.py
```

The script refuses to seed a database containing non-demo users. It is idempotent: the first run inserts the sample transactions, while later runs report them as duplicates.

Local demonstration credentials:

- Owner: `owner@demo.finsight.local`
- Password: `FinSightDemo2026!`

These credentials are synthetic and local-only. Do not reuse them for a real account.

## Run FinSight

From the repository root:

```powershell
python -m streamlit run finsight_app\app.py
```

The entry point also works when invoked by absolute path from another current directory.

## Run tests

```powershell
python -m pytest -q
python -m compileall database services finsight_app scripts
```

On the final Windows machine, `scripts\verify_windows.ps1` performs an isolated
Python 3.12 install, complete test run, compilation, temporary database seed, and
headless Streamlit health check. The README click-through must still be completed
manually because an HTTP health response does not verify interactive browser output.

## Architecture

```text
Streamlit UI
  → authentication and setup services
  → CSV normalizer and ingestion service
  → SQLite canonical identities and legacy ledger metadata
  → analytics service
  → rule-based health and decision support
  → authenticated report service and PDF adapter
```

The important data flow is:

```text
Registration → users and sessions
Business → owner membership
Registry request → independent administrator approval
Account → authorized business account
CSV → normalization → validation → identity classification → atomic persistence
Analytics/health/report → selected business + account + inclusive date range
```

## Module guide

| Area | Main files |
| --- | --- |
| Database | `database/db.py`, `database/schema.sql`, `database/queries.py` |
| Authentication | `services/auth_service.py`, `security/passwords.py` |
| Business/account setup | `services/business_service.py`, `services/account_service.py`, `services/bridge_service.py` |
| Ingestion | `services/csv_normalizer.py`, `services/ingestion_validation.py`, `services/ingestion_identity.py`, `services/ingestion_service.py` |
| Analytics | `services/analytics_service.py` |
| Health/recommendations | `services/business_health_service.py`, `services/decision_support_service.py` |
| Reports | `services/report_service.py`, `finsight_app/pdf_generator.py` |
| User interface | `finsight_app/app.py` and the `*_ui.py` adapters |
| Optional scheme RAG | `finsight_app/scheme_rag.py`, `finsight_app/scheme_docs/` |

## Security notes

- Passwords are bcrypt hashes; plaintext passwords are not stored.
- Session tokens are stored only as SHA-256 hashes.
- Business and account access is checked in backend services.
- Bridge approval requires an administrator different from the proposing owner.
- Canonical transaction identity and analytics amounts use integer minor units.
- SQL values are parameterized.
- Expected UI errors are sanitized.
- The RAG feature rebuilds its index from bundled trusted text and does not enable dangerous FAISS pickle deserialization.
- Uploaded data, tokens, passwords, and API keys must not be logged.

The legacy general-ledger compatibility table still contains a `REAL` amount mirror. Exact ingestion identity and analytics use `amount_minor INTEGER`; the legacy mirror is documented technical debt and should be migrated separately rather than treated as authoritative.

## Examination demonstration

1. Run `python scripts\seed_demo.py`, then start Streamlit.
   - Expected: seed reports 12 accepted records on the first run.
   - Viva: “The seed uses synthetic data and the normal validation and ingestion services.”
2. Sign in with the demo owner credentials.
   - Expected: Setup, Transactions, and Analytics tabs appear.
   - Viva: “Passwords are hashed and sessions are validated on the backend.”
3. Open **Setup**.
   - Expected: the synthetic business, verified registry relationship, and account appear.
   - Viva: “Ingestion requires both membership authorization and independent registry approval.”
4. Open **Transactions** and upload `sample_data\valid_transactions.csv`.
   - Expected: 12 duplicates after seeding, proving deterministic duplicate protection.
   - Viva: “A repeated upload is detected without duplicating financial records.”
5. Upload `sample_data\invalid_transactions.csv`.
   - Expected: a safe, specific validation message and no committed rows.
   - Viva: “Invalid rows fail before financial persistence and errors do not expose internals.”
6. Open **Analytics and reports** and choose `2026-03-01` through `2026-09-20`.
   - Expected: authenticated totals, trends, categories, payment modes, and account summary.
   - Viva: “Every value is scoped to the selected business, account, currency, and date range.”
7. Click **Generate health, recommendations and report**.
   - Expected: health score, deterministic recommendations, and PDF download.
   - Viva: “Anomaly detection is rule-based; it is not presented as machine learning.”
8. Download the selected-business PDF.
   - Expected: its business, period, and totals match visible analytics.
   - Viva: “The report reuses the authorized analytics and health services.”
9. Review **Synthetic scheme-matching demonstration**.
   - Expected: it is explicitly separated from authenticated analytics.
   - Viva: “These assumed profile values and bundled CSVs are only an academic scheme demo.”
10. Ask a scheme question, or demonstrate the friendly unavailable message without optional configuration.
    - Viva: “RAG is optional, restricted to bundled scheme documents, and cannot crash the core application.”

## Troubleshooting

- `No module named ...`: activate `.venv` and run from the repository root with `python -m streamlit`.
- Python 3.14 installation failure: use Python 3.12; 3.14 is not verified.
- “Awaiting registry verification”: an administrator must approve the owner’s request, or use the seeded demo business.
- Empty analytics: select the sample-data date range (`2026-03-01` to `2026-09-20`).
- RAG unavailable: install `requirements-rag.txt` and configure `GROQ_API_KEY`; all non-RAG pages remain usable.
- Seed refusal: do not overwrite an existing user database. Back it up and use a new database path.

## Known limitations

- SQLite is the current database.
- CSV and canonical JSON are supported; OCR and bank integrations are not implemented.
- At most 1,000 canonical records are accepted per ingestion request.
- Anomaly detection and recommendations are deterministic rules, not machine learning.
- The legacy ledger retains a floating-point compatibility mirror, while authoritative analytics use integer minor units.
- Government-scheme matching is a separate synthetic demonstration with assumed profile values.
- RAG covers only the supplied scheme documents. Scheme results are informational and must be checked on official portals.
- Large-scale performance such as five million records has not been validated.
- Production readiness, bank-grade security, and automatic medical-business detection are not claimed.
- Windows execution must still be performed on the student's final machine.

## Current state versus target

The verified scope is a local academic MVP that demonstrates secure login, authorized setup, controlled ingestion, analytics, rule-based insights, and reporting. Multi-tenant production operations, automated bank feeds, full government-portal integration, and unrestricted scalability remain aspirational.
