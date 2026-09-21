> Historical design record: normal onboarding approval requirements in this document are superseded by the automatic internal mapping design in [README](../README.md#automatic-onboarding-and-existing-databases).

# FinSight Module 4 Completion Report

**Assessment:** CONTROLLED DEMO READY

**Production status:** NOT PRODUCTION READY / NOT PRODUCTION APPROVAL

**Repository checkpoint:** `002fca2c20f4bb558670550f0ec3d128cccb70ad`

## Architecture summary

Module 4 preserves the existing FinSight layering:

```text
Streamlit -> service layer -> database/queries.py -> database/db.py -> SQLite
```

The Streamlit adapter authenticates the session, presents authorized business
and account selectors, accepts an already-standardized canonical JSON payload,
and delegates ingestion to `services/ingestion_service.py`. It does not own
authorization, validation, identity, or financial persistence.

The ingestion service re-reads trusted session, business, membership, account,
bridge, registry-business, and registry-owner state before classification and
writing. The legacy ledger remains the financial store; Module 4 adds audit and
identity structures without rewriting historical ledger semantics.

## Implemented phases

The verified implementation history is:

| Commit | Scope |
|---|---|
| `06d0dd7` | Additive Module 4 schema foundation |
| `ef15341` | Repository/query layer |
| `9fdc611` | Canonical validation |
| `3f9e2cb` | Canonical identity and idempotency |
| `86ec32d` | Authorization/orchestration foundation |
| `df19887` | Atomic financial writes and rollback |
| `512a753` | Batch outcomes, failure handling, and retry lifecycle |
| `d214036` | End-to-end backend integration |
| `002fca2` | Streamlit integration |

## Database additions

The additive D18 schema contains:

- `business_registry_bridges`: explicit Module 2 to legacy registry mapping,
  active-state verification metadata, and one-active-side constraints.
- `ingestion_attempts`: uploader attribution, selected account/currency,
  counts, processing/completed/failed state, safe errors, and retry lineage.
- `ingested_transaction_identities`: exact minor-unit identity components,
  source identity, canonical hash, and links to the legacy transaction and
  ingestion attempt.

Foreign keys, status checks, nonnegative counts, active-bridge uniqueness,
canonical-hash uniqueness, and partial source-ID uniqueness are retained.
Database initialization remains additive and idempotent. Existing Module 0–3
rows are preserved and no historical identity backfill is performed.

## Repository/query layer

The repository provides caller-aware Module 4 lookups for active businesses,
active memberships, active accounts, active verified bridges, registry
businesses, and registry owners. It also provides attempt creation/finalization,
identity lookups/insertion, legacy ledger insertion, and a transaction context
that allows the service to coordinate writes on one SQLite connection.

Queries are parameterized. Caller-supplied connections are not independently
committed or rolled back by the repository helpers.

## Canonical validation

The validator enforces the controlled canonical envelope and record contract:

- exact `finsight_ingestion_v1` contract version;
- exact demo-only `finsight_demo_bank_statement_v1` source token;
- strict envelope/record allowlists;
- ordered batches of 1–1000 records;
- positive integer `amount_minor` values through `99,999,999,999,999`;
- strict `income`/`expense` directions;
- strict `YYYY-MM-DD` calendar dates;
- bounded optional text and source IDs;
- signed validation-only `balance_after_minor` bounds;
- no trimming, case folding, coercion, or account/currency/payroll overrides.

Validation is pure and performs no database writes.

## Canonical identity and idempotency

Identity V1 serializes the fixed array of identity version, verified account,
source system, verified currency, date, exact minor-unit amount, and direction
as compact UTF-8 JSON. SHA-256 lowercase hexadecimal is stored as the canonical
hash. Uploader, retry, row position, source ID, descriptive fields, and bridge
routing IDs are excluded from the hash.

When present, `(account_id, source_system, source_transaction_id)` is checked
first. Canonical-hash duplicate checks remain authoritative for source-ID-absent
rows and protect against changed source identifiers. Same source ID with changed
identity is a conflict; persisted component mismatches are fail-closed conflicts.

## Ingestion service and financial writes

`prepare_ingestion()` is read-only and performs the authorization and identity
preparation boundary. `ingest()` coordinates the authorized write path.

Only active `owner` and `manager` memberships may ingest. Administrator status
alone does not grant tenant ingestion access. The selected account must be
active and belong to the selected Module 2 business. An active independently
verified bridge is required. The ledger receives the bridged legacy registry
business and legacy registry owner; the authenticated actor is stored separately
as the attempt uploader.

For unique records, the attempt, legacy ledger row, and identity companion are
written through one service-owned SQLite transaction. Any financial failure
rolls back the financial unit. A supplied connection remains caller-owned.
Duplicate records do not create a second ledger or identity row.

## Rollback, failure, and retry lifecycle

Attempts use only `processing`, `completed`, and `failed` states. Successful
operations finalize counts and completion time. Storage failures roll back
financial writes and may create a separate sanitized failed attempt when the
caller requests failure recording. Raw SQL, exception text, payloads, and
secrets are not persisted in failure messages.

Retries receive a new attempt ID and may link to the prior attempt through
`parent_attempt_id`. Retry lineage is excluded from transaction identity, so a
retry of the same transaction remains idempotent.

## Streamlit integration

`finsight_app/app.py` now provides session login, session revalidation, logout,
and expiry handling while preserving the existing synthetic dashboard.
`finsight_app/ingestion_ui.py` provides:

- active owner/manager business selection;
- active account selection scoped to the selected business;
- canonical JSON upload only;
- one backend ingestion-service call on submission;
- total, inserted, duplicate, rejected, and retry-count display;
- fixed safe validation, conflict, authentication, and storage messages.

The UI does not display session tokens, hashes, attempt IDs, SQL, payload
contents, stack traces, filesystem paths, or internal database identifiers.
Raw CSV/XLSX/PDF parsing, OCR, and source-specific standardization remain
outside Module 4.

## Verification summary

- Full regression: **373 passed**, **0 failed**, **0 skipped**, **0 collection
  errors**.
- Full-suite runtime in the available test environment: **197.85 seconds**.
- Database/Module 0–4 targeted verification: **165 passed**.
- Python compile/import smoke checks: clean.
- `git diff --check`: clean before this report; it will be rerun after staging.

The test suite covers schema constraints and idempotent initialization,
authorization matrices, exact validation, golden identity vectors, duplicate
and conflict behavior, atomic writes, rollback, retry lineage, end-to-end
flows, and Streamlit adapter behavior using a framework-compatible test double.

## Controlled-demo limitations

- The only approved source is `finsight_demo_bank_statement_v1`.
- The only concrete approved demo account currency is INR.
- Demo identifiers and fixtures are synthetic and non-production.
- The UI accepts standardized canonical JSON; it is not a bank-statement
  parser or connector.
- Browser-level Streamlit automation is not included; UI behavior is covered
  through a deterministic adapter test double.

## Production limitations

Production readiness is not claimed. Exact production business-to-registry
mappings, account evidence, source tokens, currencies, and customer data are
still unavailable. The current legacy projection uses the existing two-decimal
minor-unit compatibility rule and direct `income`/`expense` ledger type values;
those assumptions require explicit production-domain approval for any broader
currency or source scope.

The Phase 3D and Phase 3E decision documents referenced by the preceding
workflow are not present in this checkout. Their implemented controlled values
are visible in the validator, identity module, tests, and commit history, but
the missing decision-document artifacts should be restored or separately
approved before production expansion.

## Future work

Before any production rollout, complete a separate evidence and security gate
for real mappings, account/currency/source coverage, operational secrets,
deployment configuration, observability, rate limits, and browser-level UI
testing. Preserve the current additive schema and uniqueness constraints while
performing that review. Do not use `acctual data/` or synthetic fixtures as
production evidence.
