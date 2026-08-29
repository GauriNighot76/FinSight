# Phase 3B — Controlled Non-Production Demo Evidence Approval

## Status

APPROVED FOR NON-PRODUCTION FINSiGHT DEVELOPMENT ONLY

This record does not designate, represent, or infer any production customer data.

## Approval

The project owner explicitly approved a controlled non-production FinSight
demo dataset as authoritative evidence for Phase 3A Gate 3.

Approved on: 2026-08-29

## Controlled Demo Evidence

The following identifiers are intentionally synthetic project identifiers.
They are not derived from filenames, PDFs, spreadsheets, business names,
account names, or any material under `acctual data/`.

### Module 2 business

- business_id: `demo_business_001`
- status: `active`

### Authorized membership

- user_id: `demo_owner_001`
- business_id: `demo_business_001`
- membership_role: `owner`
- membership_status: `active`

### Legacy registry business

- legacy registry business_id: `legacy_demo_business_001`
- legacy owner user_id: `demo_owner_001`

The Module 2 business and legacy registry business are intentionally separate
identities. Their relationship must be represented by the approved Module 4
bridge mechanism. It must not be inferred from matching names or identifiers.

### Financial account

- account_id: `demo_account_001`
- business_id: `demo_business_001`
- account_status: `active`
- currency: `INR`

Currency is authoritative from this explicitly approved demo account
designation. Module 4 must not infer currency from transaction records,
filenames, source tokens, descriptions, or UI input.

### Source system

Approved controlled non-production source_system token:

`finsight_demo_bank_statement_v1`

Scope:

Controlled non-production FinSight demo bank-statement ingestion only.

This token is not a production source token.

## Authoritative relationship chain

The controlled demo evidence chain is:

`demo_owner_001`
→ active owner membership
→ `demo_business_001`
→ approved bridge
→ `legacy_demo_business_001`
→ `demo_account_001`
→ currency `INR`
→ source_system `finsight_demo_bank_statement_v1`

The financial account belongs to the Module 2 business, not directly to the
legacy registry record. The bridge supplies the explicit relationship between
the Module 2 business and legacy registry business.

## Gate resolution

### D02 — Module 2 / legacy registry mapping evidence

RESOLVED FOR CONTROLLED NON-PRODUCTION DEMO IMPLEMENTATION.

The approved relationship is:

- Module 2 business: `demo_business_001`
- legacy registry business: `legacy_demo_business_001`
- legacy owner: `demo_owner_001`

No production mapping is asserted.

### D06 — Source system

RESOLVED FOR CONTROLLED NON-PRODUCTION DEMO IMPLEMENTATION.

Approved token:

`finsight_demo_bank_statement_v1`

No production token is approved.

### D11 — Currency

RESOLVED FOR CONTROLLED NON-PRODUCTION DEMO IMPLEMENTATION.

Approved verified demo-account currency:

`INR`

No currency conversion or inference is authorized.

## Restrictions

1. `acctual data/` is not authoritative mapping evidence.
2. Synthetic test fixtures are not production evidence.
3. No filename-based mapping is allowed.
4. No business-name matching is allowed.
5. No account-name matching is allowed.
6. No currency inference is allowed.
7. No production source token is implied.
8. No production customer mapping is implied.
9. Existing legacy ledger ownership semantics must remain unchanged.
10. Module 4 implementation must fail closed when the required bridge,
    account, membership, currency, or source relationship is absent.

## Gate 3 conclusion

Gate 3 is APPROVED for the explicitly controlled non-production FinSight
demo implementation described above.

This approval permits design of D18.

It does not itself modify the database schema, insert demo records, implement
Module 4 services, or authorize production deployment.
