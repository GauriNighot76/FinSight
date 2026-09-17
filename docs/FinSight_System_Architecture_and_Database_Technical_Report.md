# SYSTEM ARCHITECTURE & TECHNICAL DOCUMENTATION REPORT

## FinSight Database & Backend Database Architecture

**Prepared For:** FinSight Project / Engineering Team
**Prepared By:** Backend Development Team
**Date:** September 2026
**Document Version:** v1.0.0

> **Evidence boundary.** This report is based on the checked-out FinSight
> repository, its Git history, source files, tests, and project documentation.
> The inspected checkout is
> /workspace/scratch/d98ed89b1326/finsight_attached_query.nizS1X, branch
> module5-analytics, HEAD 74d3e619145ed6bd41fce9952dba28936f1c6d79. Before this
> report was created the working tree was clean and the project virtual
> environment ran 498 tests with 498 passes, zero failures, zero skips, and no
> collection errors. Statements are labelled IMPLEMENTED, TESTED, DESIGNED,
> PLANNED, DEFERRED, BLOCKED, or UNRESOLVED where that distinction matters.

## Status vocabulary

- **IMPLEMENTED** — present in the current source/schema.
- **TESTED** — covered by an automated test that passed in this checkout.
- **DESIGNED** — described in a design/decision document or interface contract,
  but not necessarily present in code.
- **PLANNED** — identified as future work without an implementation.
- **DEFERRED** — intentionally left out of the current scope.
- **BLOCKED** — cannot safely proceed until a stated dependency/evidence gate is
  resolved.
- **UNRESOLVED** — repository evidence is incomplete or conflicting.

# 1. Executive Summary

FinSight is a Python and Streamlit financial-analysis application for small
businesses. The backend provides authenticated users, business memberships,
financial accounts, transaction ingestion, analytics, health indicators,
reports, decision support, and deterministic CSV normalization. SQLite is the
database engine. SQL is isolated in database/queries.py, while service modules
enforce validation, authorization, financial rules, and safe public responses.

The database evolved incrementally. Module 0 established the legacy SQLite
schema and query layer. Modules 1–3 added stronger identity, session,
business-membership, and account boundaries while preserving legacy financial
tables. Module 4 added an explicit bridge from modern businesses to legacy
registry businesses, canonical validation, uploader/account context,
cryptographic transaction identity, duplicate handling, atomic batch writes,
rollback, retries, and safe ingestion-attempt audit data. Modules 5–7 are
present in this checkout: read-only analytics, health/anomaly interpretation,
report adapters, and decision-support recommendations. The CSV normalizer is a
separate preprocessing layer that feeds the unchanged canonical ingestion
contract.

Important security improvements are server-side session validation, BCrypt
password hashing, hashed session tokens, membership-based tenant authorization,
owner/manager restrictions for ingestion and management, foreign keys, and
parameterized SQL. Important data-integrity improvements are exact integer
minor-unit values for new account/identity data, deterministic canonical
identities independent of uploader, duplicate classification, and atomic
ingestion transactions.

The principal architectural problem was the coexistence of the Module 0
business_registry boundary and the Module 2 businesses/membership boundary.
Replacing the legacy table would have broken existing financial queries, so
Module 4 introduced an explicit, verified bridge. A second problem was that the
legacy ledger uses floating-point REAL amounts and has owner-oriented
semantics; the new identity table supplies exact, uploader-independent
idempotency without changing that legacy contract.

The current repository is a controlled non-production implementation.
Automated verification is strong: the complete suite currently reports 498
passed tests. The controlled demo mapping, source token, and INR account
evidence are documented and tested, but no production customer mapping is
asserted. The legacy Streamlit demo still has operational limitations
(relative data paths, optional RAG configuration, and PDF layout/dependency
concerns), and the root README is empty. OTP workflow, production document
intelligence, and production deployment/backup operations are not verified as
implemented.

Module progression:

| Stage | Scope | Current status |
|---|---|---|
| Module 0 | Database foundation | IMPLEMENTED, TESTED |
| Module 1 | Authentication and user identity | IMPLEMENTED, TESTED |
| Module 2 | Business ownership and membership | IMPLEMENTED, TESTED |
| Module 3 | Financial accounts | IMPLEMENTED, TESTED |
| Module 4 | Canonical ingestion and controlled persistence | IMPLEMENTED, TESTED for controlled demo |
| Module 5 | Financial analytics and Streamlit analytics page | IMPLEMENTED, TESTED |
| Module 6 | Business health and deterministic anomalies | IMPLEMENTED, TESTED |
| Module 7 | Reporting and decision support adapters | IMPLEMENTED, TESTED |
| CSV layer | CSV normalization and upload wiring | IMPLEMENTED, TESTED |

# 2. System Overview & Requirements

## 2.1 System Overview

FinSight needs persistent, structured financial data so that a business can
revisit transactions, account balances, trends, categories, and health results
instead of calculating them only in a browser session. Financial data is
particularly sensitive: a transaction must belong to the right tenant and
account, duplicate uploads must not inflate totals, and amounts must not drift
because of binary floating-point arithmetic.

The current logical flow is:

1. A user signs up or signs in.
2. The application creates/validates a session and stores only the raw token in
   the Streamlit session state.
3. The service layer validates the session and the active business membership.
4. Management services create businesses/accounts and enforce owner/manager
   permissions.
5. A canonical JSON payload, or CSV normalized into that shape, is validated.
6. Module 4 resolves the modern business, account, explicit legacy bridge, and
   legacy owner; it classifies identities and atomically writes accepted
   transactions.
7. Module 5 reads only accepted identity rows and produces exact analytics.
8. Modules 6 and 7 consume those analytics in memory for health, reports, and
   recommendations.

The Streamlit UI is a client of services. It is not the security authority and
does not execute SQL. The query layer is the only normal location for SQL
against SQLite. The legacy demo area in finsight_app/app.py is a separate
CSV/pandas demonstration path and is not the authoritative Module 4 ledger
boundary.

## 2.2 Functional Requirements

| Requirement | Evidence and status |
|---|---|
| Create a user with a safe public result | services/auth_service.py, tests/test_auth.py; IMPLEMENTED, TESTED |
| Password hashing and verification | security/passwords.py uses BCrypt; IMPLEMENTED, TESTED |
| Login, logout, expiry and revocation | auth_sessions, auth_service.py; IMPLEMENTED, TESTED |
| Session-token protection | Raw token is generated for the client; SHA-256 hash is stored; IMPLEMENTED, TESTED |
| Global application roles | users.role allowlist and require_role; IMPLEMENTED, TESTED |
| User active/disabled status | users.account_status, session/login checks; IMPLEMENTED, TESTED |
| Google identity mapping | provider_identities, google_sign_in, injected-verifier tests; IMPLEMENTED, TESTED for service mapping. Live Google console configuration is UNVERIFIED |
| OTP verification | otp_verifications table exists, but no OTP query/service workflow is present; TABLE IMPLEMENTED, WORKFLOW DEFERRED |
| Business creation | Modern businesses plus owner membership created atomically; IMPLEMENTED, TESTED |
| Membership and business roles | business_memberships owner/manager/member/viewer and service authorization; IMPLEMENTED, TESTED |
| Business active/disabled status | Service and query filters; IMPLEMENTED, TESTED |
| Financial account CRUD/status | financial_accounts and account_service.py; IMPLEMENTED, TESTED |
| Account ownership and currency | Account belongs to modern business; uppercase 3-letter currency and integer opening balance; IMPLEMENTED, TESTED |
| Legacy counterparties, transactions and budgets | Module 0 query functions and regression tests; IMPLEMENTED, TESTED |
| Legacy upload log persistence | pipeline_upload_ingestion_logs table exists, but current query/service API does not expose a complete legacy-log workflow; TABLE IMPLEMENTED, API UNRESOLVED |
| Authentication audit log persistence | authentication_logs and write helper are present; IMPLEMENTED, TESTED indirectly. A read/report API is not present |
| Documents and chunks CRUD | Tables and query helpers exist and are exercised by the smoke query test; IMPLEMENTED, TESTED as CRUD. Full document intelligence is not implemented |
| Canonical validation | ingestion_validation.py; IMPLEMENTED, TESTED |
| Deterministic transaction identity | ingestion_identity.py; IMPLEMENTED, TESTED |
| Authorized atomic ingestion | ingestion_service.py and Module 4 tests; IMPLEMENTED, TESTED for controlled source/demo contract |
| CSV preprocessing | csv_normalizer.py; IMPLEMENTED, TESTED |
| Read-only analytics | analytics_service.py; IMPLEMENTED, TESTED |
| Business health/anomalies | business_health_service.py; IMPLEMENTED, TESTED |
| Reporting/export adapters | report_service.py supports dictionary/JSON/CSV/table/chart-ready structures; IMPLEMENTED, TESTED. PDF export in this service is DEFERRED |
| Decision support | decision_support_service.py deterministic recommendations; IMPLEMENTED, TESTED |
| Production business/account/source mapping | Controlled demo only; PRODUCTION MAPPING BLOCKED |
| Full UI integration for all backend modules | Analytics/ingestion adapters exist, but the legacy demo path remains; PARTIALLY IMPLEMENTED and operationally UNRESOLVED |

## 2.3 Non-Functional Requirements

### Security

**IMPLEMENTED/TESTED:** BCrypt password hashes, hashed session tokens,
session expiry/revocation, active-account checks, business membership
authorization, owner/manager restrictions, sanitized public errors, and
parameterized SQL. Google ID tokens are verified through the Google library
when a client ID is configured.

**UNVERIFIED/DEFERRED:** production secret management, rate limiting, CSRF
controls for a deployed web tier, centralized log retention, key rotation,
backup encryption, and formal compliance certification.

