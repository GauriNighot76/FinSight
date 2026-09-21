> Historical design record: normal onboarding approval requirements in this document are superseded by the automatic internal mapping design in [README](../README.md#automatic-onboarding-and-existing-databases).

# Phase 3C — D18 Minimal Additive Schema Design

## Status

READY FOR REVIEW — DESIGN ONLY

This document defines the proposed minimal additive database design for FinSight Module 4 ingestion.

It does not modify the database schema, create migration code, insert demo records, implement services, or authorize production deployment.

This design is constrained by the approved Phase 3A / Phase 3B decisions and the controlled non-production demo evidence.

---

## 1. Design goals

D18 must provide the minimum database structure required to support safe Module 4 ingestion while preserving all existing Module 0–3 behavior.

The design must:

1. Explicitly bridge Module 2 businesses to legacy `business_registry` records.
2. Preserve legacy ledger ownership semantics.
3. Associate each ingestion batch with exactly one verified Module 3 financial account.
4. Record uploader identity separately from legacy ledger owner identity.
5. Record a controlled `source_system`.
6. Support deterministic duplicate detection and idempotent retries.
7. Support atomic financial writes.
8. Support sanitized success/failure audit logging.
9. Avoid invented or inferred historical mappings.
10. Remain additive and backward compatible.

---

## 2. Existing boundaries that must remain unchanged

### Module 0 legacy financial boundary

The existing legacy financial tables continue to use `business_registry.business_id`.

`transaction_general_ledger.business_id` continues to reference the legacy registry business.

`transaction_general_ledger.user_id` retains its legacy-owner meaning.

Module 4 must not reinterpret `transaction_general_ledger.user_id` as the uploader.

### Module 2 business boundary

`businesses.business_id` is the authoritative Module 2 business identifier.

Authorization is determined through `business_memberships`.

Only an active owner or manager may ingest.

### Module 3 account boundary

`financial_accounts.account_id` belongs to a Module 2 business.

Each Module 4 ingestion batch must select exactly one active account.

The account must belong to the authorized Module 2 business.

Currency comes from the verified account.

---

## 3. Approved controlled demo evidence

The controlled non-production demo evidence is:

- Module 2 business: `demo_business_001`
- active owner: `demo_owner_001`
- legacy registry business: `legacy_demo_business_001`
- financial account: `demo_account_001`
- currency: `INR`
- approved source token: `finsight_demo_bank_statement_v1`

These identifiers are controlled non-production evidence only.

They must not be treated as production customer data.

The schema design must not depend on matching business names, account names, filenames, PDFs, spreadsheets, or raw upload contents.

---

## 4. Proposed table: `business_registry_bridges`

### Purpose

Provide the explicit relationship between a Module 2 business and a legacy `business_registry` business.

This table resolves the structural separation between the Module 2 authorization boundary and the Module 0 financial boundary.

### Proposed columns

| Column | Type | Required | Purpose |
|---|---|---:|---|
| `bridge_id` | TEXT | Yes | Stable bridge identifier |
| `business_id` | TEXT | Yes | Module 2 `businesses.business_id` |
| `registry_business_id` | TEXT | Yes | Legacy `business_registry.business_id` |
| `proposed_by_user_id` | TEXT | Yes | Active owner who proposed the bridge |
| `verified_by_user_id` | TEXT | No until verified | Global administrator who verified the bridge |
| `bridge_status` | TEXT | Yes | `pending`, `active`, `rejected`, or `disabled` |
| `proposed_at` | TEXT | Yes | Proposal timestamp |
| `verified_at` | TEXT | No | Verification timestamp |
| `updated_at` | TEXT | Yes | Last state-change timestamp |

### Foreign keys

- `business_id` → `businesses(business_id)`
- `registry_business_id` → `business_registry(business_id)`
- `proposed_by_user_id` → `users(user_id)`
- `verified_by_user_id` → `users(user_id)`

### Constraints

- `bridge_id` primary key.
- One Module 2 business may have at most one active bridge.
- One legacy registry business may have at most one active bridge.
- `bridge_status` must be one of the approved states.
- An active bridge must have `verified_by_user_id` and `verified_at`.
- Proposal and verification must be attributable to separate workflow roles.
- Module 4 ingestion accepts only `bridge_status = 'active'`.

### Required indexes

- index on `(business_id, bridge_status)`
- index on `(registry_business_id, bridge_status)`

A partial unique index should enforce one active bridge per Module 2 business.

A partial unique index should enforce one active bridge per legacy registry business.

---

## 5. Proposed table: `ingestion_attempts`

### Purpose

Represent one authenticated Module 4 ingestion request or retry attempt.

This is the primary audit boundary for ingestion.

It keeps uploader attribution separate from ledger ownership.

### Proposed columns

| Column | Type | Required | Purpose |
|---|---|---:|---|
| `attempt_id` | TEXT | Yes | Stable ingestion-attempt identifier |
| `parent_attempt_id` | TEXT | No | Prior failed attempt when this is a retry |
| `business_id` | TEXT | Yes | Authorized Module 2 business |
| `registry_business_id` | TEXT | Yes | Verified legacy business resolved via active bridge |
| `account_id` | TEXT | Yes | Exactly one verified Module 3 account |
| `uploader_user_id` | TEXT | Yes | Authenticated user performing ingestion |
| `source_system` | TEXT | Yes | Approved controlled source token |
| `contract_version` | TEXT | Yes | Accepted Module 4 ingestion contract version |
| `currency` | TEXT | Yes | Verified account currency snapshot |
| `record_count` | INTEGER | Yes | Total canonical records presented |
| `inserted_count` | INTEGER | Yes | Successfully inserted records |
| `duplicate_count` | INTEGER | Yes | Deterministic duplicates |
| `rejected_count` | INTEGER | Yes | Records rejected before financial write |
| `attempt_status` | TEXT | Yes | Sanitized attempt state |
| `public_error_code` | TEXT | No | Stable safe error code |
| `public_error_message` | TEXT | No | Safe client-facing message |
| `created_at` | TEXT | Yes | Attempt creation timestamp |
| `completed_at` | TEXT | No | Completion timestamp |

### Foreign keys

- `parent_attempt_id` → `ingestion_attempts(attempt_id)`
- `business_id` → `businesses(business_id)`
- `registry_business_id` → `business_registry(business_id)`
- `account_id` → `financial_accounts(account_id)`
- `uploader_user_id` → `users(user_id)`

### Status values

Proposed controlled values:

- `processing`
- `completed`
- `failed`

The implementation may distinguish validation rejection at record level rather than inventing additional batch statuses unless later approved.

### Constraints

- `record_count >= 0`
- `inserted_count >= 0`
- `duplicate_count >= 0`
- `rejected_count >= 0`
- completed attempts must have `completed_at`
- `currency` must be uppercase three-character text
- `source_system` must be a controlled allowed value
- the selected account must belong to the same Module 2 `business_id`

The cross-table account/business relationship must be verified server-side before any financial write.

---

## 6. Proposed table: `ingested_transaction_identities`

### Purpose

Store the canonical identity of each Module 4 ingested transaction independently of legacy floating-point ledger fields.

This table provides durable duplicate detection and idempotency without changing the meaning of existing legacy ledger columns.

### Proposed columns

| Column | Type | Required | Purpose |
|---|---|---:|---|
| `identity_id` | TEXT | Yes | Stable identity-row identifier |
| `transaction_id` | TEXT | Yes | Created legacy ledger transaction |
| `attempt_id` | TEXT | Yes | Ingestion attempt that first inserted it |
| `business_id` | TEXT | Yes | Module 2 business |
| `registry_business_id` | TEXT | Yes | Legacy business |
| `account_id` | TEXT | Yes | Verified financial account |
| `source_system` | TEXT | Yes | Controlled source |
| `source_transaction_id` | TEXT | Yes | Source-level stable transaction identifier |
| `transaction_date` | TEXT | Yes | Canonical transaction date |
| `amount_minor` | INTEGER | Yes | Exact non-negative amount magnitude |
| `direction` | TEXT | Yes | Canonical money direction |
| `currency` | TEXT | Yes | Verified account currency |
| `canonical_identity_hash` | TEXT | Yes | Deterministic canonical hash |
| `created_at` | TEXT | Yes | Identity creation timestamp |

### Foreign keys

- `transaction_id` → `transaction_general_ledger(transaction_id)`
- `attempt_id` → `ingestion_attempts(attempt_id)`
- `business_id` → `businesses(business_id)`
- `registry_business_id` → `business_registry(business_id)`
- `account_id` → `financial_accounts(account_id)`

### Direction values

Only the approved canonical economic directions are allowed:

- `income`
- `expense`

### Identity rule

The durable duplicate identity must be uploader-independent.

At minimum, the identity is scoped by:

- verified account
- controlled source system
- source transaction identifier
- canonical transaction date
- exact minor-unit amount
- direction
- verified currency

The uploader user ID must never participate in duplicate identity.

### Uniqueness

A unique constraint/index must guarantee that the same canonical source transaction cannot be inserted twice for the same account/source scope.

The final exact identity encoding must be deterministic and versioned in implementation.

The database must also enforce uniqueness of `canonical_identity_hash`.

---

## 7. Legacy ledger interaction

The existing `transaction_general_ledger` remains the financial ledger.

D18 must not change the semantic meaning of existing columns.

### Required behavior for new Module 4 writes

For a newly ingested Module 4 transaction:

- `business_id` receives the verified legacy `registry_business_id`.
- `user_id` receives the verified legacy registry owner required by the existing legacy model.
- uploader identity is stored in `ingestion_attempts.uploader_user_id`.
- account identity is stored in `ingested_transaction_identities.account_id`.
- exact minor-unit identity is stored in `ingested_transaction_identities.amount_minor`.
- source information is stored in the Module 4 identity/audit structures.

### Historical rows

Existing ledger rows must not be blindly backfilled with:

- Module 2 business IDs
- financial account IDs
- uploader IDs
- source-system values
- source transaction IDs
- canonical identity hashes
- exact minor-unit values

unless authoritative evidence exists for those specific historical rows.

No such historical evidence is currently approved.

Therefore historical legacy rows remain unchanged.

---

## 8. Existing `pipeline_upload_ingestion_logs`

The existing `pipeline_upload_ingestion_logs` table is legacy infrastructure.

D18 must not silently change its meaning or retrofit it into the new Module 4 security boundary.

Module 4 should use the new `ingestion_attempts` structure for its authoritative audit record.

Legacy logging may remain available for backward compatibility, but Module 4 must not rely on it for account authorization, bridge authorization, canonical transaction identity, or uploader/owner separation.

No destructive migration of the legacy table is approved.

---

## 9. Source-system control

For the currently approved controlled demo implementation, the only approved Module 4 source token is:

`finsight_demo_bank_statement_v1`

The schema must not infer or generate source tokens from filenames or source descriptions.

Unknown source tokens must fail closed before financial writes.

Production source tokens remain unapproved.

---

## 10. Currency rule

Currency comes from the verified active financial account.

For the approved demo account, the authoritative currency is:

`INR`

Module 4 must:

- verify the selected account server-side;
- read the account currency;
- use that currency for the whole batch;
- reject conflicting record/UI currency values;
- perform no conversion;
- perform no filename/source-based currency inference.

The ingestion-attempt and transaction-identity rows store the verified currency as an immutable audit snapshot for that ingestion.

---

## 11. Atomicity

All financial changes for a successful ingestion batch must occur atomically.

The financial transaction includes, as applicable:

1. creation of the active `ingestion_attempts` processing state or equivalent transaction-scoped record;
2. insertion of new legacy ledger transactions;
3. insertion of their canonical identity rows;
4. final success counts/status update.

If a financial write fails, the financial transaction must roll back.

After rollback, a sanitized failure attempt record may be written in a separate transaction according to the approved logging decision.

A retry receives a new `attempt_id` and may reference the previous attempt through `parent_attempt_id`.

---

## 12. Authorization order required before writes

The service must verify, in order:

1. authenticated session;
2. authorized Module 2 business;
3. active owner or manager membership;
4. exactly one selected active financial account belonging to that business;
5. active verified Module 2 → legacy registry bridge;
6. valid legacy registry owner;
7. approved `source_system`;
8. valid contract version and canonical records;
9. deterministic duplicate identity;
10. atomic ledger + identity writes;
11. sanitized audit completion.

No ledger write may occur before these authorization checks succeed.

---

## 13. Fail-closed requirements

Module 4 must reject the request when any required relationship is missing or ambiguous.

Examples include:

- no active membership;
- unsupported membership role;
- inactive business;
- no selected account;
- account belongs to another business;
- inactive account;
- no active bridge;
- multiple active bridges;
- legacy registry business missing;
- legacy registry owner missing;
- unsupported source token;
- unsupported contract version;
- malformed canonical record;
- unsupported direction;
- invalid exact money value;
- missing source transaction ID;
- duplicate canonical identity.

Duplicate canonical identities are reported as duplicates rather than inserted again.

Authorization failures must not leak SQL details, stack traces, local paths, raw financial data, secrets, or internal identifiers beyond the approved safe response contract.

---

## 14. Migration strategy

The D18 migration must be additive.

Approved migration operations may include:

- `CREATE TABLE IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS`
- additive constraints achievable safely in SQLite
- safe migration helpers executed from `database/db.py`

The migration must not:

- drop legacy tables;
- rename legacy columns;
- reinterpret legacy ledger columns;
- delete existing rows;
- blindly update legacy rows;
- infer bridge relationships;
- infer account mappings;
- infer source systems;
- infer currencies.

Existing databases must migrate idempotently.

Running initialization multiple times must not duplicate structures or alter existing data.

---

## 15. Demo evidence population

The approved demo identifiers may be used later to establish a controlled non-production end-to-end demo.

They must not be inserted automatically by the general database migration.

Schema initialization and demo-data creation are separate concerns.

If demo seed data is introduced, it must be explicit, non-production-only, separately invoked, and covered by tests.

---

## 16. Required migration/schema tests before implementation

Before changing production schema code, tests must be written for at least:

1. creation of `business_registry_bridges`;
2. bridge foreign keys;
3. bridge status constraint;
4. one active bridge per Module 2 business;
5. one active bridge per legacy registry business;
6. creation of `ingestion_attempts`;
7. ingestion-attempt foreign keys;
8. ingestion count constraints;
9. account/business verification behavior;
10. creation of `ingested_transaction_identities`;
11. transaction identity foreign keys;
12. direction constraint;
13. amount stored as integer minor units;
14. canonical identity uniqueness;
15. duplicate insertion rejection;
16. migration idempotency;
17. preservation of existing Module 0–3 schema and data;
18. no automatic historical backfill;
19. existing regression suite remains passing.

The existing regression baseline is 48 passing tests before Module 4 migration work.

---

## 17. Proposed indexes summary

### `business_registry_bridges`

- `(business_id, bridge_status)`
- `(registry_business_id, bridge_status)`
- unique active bridge for `business_id`
- unique active bridge for `registry_business_id`

### `ingestion_attempts`

- `(business_id, created_at)`
- `(account_id, created_at)`
- `(uploader_user_id, created_at)`
- `(attempt_status, created_at)`
- `(parent_attempt_id)`

### `ingested_transaction_identities`

- unique `(canonical_identity_hash)`
- unique source identity scope as finalized by implementation
- `(account_id, created_at)`
- `(transaction_id)`
- `(attempt_id)`
- `(registry_business_id, transaction_date)`

---

## 18. D18 decision

D18 is considered design-complete when the following are explicitly accepted:

- the explicit bridge-table approach;
- separate ingestion attempt/audit structure;
- separate canonical transaction identity structure;
- preservation of legacy ledger ownership semantics;
- account and uploader attribution remain outside legacy ledger ownership fields;
- exact minor-unit identity is additive rather than a blind rewrite of historical REAL values;
- migration is additive and idempotent;
- historical rows are not backfilled without authoritative evidence;
- controlled demo values remain non-production-only.

Until this design is approved, no Module 4 schema migration should be implemented.

---

## 19. Next implementation gate

After D18 approval, the next permitted implementation step is:

**write migration/schema tests first.**

Only after those tests exist should `database/schema.sql` and/or `database/db.py` be modified to implement the approved additive migration.

Module 4 service code must still wait until the schema/query foundation is implemented and verified.
