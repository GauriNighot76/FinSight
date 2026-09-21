> Historical design record: normal onboarding approval requirements in this document are superseded by the automatic internal mapping design in [README](../README.md#automatic-onboarding-and-existing-databases).

# FinSight Phase 3 — Ingestion Decision Record

**Document status:** RECONSTRUCTED DRAFT — PENDING PHASE 3A APPROVAL
**Reconstruction phase:** Phase 3A
**Repository baseline:** `59744445a4ed80199999c03ace11e98023065c95`
**Contract reference:** `docs/ingestion_ui_contract.md`
**Specification reference:** `docs/ingestion_implementation_spec.md`

> The original decision record is permanently unavailable. This is a new
> reconstruction from repository and preserved conversation evidence. It is
> not the lost original. Only D01 has explicit human approval. Recommendations
> below are not approvals.

## 1. Status vocabulary

**Evidence status:** CONFIRMED FROM CONVERSATION

| Label | Meaning |
|---|---|
| `APPROVED` | Explicit human decision validated against available evidence |
| `BLOCKED` | Cannot proceed until stated dependency/evidence/approval exists |
| `UNRESOLVED` | No final human decision exists |
| `UNRESOLVED / RECOMMENDATION` | A defensible option exists but is not approved |

Evidence statements are separately labelled `CONFIRMED FROM REPOSITORY`,
`CONFIRMED FROM DECISION RECORD`, `CONFIRMED FROM CONVERSATION`,
`RECOMMENDATION`, or `UNRESOLVED`.

## 2. Repository baseline

**Evidence status:** CONFIRMED FROM REPOSITORY

- Branch: `main`.
- HEAD: `59744445a4ed80199999c03ace11e98023065c95`.
- Baseline execution during reconstruction: 48 passed, 0 failed, 0 skipped.
- There are two separate business identities and no bridge.
- Session, global-role, membership, and account access helpers exist.
- The ledger references `business_registry`, stores positive `REAL` amounts,
  and has a non-unique indexed transaction hash.
- Current duplicate detection does not prevent insertion.
- The repository contains no local database with real business/account rows.
- The trial dashboard reads static CSV files and has no ingestion service.

## 3. Identity map

**Evidence status:** CONFIRMED FROM REPOSITORY

| Identifier | Identifies | Current relationship |
|---|---|---|
| `users.user_id` | system user | global roles and sessions |
| `businesses.business_id` | Module 2 business | membership and account boundary |
| `business_memberships.membership_id` | user/business role | unique business/user pair |
| `financial_accounts.account_id` | Module 3 account | belongs to Module 2 business |
| `business_registry.business_id` | legacy ledger business | owned by one legacy user |
| `transaction_general_ledger.transaction_id` | legacy transaction | belongs to registry business and legacy `user_id` |
| `pipeline_upload_ingestion_logs.upload_id` | legacy ingestion log | belongs to registry business; optional user |

No existing identifier proves the Module 2-to-registry relationship.

## 4. Decision dependency order

**Evidence status:** CONFIRMED FROM CONVERSATION

```text
D01/D02/D03/D04/D12
    -> D07/D09/D10/D11/D14
    -> D08/D15
    -> D05/D06/D13/D19/D20
    -> D16/D17
    -> D18
    -> D21
    -> D22
```

## 5. Decisions

### D01 — Bridge creation authority

**Priority:** P0
**Evidence status:** CONFIRMED FROM CONVERSATION
**Decision status:** APPROVED

**Problem:** A bridge selects the registry ledger that will receive a Module 2
business's transactions. Unauthorised selection is a cross-business data
breach.

**Repository evidence:** Global role `administrator`, membership role `owner`,
`require_role()`, and `require_business_access()` exist. Public signup assigns
`standard_business`. No bridge workflow exists.

**Approved decision:**

- An active Module 2 owner may propose an exact registry ID.
- A global administrator verifies/activates, rejects, or disables/suspends.
- Mapping replacement disables the old bridge and verifies a new proposal.
- Used bridges are not hard-deleted.
- The bridge belongs to the business, not the actor.
- Administrator status does not grant ingestion access.
- Ingestion still requires membership and the D12-approved permission.
- Exact IDs are mandatory; name/fuzzy matching and guessing are prohibited.
- Association changes are auditable.
- Public signup never grants administrator.
- External connector credentials are outside this decision.

**Security consequence:** Proposal checks session plus active owner membership;
verification checks session plus global administrator. Ingestion performs
read-only active/verified bridge resolution.

**Schema consequence:** A future business-owned lifecycle/audit relationship is
required, but its exact schema remains D18.

**Tests required:** Every role/state, cross-business and guessed IDs, duplicate
sides, invalid transitions, replacement, hard-delete prohibition, and admin
without tenant ingestion membership.

**Decision history:** Previously `APPROVAL REQUIRED`; user explicitly answered
`YES — approve D01`; current status `APPROVED`.

### D02 — Actual Module 2-to-registry mappings

**Priority:** P0
**Evidence status:** CONFIRMED FROM REPOSITORY
**Decision status:** BLOCKED

**Problem:** The bridge needs real IDs on both sides.

**Evidence:** The schema and runtime ID generators exist, but the repository has
no `.db`/SQLite data file. Tests generate temporary random IDs and are not real
mapping evidence. Raw datasets contain no FinSight business IDs. Names and
common owners are not proof.

**Required data:** A reviewed inventory for each mapping containing exact
`businesses.business_id`, business name, exact
`business_registry.business_id`, registry name, legacy owner, evidence of
identity, and intended administrator verifier. Actual account mappings should
be supplied separately under D07.

**Prohibited:** Invented/sample IDs presented as real, name matching, owner-only
matching, automatic backfill, or automatic registry creation.

**Approval requirement:** After evidence is supplied, present each exact
candidate with ambiguity/security analysis and obtain explicit human approval.

### D03 — Missing registry onboarding

**Priority:** P0
**Evidence status:** UNRESOLVED
**Decision status:** UNRESOLVED

**Problem:** Some Module 2 businesses may have no registry row, but ingestion
cannot safely create one or choose its legacy owner.

**Repository evidence:** `queries.create_business()` creates a legacy registry
row for a supplied user, but it does not enforce Module 2 owner or administrator
verification. Module 2 creates only `businesses` plus owner membership.

**Recommendation:** Use a separate administrator-controlled onboarding
workflow. An owner may request onboarding; an administrator deliberately
creates/selects the registry row, then the approved D01 bridge workflow applies.
Ingestion itself rejects a missing bridge and never onboards.

**Approval required:** Decide workflow ownership, evidence, lifecycle, and
whether this belongs to a separate administrative capability rather than
Module 4.

### D04 — Ledger owner versus uploader

**Priority:** P0
**Evidence status:** UNRESOLVED
**Decision status:** UNRESOLVED

**Problem:** Legacy `transaction_general_ledger.user_id` is both required and
used as an ownership filter, while Module 2 permits managers to act for a
business.

**Repository evidence:** `get_business_by_id(business_id, user_id)`, transaction
listing, financial summaries, and budget variance rely on registry owner/user
filtering. The legacy hash also includes user ID.

**Recommendation:** Preserve existing `user_id` legacy-owner semantics for
compatibility and add separate uploader/actor attribution if approved. Never
silently repurpose the existing field.

**Approval required:** Confirm owner/actor semantics and audit retention before
schema design. Determine delete behavior for an actor account without deleting
financial history.

### D05 — Standardizer transport

**Priority:** P2
**Evidence status:** RECOMMENDATION
**Decision status:** UNRESOLVED / RECOMMENDATION

**Problem:** No stable interface currently connects Zaara's standardisation to
the backend.

**Repository evidence:** The dashboard/KPI code uses pandas DataFrames and raw
CSV paths directly; no canonical standardizer function exists.

**Recommendation:** A versioned ordered collection of plain mappings with
deterministic primitive values and safe structured standardizer errors. Do not
expose DataFrames, Streamlit session objects, database rows, or SQL.

**Approval required:** Confirm Zaara's real output, version field, ordering,
null representation, error interface, and schema-evolution policy.

### D06 — Source-system vocabulary

**Priority:** P2
**Evidence status:** UNRESOLVED
**Decision status:** UNRESOLVED

**Problem:** Source participates in validation and identity, but no approved
vocabulary exists.

**Repository evidence:** Raw checking/card `type` contains Debit/Credit;
payroll `type` contains Employee Pay/Contractor Pay. None is a source-system
field. The schema has no source column or enum.

**Recommendation:** Use a small, controlled, versioned, lowercase vocabulary
confirmed with Zaara. Reject unknown values. Do not infer source from filename
inside Module 4.

**Approval required:** Exact tokens, casing, aliases, deprecation/versioning,
and unknown behavior.

### D07 — Financial-account mapping

**Priority:** P0
**Evidence status:** UNRESOLVED
**Decision status:** UNRESOLVED

**Problem:** Source records have labels/file context, not FinSight account IDs.

**Repository evidence:** Accounts are generated at runtime, belong to Module 2
businesses, and have status/currency. No database or mapping records connect
main checking, secondary checking, credit card, or payroll to accounts.

**Recommendation:** One ingestion batch selects one explicit active account
returned by backend listing. Re-read the account, verify its business, active
state, currency, and actor membership. Reject `business A + account B`.

**Approval/data required:** Real account IDs/mappings and confirmation of
single-account batch semantics. Do not auto-create or guess accounts.

### D08 — Payroll PII

**Priority:** P0
**Evidence status:** RECOMMENDATION
**Decision status:** UNRESOLVED

**Problem:** Payroll includes employee ID, employee name, and role.

**Repository evidence:** Current KPI calculations use payroll amount only; no
approved feature needs employee identity.

**Recommendation:** Module 4 v1 stores no employee name, raw employee ID, role,
contact, bank, or tax data and never exposes them in errors/logs. Do not create
counterparties automatically.

**Approval required:** Confirm minimisation policy and any genuine feature that
requires employee-level identity.

### D09 — Exact monetary storage

**Priority:** P0
**Evidence status:** RECOMMENDATION
**Decision status:** UNRESOLVED

**Problem:** Canonical identity requires exact money; the ledger stores `REAL`.

**Repository evidence:** Ledger/query summaries use float-compatible `REAL`.
`normalize_amount()` quantizes to two decimals, then insertion converts to
float. Module 3 accounts use integer minor units and Decimal conversion.

**Recommendation:** Add exact minor-unit representation for new ingestion while
retaining legacy `REAL` compatibility through deterministic dual write. Minor
units—not float—participate in new identity.

**Approval required:** Currency scale, accepted input, range, rounding versus
rejection, legacy backfill/preflight, consistency rules, and hash transition.
If legacy conversion cannot be proved deterministic, backfill is blocked.

### D10 — Balance-after persistence

**Priority:** P3
**Evidence status:** RECOMMENDATION
**Decision status:** UNRESOLVED / RECOMMENDATION

**Problem:** Raw checking/card files include balance, but the ledger and current
backend analytics do not.

**Recommendation:** If provided canonically, validate exact representation but
do not persist in v1 unless a proven backend requirement emerges. A source
balance may become stale after corrections and may use different account
semantics.

**Approval required:** Confirm omission or identify an existing analytical
requirement and authoritative correction semantics.

### D11 — Currency

**Priority:** P0
**Evidence status:** UNRESOLVED
**Decision status:** UNRESOLVED

**Problem:** Ledger rows and raw datasets lack currency; financial accounts
contain an editable uppercase three-letter code defaulting to INR.

**Recommendation:** Use the verified financial account's currency for the
transaction; do not trust a row override or infer from locale/country. Perform
no conversion. Unknown/unsupported currency blocks ingestion.

**Approval required:** Whether currency is persisted per transaction, account
currency immutability after transactions, supported currency/scale source, and
handling of historical account currency changes. Do not assume INR.

### D12 — Ingestion permissions

**Priority:** P0
**Evidence status:** UNRESOLVED
**Decision status:** UNRESOLVED

**Problem:** Ingestion is a business write action with no existing permission.

**Repository evidence:** Membership roles are owner, manager, member, viewer.
Owners/managers create/update/disable accounts; all active roles may read.
Global administrator is separate.

**Recommendation:** Active owners and managers may ingest/retry; members and
viewers cannot. Administrator role alone provides no tenant bypass.

**Approval required:** Confirm action/role matrix for create, retry, view status,
view row errors, and any future revoke capability.

### D13 — Text-field limits

**Priority:** P2
**Evidence status:** RECOMMENDATION
**Decision status:** UNRESOLVED / RECOMMENDATION

**Problem:** Canonical source IDs, descriptions, categories, counterparties,
display names, and safe errors need bounded input.

**Repository evidence:** Existing services use field-specific limits (for
example user 80, business 150, legal/account identifiers 100, account/
institution names 120), but no canonical transaction limits exist.

**Recommendation:** Approve field-specific Unicode character limits; normalise
whitespace deterministically; reject rather than truncate; bound batch error
lists and total record count.

**Approval required:** Exact limits and whether normalisation uses Unicode
normal form/case folding for identity fields.

### D14 — Canonical economic type to legacy transaction type

**Priority:** P0
**Evidence status:** CONFIRMED FROM REPOSITORY
**Decision status:** BLOCKED

**Problem:** Legacy summaries recognise `income` and `expense`; raw direction
contains debit/credit and includes transfers/card payments that are not simply
income/expense.

**Risk:** A blanket debit→expense and credit→income rule silently corrupts
analytics and double-counts transfers or debt payments.

**Recommendation:** Restrict v1 to explicitly proven economic mappings and
reject unknown/ambiguous rows. Approve a taxonomy separately from direction,
category, payment method, and source subtype.

**Approval required:** Exact canonical economic types and lossless/intentional
legacy mapping. Until then D14 is blocked.

### D15 — Privacy-safe payroll identity

**Priority:** P0
**Evidence status:** CONFIRMED FROM REPOSITORY
**Decision status:** BLOCKED

**Problem:** Payroll lacks transaction IDs; repeated low-entropy employee IDs
are sensitive and insufficient alone for transaction identity.

**Risk:** A plain unsalted hash is dictionary-attackable and does not prove
payment uniqueness. Employee/date/amount fallback may collide or expose PII.

**Recommendation:** Prefer a stable opaque source-issued payroll transaction
ID. Otherwise approve a reviewed business/source-scoped keyed pseudonym and
event identity with key lifecycle, or exclude payroll from v1.

**Approval required:** Privacy/security model and source capability. Payroll
remains blocked without it.

### D16 — Pre-bridge failure logging

**Priority:** P1
**Evidence status:** UNRESOLVED
**Decision status:** UNRESOLVED

**Problem:** Authentication, authorisation, and bridge failures can occur before
a verified registry business exists, while the current upload log requires one.

**Repository evidence:** `authentication_logs` is auth-specific; upload logs
require registry `business_id`. There is no general application audit table.

**Recommendation:** Do not fabricate a business or upload row. Return a safe
error and emit a redacted structured application/security log with actor only
when authenticated. Durable audit storage requires separate approval/schema.

**Approval required:** Retention, durable versus operational log, event types,
and who may access diagnostics.

### D17 — Post-rollback failure logging

**Priority:** P1
**Evidence status:** RECOMMENDATION
**Decision status:** UNRESOLVED / RECOMMENDATION

**Problem:** A failure log written inside the failed transaction disappears on
rollback.

**Recommendation:** Roll back all new ledger/log-success writes, close/reset
the failed transaction, then write one minimal safe failure record in a
separate transaction. If even that fails, retain only redacted application
logging and return a generic failure.

**Approval required:** Minimal persisted fields, status, retryability, and
whether failure-log failure affects the public response.

### D18 — Final schema extensions

**Priority:** P1
**Evidence status:** UNRESOLVED
**Decision status:** BLOCKED

**Problem:** D01–D17 jointly determine bridge, ledger, identity, amount,
currency, actor, source, and log schema.

**Known direction:** Changes must be additive, idempotent, minimal, and preserve
all Module 0–3 data and queries. No table drops, guessed backfills, or second
ledger/business/upload system.

**Candidate impacts, not approvals:** bridge lifecycle/audit table; ledger
account/source/source-ID/direction/minor-unit/currency/actor fields; canonical
identity protection; upload duplicate/account/source/status fields.

**Blockers:** D02–D17 approvals plus real-database preflight for hashes, amounts,
owners, FKs, and upload states.

### D19 — Public error vocabulary

**Priority:** P2
**Evidence status:** RECOMMENDATION
**Decision status:** UNRESOLVED / RECOMMENDATION

**Problem:** Streamlit needs stable errors without internal leakage.

**Repository evidence:** Existing services return `success`, stable `error`, and
safe `message`, including session/business/membership/account codes.

**Recommendation:** Reuse established codes where applicable and add controlled
ingestion categories for invalid envelope/record/source, missing bridge,
conflict, persistence failure, and internal failure. Row errors contain only
row reference, code, and safe message.

**Approval required:** Exact names, public messages, retryability, HTTP-free
Python semantics, and whether missing/unauthorised resources are intentionally
indistinguishable.

### D20 — Raw-file scope

**Priority:** P0
**Evidence status:** CONFIRMED FROM CONVERSATION
**Decision status:** UNRESOLVED

**Problem:** The reconstructed contract preserves canonical-record ingestion,
while raw files would add storage, parser, MIME, malicious-file, dependency,
retention, and background-processing responsibilities.

**Recommendation:** Approve canonical records only. Zaara/source adapters own
raw parsing. Raw-file support requires an explicit contract amendment covering
all file-security and lifecycle concerns.

**Current constraint:** Until D20 is approved, no raw-file capability may be
implemented because it is outside the contract baseline.

### D21 — Cross-cutting dependencies

**Priority:** P0
**Evidence status:** UNRESOLVED
**Decision status:** BLOCKED

**Problem:** Decisions cannot be implemented independently: ownership affects
ledger/schema; account affects currency; money affects hashing; payroll affects
identity/privacy; errors affect logs; rollback affects upload state; scope
affects dependencies/storage.

**Required action:** After D02–D20 approvals, recalculate the dependency graph,
detect contradictions/revisit decisions, and prove no circular unresolved
dependency remains. Any unresolved P0/P1 item keeps D21 blocked.

### D22 — Implementation readiness

**Priority:** P0
**Evidence status:** CONFIRMED FROM CONVERSATION
**Decision status:** BLOCKED

**Problem:** Recommendations are not authority to implement.

**Readiness requirements:** Approved ownership/mapping/permissions, financial
model, payroll privacy, interface/scope, failure/error model, stable schema
direction, feasible migration preflight, compatibility plan, test strategy,
green regression, and no contract conflict.

**Current conclusion:** Only D01 is approved; requirements are not met.

## 6. Decision matrix

**Evidence status:** CONFIRMED FROM CONVERSATION

| Decision | Status |
|---|---|
| D01 | APPROVED |
| D02 | BLOCKED |
| D03 | UNRESOLVED |
| D04 | UNRESOLVED |
| D05 | UNRESOLVED / RECOMMENDATION |
| D06 | UNRESOLVED |
| D07 | UNRESOLVED |
| D08 | UNRESOLVED |
| D09 | UNRESOLVED |
| D10 | UNRESOLVED / RECOMMENDATION |
| D11 | UNRESOLVED |
| D12 | UNRESOLVED |
| D13 | UNRESOLVED / RECOMMENDATION |
| D14 | BLOCKED |
| D15 | BLOCKED |
| D16 | UNRESOLVED |
| D17 | UNRESOLVED / RECOMMENDATION |
| D18 | BLOCKED |
| D19 | UNRESOLVED / RECOMMENDATION |
| D20 | UNRESOLVED |
| D21 | BLOCKED |
| D22 | BLOCKED |

## 7. Cross-document consistency constraints

**Evidence status:** CONFIRMED FROM CONVERSATION

- Only D01 is approved.
- Canonical-only scope is the current contract boundary, but D20 human approval
  remains outstanding; raw-file work is prohibited meanwhile.
- Recommendations for owner/actor separation, account selection, minor units,
  currency, permissions, privacy, and logging are not approved schema/API.
- No real mapping/account/source vocabulary may be inferred from examples.
- The standalone KPI payroll assumption does not override the observed
  non-reconciliation or create a ledger rule.

## 8. Decision history

**Evidence status:** CONFIRMED FROM CONVERSATION

| Decision | Previous status | Answer/change | Evidence | Current status |
|---|---|---|---|---|
| D01 | approval required | User: `YES — approve D01` | Repository has owner and administrator boundaries; approved conditions preserved | APPROVED |
| D02 | blocked by missing documents/data | Documents reconstructed; real mapping data still absent | No repository database or ID inventory | BLOCKED |
| D03–D22 | unresolved/blocked/recommended | No human approval recorded | Preserved conversation and repository evidence only | Matrix above |

## 9. Remaining risks

**Evidence status:** CONFIRMED FROM REPOSITORY

- Cross-business ledger routing without real mappings.
- Legacy owner/uploader confusion.
- Float-based financial identity and absent currency/direction/account/source.
- Non-idempotent existing insertion.
- Incorrect debit/credit to income/expense conversion.
- Payroll PII/identity and non-reconciliation.
- Unbounded or leaking errors/logs.
- Schema constraints that existing data may not satisfy.
- Raw-file scope creep and duplicate standardisation.

## 10. Phase 3A implementation gate

**Evidence status:** CONFIRMED FROM CONVERSATION

These reconstructed documents require explicit approval as the new
authoritative baseline. Reconstruction does not approve D02–D22 and does not
authorise production changes.

**NOT READY FOR MODULE 4 IMPLEMENTATION**