### Data integrity and precision

**IMPLEMENTED/TESTED:** primary/foreign keys, status CHECK constraints,
uniqueness constraints, active-bridge partial unique indexes, canonical hash
uniqueness, source identity uniqueness, exact integer minor-unit values in
account and identity records, and atomic Module 4 writes.

The legacy ledger remains a compatibility projection with amount REAL. There
is no evidence that all historical ledger values have been migrated to minor
units.

### Reliability and compatibility

**IMPLEMENTED/TESTED:** idempotent schema execution, additive users-column
migration, Module 4 rollback/retry semantics, isolated temporary SQLite tests,
and a passing 498-test regression. The schema initializer is deliberately
non-destructive.

### Maintainability and testability

**IMPLEMENTED/TESTED:** service/query separation, pure validation and identity
helpers, bounded public errors, small service APIs, and module-specific pytest
suites.

### PII minimization and auditability

**IMPLEMENTED/TESTED:** account identifiers are masked in account-service
responses; analytics/health/report outputs remove transaction and identity
secrets; payroll employee PII is excluded from Module 4 v1. Ingestion attempts
store safe error codes/messages and uploader/account context.

## 2.4 Module Overview

### Module 0 — Database Foundation

#### Purpose

Provide a persistent SQLite database, a relational schema, and a reusable
query layer for the original FinSight workflow.

#### Database Work

Git history shows the initial project commit had empty database files. Commit
dd5bc78 added the first relational schema; e7e7d24 added the SQLite connection
layer. The current database/schema.sql contains the legacy tables for users,
businesses, counterparties, transactions, budgets, upload logs,
authentication logs, OTP, documents, chunks, sessions, and provider
identities. database/db.py provides connections and initialization;
database/queries.py provides CRUD and summary queries.

#### Why It Was Needed

The application needed a durable relational boundary rather than CSV-only
calculations. A schema also made ownership, constraints, and test fixtures
explicit.

#### How It Works

get_connection() creates the ignored runtime data/finsight.db, sets a
30-second SQLite timeout, returns sqlite3.Row objects, and enables foreign
keys. initialize_database() executes the schema and applies only additive
compatibility changes to old users tables.

#### Security and Data Integrity

Foreign keys are enabled for each connection. Legacy query functions require
the legacy business owner where that was the original contract. SQL values are
bound as parameters.

#### Testing

tests/test_db.py, tests/test_queries.py, and tests/test_module0_regression.py
pass. The full current suite passes.

#### Problems Encountered

The initial repository state contained empty database files, and later modules
needed new identity/security fields without destroying old data.

#### Solutions

The schema and connection layer were added, then expanded through additive
CREATE TABLE IF NOT EXISTS / ALTER TABLE logic and isolated fixtures. Legacy
tables were retained for compatibility.

### Module 1 — Authentication & User Identity

#### Purpose

Authenticate users, protect credentials and sessions, and create a trusted
actor identity for later services.

#### Database Work

users stores a user ID, unique case-insensitive email, contact number,
nullable password hash, secret-answer fields, global role, status, and
timestamps. auth_sessions stores a unique SHA-256 token hash and expiry/
revocation fields. authentication_logs records event type and optional
network metadata. provider_identities maps a provider subject to a local user.
The initializer adds missing username, role, account_status, and updated_at
columns to older Module 0 user tables and preserves existing rows.

#### Why It Was Needed

Financial operations cannot trust an email, user ID, or role supplied by a
browser. A validated session must establish the actor before any business or
ledger operation.

#### How It Works

Signup validates email/contact/password policy and hashes the password with
BCrypt. Login verifies the hash, rejects disabled accounts, creates a random
URL-safe token, stores only its SHA-256 hash, and returns the raw token once
to the caller. Validation hashes the presented token and checks the active
session, expiry, revocation, and account status. Logout revokes the hash.
Google sign-in verifies a Google ID token, maps its stable subject, and then
uses the same local session mechanism.

#### Security and Data Integrity

The frontend cannot choose the global role. The safe user serializer excludes
password hashes. A raw session token is never stored in SQLite. Global
application roles are separate from business membership roles introduced in
Module 2.

#### Testing

tests/test_auth.py has 11 tests covering hashes, signup/login, failures,
expiry, revocation, role checks, Google mapping, and raw-token
non-persistence.

#### Problems Encountered

Older user schemas were less expressive than the later service contract.

#### Solutions

Idempotent additive migration added missing columns with safe defaults. Google
accounts receive an unusable random BCrypt credential so legacy NOT NULL
password constraints remain valid.

### Module 2 — Business Ownership & Membership

#### Purpose

Introduce a modern business tenant boundary and roles within that tenant.

#### Database Work

businesses stores modern business profile/status data.
business_memberships connects users to businesses with owner, manager, member,
or viewer roles and active/disabled status. Foreign keys and a unique
business/user pair prevent orphaned or duplicate memberships.

#### Why It Was Needed

Global user roles do not express what a user may do inside one business.
Tenant-specific membership is required for business isolation.

#### How It Works

create_business() derives the actor from the validated session and atomically
creates a business plus owner membership. require_business_access() loads the
modern business, checks active status, then checks the current user's active
membership and optional allowed role set. Managers cannot grant manager/owner
privileges; the final owner cannot be removed.

#### Security and Data Integrity

The service ignores frontend role/user identity fields. Access is always
looked up from session-derived user ID and membership. Business and membership
status are checked on every protected operation.

#### Testing

tests/test_business_service.py has 14 tests for atomic creation, session
states, status, isolation, membership administration, escalation prevention,
and owner protection.

#### Problems Encountered

Module 0 already had a business_registry table that legacy financial queries
require.

#### Solutions

The modern businesses table was introduced without deleting or repurposing the
legacy table. The consequence and later bridge are documented in Section 3.6.

### Module 3 — Financial Accounts

#### Purpose

Represent bank, cash, card, loan, and other accounts owned by a modern
business.

#### Database Work

financial_accounts contains account ID, modern business ID, name, account
type, institution, optional account identifier, uppercase three-letter
currency, integer opening_balance_minor, active/disabled status, and
timestamps. Account ownership is a foreign key to businesses with ON DELETE
RESTRICT; a partial unique index prevents repeated non-empty identifiers
inside one business.

#### Why It Was Needed

Module 4 needs one explicit account context per ingestion. Account ownership
also provides the source of truth for currency.

#### How It Works

Owners/managers create, update, or disable accounts; all active business
members may read active accounts. Amounts are parsed with Decimal and stored
as integer minor units. Account identifiers are masked in returned responses.

#### Security and Data Integrity

Immutable IDs, business ownership, actor fields, and status cannot be changed
through update input. Disabled accounts are rejected by protected operations.

#### Testing

tests/test_account_service.py has 14 tests covering exact precision,
authorization, isolation, status, identifier uniqueness, updates, and
disabling. Module 3 schema/migration cases are also in tests/test_db.py.

#### Problems Encountered

Binary floating point is unsuitable for balances and cross-business account
selection is dangerous.

#### Solutions

The account service uses exact Decimal parsing, integer storage, strict
currency syntax, and a reusable session-to-business-to-account access path.

### Module 4 — Financial Ingestion

#### Purpose

Accept controlled canonical transactions and persist only authenticated,
validated, unique records without changing Modules 0–3 semantics.

#### Documentation and Contract

The repository contains reconstructed design documents
(docs/ingestion_implementation_spec.md, docs/phase3_decision_record.md,
docs/phase3a_current_state_amendment.md,
docs/phase3b_demo_evidence_approval.md, and
docs/phase3c_d18_schema_design.md). Their earlier sections explicitly say
they are design-only and that raw files are outside the original Module 4
boundary. Later Git commits implement the approved controlled-demo contract;
the current code and tests, not the old draft status, are authoritative for
current implementation claims.

#### Database Work

Three additive structures implement the boundary:

1. business_registry_bridges explicitly relates modern and legacy business IDs,
   with proposal/verification attribution, lifecycle status, and one active
   bridge per side.
2. ingestion_attempts records one request/retry, selected account, uploader,
   source token, currency snapshot, counts, lifecycle status, and sanitized
   error fields.
3. ingested_transaction_identities stores accepted transaction identity,
   exact amount minor units, direction, currency, source identity, and links
   to both the legacy ledger row and ingestion attempt.

#### Why It Was Needed

The modern authorization boundary and legacy ledger boundary use different
business identities. The system also needed duplicate-safe retries and exact
money identity without breaking legacy readers.

#### How It Works

The service validates the session, active modern business/membership, explicit
active financial account, active verified bridge, and legacy registry owner.
It validates a canonical envelope and each record, builds an
uploader-independent identity hash, classifies existing and within-batch
duplicates, and writes the attempt, legacy ledger projection, and identity
rows in one transaction. A storage failure rolls back financial writes; a
sanitized failed-attempt record may be persisted separately. Retry attempts
link to their parent and never overwrite history.

The current controlled envelope uses contract version
finsight_ingestion_v1 and source token finsight_demo_bank_statement_v1. Each
record requires an ISO calendar date, a positive built-in integer amount_minor,
and direction income or expense. Optional bounded fields include source
transaction ID, category, payment mode, description and a signed balance
after-value. Business, account, uploader, bridge, identity hash, persistence
status and timestamps are derived or stored by trusted backend layers rather
than accepted as record authority.

#### Security and Data Integrity

Only active owners/managers ingest. Business/account/bridge IDs are loaded
from database state; caller-provided roles, users, or record-level account
overrides are not trusted. Public errors are bounded and do not contain SQL,
paths, payloads, or stack traces. Legacy ledger user_id remains the legacy
owner, while uploader identity is stored in ingestion_attempts.

#### Testing

