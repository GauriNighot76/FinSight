# Final submission stabilization

Base: `submission-fix`, commit `13adb321ae9222f7e80fd6d5c143cea157f9041d`.
Repair branch: `fix/final-submission-stability`. No changes to main and no automatic merge.

## Root cause and audit

The main business and Owner membership were already active. The legacy-ledger bridge was a separate owner-proposal/admin-approval workflow. Ingestion additionally rejected a bridge whose proposer and verifier were the same user. This blocked normal users after account creation even though their business authorization was valid.

The application uses Streamlit adapters, service-level authorization, SQLite repositories, canonical integer-minor-unit transaction identities, and a legacy floating-point ledger mirror. Accounts belong to the main business. Ingestion authorizes session, business, membership role, account, and mapping before validation and atomic persistence. Analytics reads accepted identities by business/account/inclusive dates; health and recommendations are deterministic rules. Reports reuse those authorized services.

The audit inspected database/schema, services, security, UI, scripts, samples, tests, requirements and configuration. Searches covered approval/bridge/registry logic, medical/clinic/pharmacy defaults, buttons/state, and unfinished-code markers. No production medical default was found; explicit Medical input is preserved by existing category tests. No TODO/FIXME/NotImplemented stubs were found in the core searched modules.

Confirmed additional issues: upload widget state was shared across account selections; logout retained widget state; Windows native-command failures were not checked; ReportLab interpreted user business names as markup; zero savings rate displayed as unavailable; documented root `.env` configuration was not loaded by RAG. The app's synthetic scheme section remains clearly separate from authenticated analytics. Analytics is recomputed from current selections rather than cached session results.

## Minimal implementation

Business creation now writes business, active Owner membership, new internal registry identity, and active bridge in one transaction. Failure in membership, registry, or bridge creation rolls back. Existing schema constraints and bridge tables remain intact. The creator occupies both historical proposer/verifier columns for automatic activation. Independent approval is no longer an ingestion condition. An active mapping is still mandatory.

Registry identities are never inferred from names. Internal names include the main business ID to accommodate the legacy per-owner name uniqueness constraint, allowing separate same-name businesses without accidental merging.

Initialization backfills only active businesses with exactly one active owner whose user account is active. Missing mapping history receives a fresh identity. A sole pending bridge is activated only when its proposer and registry owner match that owner and no other bridge references that registry. Active, rejected, disabled, conflicting, and ambiguous histories are preserved. Financial rows are not rewritten. The backfill shares the initialization transaction; failures roll back its changes. Back up existing databases before upgrading.

The administrator role, backend role checks, and legacy exceptional-maintenance APIs remain. The approval-only setup panel is removed. Owners cannot create a replacement proposal to bypass rejected/disabled history.

## Changed files

