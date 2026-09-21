# FinSight

FinSight is an academic financial analytics and transaction-intelligence application for small businesses. The verified core uses Python, Streamlit, SQLite, Pandas, integer minor units for canonical transaction amounts, deterministic duplicate detection, and rule-based business-health recommendations.

The application is an examination-ready MVP, not a production banking system.

## Implemented features

- Local registration, bcrypt password hashing, sign-in, sign-out, and revocable sessions.
- Business memberships and active financial accounts with backend authorization.
- Automatic internal registry mappings for self-service business onboarding.
- CSV and canonical JSON normalization, validation, atomic ingestion, and duplicate detection.
- Account-scoped income, expense, cash-flow, trend, category, and payment-mode analytics.
- Deterministic rule-based health metrics, anomalies, and recommendations.
- Authenticated selected-business PDF reporting.
- A clearly separated synthetic government-scheme demonstration.
- Optional scheme-document question answering through Groq and local embeddings.

## Requirements and supported Python

- Windows 10 or 11
- Git
- Python **3.12** (clean core install and tests verified on Linux; verify Windows on the exam machine)

The pinned environment targets Python 3.12; Python 3.11 is not supported by this lockfile. Python 3.14 has **not** been verified. If `py --version` reports 3.14, install Python 3.12 and use `py -3.12` in the commands below. Do not assume optional FAISS, Torch, or sentence-transformers packages support an untested Python version.

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
Business → active owner membership + active internal registry mapping (one transaction)
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
- Normal onboarding needs no administrator. An active internal mapping remains mandatory for ingestion; business/account authorization is unchanged.
- Canonical transaction identity and analytics amounts use integer minor units.
- SQL values are parameterized.
- Expected UI errors are sanitized.
- The RAG feature rebuilds its index from bundled trusted text and does not enable dangerous FAISS pickle deserialization.
- Uploaded data, tokens, passwords, and API keys must not be logged.

The legacy general-ledger compatibility table still contains a `REAL` amount mirror. Exact ingestion identity and analytics use `amount_minor INTEGER`; the legacy mirror is documented technical debt and should be migrated separately rather than treated as authoritative.

## Examination demonstration

1. Complete the Python 3.12 installation above, then run `python -m streamlit run finsight_app\app.py`.
2. Register a new user and sign in. No demo seed or administrator is required.
3. In **Setup**, create **ABC Traders**. The business, active Owner membership, legacy registry row, and active internal mapping are created together.
4. Create a bank account in INR with opening balance `10000.00`.
5. In **Transactions**, select that business/account and upload `sample_data\valid_transactions.csv`, then click **Ingest transactions**. Expect 12 inserted rows.
6. Submit the same file again (or `sample_data\duplicate_transactions.csv`). Expect 0 inserted and 12 duplicates.
7. Upload `sample_data\invalid_transactions.csv`. Expect a readable validation error and no changes to saved transactions.
8. In **Analytics and reports**, select the same business/account and dates **2026-03-01 through 2026-09-20**. Expect income **INR 371,000**, expenses **INR 125,000**, net cash flow **INR 246,000**, and **12 transactions**.
9. Click **Generate health, recommendations and report**. Review the rule-based health score and recommendations, then download the selected-business PDF. Its financial totals must match the screen. The PDF is a financial summary; detailed recommendations are displayed in the app.
10. Optionally review the clearly separate synthetic scheme demonstration. Missing RAG packages/key should produce a friendly message.
11. Sign out. Sign in as a second registered user and confirm the first user's business is not listed.

For an optional pre-populated demo, the seed command above follows the same self-service backend flow. It does not create an administrator. Repeat seeding detects duplicates.

## Automatic onboarding and existing databases

When a user creates a business, FinSight creates an active owner membership and automatically establishes the internal registry compatibility mapping required by the legacy ledger. Normal business onboarding does not require administrator approval. All four rows share one database transaction; a failure rolls them all back.

Startup applies an idempotent compatibility backfill to active businesses with exactly one active owner whose user account is active:

- No mapping history: create a new internal registry identity and active mapping.
- Exactly one pending mapping: activate only if its proposer and legacy registry owner are that owner and the registry is not referenced by another bridge.
- Active mappings: leave unchanged.
- Rejected, disabled, conflicting, or ambiguous histories: leave unchanged for exceptional maintenance.

No legacy business is matched by name, and no financial rows are rewritten. Back up an existing database before updating. Legacy registry names include the main business ID to satisfy their historical per-owner uniqueness constraint without merging same-name businesses.

Historical `proposed_by_user_id`, `verified_by_user_id`, and `verified_at` columns are retained. For automatic activation the creator is recorded in both user fields. These fields now describe internal activation, not independent human approval. The administrator role and legacy maintenance APIs remain, but are absent from normal setup.

## Troubleshooting

- `No module named ...`: activate `.venv` and run from the repository root with `python -m streamlit`.
- Python 3.14 installation failure: use Python 3.12; 3.14 is not verified.
- Internal mapping unavailable: restart the updated app to apply safe compatibility backfills. Rejected/disabled or ambiguous legacy mappings remain restricted and require exceptional maintenance; ordinary new businesses are ready immediately.
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
