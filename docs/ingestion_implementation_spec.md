# FinSight Module 4 — Ingestion Implementation Specification

**Document status:** RECONSTRUCTED DRAFT — DESIGN ONLY
**Reconstruction phase:** Phase 3A
**Repository baseline:** `59744445a4ed80199999c03ace11e98023065c95`
**Contract reference:** `docs/ingestion_ui_contract.md`, version
`1.0-reconstructed-draft`

> The lost Phase 3 specification could not be recovered. This is a new,
> auditable reconstruction and is not the original file. It contains no
> production code, SQL migration, parser, tests, or Streamlit implementation.
> Status labels distinguish facts, preserved decisions, recommendations, and
> unresolved work.

## 1. Executive summary

**Evidence status:** CONFIRMED FROM CONVERSATION

Module 4 will eventually accept canonical transaction records and persist
authorised, valid, unique transactions in the existing
`transaction_general_ledger`. It must reuse Module 1 sessions, Module 2
business memberships, Module 3 account access, the existing query/database
layers, and the existing upload-log concept.

Implementation is blocked. Only D01 is approved. This specification describes
the intended architecture and the dependencies that must be approved before
schema or code work begins.

## 2. Repository evidence inventory

**Evidence status:** CONFIRMED FROM REPOSITORY

| File/component | Relevant behavior | Security/financial implication | Decisions |
|---|---|---|---|
| `database/schema.sql` | Defines both business models, legacy ledger/log, memberships and accounts | No bridge; ledger uses registry business and `REAL`; account balance uses minor units | D02–D04, D07, D09–D11, D18 |
| `database/db.py` | Enables foreign keys; executes authoritative schema; performs limited additive `users` migration | Future migration must remain idempotent and non-destructive | D18 |
| `database/queries.py` | Parameterised queries and UUID-prefixed IDs; one connection per operation | Multi-row ingestion requires an explicit shared transaction design | D17–D18 |
| `create_transaction_hash()` | Hashes business/entity/date/rounded amount/type/category/mode/description/**user** | Uploader/owner affects legacy identity; incompatible with canonical identity | D04, D09, D15, D18 |
| `create_transaction()` | Detects existing hash but inserts anyway; converts Decimal to float | Not idempotent; loses exact canonical amount storage | D09, D18 |
| `get_business_transactions()` and summaries | Require registry business to belong to `user_id`; filter ledger by `user_id` | Legacy owner semantics cannot be silently repurposed | D04 |
| `services/auth_service.py` | Validates hashed session; global roles; public signup defaults to `standard_business` | Reusable authentication/global administrator boundary | D01, D12 |
| `services/business_service.py` | Active business/membership enforcement; owner/manager/member/viewer | Reusable tenant boundary | D01, D12 |
| `services/account_service.py` | Owner/manager write; all active roles read; active-account enforcement | Reusable account boundary; account currency exists | D07, D11, D12 |
| `pipeline_upload_ingestion_logs` | Registry-business log with counts/status/error | Missing duplicate/account/source/lifecycle fields | D16–D18 |
| `finsight_app/app.py` | Static demo; directly calls KPI/eligibility/PDF code | Not an ingestion client; no backend session/business/account integration | D05, D20 |
| `finsight_app/kpi_engine.py` | Reads raw CSV with pandas and source-specific date formats | Standardisation/parsing remains outside canonical ingestion | D05, D20 |
| `schemes/compute_kpis.py` | Assumes payroll funding and payroll represent the same money | Conflicts with observed non-reconciliation; not authoritative ledger policy | D08, D14, D15 |
| tests | Isolated temporary SQLite using production schema; 48 tests pass | Provides regression and FK/role/isolation conventions | all |

## 3. Current data and schema facts

**Evidence status:** CONFIRMED FROM REPOSITORY

### 3.1 Business identities

- `business_registry.business_id` identifies legacy ledger businesses and has
  one legacy owner `user_id`.
- `businesses.business_id` identifies Module 2 businesses.
- `business_memberships` connects users to Module 2 businesses.
- No table or query connects these two business identities.
- IDs from both models use the same `biz_` generation prefix, which does not
  make them interchangeable.

### 3.2 Ledger

The existing ledger has transaction, registry business, optional counterparty,
user, date, positive `REAL` amount, transaction type, category, payment mode,
description, hash, and creation time. It has no account ID, currency, source,
source transaction ID, direction, exact minor-unit amount, or post-balance.

### 3.3 Accounts

Financial accounts reference Module 2 businesses, use active/disabled status,
store uppercase three-character currency text, and store opening balances as
integer minor units. Currency syntax is checked; ISO membership is not.

### 3.4 Upload logs

The legacy log references registry business and optional user. It stores a
filename/type, total/success/failed counts, free status, one error message, and
upload time. Duplicate count and account/source context are absent.

## 4. Dataset evidence

**Evidence status:** CONFIRMED FROM REPOSITORY

| Source file | Rows | Date format | ID evidence | Fields relevant to canonicalisation |
|---|---:|---|---|---|
| main checking | 877 | `DD-MM-YYYY` | unique transaction IDs in current file | date, ID, description, category, type, amount, balance |
| secondary checking | 48 | `YYYY-MM-DD` | unique transaction IDs in current file | date, ID, description, category, type, amount, balance |
| credit card | 133 | `YYYY-MM-DD` | unique transaction IDs in current file | date, ID, vendor, category, type, amount, balance |
| payroll | 92 | `DD-MM-YYYY` | no transaction ID; repeated employee IDs | pay date, employee PII, role, subtype, amount, account label |

No raw file contains a FinSight business ID, registry ID, financial-account ID,
or currency. Repository inspection found no exact duplicate rows or duplicate
checking/card IDs in these files. Those observations do not establish future
source guarantees.

Payroll totals `159854`; secondary payroll debits total `97811`. No automatic
reconciliation, merge, or duplicate inference is permitted.

## 5. Approved architecture boundary

**Evidence status:** CONFIRMED FROM CONVERSATION

The service boundary is canonical records, not raw files:

```text
standardiser -> ingestion service -> query layer -> SQLite
```

Raw parsing, MIME inspection, XLSX/PDF/OCR, file staging, retention, and parser
dependencies are excluded unless D20 and a contract amendment approve them.

## 6. Proposed components

**Evidence status:** RECOMMENDATION

No component in this section exists yet.

| Component | Intended responsibility | Must not do |
|---|---|---|
| `services/ingestion_service.py` | Orchestrate auth, context, validation, identity, duplicate classification, transaction, result | Contain large SQL, trust Streamlit, parse arbitrary files |
| validation/identity helpers | Pure deterministic canonical validation and hashing | Open databases, authorise users, log sensitive data |
| `database/queries.py` extensions | Exact scoped lookups and transactional persistence | Make UI decisions or accept unverified ownership |
| schema/migration extension | Bridge and approved additive fields/constraints | Drop/recreate legacy tables or infer mappings |

Decomposition should keep pure record validation and identity independent from
session/database orchestration so they can be tested deterministically.

## 7. Service entry contract

**Evidence status:** RECOMMENDATION

The future public service should accept a token, Module 2 business ID,
financial-account ID, canonical source context, and ordered canonical records.
The exact function name/signature waits on D05.

It returns the safe result described by the reconstructed Phase 2 contract.
It never returns SQLite rows, stack traces, raw exceptions, raw hashes,
credentials, or sensitive source values.

## 8. Required control flow

**Evidence status:** CONFIRMED FROM CONVERSATION

1. Validate session and active user.
2. Authorise active Module 2 business membership and approved ingestion role.
3. Load the account and prove it belongs to the same active business.
4. Resolve one active verified bridge.
5. Derive registry business and legacy owner context from database state.
6. Validate request shape and source vocabulary.
7. Validate each canonical record without database writes.
8. Build deterministic transaction identity for accepted records.
9. Classify existing and within-batch duplicates.
10. Persist unique accepted rows and success log atomically.
11. If persistence fails, roll back and safely record failure according to D17.
12. Return bounded, non-sensitive counts and row errors.

No later step may weaken an earlier security check.

## 9. Authentication and authorisation specification

**Evidence status:** CONFIRMED FROM REPOSITORY

The service must reuse `validate_session()`, `require_business_access()`, and
account-access behavior. It must not accept a frontend user or role.

Every account/bridge/upload/transaction lookup must be scoped through the
already authorised business. A globally privileged administrator does not gain
tenant ingestion access without membership and the D12-approved role.

## 10. Bridge specification

**Evidence status:** CONFIRMED FROM DECISION RECORD

D01 is approved. The future bridge is business-owned with owner proposal and
global-administrator verification. It uses exact IDs, supports audited
pending/verified/disabled lifecycle, prohibits hard deletion after use, and
cannot be created by ingestion.

The bridge's final table/columns/constraints wait on D02, D03, D04, and D18.
One-to-one uniqueness on both business IDs is recommended but cannot be
migrated until real data and lifecycle rules are approved.

## 11. Account specification

**Evidence status:** RECOMMENDATION

One batch should select one explicit active `financial_accounts.account_id`.
The backend must load it, derive its Module 2 business, compare that business
with the authorised envelope, and reject cross-business or disabled accounts.

Real account mappings are absent. D07 must be approved before implementation.

## 12. Canonical record specification

**Evidence status:** CONFIRMED FROM CONVERSATION

The canonical record contains strict date, exact positive amount, debit/credit
direction, stable source identity, and optional minimised descriptive fields.
It does not contain authoritative business, registry, actor, role, bridge,
hash, persistence status, or timestamps.

Exact transport, source vocabulary, money type, limits, economic mapping, and
payroll identity remain unresolved under D05, D06, D09, D13–D15.

## 13. Validation model

**Evidence status:** RECOMMENDATION

| Layer | Responsibilities |
|---|---|
| Streamlit | Helpful required-input feedback only; never security authority |
| Standardiser | Source layout/date/type parsing into canonical shape |
| Ingestion service | Envelope, canonical types, domain values, identity sufficiency, authorisation |
| Query layer | Parameter binding, exact scoped retrieval, transactional operations |
| Database | FK, check, not-null, uniqueness, and atomicity approved in D18 |

Validation must reject bad records rather than truncate, coerce ambiguous
dates, default unknown currency, reinterpret signs, or invent identity.

## 14. Money and currency specification

**Evidence status:** RECOMMENDATION

Canonical identity should use integer minor units. The legacy `amount REAL`
must remain available for existing Module 0 summaries until a proven
transition is approved. A dual-write design is recommended but unresolved:
minor units are authoritative for new identity, and legacy major-unit `REAL`
is a compatibility projection produced by one deterministic conversion.

Required approvals include currency source, scale, range, rounding/rejection,
legacy backfill, consistency constraints, and multi-currency limitations. No
silent conversion is permitted.

## 15. Direction and economic type

**Evidence status:** UNRESOLVED

Canonical direction is debit/credit. The current ledger summary recognizes
only `transaction_type='income'` and `'expense'`. Raw debits/credits are not
universally equivalent to expense/income: transfers and card payments prove
that a one-to-one conversion can be wrong.

Module 4 v1 should accept only explicitly approved economic mappings and reject
unknown/ambiguous types. D14 is blocked pending a taxonomy decision.

## 16. Transaction identity

**Evidence status:** RECOMMENDATION

The identity must be stable, cryptographic, uploader-independent, and scoped by
registry business, financial account, and source. Source transaction ID should
be preferred where its scope is known. A canonical stable-field fallback may
be used only after D09/D13/D15 approve its fields and normalisation.

The current hash function is unsuitable unchanged because it includes user ID,
uses rounded major-unit text, omits account/source/direction, and is tied to
legacy ledger fields.

## 17. Deduplication and idempotency

**Evidence status:** CONFIRMED FROM REPOSITORY

Module 4 must prevent insertion of existing and within-batch duplicates. The
existing duplicate boolean is insufficient because insertion still occurs.

The eventual database protection must be atomic with insertion and match the
canonical identity scope. Before adding uniqueness, migration must inventory
existing nulls, duplicate/colliding hashes, and legacy hashes generated with
different semantics.

Repeated canonical requests must produce duplicate outcomes without changing
ledger count. Different uploaders must not produce different identities.

## 18. Partial success

**Evidence status:** CONFIRMED FROM CONVERSATION

Record validation is row-level: valid unique peers may be inserted while
invalid rows are reported and duplicates skipped. Internal database failure is
batch-level and rolls back all new inserts. Counts must satisfy the contract
invariant and status table.

## 19. Database transaction boundaries

**Evidence status:** RECOMMENDATION

Current query functions open independent connections, so ingestion cannot
compose them into one atomic batch unchanged. The future query layer must
provide a transaction-scoped batch operation or accept an internal connection
under a controlled repository API.

The atomic persistence unit includes all unique accepted ledger inserts and
the completed/partial/duplicate-only upload result update. A failure causes
SQLite rollback. A safe failure record, if required, is written afterward in a
separate transaction (D17 unresolved).

## 20. Upload-log specification

**Evidence status:** RECOMMENDATION

Reuse the existing log table concept. Add only fields approved by D18. Expected
future capabilities include server-generated upload ID, actor, registry
business, Module 2/account/source context, total/inserted/duplicate/rejected
counts, controlled status, safe summary, and timestamps.

Do not persist raw rows, employee PII, token, SQL, traceback, filesystem path,
or unbounded error collections. Whether row errors need durable storage is
UNRESOLVED.

## 21. Failure and rollback model

**Evidence status:** RECOMMENDATION

- Invalid authentication/authorisation/context: no upload/ledger writes unless
  an approved non-business audit mechanism exists.
- Row validation failures: return safe row errors; valid peers may proceed.
- Duplicate rows: report separately; not failures.
- Persistence failure: roll back the entire new batch.
- Post-rollback: optionally write a minimal failed ingestion record using a
  new transaction, never reusing the failed connection state.

D16 and D17 require approval before implementation.

## 22. Error model

**Evidence status:** RECOMMENDATION

Reuse existing error shapes and auth/business/account codes where applicable.
Ingestion needs stable public categories for invalid envelope/record/source,
missing bridge, duplicate-only result, persistence failure, and internal
failure. Exact codes/messages and retryability are D19.

Internal logs may contain correlation IDs and exception class/controlled
context, but never sensitive payload, token, SQL text, path, payroll identity,
or credential.

## 23. Payroll/privacy model

**Evidence status:** RECOMMENDATION

Module 4 v1 should not persist payroll employee name, raw employee ID, role,
bank/tax/contact details, or create counterparties from them. The current KPI
function needs only monetary aggregates.

A plain unsalted hash of low-entropy employee ID is not privacy protection.
Without an approved stable opaque source transaction ID or reviewed keyed
pseudonym scheme, payroll ingestion should remain excluded. The two payroll-
related datasets must remain independent until reconciliation is approved.

## 24. Repository/query specification

**Evidence status:** RECOMMENDATION

Future query capabilities—not approved function names—include:

| Capability | Inputs and scope | Result/behavior |
|---|---|---|
| resolve bridge | authorised Module 2 business | one active verified registry business or none |
| create proposal | actor plus exact business/registry IDs | pending bridge under D01 rules |
| verify/disable bridge | administrator actor plus bridge/version | valid state transition with audit attribution |
| load account context | account ID plus authorised business | active account only; reject mismatch |
| find identities | registry business/account/source plus hashes | existing identity set, business scoped |
| batch persist | validated unique rows plus result metadata | one transaction; all-or-nothing DB writes |
| record failure | safe context after rollback | separate transaction if D17 approved |

Repository functions assume service-level authorisation but still require
explicit business scope. They must use parameterised SQL and must not receive
frontend-derived actor/role authority.

## 25. Service decomposition

**Evidence status:** RECOMMENDATION

Keep the future service small through internal components for:

- context resolution;
- pure canonical record validation;
- deterministic identity construction;
- duplicate classification;
- persistence orchestration;
- safe result/error translation.

The public service owns orchestration and policy. Pure helpers do not access
sessions or SQLite. The query layer owns SQL and transaction mechanics.

## 26. Parser and standardiser boundary

**Evidence status:** CONFIRMED FROM CONVERSATION

No parser is specified for Module 4. The existing pandas code proves only that
the demo sources have different layouts/date formats. It does not define a
stable standardizer API.

D05 should approve a versioned ordered collection of plain mappings after
Zaara's actual output is confirmed. DataFrames, Streamlit state, and SQLite
rows must not become the public service contract.

## 27. Audit and observability

**Evidence status:** RECOMMENDATION

Auditable events should include bridge proposal/verification/state change,
ingestion attempt/start/completion/failure, duplicate-only result, and retry.
Each event should identify the session-derived actor, authorised business
context where known, operation/result, and timestamp.

Business-less preflight failures must not fabricate a registry ID. Sensitive
values listed in the contract must never be logged. Existing
`authentication_logs` is authentication-specific and should not silently
become a generic ingestion audit store.

## 28. Migration specification

**Evidence status:** BLOCKED

No SQL may be designed until D02–D17 stabilise required fields. Any future
migration must be additive, idempotent, preserve every Module 0–3 row, keep
foreign keys enabled, and safely rerun.

Required preflight categories include:

- real Module 2/registry/account records and mapping inventory;
- existing ledger row count/nullability/type distributions;
- duplicate/colliding/null transaction hashes;
- deterministic convertibility of legacy `REAL` amounts;
- legacy owner consistency between ledger and registry;
- existing upload statuses/counts;
- FK violations and index inventory.

No `DROP TABLE`, blind backfill, name matching, or guessed currency/account is
permitted. D18 remains blocked.

## 29. Conceptual schema impact

**Evidence status:** UNRESOLVED

Potential additive needs include a bridge table, bridge audit actors/state,
ledger account/source/source-ID/direction/exact amount/currency/uploader
attribution, canonical identity protection, and upload duplicate/account/source
fields. These are candidate consequences, not approved columns.

Final nullability, FK deletion actions, uniqueness, indexes, checks, backfill,
and compatibility projections depend on D02–D18.

## 30. Test strategy

**Evidence status:** CONFIRMED FROM CONVERSATION

Future tests must cover:

- migration on fresh and existing Module 0–3 databases;
- bridge FK/one-to-one/state/role/IDOR behavior;
- every session, business, membership, and account state;
- cross-business business/account/bridge/upload/transaction attacks;
- canonical type/date/money/direction/source/limit validation;
- deterministic identity, uploader independence, and collision cases;
- first, repeated, within-batch, mixed, and duplicate-only ingestion;
- partial success accounting;
- rollback at every insertion/log failure point;
- safe public errors and sensitive-value redaction;
- payroll PII sentinels;
- legacy query/summary/budget/document/authentication regressions;
- actual dataset copy after approvals and real mapping data.

Tests must continue using the authoritative schema and isolated foreign-key-
enabled temporary SQLite databases.

## 31. Security abuse cases

**Evidence status:** CONFIRMED FROM CONVERSATION

The future implementation must prove that changing user/business/account/
bridge/upload/transaction IDs cannot cross tenant boundaries; direct service
calls cannot bypass Streamlit; managers cannot manage bridges; administrators
cannot ingest without membership; disabled resources fail; replays are
idempotent; and error/log paths do not leak sensitive values.

## 32. Performance considerations

**Evidence status:** RECOMMENDATION

The observed dataset has 1,150 rows and is suitable for synchronous MVP
processing if validation is streaming/bounded and database writes are batched
inside one transaction. Avoid one connection/query per row. Batch-size limits
and worker/concurrency support are unapproved; do not introduce background
infrastructure prematurely.

SQLite uniqueness and transaction locks must provide final duplicate-race
protection after D18. In-memory validation must have an approved record limit.

## 33. Compatibility requirements

**Evidence status:** CONFIRMED FROM REPOSITORY

- Keep `business_registry`, `businesses`, and `financial_accounts`.
- Keep the existing ledger and Module 0 query behavior.
- Preserve legacy `user_id` semantics until D04 approves a transition.
- Preserve existing `amount REAL` readers while adding exact representation
  only if D09 approves it.
- Preserve all users, sessions, logs, budgets, documents, transactions,
  memberships, and accounts.
- Reuse current auth/business/account service boundaries.
- Keep all 48 tests green and add focused Module 4 tests later.

## 34. Scope exclusions

**Evidence status:** CONFIRMED FROM CONVERSATION

No raw-file staging, file retention, MIME policy, XLSX/PDF/OCR parser, bank API,
currency conversion, payroll reconciliation, transaction correction, KPI/RAG/
eligibility redesign, queue, worker, or microservice belongs to this
specification.

## 35. Dependency order

**Evidence status:** CONFIRMED FROM DECISION RECORD

1. Identity/ownership: D01, D02, D03, D04, D12.
2. Financial model: D07, D09, D10, D11, D14.
3. Payroll/privacy: D08, D15.
4. Interface/scope: D05, D06, D13, D19, D20.
5. Failure/audit: D16, D17.
6. Final schema: D18.
7. Cross-cutting validation: D21.
8. Implementation gate: D22.

## 36. Implementation sequence after approval

**Evidence status:** RECOMMENDATION

After D22 only: approve schema delta; write migration tests; implement migration;
write bridge repository tests; implement bridge queries/services; implement
pure validation and identity tests/helpers; implement duplicate and batch
transaction tests/repository; implement ingestion service tests/service; run
full regression/security/real-data validation; then separately integrate
Streamlit. Documentation and implementation commits remain separate.

## 37. Open decisions and readiness

**Evidence status:** CONFIRMED FROM DECISION RECORD

D01 is approved. D02 and D14/D15/D18/D21/D22 are blocked. All other decisions
retain unresolved or recommendation status as shown in
`docs/phase3_decision_record.md`.

The final gate is **NOT READY FOR MODULE 4 IMPLEMENTATION**.
