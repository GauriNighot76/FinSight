> Historical design record: normal onboarding approval requirements in this document are superseded by the automatic internal mapping design in [README](../README.md#automatic-onboarding-and-existing-databases).

# FinSight Module 4 — Ingestion UI Contract

**Document status:** RECONSTRUCTED DRAFT — PENDING PHASE 3 APPROVAL
**Reconstruction phase:** Phase 3A
**Repository baseline:** `59744445a4ed80199999c03ace11e98023065c95`
**Contract version:** `1.0-reconstructed-draft`

> This is a new reconstruction. The original Phase 2 contract is permanently
> unavailable. This document does not claim to reproduce the lost file
> byte-for-byte. It is limited to current repository evidence, preserved
> conversation evidence, and explicitly identified recommendations. Anything
> not established by those sources is marked **UNRESOLVED**.

## 1. Purpose

**Evidence status:** CONFIRMED FROM CONVERSATION

This contract defines the boundary between Zaara's standardisation work,
Streamlit, the future Module 4 ingestion service, the query layer, and SQLite.
It specifies what canonical financial data the backend may receive, which
security context the backend must derive itself, and which safe result the UI
may receive.

This is a contract, not an implementation, migration, parser, or Streamlit
change.

## 2. Scope

**Evidence status:** CONFIRMED FROM CONVERSATION

The current contract boundary is **canonical-record ingestion**:

```text
raw source data
    -> Zaara's source-specific standardisation
    -> canonical records
    -> Module 4 authentication and authorisation
    -> business/account/bridge verification
    -> validation and deterministic identity
    -> duplicate classification
    -> atomic ledger persistence
    -> safe ingestion result
```

Changing this boundary requires explicit approval of D20 and a contract
amendment.

## 3. Non-goals

**Evidence status:** CONFIRMED FROM CONVERSATION

Module 4 does not currently own:

- raw-file storage or retention;
- MIME or extension validation;
- CSV/XLSX/PDF parsing;
- OCR;
- arbitrary file-layout interpretation;
- parser-specific UI behavior;
- bank/API connectors or credentials;
- KPI, scheme eligibility, RAG, or PDF redesign;
- transaction editing or reconciliation;
- automatic business or account creation.

The repository's trial dashboard reads static CSV files directly. That is
prototype behavior, not the approved backend ingestion boundary.

## 4. Evidence and terminology

**Evidence status:** CONFIRMED FROM REPOSITORY

| Term | Meaning in this contract |
|---|---|
| Module 2 business | A row in `businesses`, authorised through `business_memberships` |
| Registry business | A legacy row in `business_registry`, referenced by the ledger |
| Financial account | A row in `financial_accounts` belonging to a Module 2 business |
| Bridge | The future explicit relationship between a Module 2 business and one registry business; not an API credential |
| Canonical record | A source-independent transaction representation accepted by Module 4 |
| Uploader/actor | The session-derived user initiating ingestion |
| Ledger | Existing `transaction_general_ledger`; no parallel ledger may be created |
| Standardiser | Source-specific component that emits canonical records |

## 5. Architecture and trusted boundaries

**Evidence status:** CONFIRMED FROM REPOSITORY

```text
Streamlit -> service -> database/queries.py -> database/db.py -> SQLite
```

Streamlit and canonical record contents are untrusted. The backend trusts only
facts re-read through validated session and database state. The service must
derive the actor, global role, membership role/status, business status,
account ownership/status, and bridge state.

The frontend must never be authoritative for `user_id`, role, membership,
business ownership, registry identity, account ownership, status, hashes,
counts, or timestamps.

## 6. Ingestion request envelope

**Evidence status:** CONFIRMED FROM CONVERSATION

The future service request must conceptually contain:

| Item | Requirement | Authority |
|---|---|---|
| session token | Required; opaque string | Validated by `validate_session()`; never persisted or logged in raw form |
| Module 2 `business_id` | Required context selector | Re-verified through `require_business_access()` |
| `account_id` | Required context selector | Re-verified through account and business access |
| `source_system` | Required canonical source label | Controlled vocabulary; exact values are UNRESOLVED (D06) |
| records | Required ordered collection | Canonical mappings; exact transport is UNRESOLVED (D05) |
| contract/standardiser version | Recommended | Exact key and version policy are UNRESOLVED (D05) |
| source display name | Optional, non-authoritative | Safe length and logging rules are UNRESOLVED (D13) |

The envelope must reject or ignore frontend attempts to supply an actor ID,
global role, membership role/status, registry business ID, bridge status,
transaction hash, persistence status, or result counts.

## 7. Canonical transaction representation

**Evidence status:** CONFIRMED FROM CONVERSATION

The canonical model must carry the following conceptual information. Exact
Python types and field names remain subject to the decisions identified below.

| Field | Required? | Meaning | Current decision state |
|---|---:|---|---|
| `transaction_date` | yes | Canonical calendar date | `YYYY-MM-DD` required by preserved contract evidence |
| exact amount | yes | Positive transaction magnitude | Minor units recommended; schema decision D09 unresolved |
| `direction` | yes | `debit` or `credit` | Independent from category and subtype |
| source identity | yes | Source system plus stable transaction identity | Vocabulary/scope unresolved in D06 and identity rules |
| `source_transaction_id` | when available | Identifier issued by the source | Uniqueness scope unresolved |
| `category` | optional | Canonical analytical category | Taxonomy and limits unresolved |
| `description` | optional | Human-readable transaction narrative | Limits unresolved; must not authorise anything |
| `counterparty` | optional | Minimised canonical counterparty label/reference | Representation and PII policy unresolved |
| `balance_after` | optional | Source-reported post-transaction balance | Persistence unresolved in D10 |
| `payment_method` | optional | Payment rail/method | Must not be confused with direction/source |
| `source_subtype` | optional | Source-specific classification | Mapping to legacy type unresolved in D14 |
| source record number | optional | Diagnostic row reference | Must not become transaction identity by itself |

Business and account context belong to the authenticated request envelope, not
arbitrary row text. If row-level context is ever supported, it must match the
verified envelope exactly and may not expand authorisation.

## 8. Required fields

**Evidence status:** CONFIRMED FROM CONVERSATION

A record must provide a valid date, exact positive amount, direction, source
context, account context inherited from the authorised envelope, and enough
stable information to calculate deterministic transaction identity.

If no approved identity can be calculated, the record must be rejected. The
backend must not invent a random identity merely to permit insertion.

## 9. Optional fields and data minimisation

**Evidence status:** CONFIRMED FROM CONVERSATION

Optional fields may be absent or null. They must not be used as authority.
Empty strings should be normalised consistently once D13 is approved; silent
truncation is prohibited.

Payroll employee name, employee ID, role, bank information, tax information,
and contact information must not automatically become ledger, counterparty,
error, or log data. D08 and D15 remain unresolved.

## 10. Data types and limits

**Evidence status:** UNRESOLVED

The backend contract must use deterministic, serialisable values and reject
booleans where numeric values are expected. Exact text limits, source-ID
limits, collection limits, and maximum batch size are not approved (D13).

No implementation may silently truncate a value to fit a database column or
UI component.

## 11. Date rules

**Evidence status:** CONFIRMED FROM CONVERSATION

The canonical date representation is `YYYY-MM-DD`. Source-specific formats are
the standardiser's responsibility. Module 4 validates strict syntax and a real
calendar date; it does not reinterpret ambiguous dates.

Examples:

- accepted shape: `2023-01-31`
- rejected shapes: `31-01-2023`, `01/31/2023`, `January 31, 2023`

Timezone and datetime support are outside the current transaction contract.

## 12. Money rules

**Evidence status:** RECOMMENDATION

The canonical interface should carry a positive integer number of minor units,
not a binary floating-point number. For a two-decimal currency, `123.45` would
be represented as `12345` minor units.

This is not yet an approved ledger migration. The legacy ledger stores
`amount REAL CHECK (amount > 0)`, while Module 3 accounts store
`opening_balance_minor INTEGER`. D09 must approve exact storage, conversion,
rounding, range, and backfill behavior before implementation.

No currency conversion or silent rounding is allowed.

## 13. Direction rules

**Evidence status:** CONFIRMED FROM CONVERSATION

`debit` and `credit` describe movement direction. Direction is not a category,
economic type, payroll subtype, account type, or payment method.

The raw checking/card data uses `Debit` and `Credit`; the standardiser is
responsible for canonical casing. The legacy ledger has no direction column,
so its persistence mapping remains unresolved under D14/D18.

## 14. Source-system rules

**Evidence status:** UNRESOLVED

The source system must identify the originating source family and participate
in transaction identity. Exact tokens, casing, aliases, and versioning are not
present in the current schema or service layer and require D06 approval.

Names such as `checking`, `credit_card`, and `payroll` are examples from prior
discussion only; they are not approved production enum values.

Unknown sources must be rejected safely once the vocabulary is approved.

## 15. Source transaction identity

**Evidence status:** CONFIRMED FROM CONVERSATION

Checking and card datasets contain transaction IDs; payroll does not contain a
transaction ID. A source transaction ID must not be assumed globally unique.
Its approved scope must include source and business/account context.

When no stable source transaction ID exists, an approved deterministic
fallback is required. Payroll identity remains blocked by D15.

## 16. Business identity

**Evidence status:** CONFIRMED FROM REPOSITORY

Business identity is determined by:

```text
validated session
    + active Module 2 business membership
    + approved ingestion role
    + active authorised financial account
    + active verified bridge
    -> registry business used by the ledger
```

The backend must not match by business name, filename, account label,
description, category, source text, owner name, or approximate similarity.

## 17. Financial-account identity

**Evidence status:** CONFIRMED FROM REPOSITORY

`financial_accounts.business_id` references Module 2 `businesses`. The account
must exist, be active, belong to the selected business, and be authorised
through the session user's active membership. A supplied account from another
business must be rejected even when its identifier is valid.

The mapping of real source accounts to actual `account_id` values is
UNRESOLVED (D07). No account may be auto-created or guessed.

## 18. Business bridge

**Evidence status:** CONFIRMED FROM DECISION RECORD

The conceptual bridge connects:

```text
businesses -> business ledger bridge -> business_registry
```

D01 is approved:

- an active Module 2 owner may propose an exact registry ID;
- a global administrator verifies, activates, rejects, suspends, or disables;
- a changed mapping requires disabling the old bridge and verifying a new one;
- a used bridge is never hard-deleted;
- the bridge belongs to the business;
- administrator status does not grant ingestion access;
- registry IDs are exact and name matching is prohibited;
- changes are auditable;
- external connector credentials are outside this decision.

The table name and final schema are not approved. D02 remains blocked because
no real mapping IDs are stored in the repository.

## 19. Authentication and authorisation

**Evidence status:** CONFIRMED FROM REPOSITORY

Every ingestion operation must:

1. call existing session validation;
2. reject missing, invalid, expired, revoked, or disabled-user sessions;
3. load the Module 2 business and active membership;
4. enforce the approved ingestion role (D12 unresolved);
5. load the account and verify business/status;
6. resolve an active verified bridge;
7. use the registry business selected by that bridge.

Streamlit visibility is not authorisation. Global administrator status alone
must not bypass tenant membership for ingestion.

## 20. Validation

**Evidence status:** CONFIRMED FROM CONVERSATION

Validation occurs before persistence and distinguishes batch-level context
failure from row-level record rejection.

Batch-level failures include invalid session, unauthorised business/account,
missing or inactive bridge, invalid envelope, and unsupported source. They
persist no ledger transactions.

Row-level rules cover required values, strict date, exact positive amount,
direction, source identity, approved text limits, supported classifications,
and deterministic identity. Every rejection receives a safe stable reason.

## 21. Transaction identity

**Evidence status:** RECOMMENDATION

The uploader must never participate in canonical transaction identity.

When a stable source transaction ID exists, the conceptual identity is:

```text
registry business + financial account + source system + source transaction ID
```

Without one, the preserved recommendation is a deterministic canonical
serialization of stable fields such as registry business, account, source,
date, direction, exact amount, normalised category, counterparty, and
description. The exact fields and canonicalisation remain unresolved,
especially for payroll.

SHA-256 is the compatible hash destination concept. Python's built-in `hash()`
must never be used. The existing `create_transaction_hash()` includes
`user_id` and therefore cannot implement this contract unchanged.

## 22. Deduplication

**Evidence status:** CONFIRMED FROM REPOSITORY

The current `create_transaction()` detects a matching hash but inserts the new
row anyway. `transaction_hash` is indexed but not unique. Module 4 requires
actual idempotency: known duplicates are classified and not inserted.

Database uniqueness or another atomic protection may be introduced only after
legacy collision inventory and D18 approval. No second ledger or alternative
hash table may be invented solely to avoid compatibility work.

## 23. Duplicate semantics

**Evidence status:** CONFIRMED FROM CONVERSATION

Every submitted record is classified exactly once as:

- `INSERTED`: valid, unique, and persisted;
- `DUPLICATE`: valid but already represented; not inserted;
- `REJECTED`: invalid or lacks an approved identity.

Duplicates are not validation failures. A duplicate-only repeated request is
successful and idempotent.

## 24. Rejection and error semantics

**Evidence status:** CONFIRMED FROM CONVERSATION

A row rejection contains only a row number/reference, stable error code, and
human-safe message. It must not contain SQL, tracebacks, paths, tokens,
credentials, hashes, raw payroll values, employee IDs/names, or other sensitive
source content.

Exact error codes and limits require D19 approval.

## 25. Partial-success semantics

**Evidence status:** CONFIRMED FROM CONVERSATION

| Status | Meaning |
|---|---|
| `completed` | all accepted records were unique and inserted; no rejections |
| `partially_completed` | at least one inserted and at least one duplicate or rejection |
| `duplicate_only` | no insertions or rejections; every record already existed |
| `failed` | no records inserted because validation/context failed or persistence failed |

The accounting invariant is:

```text
total_records = inserted + duplicates + rejected
```

## 26. Database transaction semantics

**Evidence status:** CONFIRMED FROM CONVERSATION

Validation and duplicate classification may occur before writes. All newly
accepted transactions and the successful upload-log update must be written in
one SQLite transaction. A persistence failure rolls back every new transaction
from that batch.

Row-level validation rejection does not require rolling back valid peers.
Post-rollback failure logging is unresolved under D17.

## 27. Upload logging

**Evidence status:** CONFIRMED FROM REPOSITORY

Module 4 should reuse `pipeline_upload_ingestion_logs`; it must not create a
parallel log without approved justification. The existing table tracks upload
ID, user, registry business, filename, type, total/success/failed counts,
status, one error message, and timestamp.

It cannot currently represent account ID, source system, duplicate count,
separate actor/owner semantics, row errors, or lifecycle timestamps. Any
extension is blocked on D16–D18. The word "upload" is retained for compatibility
even though the current contract accepts canonical records rather than files.

## 28. Ingestion result contract

**Evidence status:** CONFIRMED FROM CONVERSATION

The future safe result must conceptually contain:

| Field | Meaning |
|---|---|
| `success` | operation-level boolean consistent with approved status semantics |
| `upload_id` | server-generated ingestion identifier, if a log was created |
| `total_records` | submitted canonical record count |
| `inserted` | inserted count |
| `duplicates` | duplicate count |
| `rejected` | rejected count |
| `status` | approved lifecycle status |
| `errors` | bounded list of safe row errors |

The UI must not calculate authoritative counts or statuses.

## 29. Safe error contract

**Evidence status:** RECOMMENDATION

Authentication, business, membership, and account errors should reuse the
existing service convention: `success=False`, stable `error`, and safe
`message`. Ingestion-specific vocabulary is unresolved in D19.

Internal database/parser exceptions must map to a generic safe failure while
the internal diagnostic is logged without sensitive payloads.

## 30. Security requirements

**Evidence status:** CONFIRMED FROM REPOSITORY

- Validate the session server-side for every operation.
- Enforce active user, business, membership, account, and bridge state.
- Scope all lookups and mutations to the authorised business context.
- Reject cross-business business/account/upload/transaction identifiers.
- Use parameterised SQL and enabled SQLite foreign keys.
- Never accept frontend identity, role, registry ownership, hash, or status.
- Never log raw session tokens, passwords, OTPs, credentials, SQL, or payloads.
- Never derive a bridge from names or transaction content.
- Never include the uploader in duplicate identity.

## 31. PII and payroll handling

**Evidence status:** RECOMMENDATION

The raw payroll data contains employee ID, name, and role. The current KPI code
uses only payroll amounts, so repository evidence does not prove a need to
persist employee PII.

Module 4 v1 should not persist employee name, raw employee ID, role, contact,
bank, or tax data. Employee data must never appear in logs/errors. Whether a
privacy-safe payroll identity can be used is blocked under D15.

The payroll total (`159854`) and secondary-account payroll debits (`97811`) do
not reconcile. They must not be merged or declared duplicates without a
separate approved business rule. A prototype KPI comment asserting that they
are the same money is not authoritative ledger evidence.

## 32. Standardiser responsibilities

**Evidence status:** CONFIRMED FROM CONVERSATION

Zaara's standardiser:

- reads approved raw layouts;
- parses source-specific dates/amounts/types;
- normalises them to the approved canonical contract;
- supplies source identity/provenance supported by the source;
- reports source parsing errors before Module 4;
- does not authorise users/businesses/accounts;
- does not choose registry businesses;
- does not calculate database hashes or write SQLite.

The actual transport format remains unresolved in D05.

## 33. Module 4 responsibilities

**Evidence status:** CONFIRMED FROM CONVERSATION

Module 4 authenticates, authorises, verifies business/account/bridge context,
validates canonical records, creates deterministic identities, classifies
duplicates, persists accepted records atomically, records safe ingestion
outcomes, and returns a safe result.

It does not parse arbitrary files or implement UI logic.

## 34. Streamlit responsibilities

**Evidence status:** CONFIRMED FROM CONVERSATION

Streamlit selects only businesses and accounts returned by backend services,
sends the session token plus canonical input to the service, and displays safe
results. It must not execute SQL, open SQLite, infer roles, create hashes,
resolve bridges, deduplicate rows, or decide authorisation.

## 35. Database/query-layer responsibilities

**Evidence status:** CONFIRMED FROM REPOSITORY

The query layer performs parameterised, business-scoped persistence and lookup
operations. The database enforces approved foreign keys, constraints,
uniqueness, and atomic transaction boundaries. Query functions must not make
Streamlit decisions or trust caller-supplied ownership claims.

## 36. Non-production examples

**Evidence status:** RECOMMENDATION

These examples show conceptual shape only. Field names and source tokens are
not approved.

```text
Checking example
transaction_date: 2023-01-31
amount_minor: 12345
direction: credit
source_system: <approved-checking-source-token>
source_transaction_id: <source-transaction-id>
category: Sales Revenue
description: Daily sales deposit
```

```text
Credit-card example
transaction_date: 2023-01-31
amount_minor: 4567
direction: debit
source_system: <approved-card-source-token>
source_transaction_id: <source-transaction-id>
category: Supplies
counterparty: <minimised-counterparty-label>
```

```text
Payroll example — NOT APPROVED FOR INGESTION
transaction_date: 2023-01-31
amount_minor: 50000
direction: debit
source_system: <approved-payroll-source-token>
source_transaction_id: null
source_subtype: Employee Pay
```

Business, registry, account, actor, hash, and timestamps are server-resolved or
server-generated; they are not copied from transaction text.

## 37. Unresolved decisions

**Evidence status:** CONFIRMED FROM CONVERSATION

Only D01 is approved. D02–D22 retain the statuses recorded in the reconstructed
decision record. Major unresolved items include real business/account mapping,
registry onboarding, owner/uploader semantics, transport and source vocabulary,
money/currency, payroll privacy/identity, ingestion permissions, limits,
economic mapping, failure logging, final schema, public errors, raw-file scope,
and final readiness.

## 38. Assumptions prohibited

**Evidence status:** CONFIRMED FROM CONVERSATION

No implementation may assume that names prove identity, that a source ID is
globally unique, that INR is always correct, that uploader equals owner, that
all debits are expenses, that all credits are income, that payroll datasets
represent identical events, or that current legacy hashes are unique.

## 39. Versioning and change control

**Evidence status:** CONFIRMED FROM CONVERSATION

This reconstructed draft becomes authoritative only after explicit Phase 3A
approval. A change to canonical fields, identity, status semantics, security
boundary, or raw-file scope requires a reviewed contract amendment. Document
approval and Module 4 implementation must remain separate changes.

## 40. Phase 3A completion criteria

**Evidence status:** CONFIRMED FROM CONVERSATION

Phase 3A reconstructs and cross-validates the three documents, records new
hashes, confirms no production changes, and stops for approval. It does not
approve D02–D22 or make Module 4 ready for implementation.

**NOT READY FOR MODULE 4 IMPLEMENTATION**
