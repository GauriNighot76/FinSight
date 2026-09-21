> Historical design record: normal onboarding approval requirements in this document are superseded by the automatic internal mapping design in [README](../README.md#automatic-onboarding-and-existing-databases).

# FinSight Phase 3A — Current-State Amendment

**Document status:** CONTROLLED CURRENT-STATE AMENDMENT
**Repository baseline:** `59744445a4ed80199999c03ace11e98023065c95`
**Scope:** Decision-status amendment only; no implementation authorization

## 1. Purpose and authority

The three Phase 3A documents listed below are byte-verified reconstructed
historical baseline artifacts. They were reconstructed before most Phase 3
decisions received explicit approval, so their original status statements and
matrices preserve that earlier historical state.

Subsequent approvals were established through the controlled decision process.
This document records those approvals without pretending that they existed in
the original reconstructed bytes. It is the authoritative source for the
**current decision status**. The recovered documents remain authoritative as
historical reconstruction artifacts and as technical evidence, subject to
later approved decisions recorded here.

If a recovered document and this amendment conflict solely on decision status,
this amendment controls the current status. This precedence does not authorize
silent changes to technical requirements, production code, database schema, or
financial mappings.

## 2. Recovered Phase 3A baseline

| Recovered document | Original reconstructed SHA-256 | Bytes | Lines |
|---|---|---:|---:|
| `docs/ingestion_ui_contract.md` | `2f27427b5f1dce371042c433374a0879b9e64d0325a6bd87141af330af9176e6` | 24,038 | 619 |
| `docs/ingestion_implementation_spec.md` | `bf0897ad07c6e58547eb55ba08452b130d20c21cc245fd38b1128a145f72cd21` | 24,959 | 549 |
| `docs/phase3_decision_record.md` | `9209808664add91963bd372e5b9b2ea99694b345450db7fbfbbcdc8be28bf6bb` | 23,184 | 592 |

These are reconstruction hashes, not hashes of the permanently unavailable
original historical documents. The original reconstructed hashes remain part
of the permanent provenance record. Notices added for this amendment produce
new current hashes, recorded in Section 11.

## 3. Current decision matrix

| Decision | Current status | Qualification |
|---|---|---|
| D01 | APPROVED | Active Module 2 owner proposes; global administrator independently verifies and controls bridge activation |
| D02 | BLOCKED | Required authoritative mapping data unavailable |
| D03 | APPROVED | Option D — owner proposes registry onboarding; administrator verifies or rejects |
| D04 | APPROVED | Option A — preserve legacy owner; record uploader separately |
| D05 | APPROVED | Option A — versioned ordered collection of JSON-compatible plain mappings |
| D06 | APPROVED MECHANISM ONLY | Controlled tokens; no production token approved |
| D07 | APPROVED | One server-authorized financial account per batch |
| D08 | APPROVED | No employee payroll PII |
| D09 | APPROVED | Exact minor units with legacy `REAL` compatibility |
| D10 | APPROVED | Validate `balance_after`; do not persist it |
| D11 | APPROVED | Verified account currency; no conversion; real mapping still required |
| D12 | APPROVED | Active owners and managers only |
| D13 | APPROVED | Bounded text and batch limits; no silent truncation |
| D14 | APPROVED | Only `income` and `expense` |
| D15 | APPROVED | Option A — exclude payroll ingestion from Module 4 v1 |
| D16 | APPROVED | Option A — safe pre-bridge logging; no ingestion attempt before authorization |
| D17 | APPROVED | Option A — rollback financial writes and persist failure separately; linked retry |
| D18 | BLOCKED | Final database schema remains unresolved |
| D19 | APPROVED | Option A — stable public error codes and safe messages |
| D20 | APPROVED | Option A — canonical records only; raw-file work remains outside Module 4 |
| D21 | BLOCKED UNTIL D18 | Cross-cutting dependency validation requires the final schema |
| D22 | NOT READY FOR IMPLEMENTATION | Mandatory readiness conditions are not satisfied |

**Summary:** 18 decisions are approved. D02, D18, and D21 remain blocked;
D22 remains not ready.

## 4. Approved identity, ownership, and authorization decisions

### D01 — Bridge authority

An active Module 2 business owner proposes a bridge. A global administrator
independently verifies and controls activation, rejection, suspension,
replacement, or disabling. Administrator approval does not confer tenant
ingestion access. Exact Module 2 and registry identities remain mandatory;
name-only inference is forbidden.

### D03 — Registry-business onboarding (Option D)

An active Module 2 owner proposes registry-business onboarding. A global
administrator independently verifies or rejects it. Registry creation neither
creates nor activates a bridge. Evidence must establish the legitimate
registry business without name-only inference. D04 controls legacy registry
`user_id` semantics.

### D04 — Ledger owner versus uploader (Option A)

Legacy ownership remains unchanged:

```text
business_registry.user_id
    = legacy registry owner/access principal

transaction_general_ledger.user_id
    = corresponding legacy owner/access principal
```

Ledger `user_id` is not uploader identity. Future uploader attribution is
separate and derived from the authenticated session. Historical uploader
identity remains unknown and must not be fabricated. Uploader identity cannot
affect transaction ownership, financial grouping, or canonical identity.

### D07 — Financial-account mapping

Each ingestion batch targets exactly one financial account. The server must
verify that the account exists, is active, belongs to the authorized Module 2
business, and is permitted for the authenticated actor. A caller-supplied
account ID never proves authority.

### D12 — Ingestion permissions

Only active business owners and managers may ingest. Authorization is
server-side and must verify the session, user, business, membership, account,
and bridge from current database state. Members, viewers, outsiders, and global
administrators without the required tenant membership cannot ingest.

## 5. Approved interface and validation decisions

### D05 — Standardizer transport (Option A)

The Module 4 boundary receives a versioned ordered collection of plain mappings
whose values are JSON-compatible primitives permitted by the contract.
Standardization errors remain separate. Pandas DataFrames, Streamlit upload
objects or session state, raw files, filesystem paths, database rows, and
executable or arbitrary Python objects are outside the boundary.

### D06 — Source-system vocabulary mechanism

The controlled enumerated-token mechanism is approved. This approval does not
approve an actual production `source_system` token. Tokens require exact
matching; unknown, deprecated, incorrectly cased, whitespace-altered, or
malformed values fail closed. A token cannot authorize access, select tenant
resources, construct SQL or paths, or choose arbitrary Python code.

### D13 — Text and batch limits

Bounded text and batch limits are approved. Limits must be enforced before
persistence; identity and financial fields cannot be silently truncated.
Oversized input fails safely without exposing raw values. Implementers must use
the approved bounded values from the controlled decision record and may not
invent or weaken production limits.

### D19 — Public errors (Option A)

Public responses use stable codes and safe human-readable messages. They never
expose SQL, stack traces, filesystem paths, credentials, tokens, raw records,
database internals, or implementation details. Sanitized internal diagnostics
remain separate.

### D20 — Raw-file scope (Option A)

Module 4 accepts canonical records only. Raw file upload, OCR, parsing,
source-specific extraction, and standardization remain outside Module 4.

## 6. Approved financial decisions

### D09 — Exact monetary representation

New canonical monetary storage uses integer minor units while preserving
required legacy `REAL` compatibility. Binary floating-point values cannot cross
the canonical financial boundary. Silent rounding and monetary coercion are
forbidden.

### D10 — Balance-after

`balance_after` may be validated when supplied but is not persisted by Module 4
v1 and does not participate in transaction identity.

### D11 — Currency

Currency comes from the verified financial account. Module 4 v1 performs no
currency conversion and does not infer currency from locale, filename,
description, source token, or UI input. The policy is approved, but the real
account-to-currency mapping remains unavailable and must be proven under D02.

### D14 — Economic type

The only permitted Module 4 v1 economic types are:

```text
income
expense
```

No third type—including transfer, payroll, refund, adjustment, fee, `other`, or
`unknown`—is approved. Economic type cannot be inferred from arbitrary
filenames or descriptions.

## 7. Approved payroll/privacy decisions

### D08 — Payroll PII

Module 4 v1 does not ingest employee PII. Employee identifiers, names, and
equivalent identity data cannot be persisted. Payroll remains excluded where a
privacy-safe transaction identity cannot be established.

### D15 — Payroll identity (Option A)

Payroll ingestion is excluded from Module 4 v1. No payroll identity may be
invented, and employee identifiers may not be hashed to manufacture one. No
employee PII is stored.

## 8. Approved failure and audit decisions

### D16 — Pre-bridge failure logging (Option A)

Authentication and authorization failures use the existing security logging
boundary where applicable. Malformed requests, invalid source values, and
similar application failures use sanitized structured application logging. No
ingestion-attempt record is created before business, bridge, and account
authorization succeeds. Logs exclude secrets, raw financial records, account
numbers, PII, paths, public stack traces, and credentials.

### D17 — Post-rollback failure logging (Option A)

The ingestion-attempt record is committed separately where required by the
approved specification. If financial persistence fails, all financial writes
are rolled back, then the sanitized failure state is committed separately.
The original failed attempt is preserved. A retry creates a new linked attempt
and never overwrites prior history.

## 9. Blocked gates

### D02 — Required mapping data unavailable

D02 remains **BLOCKED**. No real mapping is established by this amendment.
The required evidence remains:

1. exact Module 2 `business_id`;
2. exact legacy registry `business_id`;
3. exact financial `account_id`;
4. external source/account identity;
5. verified account currency;
6. approved production `source_system` token; and
7. authoritative relationship and approval evidence.

Mappings cannot be inferred from name similarity, test or fixture IDs, common
users, filenames, account names, CSV contents, synthetic records, or historical
assumptions.

### D18 — Final schema

D18 remains **BLOCKED**. The final schema cannot be approved until required
real mappings, production source tokens, currency evidence, canonical identity
rules, and migration inventory are available. This amendment creates no table,
column, index, constraint, or migration.

### D21 — Dependency validation

D21 remains **BLOCKED UNTIL D18**. Final dependency validation requires an
approved schema and implementation plan.

### D22 — Implementation readiness

D22 remains **NOT READY FOR IMPLEMENTATION**. The documentation amendment does
not authorize production implementation.

## 10. Safety and implementation boundary

This amendment:

- creates no D02 mapping;
- approves no production source token;
- invents no account currency;
- creates no payroll identity;
- changes no production code, schema, migration, test, dependency, or UI;
- does not rewrite historical financial data or hashes; and
- does not make Module 4 implementation-ready.

All future work must satisfy both the recovered technical documents and this
current-state amendment. Where decision status conflicts, this amendment is
authoritative for current status while the recovered bytes remain authoritative
historical reconstruction artifacts.

## 11. Current amended-document hashes

The notices added under this controlled amendment produce new hashes without
altering the recorded original reconstruction hashes:

| Current amended document | Current SHA-256 |
|---|---|
| `docs/ingestion_ui_contract.md` | `448b387fabe980796826a03850b385acb573ac64259eff4a9e1cff3e1f75aedb` |
| `docs/ingestion_implementation_spec.md` | `eed1026db2cde771497f58145caba8f1eb7eb80666113c3a0129d2f23d52471b` |
| `docs/phase3_decision_record.md` | `a588bd5d2943a9a1b3ec597c2615545c7b01341cf345081df80bd9ed6f5927ba` |

The SHA-256 of this amendment is recorded in the final verification report and
commit audit because a document cannot contain its own stable cryptographic
hash.

## 12. Next gate

The next permitted gate is D02: authoritative real
business/registry/account/source/currency mapping evidence. D02 must remain
blocked unless every required relationship is proven without inference.

**D22 = NOT READY FOR IMPLEMENTATION.**