The Module 4 suite contains 23 schema tests, 150 validation tests, 49
identity tests, 50 ingestion-service tests, 22 end-to-end tests, 18 query
tests, and 17 Streamlit adapter tests. These tests pass in the current
498-test regression.

#### Problems Encountered

The bridge was missing from the original schema; the legacy hash included
uploader/user context and converted amounts to floating point; single-row
legacy insertion was not an idempotent batch protocol.

#### Solutions

The additive bridge/attempt/identity schema, pure validation/identity layers,
and transactional ingestion service preserve legacy behavior while providing
controlled idempotency, exact identity, and rollback/retry semantics.

#### Status separation

- Controlled canonical implementation: **IMPLEMENTED, TESTED**.
- Controlled non-production mapping and source token: **DOCUMENTED, TESTED**.
- Production business/account/source mappings: **BLOCKED** pending authoritative
  evidence.
- Arbitrary raw file ingestion at the original Module 4 boundary: **DEFERRED**;
  the later CSV layer preprocesses into canonical JSON.
- Full production deployment readiness: **UNRESOLVED**.

### Module 5 — Financial Analytics & KPI Engine

#### Purpose

Transform accepted Module 4 identity rows into read-only KPIs and summaries.

#### Database Work

No schema change was needed. analytics_service.py performs one parameterized
read joining ingested_transaction_identities to the legacy ledger and
scoping by modern business, account, date range, and currency.

#### Why It Was Needed

Raw ledger rows are not enough for operational decisions. The application
needs exact income, expense, net cash flow, averages, balances, trends,
categories and payment summaries without counting unaccepted/duplicate legacy
rows.

#### How It Works

The service checks an authenticated owner/manager session, validates an active
business/account and currency, loads only accepted identity rows, and
aggregates in memory with integer/Decimal arithmetic. Daily, ISO-weekly, and
monthly datasets are chronological. It returns sanitized transaction rows,
not raw IDs or identity hashes.

#### Security and Testing

Business and account isolation, date inclusivity, mixed-currency rejection,
read-only behavior, duplicate exclusion, exact calculations, empty results,
and chart/export-ready shapes are covered by 18 backend tests. The thin
Streamlit adapter is covered by 18 tests.

#### Problems and Solutions

The compatibility ledger includes rows that are not accepted Module 4
transactions. Analytics therefore joins through the identity table and
ignores legacy-only rows. The service also validates authorization before
reading data.

### CSV Normalization Layer

#### Purpose

Convert varied bank/Excel-style CSV layouts into the existing canonical JSON
contract without modifying Module 4 validation or identity rules.

#### How It Works

csv_normalizer.py reads text/bytes/file-like uploads, supports UTF-8/BOM,
quoted commas, semicolon delimiters, aliases and deterministic header scoring,
dates, commas/currency symbols, parentheses/negative values, debit/credit
columns, optional dimensions, blank rows, and safe malformed-input errors.
Low-confidence/unknown/duplicate headers fail closed. The output is only a
canonical payload; Module 4 remains the authority for validation and writes.

#### Status

**IMPLEMENTED, TESTED** by 22 normalizer tests and Module 4 Streamlit
integration tests. It does not establish business/account/currency authority
from filenames or arbitrary CSV content.

### Module 6 — Business Health & Anomaly Detection

#### Purpose

Interpret Module 5 analytics into deterministic health metrics and explainable
anomalies.

#### Database Work

None. The service is read-only and calls analytics once.

#### How It Works

Health metrics include cash-flow stability, expense/income ratio, savings,
monthly growth/decline, recurring expense burden, category concentration,
largest-income/expense percentages, cash-reserve estimate, score, and health
level/rating. Rule-based anomaly detection covers large/repeated transactions,
expense spikes/explosions, income drops/interruption, negative periods,
high-ratio/instability, inactive periods, category spikes, payment-mode
changes, and recurring growth. Outputs are deterministic and sanitize
transaction references.

#### Security and Testing

Owner/manager access and the same business/account/currency scope are
forwarded to analytics. 27 health tests cover empty data, thresholds,
determinism, explainability, isolation, and read-only behavior.

### Module 7 — Reporting & Decision Support

#### Purpose

Provide backend report structures and explainable recommendations without
duplicating SQL or KPI calculations.

#### Database Work

None. report_service.py calls analytics and health once each. It creates
financial summary, income statement, expense, cash-flow, category, payment,
account, health, anomaly, and combined executive sections. It also produces
JSON-ready dictionaries, CSV/table rows, and chart datasets. PDF generation is
not part of this backend adapter.

decision_support_service.py calls analytics, health, and report once each and
applies deterministic thresholds for negative cash flow, expense ratio,
savings, income decline/growth, category concentration, recurring burden,
reserve, stability, payment concentration, inactivity, and health anomalies.
Recommendations are deduplicated and sorted by priority/severity/category/title.

#### Security and Testing

Both services require active owner/manager membership through
business_service.require_business_access, forward the complete scope, omit
sensitive identifiers from reports, and wrap downstream failures in safe
public errors. Report tests: 19; decision-support tests: 13. Both pass.

#### Limitations

The current decision-support implementation generates an id during final
ordering, but raw recommendations before finalization do not have an id.
The report service intentionally does not generate PDFs. A full document/RAG
backend is not implemented in these services.

# 3. Technical Architecture & System Design

## 3.1 Technology Stack

| Component layer | Technology used | Core responsibility |
|---|---|---|
| User interface | Streamlit, Python | Authentication form, ingestion and analytics controls, legacy demo presentation |
| Application/service layer | Python modules under services/ | Business rules, validation, authorization orchestration, analytics, health, reports |
| Security | bcrypt; Google OAuth token verification libraries | Password hashing, password verification, Google identity verification |
| Query/data-access layer | Python sqlite3 in database/queries.py | Parameterized SQL, row mapping, transactional repository helpers |
| Database engine | SQLite | Local relational persistence with foreign keys and constraints |
| CSV preprocessing | Python standard CSV parsing plus deterministic normalizer | Header detection and conversion into canonical JSON |
| Financial arithmetic | Decimal and integer minor units | Exact balances, identity fields, ratios and percentages |
| Testing | pytest, temporary SQLite fixtures | Unit, integration, authorization, schema, rollback and regression verification |
| Version control | Git | Module-scoped history and controlled branch delivery |
| Optional legacy scheme/RAG path | pandas, ReportLab, LangChain/FAISS/HuggingFace/Groq imports in finsight_app requirements | Demo CSV KPIs, PDF scheme report, optional scheme-document Q&A; not the Module 4 authority |

## 3.2 Overall System Architecture

~~~mermaid
flowchart TD
    U["User"] --> UI["Streamlit UI"]
    UI --> AUTH["Auth and session services"]
    UI --> ING["CSV normalizer or canonical JSON"]
    AUTH --> SVC["Business, account, ingestion, analytics, health and report services"]
    ING --> SVC
    SVC --> Q["Parameterized query layer"]
    Q --> DB["SQLite database"]
~~~

The UI collects inputs but does not decide identity, role, business ownership,
account ownership, or currency. Authentication derives the user from a
validated token. Business/account services enforce modern tenant scope.
Validation and identity helpers are pure and can be tested without a database.
The ingestion service is the only writer for Module 4 financial records.
Analytics, health, reports, and decision support are read-only consumers.
The query layer binds values and owns transaction boundaries. SQLite enforces
relational constraints.