| File | Change and reason |
| --- | --- |
| `database/queries.py` | Atomic internal mapping creation and conservative backfill; avoids name-based merging. |
| `database/db.py` | Runs compatibility backfill during initialization. |
| `services/ingestion_service.py` | Removes only the independent-verifier restriction. |
| `services/bridge_service.py` | Documents maintenance-only APIs and blocks reproposal over restricted history. |
| `finsight_app/setup_ui.py` | Removes normal approval steps and approval-only admin panel. |
| `finsight_app/ingestion_ui.py` | Scopes uploaded files to business/account; replaces obsolete approval guidance. |
| `finsight_app/app.py` | Clears session/widget state on logout or expired login. |
| `finsight_app/pdf_generator.py` | Escapes business names, preserves zero savings, formats minor units with Decimal. |
| `finsight_app/scheme_rag.py` | Loads root `.env` without overriding existing environment configuration. |
| `scripts/seed_demo.py` | Seeds through self-service onboarding without creating/logging in an administrator. |
| `scripts/verify_windows.ps1` | Fails immediately when native setup/install/test/compile/seed commands fail. |
| `tests/test_bridge_service.py` | Replaces ordinary approval expectation with automatic active mapping; retains admin authorization denial. |
| `tests/test_module4_ingestion_service.py` | Accepts active self-activated bridges; other authorization checks remain tested. |
| `tests/test_smoke_end_to_end.py` | Fresh initialization, no-admin flow, exact sample totals, invalid/duplicate data, empty data, isolation, PDF and logout. |
| `tests/test_self_service_migration.py` | Idempotence, existing data preservation, blocked/ambiguous states, rollback and same-name isolation. |
| `tests/test_streamlit_app.py` | Actual Streamlit registration/setup/report/switch/logout interaction regression. |
| `tests/test_scheme_rag_safety.py` | Verifies `.env` loading and environment precedence with synthetic configuration. |
| `README.md` | Current self-service architecture, migration behavior, supported runtime, exam steps and expected totals. |
| `finsight_app/README.md` | Replaces obsolete setup/index-caching instructions with root installation guidance. |
| `TRIAGE.md` | Marks prior audit as historical and links to this verification. |
| `docs/ingestion_implementation_spec.md` | Marks historical human-approval design as superseded. |
| `docs/ingestion_ui_contract.md` | Marks historical human-approval design as superseded. |
| `docs/module4_completion_report.md` | Marks historical human-approval design as superseded. |
| `docs/phase3_decision_record.md` | Marks historical human-approval design as superseded. |
| `docs/phase3a_current_state_amendment.md` | Marks historical human-approval design as superseded. |
| `docs/phase3c_d18_schema_design.md` | Marks historical human-approval design as superseded. |
| `STABILIZATION.md` | Records audit, changes, evidence and limitations for review. |

No schema rebuild, dependency upgrade, ORM, database replacement, or new product feature was introduced.

## Security evidence

The fresh-database smoke test creates no administrator. A second registered user cannot view the first business/account, add a member, create or modify an account, ingest transactions, or obtain analytics, health, recommendations or reports. Existing tests cover invalid/expired/revoked sessions, disabled entities, role restrictions, account mismatch, validation/precision, duplicate identities and transactional rollback. Bcrypt, hashed session tokens, SQL parameters, foreign keys and canonical integer amounts remain unchanged.

## Verification

Executed in a new Python 3.12.14 virtual environment on Linux, with core dependencies only:

- `python -m pip install --upgrade pip`: passed.
- `python -m pip install -r requirements.txt`: passed with existing pins.
- `python -m pip check`: no broken requirements.
- `python -m pytest -q`: **522 passed in 38.42s; 0 failed, 0 skipped**.
- `python -m compileall -q database services finsight_app scripts`: passed.
- Database/service/security/UI module imports: passed; application entry point exercised through Streamlit AppTest.
- Headless Streamlit health: HTTP 200 `ok`; no startup traceback.
- Synthetic demo seed: 12 inserted on first run; 0 inserted, 12 duplicates on repeat.
- Interactive AppTest: registration, login, business/account creation, totals, health/report output, business switch and logout without rendered exceptions.
- Sample totals: income INR 371,000; expenses INR 125,000; net INR 246,000; 12 transactions.

## Limits and exam preparation

Windows execution is NOT VERIFIED in this Linux environment. Run `scripts\verify_windows.ps1` and the root README click-through on the actual examination machine. Python 3.11/3.14 are not the supported tested environment.

AppTest does not expose file-uploader interaction here. CSV bytes were tested through the real normalizer/ingestion services and existing UI adapter tests; a physical browser file upload and PDF download remain manual exam-machine checks. The PDF contains financial summary totals; detailed recommendations remain in the application.

Live Groq/FAISS/MiniLM inference is NOT VERIFIED: no real API key, optional dependencies, or model download was used. Core startup/imports and safe unavailable behavior are tested. Scheme matching remains synthetic and separate from user financial data.

Legacy verifier column names and the ledger REAL amount mirror remain technical debt. Ambiguous/restricted old mappings deliberately require exceptional maintenance. No real user database was modified during testing. Ordinary new business onboarding requires no administrator.
