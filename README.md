# FinSight

FinSight is a Streamlit financial analytics application for MSMEs. The UI
calls the Python service layer, which authenticates the user, enforces business
and account access, validates uploaded records, and reads/writes SQLite data.

## Architecture

```text
Streamlit UI
    -> Python services
    -> validation and authorization
    -> database/queries.py
    -> database/db.py
    -> SQLite (data/finsight.db)
```

The financial dashboard and PDF report use accepted transactions returned by
the backend analytics/report services. They do not use the static demo
transaction CSV files as their financial source.

## Requirements

- Python 3.10 or newer
- SQLite (included with Python)
- Internet access only if the optional scheme-chat dependencies are used

## Installation

From the repository root:

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Database initialization

The database is created or upgraded without deleting existing data when the
application starts. It can also be initialized explicitly:

```bash
python -m database.db
```

The database file is created at `data/finsight.db` and is intentionally ignored
by Git. Do not commit real financial, medical, banking, or other personal data.

## Run the application

Run this command from the repository root so the package imports and project
paths are consistent:

```bash
python -m streamlit run finsight_app/app.py
```

The application supports:

1. Account registration and login.
2. Business creation and selection.
3. Automatic creation of a primary data source; additional sources are optional.
4. CSV, XML, or canonical JSON ingestion with automatic column detection,
   a five-row preview, confidence scores, and manual mapping overrides.
5. Validation, duplicate detection, and atomic persistence.
6. Database-backed financial analytics.
7. Business-health and anomaly results through the backend services.
8. Database-backed PDF report generation.

## Business setup and import readiness

Creating a business now creates and activates its internal ledger link and its
primary data source in one guided step. A business owner does not wait for a
person to approve routine imports. Existing businesses created by older builds
can use **Finish setup** once; ownership is verified by the backend before the
link is activated.

If Import says the business relationship is unavailable, open **Setup**, select
that business, click **Finish setup**, and return to Import. This replaces an
old pending request without deleting the business or its data sources.

## Optional configuration

Create a local `.env` only when you need optional integrations. Never commit it.

```text
GROQ_API_KEY=your_key_here
GOOGLE_CLIENT_ID=your_client_id_here
```

The scheme question-and-answer feature requires the RAG dependencies and a
valid Groq key. Install it separately with
`python -m pip install -r requirements-rag.txt`; the normal dashboard does not
need these large AI packages. Google sign-in additionally requires a correctly configured
Google OAuth client and frontend ID-token flow.

## Tests

Run the full suite from the repository root:

```bash
python -m pytest tests -q
```

Useful targeted commands are:

```bash
python -m pytest tests/test_db.py tests/test_queries.py -q
python -m pytest tests/test_module4_* tests/test_module5_* -q
python -m pytest tests/test_module6_health.py tests/test_module7_*.py -q
```

Tests use isolated temporary SQLite databases. They do not require the local
runtime database to contain real data.

## Flexible transaction imports

CSV imports support comma, semicolon, tab, and pipe delimiters and common text
encodings. XML imports support repeated, flat transaction elements. FinSight
scores header names together with sample values, preselects likely date,
amount/debit/credit, direction, description, category, reference, payment,
counterparty, and balance columns, and lets the uploader correct every mapping
before ingestion.

The importer will not guess whether an all-positive amount is income or expense
when the file supplies no direction/type or separate debit and credit columns.
In that case, select the correct direction column or provide a signed amount
export. Uploads are limited to 5 MB and still pass through the strict canonical
validator before any database write.

## First administrator (optional, maintenance only)

Administrators are not needed for normal imports. The first administrator can
only be bootstrapped from the host computer, only when no active administrator
exists, and only with a long secret kept outside source control. Set both
values to the same secret, then run:

```powershell
$env:FINSIGHT_ADMIN_BOOTSTRAP_SECRET="replace-with-at-least-24-random-characters"
python -m automation.admin_cli admin@example.com
```

The command prompts for the secret. Later role changes should be handled by a
proper deployment identity provider, not by public sign-up.

## Recovering from imports made by an older build

Old releases could skip legitimate same-date/same-amount rows and could retain
partial repeated imports. Inspect the current counts first:

```powershell
python -m automation.reset_imported_transactions
```

To start analytics again from a clean import, run the explicit reset below.
It preserves users, businesses, and data sources and creates a timestamped
database backup before removing imported transactions:

```powershell
python -m automation.reset_imported_transactions --confirm RESET-IMPORTED-TRANSACTIONS
```

## Data and security notes

- Passwords are stored as bcrypt hashes.
- Session tokens are generated securely and only their SHA-256 lookup hashes
  are stored in the database.
- Business and account access is checked in the backend services.
- SQL statements use parameters rather than string concatenation.
- Financial amounts in the modern ingestion/analytics path use integer minor
  units, such as paise for INR.
- Raw uploaded files are not intended to be retained as permanent uploads, but
  accepted transaction records and required metadata are persisted in SQLite.
- The current project is a tested controlled demo, not a production deployment.