The legacy bottom portion of finsight_app/app.py also reads
data/*.csv through pandas for the original scheme-matcher demo. This is an
additional presentation path, not a replacement for the authenticated Module
4 ledger flow.

## 3.3 Database Technology and Lifecycle

FinSight uses SQLite through the standard-library sqlite3 module. Important
paths are computed relative to the repository in database/db.py:

- BASE_DIR is the repository root.
- Runtime database path is data/finsight.db.
- Schema path is database/schema.sql.

get_connection() creates the runtime data directory, opens SQLite with a
30-second timeout, assigns sqlite3.Row, and executes PRAGMA foreign_keys =
ON. Each service/query operation normally opens a context-managed connection.
Module 4 additionally supports caller-owned connections and explicit
transaction context management, which is covered by tests.

initialize_database() checks that the schema file exists, executes the
idempotent schema, then inspects PRAGMA table_info(users). It adds only
missing legacy user columns (username, role, account_status, updated_at) and
fills missing update timestamps. It does not drop tables, rename columns,
rebuild data, or backfill legacy transactions.

## 3.4 Complete Database Schema

The authoritative schema is database/schema.sql. It contains 18 tables in
this checkout. The following table records the verified keys, relationships,
constraints, and security meaning.

| Table | Introduced/modified | Purpose | Primary key | Foreign keys | Important columns and constraints | Security considerations |
|---|---|---|---|---|---|---|
| users | Module 0; expanded Modules 1–2 | Local user identity and credential metadata | user_id | None | Unique case-insensitive email; nullable password_hash; role CHECK; active/disabled status; timestamps | Password/hash fields never returned by safe service responses; role is server assigned |
| business_registry | Module 0 legacy | Legacy financial-business owner boundary | business_id | user_id → users CASCADE | Unique (user_id,business_name); name/type/address | Legacy owner semantics must not be replaced by uploader identity |
| counterparty_entities | Module 0 | Customers/vendors/other counterparties | entity_id | business_id → business_registry CASCADE | Unique (business_id,entity_name,entity_type) | Always scoped to legacy business |
| transaction_general_ledger | Module 0 legacy | Compatibility transaction ledger | transaction_id | Registry CASCADE; entity SET NULL; user CASCADE | Positive REAL amount; transaction type; category/payment/description; hash | Legacy rows are not automatically accepted Module 4 rows; analytics uses identity join |
| structural_budget_allocations | Module 0 | Legacy category budgets | budget_id | business_id → business_registry CASCADE | Non-negative amount; unique business/category | Legacy budget owner scope |
| pipeline_upload_ingestion_logs | Module 0 | Legacy upload summary log | upload_id | Optional user SET NULL; registry business CASCADE | Filename/type, total/success/failure counts, status, error text | Current complete Module 4 audit is ingestion_attempts; do not treat filename as authority |
| authentication_logs | Module 1 | Authentication/security event audit | authentication_log_id | Optional user SET NULL | Event type, optional IP/user-agent, timestamp | Must not contain passwords or raw tokens |
| otp_verifications | Module 1 schema | OTP hash/expiry/attempt record | otp_id | user_id → users CASCADE | otp_hash, expiry, used flag CHECK, attempt count CHECK | Table exists; no verified OTP service workflow |
| documents | Legacy feature | User document metadata | document_id | user_id → users CASCADE | File name/type/path, timestamp | Path field is storage metadata; never expose arbitrary paths to public reports |
| document_chunks | Legacy feature | Text chunks associated with a document | chunk_id | Document/user CASCADE | Unique (document_id,chunk_index); non-empty text | No vector/embedding tables or verified RAG DB integration |
| auth_sessions | Module 1 | Session lifecycle | session_id | user_id → users CASCADE | Unique token_hash; expiry; optional revocation | Raw token is not stored; service checks active user, expiry, revocation |
| provider_identities | Module 1 | External provider-to-local identity mapping | identity_id | user_id → users CASCADE | Unique (provider,provider_subject); provider email | Only verified provider claims are accepted |
| businesses | Module 2 | Modern tenant/business profile | business_id | None | Active/disabled status CHECK; contact/legal fields; timestamps | Membership, not global role or frontend ID, is authority |
| business_memberships | Module 2 | User membership and business role | membership_id | Business/users CASCADE | Role CHECK owner/manager/member/viewer; status CHECK; unique business/user | Service checks current session user and active membership |
| financial_accounts | Module 3 | Account owned by modern business | account_id | business_id → businesses RESTRICT | Type CHECK; uppercase 3-letter currency CHECK; integer opening balance; active status | Account identifier is masked; account/business scope checked before reads/writes |
| business_registry_bridges | Module 4 | Explicit modern-to-legacy business link | bridge_id | Modern business/legacy registry/users RESTRICT | Status lifecycle; active requires verifier/time; partial unique indexes one active bridge per side | Ingestion requires active verified bridge; no name/filename inference |
| ingestion_attempts | Module 4 | Authenticated batch/retry audit boundary | attempt_id | Parent self-FK; modern/legacy business; account; uploader user RESTRICT | Controlled source token; currency format; non-negative counts; lifecycle CHECK; safe errors | Uploader and legacy owner are distinct; public errors exclude internals |
| ingested_transaction_identities | Module 4 | Exact, deterministic accepted-transaction identity | identity_id | Ledger/attempt/business/registry/account RESTRICT | Unique transaction/hash; integer non-negative amount; direction and currency CHECK; partial source-ID uniqueness | Hash is never exposed; identity is uploader independent and business/account scoped |

database/schema.sql begins with PRAGMA foreign_keys = ON. Runtime connections
repeat that pragma because SQLite enables it per connection.

## 3.5 Database Relationships

~~~text
users
├── auth_sessions
├── authentication_logs
├── provider_identities
├── otp_verifications
├── documents
├── document_chunks
├── business_memberships ──> businesses
├── financial_accounts (through businesses)
└── legacy business_registry (legacy owner)

businesses
├── business_memberships
├── financial_accounts
├── business_registry_bridges ──> business_registry
└── ingestion_attempts

business_registry
├── counterparty_entities
├── transaction_general_ledger
├── structural_budget_allocations
├── pipeline_upload_ingestion_logs
├── business_registry_bridges
└── ingestion_attempts

ingestion_attempts
└── ingested_transaction_identities ──> transaction_general_ledger
~~~

The modern business has no direct foreign key to a user; ownership is a
membership row. The legacy registry has a direct user_id owner because that
was the original Module 0 contract. A bridge connects the two identities only
when explicitly active and verified. An ingestion attempt points to one
modern business, one legacy registry business, one financial account, and one
authenticated uploader. An accepted identity links the attempt to exactly one
legacy ledger row.

## 3.6 Legacy vs Modern Business Architecture

business_registry and businesses represent different architectural boundaries:

| Concept | Module | Authority | Data it owns |
|---|---|---|---|
| business_registry | Module 0 | Legacy user_id owner | Existing counterparties, ledger rows, budgets and legacy upload logs |
| businesses | Module 2 | business_memberships | Modern business profile, status, tenant access and account ownership |

The legacy table could not simply be renamed or replaced because existing
queries, foreign keys, summaries, and regression tests use its primary key.
The modern table was therefore added. This preserves backward compatibility but
creates a structural boundary: a modern business ID is not automatically a
legacy registry ID even though both IDs use a similar text prefix.

Module 4 resolves the boundary through business_registry_bridges. A bridge
contains exact IDs, proposal/verification attribution, lifecycle status, and
one-active-per-side uniqueness. Ingestion fails closed when the bridge is
missing, inactive, or not independently verified. The controlled demo has
documented IDs (demo_business_001, legacy_demo_business_001,
demo_account_001, demo_owner_001) and INR/source evidence; those are not
production mappings.

## 3.7 Query Layer

database/queries.py separates SQL and row access from service-layer business
rules. This limits duplication and gives services a single place to bind SQL
parameters, manage connection context, and preserve legacy contracts.

Verified query groups include:

- user create/read/update and password-hash update;
- legacy business and user-business lookup;
- counterparties;
- legacy transactions and financial summary;
- budgets and budget variance;
- authentication logs, sessions, revocation, provider identity;
- documents and document chunks;
- modern business creation with owner membership, business/membership
  lookup/list/add/disable/status changes;
- financial account create/read/list/update/disable;
- Module 4 active business/membership/account/bridge/registry/owner lookups;
- Module 4 attempt lifecycle, identity lookup/classification, ledger insert and
  identity insert.

All value-bearing SQL in these functions uses ? placeholders and a parameter
tuple. The schema is executed as trusted repository text, not built from user
input. Parameterization prevents SQL injection by keeping values separate from
SQL syntax and also makes repeated query shapes predictable. Services still
validate business/account scope before invoking a query.

## 3.8 Indexes

The authoritative schema creates these indexes:

| Index | Table/columns | Purpose |
|---|---|---|
| idx_business_user | legacy registry (user_id) | List legacy businesses for a user |
| idx_counterparty_business | counterparties (business_id) | Business-scoped counterparties |
| idx_transaction_business | ledger (business_id) | Legacy ledger scope |
| idx_transaction_user | ledger (user_id) | Legacy owner scope |
| idx_transaction_entity | ledger (entity_id) | Counterparty joins |
| idx_transaction_date | ledger (transaction_date) | Date filtering |
| idx_transaction_hash | ledger (transaction_hash) | Legacy identity lookup |
| idx_budget_business | budgets (business_id) | Business budgets |
| idx_upload_user | upload logs (user_id) | User upload history |
| idx_upload_business | upload logs (business_id) | Business upload history |
| idx_auth_user | auth logs (user_id) | User security history |
| idx_otp_user | OTP (user_id) | User OTP records |
| idx_document_user | documents (user_id) | User documents |
| idx_chunk_document | chunks (document_id) | Document retrieval |
| idx_chunk_user | chunks (user_id) | User-scoped chunks |
| idx_session_user | sessions (user_id) | User sessions |
| idx_session_expiry | sessions (expires_at) | Expiry filtering |
| idx_identity_user | provider identities (user_id) | Linked providers |
| idx_business_status | businesses (business_status) | Active/disabled filtering |
| idx_membership_user_status | memberships (user_id,membership_status) | User tenant lookup |
| idx_membership_business_status | memberships (business_id,membership_status) | Business membership checks |
| idx_financial_account_business_status | accounts (business_id,account_status) | Active account listing |
| idx_financial_account_identifier | partial accounts (business_id,account_identifier) | Non-empty identifier uniqueness |
| idx_bridge_one_active_business | partial bridges (business_id) | One active bridge per modern business |
| idx_bridge_one_active_registry | partial bridges (registry_business_id) | One active bridge per legacy business |
| idx_bridge_business_status | bridges (business_id,bridge_status) | Bridge lifecycle lookup |
| idx_bridge_registry_status | bridges (registry_business_id,bridge_status) | Reverse bridge lookup |
| idx_ingestion_attempt_business_created | attempts (business_id,created_at) | Business attempt history |
| idx_ingestion_attempt_account_created | attempts (account_id,created_at) | Account attempt history |
| idx_ingestion_attempt_uploader_created | attempts (uploader_user_id,created_at) | Uploader audit history |
| idx_ingestion_attempt_status_created | attempts (attempt_status,created_at) | Lifecycle queries |
| idx_ingestion_attempt_parent | attempts (parent_attempt_id) | Retry lineage |
| idx_ingested_source_identity | partial identities (account_id,source_system,source_transaction_id) | Source duplicate prevention |
| idx_ingested_identity_account_created | identities (account_id,created_at) | Account analytics/history |
| idx_ingested_identity_attempt | identities (attempt_id) | Attempt-to-identities |
| idx_ingested_identity_registry_date | identities (registry_business_id,transaction_date) | Legacy/date-scoped analysis |

Primary-key and UNIQUE constraints create additional SQLite indexes
implicitly. Index design is local SQLite design; no production workload
benchmark or target latency is claimed.

## 3.9 Database Initialization & Migration

The schema is designed to be executed repeatedly. CREATE TABLE IF NOT EXISTS
and CREATE INDEX IF NOT EXISTS preserve existing rows. The initializer’s
explicit migration covers the older users shape only. Module 2 and Module 3
tables are additive; Module 4 tables are additive. Tests verify idempotence,
foreign keys, preservation of existing Module 0–3 rows, and the deliberate
absence of automatic backfill for legacy transactions.

Deleting and recreating a database on every schema change would destroy
financial history, identity links, and audit records. The current migration
approach is safer but intentionally limited: there is no general migration
framework, rollback migration, data backfill, or production migration runner
verified in the repository.

## 3.10 Financial Data Representation

The legacy ledger stores a positive REAL amount and a string transaction_type
(income or expense). IEEE-754 binary floats cannot represent many decimal
fractions exactly; repeated arithmetic can produce values such as 0.1 + 0.2
not equal to exactly 0.3.

Newer boundaries store exact integer minor units:

~~~text
₹100.25 = 10025 minor units
~~~

financial_accounts.opening_balance_minor and
ingested_transaction_identities.amount_minor are SQLite INTEGER columns.
Validation requires built-in non-negative integers for canonical amounts.
Account parsing uses Decimal and limits scale to two decimal places. Analytics
sums integer values and uses Decimal for ratios/percentages.

Module 4 writes a deterministic legacy major-unit projection for compatibility,
but analytics treats the identity table as authoritative for accepted rows.
There is no evidence that every historical transaction_general_ledger.amount
has been migrated or that all legacy rows have an account/currency identity.

## 3.11 Authentication & Database Security

### Database-level protections

- PRIMARY KEY, UNIQUE, NOT NULL, and CHECK constraints.
- Foreign keys with explicit CASCADE, SET NULL, or RESTRICT behavior.
- Unique token hashes, provider subjects, membership pairs, identities, and
  active bridges.
- Uppercase three-character currency syntax.
- Integer non-negative identity amounts and approved direction/source values.
- Foreign-key enforcement enabled per connection.

### Service/application-level protections

- BCrypt hashes passwords; verification fails safely for malformed hashes.
- Sessions expose a raw token only to the caller; SQLite stores SHA-256 hashes.
- Validation checks account status and session expiry/revocation.
- Business services derive user identity from the validated session.
- Membership role is checked on each business-scoped action.
- Ingestion requires owner/manager, active account, active bridge, and verified
  registry owner context.
- Analytics/health/report/decision services require owner/manager membership.
- Public errors are generic and sanitized.
- Account identifiers are masked; analytics/report outputs omit sensitive keys.

Database constraints cannot replace service authorization: SQLite can ensure
that an ID exists, but only the service can determine whether the current
session may read that tenant.

## 3.12 Data Integrity

Integrity is layered:

1. Database keys and CHECK/UNIQUE constraints prevent impossible or duplicate
   structural rows.
2. Services validate shape, status, role, ownership, currency and ranges.
3. Module 4 identity hashing provides deterministic uploader-independent
   duplicate classification.
4. A single SQLite transaction coordinates attempt, ledger, and identity rows.
5. Retry lineage preserves failed-attempt history.
6. Analytics joins accepted identities and excludes legacy-only rows.

The architecture deliberately does not infer missing business IDs, account IDs,
currency, economic direction, or payroll identity from filenames, descriptions,
or user-supplied labels.

## 3.13 Testing Architecture

tests/conftest.py creates a fresh temporary SQLite database per test, executes
the authoritative database/schema.sql, enables foreign keys, and monkeypatches
database.queries.get_connection. Tests therefore do not write the developer’s
runtime database.

| Test file | Count | Coverage |
|---|---:|---|
| test_db.py | 7 | Schema, FK pragma, additive migrations, account precision |
| test_queries.py | 1 | Legacy query smoke workflow |
| test_module0_regression.py | 1 | Original Module 0 workflow |
| test_auth.py | 11 | Passwords, sessions, roles, Google mapping |
| test_business_service.py | 14 | Business/membership authorization |
| test_account_service.py | 14 | Account CRUD, precision and isolation |
| test_module4_schema.py | 23 | Bridges, attempts, identity constraints/upgrades |
| test_module4_queries.py | 18 | Module 4 repository functions |
| test_module4_validation.py | 150 | Canonical contract boundaries and safe errors |
| test_module4_identity.py | 49 | Hash determinism, duplicate/conflict classification |
| test_module4_ingestion_service.py | 50 | Auth, atomic writes, rollback, retries, errors |
| test_module4_end_to_end.py | 22 | Controlled batch lifecycle |
| test_module4_streamlit.py | 17 | UI adapter authorization and CSV wiring |
| test_module5_analytics.py | 18 | KPI, trend, summary, precision and isolation |
| test_module5_streamlit.py | 18 | Analytics page/service invocation and safe rendering |
| test_module6_health.py | 27 | Health metrics, anomalies, thresholds and determinism |
| test_csv_normalizer.py | 22 | Header aliases, delimiters, numbers, dates, errors |
| test_module7_reports.py | 19 | Report sections, exports, sanitization |
| test_module7_decision_support.py | 13 | Rules, priorities, explanations, scope |
| test_backend_polish.py | 4 | Authorization hardening and safe failure behavior |
| **Total** | **498** | Current full regression |

All 498 tests passed under Python 3.12.13 and pytest 9.1.1 in the project
.venv. A historical stage-by-stage count is not always preserved in Git;
where it is not directly recorded, this report does not invent a number.

### Verified Git implementation timeline

The following history is present in the inspected repository. It preserves
the Module 4 controlled-demo baseline 826bc15 as an ancestor.

| Commit | Date | Scope |
|---|---|---|
| 11fab79 | 2026-07-27 | Initial FinSight project files; database artifacts were placeholders |
| dd5bc78 | 2026-08-01 | Original relational database schema |
| e7e7d24 | 2026-08-01 | SQLite connection layer |
| f646c83 | 2026-08-18 | Consolidated Modules 0–3 implementation |
| 06d0dd7 | 2026-08-29 | Module 4 ingestion schema foundation |
| ef15341 | 2026-08-29 | Module 4 repository queries |
| 9fdc611 | 2026-08-29 | Canonical validation |
| 3f9e2cb | 2026-08-29 | Canonical identity and idempotency |
| 86ec32d | 2026-08-29 | Ingestion service foundation |
| df19887 | 2026-08-29 | Atomic financial writes and rollback |
| 512a753 | 2026-08-29 | Batch lifecycle and failure handling |
| d214036 | 2026-08-29 | Module 4 end-to-end backend integration |
| 002fca2 | 2026-08-29 | Module 4 Streamlit integration |
| 826bc15 | 2026-08-29 | Finalize Module 4 controlled demo |
| ead4e21 | 2026-09-01 | Module 5 analytics engine |
| 2c1001a | 2026-09-01 | Module 5 trend analytics |
| ace9bff | 2026-09-01 | Module 5 Streamlit analytics integration |
| f0ca692 | 2026-09-01 | Module 6 business health engine |
| d1e298b | 2026-09-02 | Flexible CSV normalization |
| 1e28703 | 2026-09-02 | CSV upload integration |
| 1b63f77 | 2026-09-02 | Module 6 health completion |
| 71dd845 | 2026-09-02 | Module 7 reporting engine |
| 30c6313 | 2026-09-02 | Module 7 decision support engine |
| 74d3e61 | 2026-09-02 | Analytics authorization hardening; current HEAD |

# 4. Deployment & Infrastructure Operations

## 4.1 Development Environment

Verified current environment:

- Python 3.12.13 through the repository .venv
- pytest 9.1.1
- SQLite through Python sqlite3
- Dependencies declared in root requirements.txt; a separate, unpinned
  finsight_app/requirements.txt contains optional legacy/RAG dependencies
- The environment example contains GOOGLE_CLIENT_ID; the app README also
  refers to GROQ_API_KEY, but the root example does not include it

The repository ignores runtime databases, caches, virtual environments, .env
files, and the acctual data/ directory. No secrets or database binary is
tracked.

## 4.2 Database Setup

The repository does not provide a root setup script. The following commands
are derived from verified code and test configuration:

~~~bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -c "from database import db; db.initialize_database()"
python -m pytest
~~~

On Windows PowerShell the project virtual environment can be activated with
.\.venv\Scripts\Activate.ps1 after an appropriate process execution policy.
The tests use temporary databases; normal application startup calls
db.initialize_database() from finsight_app/app.py.

## 4.3 Database Upgrade / Migration Procedure

Run db.initialize_database() against the intended database. It executes the
idempotent schema and adds only the four supported legacy users columns.
Before any real deployment, create a database backup and review schema
compatibility; the repository does not provide a backup or rollback command.
Do not delete data/finsight.db as a schema-upgrade strategy.

## 4.4 Testing Procedure

Verified commands in this checkout:

~~~bash
./.venv/bin/python -m pytest
./.venv/bin/python -m pytest tests/test_db.py tests/test_queries.py
./.venv/bin/python -m pytest tests/test_module4_validation.py
./.venv/bin/python -m pytest tests/test_module5_analytics.py
./.venv/bin/python -m pytest tests/test_module6_health.py
./.venv/bin/python -m pytest tests/test_module7_reports.py tests/test_module7_decision_support.py
~~~

The complete command produced 498 collected/passed tests in approximately
33 seconds in the inspected environment. Runtime naturally varies by machine.

## 4.5 Git & Repository Workflow

The verified history preserves the Module 4 baseline 826bc15 and continues
on feature branch module5-analytics. Module-scoped commits were kept
separate through analytics, health, CSV, reports, decision support, and
authorization hardening. The checkout’s origin/main tracking ref points to
826bc15, while the local branch contains later commits; this is a repository
synchronization fact, not a reason to rewrite history. No Git operation was
performed for this report.

Earlier work included bundle recovery and branch synchronization. The current
reporting task is read-only and creates no commit or push.
No stash conflict is evidenced in the inspected history, so this report does
not claim a stash-related data-loss incident.

## 4.6 Operational Limitations

- SQLite is a local-file database; no concurrent production deployment,
  replication, backup, or high-availability design is verified.
- The root README.md is empty. Setup instructions are split between
  finsight_app/README.md, requirements files, and source code.
- finsight_app/app.py retains a CWD-relative legacy CSV path (data/...);
  launching from the repository root can fail when only
  finsight_app/data/... is present.
- PDF download uses finsight_app/pdf_generator.py, which imports ReportLab;
  a missing package in the selected virtual environment prevents startup.
- The legacy PDF table uses fixed-width strings; a user-provided screenshot
  showed overlapping/truncated scheme text. No layout fix is verified here.
- Optional RAG uses local scheme documents and external/model dependencies; it
  is not a database-backed document-intelligence service.
- Production business/registry/account/source/currency mappings are absent;
  only the controlled non-production evidence is approved.
- OTP table behavior, password recovery, email/SMS delivery, session cleanup,
  and rate limiting are not implemented/verified.

# 5. Maintenance, Troubleshooting & Appendices

This section records problems only when repository, Git, automated-test, or
user-run evidence supports them. A possible issue is not described as a fact
merely because it appeared in an earlier task prompt.

## 5.1 Problems Faced & Solutions

### Problem 1 — Empty initial database artifacts

**Module:** Module 0
**What Happened:** The early project commit contained empty database files.
**Affected Files:** database/schema.sql, database/db.py, database/queries.py.
**Technical Root Cause:** The repository had project placeholders before the
relational foundation was committed.
**Impact:** There was no reproducible schema or query boundary.
**How We Detected It:** Git history inspection (11fab79 followed by the schema
and connection commits).
**Solution Implemented:** Added the relational schema, SQLite connection
initialization, queries, and temporary database tests.
**Why the Solution Works:** Every test/application connection now executes the
same authoritative schema and enables foreign keys.
**Verification:** Database/query/Module 0 tests and the current full suite pass.
**Status:** RESOLVED.

### Problem 2 — Older users schema versus authentication contract

**Module:** Module 1
**What Happened:** Existing user rows did not necessarily have the later
username, role, status, or update-timestamp fields.
**Affected Files:** database/db.py, database/schema.sql,
services/auth_service.py.
**Technical Root Cause:** Modules were added incrementally to an existing
SQLite file.
**Impact:** Recreating or replacing users could lose users; querying missing
columns could fail.
**Solution Implemented:** db.initialize_database() applies additive,
idempotent ALTER TABLE statements with safe defaults and preserves rows.
**Why the Solution Works:** Existing values remain in place while new service
queries can rely on the expanded shape.
**Verification:** tests/test_db.py migration cases pass, including Module 1–3
data preservation.
**Status:** RESOLVED for the supported columns; a general migration framework
remains DEFERRED.

### Problem 3 — Legacy registry and modern business boundaries

**Module:** Modules 2–4
**What Happened:** Legacy financial tables reference business_registry, while
modern authorization/accounts reference businesses.
**Technical Root Cause:** The original Module 0 ownership model and Module 2
membership model have different identifiers and responsibilities.
**Impact:** A modern business ID could not safely be used to query the legacy
ledger; name similarity would permit cross-tenant leakage.
**Solution Implemented:** Preserve both models and add business_registry_bridges
with explicit IDs, verification state, and one-active-per-side uniqueness.
**Verification:** Module 4 schema, query, service and end-to-end tests reject
missing/unverified bridges and preserve legacy owner semantics.
**Status:** RESOLVED for the controlled demo; production mapping BLOCKED.

### Problem 4 — Legacy floating-point ledger and uploader-dependent identity

**Module:** Module 4
**What Happened:** Legacy ledger amounts are REAL; the legacy transaction hash
includes user context and the old helper is not an idempotent batch protocol.
**Impact:** Exact financial identity and retry-safe duplicate detection could
not rely on the old row/hash alone.
**Solution Implemented:** Add exact amount_minor identity rows and a canonical
SHA-256 identity that excludes uploader/row position; retain the legacy
major-unit projection for compatibility.
**Verification:** Identity golden-vector, conflict, duplicate, and exact-integer
tests pass; analytics excludes ledger-only rows without identity.
**Status:** RESOLVED for new controlled ingestion; historical backfill
DEFERRED.

### Problem 5 — Partial writes during ingestion failure

**Module:** Module 4
**What Happened:** A multi-record ingestion must coordinate attempt, ledger,
and identity rows; a failure after one insert could otherwise leave partial
financial data.
**Solution Implemented:** A shared SQLite transaction writes all financial
rows atomically. Failed persistence rolls back and may record a sanitized
failed attempt separately. Retry attempts link through parent_attempt_id.
**Verification:** Rollback, caller-owned connection, retry-lineage, terminal
failure, and sanitized-error tests pass.
**Status:** RESOLVED.

### Problem 6 — Design documents versus later implementation

**Module:** Module 4 process
**What Happened:** Reconstructed Phase 3 documents state that implementation
was design-only and raw files were outside scope, while later commits
implemented the controlled canonical service and a separate CSV layer.
**Impact:** Treating an old draft as current would under-report implementation
or incorrectly claim production readiness.
**Solution:** Use current source/tests/Git history for implementation status and
label the documents as historical design evidence.
**Verification:** Commit chain and 498-test suite inspected.
**Status:** RESOLVED as documentation interpretation; document refresh is
PLANNED.

### Problem 7 — Production schema versus standalone test schema drift

**Module:** Testing/database documentation
**What Happened:** tests/test_schema.sql is a separate older schema with
different users, budget, upload-log, authentication-log, and document fields.
**Root Cause:** It was retained as a legacy/reference artifact while
tests/conftest.py moved to the authoritative database/schema.sql.
**Impact:** Running the standalone SQL as if it were current could produce
false conclusions.
**Solution:** Current fixtures read database/schema.sql; this report labels
tests/test_schema.sql as legacy/reference drift.
**Verification:** Fixture inspection and full test pass.
**Status:** PARTIALLY RESOLVED; cleanup/documentation alignment is PLANNED.

### Problem 8 — Wrong Python executable or unusable virtual environment

**Module:** Development operations
**What Happened:** A Windows launch used a Streamlit launcher whose embedded
Python path no longer existed; in another environment the system Python had
no pytest.
**Impact:** Application/test commands failed before project code could run.
**Solution Implemented:** Select the repository .venv interpreter and run
./.venv/bin/python -m pytest; the inspected interpreter is Python 3.12.13
with pytest 9.1.1.
**Verification:** 498 tests pass.
**Status:** RESOLVED in this checkout; Windows environment recreation remains
an operator task.

### Problem 9 — Legacy Streamlit data path

**Module:** Legacy Streamlit demo
**What Happened:** kpi_engine.py reads data/checking_account_main.csv relative
to the current working directory. The tracked sample is under
finsight_app/data. Launching from the repository root produced FileNotFoundError.
**Impact:** Login could render, then the legacy demo failed before the user
could use the page.
**Solution:** No production fix was made during this documentation task. The
problem is recorded so launch instructions or path handling can be corrected
deliberately.
**Verification:** The error was observed in the user-provided run; no current
automated regression asserts a corrected path.
**Status:** UNRESOLVED.

### Problem 10 — Missing ReportLab in selected environment

**Module:** Legacy PDF presentation
**What Happened:** pdf_generator.py imports ReportLab; the user’s selected
environment raised ModuleNotFoundError.
**Impact:** app.py could not import and start.
**Solution:** Root requirements.txt declares reportlab, but the user’s
environment must install repository requirements in the same interpreter used
to run Streamlit. No code change was made here.
**Verification:** The missing-package error was observed in the user-provided
run; current backend tests do not exercise a live Streamlit process.
**Status:** UNRESOLVED operationally.

### Problem 11 — PDF table layout quality

**Module:** Legacy PDF presentation
**What Happened:** A screenshot showed long government-scheme names/reasons
overlapping or being truncated in a fixed-width table.
**Impact:** The report is difficult to read despite correct-looking data.
**Solution:** No code was changed here; wrapping/column sizing should be
addressed in a UI/report-presentation phase.
**Verification:** User-provided screenshot; no layout regression test.
**Status:** UNRESOLVED.

### Problem 12 — OTP and document-intelligence gap

**Module:** Authentication/document features
**What Happened:** Schema tables for OTP, documents, and chunks exist, and
document CRUD helpers exist, but no OTP workflow or database-backed embedding,
retrieval, citation, or question-answering service is present.
**Impact:** Tables may be mistaken for complete user-facing features.
**Solution:** This report distinguishes table/CRUD implementation from
workflow implementation.
**Verification:** Source/query inspection and test inventory; no corresponding
OTP/RAG service tests.
**Status:** DEFERRED/UNRESOLVED.

### Problem 13 — Missing production mapping and private data authority

**Module:** Module 4 readiness
**What Happened:** Repository evidence does not provide authoritative
production mappings for modern business, legacy registry, account, currency,
or source system. Raw acctual data/ is ignored and must not become mapping
authority.
**Impact:** Inferring mappings from filenames, names, or CSV contents could
cross tenants or misstate money.
**Solution:** Controlled demo identifiers and a verified bridge are used in
tests; production mappings remain a fail-closed gate.
**Verification:** Decision records, demo-evidence document, schema constraints,
and service checks.
**Status:** BLOCKED for production deployment.

### Requested historical defect inventory — not independently confirmed

The audit request listed possible historical failures including a queries.py
import/syntax failure, duplicate keyword arguments in create_transaction(), a
create_business() SQL mismatch, duplicate SQL columns, placeholder-count
mismatches, and upload/authentication-log schema mismatches. The current
database/queries.py imports, compileall succeeds, and the complete suite
passes. Git message/search inspection did not provide reliable evidence for
each exact incident. They are therefore not claimed as historical facts. Their
provenance is UNRESOLVED, while the current runtime state is verified green.

## 5.2 Problems & Solutions Summary

| # | Module | Problem/root cause | Solution | Verification | Status |
|---:|---|---|---|---|---|
| 1 | 0 | Empty initial DB artifacts | Schema, connection and queries | DB/query/regression tests | RESOLVED |
| 2 | 1 | Older users shape | Additive idempotent columns | Migration tests | RESOLVED |
| 3 | 2–4 | Two business identities | Explicit verified bridge | Module 4 isolation tests | DEMO RESOLVED; production BLOCKED |
| 4 | 4 | REAL/uploader-dependent legacy identity | Exact canonical identity table/hash | Identity/analytics tests | RESOLVED for new data |
| 5 | 4 | Partial batch writes | Atomic transaction and rollback | Ingestion failure tests | RESOLVED |
| 6 | 4 | Design docs lagged implementation | Evidence/status separation | Git/source audit | RESOLVED |
| 7 | Testing | Standalone schema drift | Use authoritative schema fixture | Fixture/full-suite audit | PARTIAL |
| 8 | Operations | Wrong/missing Python environment | Use project .venv | 498 tests | RESOLVED here |
| 9 | UI | CWD-relative CSV path | Not yet changed | User run only | UNRESOLVED |
| 10 | UI | Missing ReportLab dependency | Install declared dependency | User run only | UNRESOLVED |
| 11 | UI | Fixed-width PDF layout | Needs presentation fix | Screenshot only | UNRESOLVED |
| 12 | Auth/docs | Tables without complete workflows | Explicit status labeling | Source/test audit | DEFERRED |
| 13 | Module 4 | No production mapping evidence | Fail closed; controlled demo only | Decision/schema/service tests | BLOCKED |

## 5.3 Major Architectural Decisions

### Decision: Use SQLite

**Reason:** A local, zero-server relational engine matched the student project
and existing Python stack.
**Benefit:** Simple setup, transactional writes, FK/constraint support,
reproducible temporary tests.
**Trade-off:** No verified replication, high availability, or multi-process
production deployment plan.
**Current Status:** IMPLEMENTED, TESTED; production operations UNRESOLVED.

### Decision: Parameterized SQL in a dedicated query layer

**Reason:** Prevent injection and keep SQL separate from business rules.
**Benefit:** Consistent binding, reusable queries, easier tests and review.
**Trade-off:** Services must coordinate multiple repository calls and
transactions.
**Current Status:** IMPLEMENTED, TESTED.

### Decision: Enable foreign keys

**Reason:** Financial ownership and identity links must not silently orphan.
**Benefit:** Database enforces relationships and controlled delete behavior.
**Trade-off:** Fixture/setup order matters; legacy migrations need care.
**Current Status:** IMPLEMENTED, TESTED.

### Decision: Preserve business_registry

**Reason:** Module 0 queries and ledger rows depend on it.
**Benefit:** Backward compatibility and no destructive migration.
**Trade-off:** Two business identifiers require a bridge and more validation.
**Current Status:** IMPLEMENTED; bridge is IMPLEMENTED for controlled demo.

### Decision: Add businesses plus memberships

**Reason:** Tenant roles cannot be represented by a global user role.
**Benefit:** Explicit owner/manager/member/viewer authorization.
**Trade-off:** Membership lookup is required on every protected operation.
**Current Status:** IMPLEMENTED, TESTED.

### Decision: Text IDs generated with prefixes and UUID entropy

**Reason:** Stable opaque identifiers are convenient across service boundaries.
**Benefit:** Avoid sequential disclosure and make entity type recognizable
internally.
**Trade-off:** IDs are not a substitute for authorization and are not exposed
in report outputs.
**Current Status:** IMPLEMENTED, TESTED.

### Decision: Integer minor units for new financial identity

**Reason:** Avoid binary floating-point corruption.
**Benefit:** Exact addition, deterministic hashing and safe balance arithmetic.
**Trade-off:** Scale/currency policy must be explicit; legacy REAL remains.
**Current Status:** IMPLEMENTED, TESTED for account/identity paths.

### Decision: BCrypt password hashes and SHA-256 session-token hashes

**Reason:** Passwords need adaptive one-way hashing; bearer tokens should not
be recoverable from the database.
**Benefit:** Safer credential/session storage.
**Trade-off:** Requires correct secret/session lifecycle and does not provide
rate limiting by itself.
**Current Status:** IMPLEMENTED, TESTED.

### Decision: Layer separation

**Reason:** UI, services, pure validation/identity, queries and schema have
different responsibilities.
**Benefit:** No SQL in UI, testable pure logic, reusable authorization.
**Trade-off:** More modules and explicit data contracts.
**Current Status:** IMPLEMENTED, TESTED.

### Decision: Non-destructive, additive migrations

**Reason:** Existing financial/user data must survive upgrades.
**Benefit:** Idempotent startup and compatibility.
**Trade-off:** No general migration history/backfill.
**Current Status:** IMPLEMENTED, TESTED for covered migrations; broader
framework PLANNED.

### Decision: Explicit ingestion bridge and canonical identity

**Reason:** Modern tenant access and legacy ledger ownership are different;
duplicate detection must not depend on uploader.
**Benefit:** Fail-closed cross-tenant boundary, exact identity, rollback,
retry lineage.
**Trade-off:** Production mappings and verification workflow must be supplied.
**Current Status:** IMPLEMENTED, TESTED for controlled demo; production
mapping BLOCKED.

### Decision: Deterministic analytics/health/report/decision services

**Reason:** Financial outputs need repeatable, explainable results.
**Benefit:** Testable thresholds, reproducible reports, no hidden model
behavior.
**Trade-off:** Rules require deliberate maintenance and are not predictive.
**Current Status:** IMPLEMENTED, TESTED.

## 5.4 Current System Status

| Area | Status | Evidence | Remaining work |
|---|---|---|---|
| SQLite schema and FK setup | IMPLEMENTED, TESTED | database/schema.sql, db.py, DB tests | Production backup/operations |
| Legacy Module 0 query workflow | IMPLEMENTED, TESTED | Query/regression tests | Preserve compatibility |
| Authentication/sessions | IMPLEMENTED, TESTED | Auth service/tests | OTP/recovery/rate limits |
| Google mapping | IMPLEMENTED, TESTED with injected verifier | Provider table/service tests | Live console/client configuration |
| Modern businesses/memberships | IMPLEMENTED, TESTED | Business service/tests | Ownership transfer not implemented |
| Financial accounts | IMPLEMENTED, TESTED | Account service/tests | Real account mapping |
| Module 4 canonical ingestion | IMPLEMENTED, TESTED | Module 4 test suites | Production mapping/source approval |
| CSV normalization/integration | IMPLEMENTED, TESTED | CSV and Streamlit tests | Broader bank-format coverage as needed |
| Module 5 analytics | IMPLEMENTED, TESTED | 18 backend + 18 UI tests | UI path cleanup |
| Module 6 health/anomalies | IMPLEMENTED, TESTED | 27 tests | Rule governance and UI polish |
| Module 7 reporting | IMPLEMENTED, TESTED | 19 tests | PDF/export presentation |
| Module 7 decision support | IMPLEMENTED, TESTED | 13 tests | Product review of thresholds |
| Documents/chunks CRUD | IMPLEMENTED, TESTED as CRUD | Query smoke test/schema | Full document intelligence |
| RAG/embeddings/citations | PLANNED/DEFERRED | Optional scheme_rag.py only | Backend architecture and dependencies |
| Production deployment | UNRESOLVED | No deployment/backup config | Define safe operational target |
| Documentation/setup | PARTIALLY IMPLEMENTED | Scattered docs, empty root README | Consolidate setup and status |

## 5.5 Database Evolution

~~~text
Module 0  Database foundation
    ↓
Module 1  Authentication, sessions, user identity
    ↓
Module 2  Modern businesses and memberships
    ↓
Module 3  Financial accounts and exact opening balances
    ↓
Module 4  Explicit bridge, canonical validation, identity, ingestion
    ↓
Module 5  Read-only analytics and trends
    ↓
Module 6  Health metrics and deterministic anomalies
    ↓
Module 7  Reports and decision support
~~~

Each stage consumes the previous stage’s trusted boundary. Analytics does not
bypass accepted identity rows, health does not recalculate SQL KPIs, and
reports/decision support consume analytics/health rather than reading
arbitrary files.

## 5.6 Glossary

| Term | Meaning |
|---|---|
| SQLite | A serverless relational database stored in a local file |
| Schema | Tables, columns, constraints, indexes and relationships |
| Primary key | A column/value that uniquely identifies a row |
| Foreign key | A constraint linking a row to a parent table |
| Index | An auxiliary structure that speeds lookups |
| CRUD | Create, read, update and delete operations |
| Parameterized SQL | SQL with placeholders and separately bound values |
| SQL injection | Supplying input that changes SQL syntax rather than remaining a value |
| Migration | A controlled change that upgrades an existing database |
| UUID | A high-entropy identifier format; FinSight uses UUID entropy in text IDs |
| Authentication | Proving who a user is |
| Authorization | Deciding what an authenticated user may do |
| Session | Server-recognized period of authenticated access |
| Password hash | One-way derived value used to verify a password without storing it |
| Token hash | One-way value stored for a bearer session token |
| Business membership | A user’s role/status inside one modern business |
| Ledger | A record of financial transactions |
| Minor unit | Integer currency subunit, such as paise; ₹100.25 becomes 10025 |
| Data integrity | Correctness, consistency and valid relationships of stored data |
| Regression test | A test ensuring older behavior still works after a change |
| Ingestion | Validating and persisting external financial records |
| Bridge | Explicit relationship between modern and legacy business IDs |
| PII | Personally identifiable information |
| Idempotency | Repeating the same operation without creating duplicate effect |
| Fail closed | Rejecting when required authority/evidence is absent |

## 5.7 How I Would Explain My Database Work to My Teacher

I worked mainly on the backend and database side of FinSight. The project uses
SQLite as its database. My work started with auditing and repairing the
original database foundation. The early repository had database placeholders,
so Module 0 established the schema, connection helper, query layer, foreign
keys, and tests. I kept the original legacy financial tables because existing
queries and regression behavior depended on them.

In Module 1 I added the security boundary around users. Passwords are stored
as BCrypt hashes, not plain text. When a user logs in, FinSight creates a
random session token but stores only its SHA-256 hash. Logout revokes that
hash, and session validation checks expiry and whether the user is still
active. I also kept global application roles separate from the role a user
has inside a particular business. Google sign-in is mapped through a provider
identity table after the ID token is verified; live Google console setup still
has to be configured separately.

Module 2 introduced the modern businesses and business_memberships tables. A
business creator becomes the owner, and membership roles are owner, manager,
member, or viewer. The backend never trusts a user ID or role sent by the
frontend. It derives the user from the validated session and checks the
membership from the database. This is how I enforce business isolation.

Module 3 added financial_accounts. Accounts belong to modern businesses,
have a type, institution, optional identifier, currency, opening balance, and
active/disabled status. Money is represented in integer minor units for new
account and ingestion identity data. For example, ₹100.25 is stored as 10025.
I use Decimal while parsing values so that binary floating point does not
silently change financial results. Account identifiers are masked in
responses.

The biggest design issue came in Module 4. The modern business table and the
old business_registry table are not the same identity. The old ledger still
points to the registry table, while authorization and accounts point to the
modern business. I could not safely replace the legacy table, so I introduced
an explicit verified bridge. Ingestion checks the session, active owner or
manager membership, active account, bridge, registry business, and legacy
owner before writing anything.

Module 4 also separates validation, identity generation, and persistence. A
canonical record has an exact amount, date and direction. A deterministic
identity hash does not include the uploader or row number, so re-uploading a
record can be recognized as a duplicate. Accepted identity rows point to
legacy ledger projections. The attempt, ledger rows, and identity rows are
written atomically. If storage fails, the financial transaction rolls back;
retries create a new linked attempt instead of overwriting history.

Module 5 reads only accepted identity rows and produces analytics such as
income, expense, net cash flow, balances, trends, categories and payment
summaries. Module 6 interprets those results into health scores and
explainable anomalies. Module 7 builds reports and deterministic
recommendations on top of the existing services. These modules are read-only
and do not change transactions.

I also verified the CSV normalizer. It supports common bank variations such
as different date/description/amount headers, commas, currency symbols,
debit/credit columns, BOM, quoted commas, and semicolon exports. It only
produces the canonical JSON contract; the existing Module 4 validator and
identity rules remain authoritative.

The main database security decisions were parameterized SQL, foreign keys,
hashed credentials, session revocation, membership authorization, explicit
bridging, exact minor units, and sanitized errors. The main challenges were
backward compatibility, the two business models, duplicate-safe ingestion,
and keeping old ledger semantics while adding stronger new controls.

The current automated result is 498 passed tests. That verifies the controlled
implementation and its regression safety, but it does not prove production
deployment. Production business/account mappings, a general migration
framework, OTP workflow, full document intelligence, backup/HA operations,
and some legacy Streamlit path/dependency issues remain.

# APPENDIX A — Database Tables

| Table | Module | One-line purpose |
|---|---|---|
| users | 0–1 | Local identity, credentials, global role/status |
| business_registry | 0 | Legacy business owner boundary |
| counterparty_entities | 0 | Legacy business counterparties |
| transaction_general_ledger | 0 | Legacy financial ledger |
| structural_budget_allocations | 0 | Legacy category budgets |
| pipeline_upload_ingestion_logs | 0 | Legacy upload summaries |
| authentication_logs | 1 | Authentication/security events |
| otp_verifications | 1 schema | OTP hash/expiry records |
| documents | Legacy feature | Document metadata |
| document_chunks | Legacy feature | Document text chunks |
| auth_sessions | 1 | Hashed session token lifecycle |
| provider_identities | 1 | Google/provider subject mapping |
| businesses | 2 | Modern business profiles |
| business_memberships | 2 | Tenant roles and status |
| financial_accounts | 3 | Business-owned financial accounts |
| business_registry_bridges | 4 | Modern/legacy business bridge |
| ingestion_attempts | 4 | Batch/retry audit boundary |
| ingested_transaction_identities | 4 | Accepted canonical identity |

# APPENDIX B — Important Database Files

| File | Purpose | Module |
|---|---|---|
| database/schema.sql | Authoritative tables, constraints, indexes and FK pragma | 0–4 |
| database/db.py | Connection factory, initialization and additive user migration | 0–3 |
| database/queries.py | Parameterized SQL and repository helpers | 0–4 |
| database/__init__.py | Database package marker | 0 |
| tests/conftest.py | Isolated temporary SQLite fixture using production schema | Testing |
| tests/test_schema.sql | Older standalone/reference schema; not authoritative fixture | Legacy/testing |
| services/ingestion_validation.py | Pure canonical validation | 4 |
| services/ingestion_identity.py | Deterministic hash/classification | 4 |
| services/ingestion_service.py | Authorized atomic persistence | 4 |
| services/analytics_service.py | Read-only exact analytics | 5 |
| services/business_health_service.py | Read-only health/anomaly interpretation | 6 |
| services/report_service.py | Report adapter/export structures | 7 |
| services/decision_support_service.py | Deterministic recommendations | 7 |
| services/csv_normalizer.py | CSV-to-canonical preprocessing | CSV layer |

# APPENDIX C — Test Files

| Test file | What it verifies |
|---|---|
| test_db.py | Schema creation, migrations, constraints and data preservation |
| test_queries.py | Legacy query workflow |
| test_module0_regression.py | Original Module 0 compatibility |
| test_auth.py | Passwords, sessions, logout, roles, Google identity |
| test_business_service.py | Business/membership roles and isolation |
| test_account_service.py | Account lifecycle, minor units, isolation |
| test_module4_schema.py | Additive ingestion schema and constraints |
| test_module4_queries.py | Ingestion repository access and lifecycle |
| test_module4_validation.py | Canonical payload/record boundaries |
| test_module4_identity.py | Determinism, duplicates, conflicts and safety |
| test_module4_ingestion_service.py | Authorization, atomicity, rollback, retries |
| test_module4_end_to_end.py | Controlled batch lifecycle |
| test_module4_streamlit.py | Upload adapter and CSV wiring |
| test_module5_analytics.py | KPIs, trends, summaries, currency and isolation |
| test_module5_streamlit.py | Analytics UI/service invocation |
| test_module6_health.py | Health metrics/anomalies |
| test_csv_normalizer.py | Flexible CSV formats and safe rejection |
| test_module7_reports.py | Report sections, sanitization and export rows |
| test_module7_decision_support.py | Recommendation rules and deterministic output |
| test_backend_polish.py | Analytics authorization hardening |

# APPENDIX D — Module Status

| Module | Purpose | Database changes | Testing | Current status |
|---|---|---|---|---|
| 0 | Foundation | Initial legacy schema and queries | DB/query/regression tests | IMPLEMENTED, TESTED |
| 1 | Auth/identity | User columns, sessions, provider identities, auth logs | 11 auth + migration tests | IMPLEMENTED, TESTED |
| 2 | Business/membership | businesses, business_memberships | 14 service + schema tests | IMPLEMENTED, TESTED |
| 3 | Accounts | financial_accounts, minor opening balance | Account and migration tests | IMPLEMENTED, TESTED |
| 4 | Ingestion | Bridge, attempts, identities | 300+ focused tests | IMPLEMENTED, TESTED for controlled demo |
| 5 | Analytics | No schema change | 36 backend/UI tests | IMPLEMENTED, TESTED |
| 6 | Health/anomalies | No schema change | 27 tests | IMPLEMENTED, TESTED |
| 7 | Reports/decisions | No schema change | 32 tests | IMPLEMENTED, TESTED |
| CSV | Preprocessing | No schema change | 22 + integration tests | IMPLEMENTED, TESTED |

# APPENDIX E — Known Limitations & Future Work

1. Establish and review authoritative production mappings between modern
   businesses, legacy registries, accounts, currencies, and source systems.
   Until then, keep ingestion fail-closed.
2. Decide whether a general migration/versioning framework is required beyond
   the current additive initializer.
3. Consolidate setup instructions in a maintained root README and document the
   correct Windows working directory and virtual environment.
4. Fix the legacy Streamlit CWD-relative CSV path and ensure ReportLab is
   installed in the same interpreter used to launch Streamlit.
5. Improve PDF table wrapping and add a layout regression check.
6. Decide whether OTP/password recovery is in scope; if so, implement service,
   rate limits, delivery and tests around the existing table.
7. Keep employee/payroll PII out of canonical ingestion unless a privacy-safe
   identity and purpose are explicitly approved.
8. Define production SQLite backup, restore, locking, retention and deployment
   procedures, or select a different deployment database with an approved
   migration plan.
9. Separate or retire the optional scheme RAG prototype unless document
   ingestion, embeddings, citations and provider secrets receive an explicit
   backend design.
10. Refresh historical design-only Module 4 documents so readers can see which
    decisions were later implemented and which remain open.
11. Review Module 7 threshold policy with the project owner; deterministic rules
    are implemented, not predictive financial advice.
