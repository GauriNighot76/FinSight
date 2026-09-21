# FinSight stabilization triage

Repository: `https://github.com/GauriNighot76/FinSight`

Starting commit: `ba654b602a0717986c164557d5c7abebcefe5987`

Working branch: `submission-fix` (never merged into `main`)

This file records observed behavior from the checked-out code. Tests and runtime
probes use temporary databases; the repository's user database is never used.

## Triage table

| ID | Severity | Area | Symptom | Reproduction | Root cause | Regression test | Fix | Status |
| -- | -------- | ---- | ------- | ------------ | ---------- | --------------- | --- | ------ |
| T-01 | P0 | Entry point / paths | AppTest failed from the repository root or an unrelated directory | Run the absolute `finsight_app/app.py` entry point with AppTest after changing cwd | Package and bundled-data imports depended on cwd | `tests/test_streamlit_app.py::test_app_loads_from_unrelated_working_directory` | Package-qualified imports and module-relative `Path` values | VERIFIED |
| T-02 | P0 | Authenticated UI | Signed-in view raised `StreamlitDuplicateElementId` | Sign in to a temporary seeded database containing one business/account | Ingestion and analytics used identical implicit widget IDs | Module 4/5 Streamlit suites plus authenticated AppTest probe | Stable page-specific keys for every duplicated widget | VERIFIED |
| T-03 | P0 | Fresh ingestion | A newly created business always returned `BRIDGE_NOT_VERIFIED` | Register → create business/account → upload valid payload | Ingestion correctly required an independently verified bridge, but no public proposal/approval flow existed | `tests/test_bridge_service.py`; `tests/test_smoke_end_to_end.py` | Owner proposal service/UI and separate administrator approval; seed uses both roles | VERIFIED |
| T-04 | P1 | Stored money | Legacy ledger retains a floating-point amount mirror | Inspect schema and ingestion persistence | Backward-compatible `transaction_general_ledger.amount REAL` predates authoritative integer identities | Existing ingestion/analytics suite verifies integer identity and analytics | Authoritative analytics remain integer-minor-unit based; legacy mirror documented for later migration | KNOWN LIMITATION |
| T-05 | P1 | Summary / PDF | Visible summary and original PDF did not use the signed-in user's selected data | Load the app and inspect `Download PDF Report` data flow | Synthetic KPI engine always reads bundled CSVs and the PDF name was literal `Demo Coffee Shop` | `tests/test_smoke_end_to_end.py`; authenticated AppTest probe | Synthetic area is explicitly labelled and isolated; authenticated analytics now generates a selected-business PDF | VERIFIED |
| T-06 | P1 | RAG | Optional RAG could crash on missing packages/key and enabled dangerous FAISS deserialization | Import/call RAG without optional packages or key; inspect old `load_local` call | Eager optional dependencies, cwd-relative paths, and unsafe pickle opt-in | `tests/test_scheme_rag_safety.py` | Lazy imports, module-relative documents, in-memory trusted index build, safe messages, no dangerous deserialization | VERIFIED |
| T-07 | P1 | Selection | Duplicate business/account names could select the first row | Supply two records with the same visible name | UI labels were used as identifiers through `list.index` | Duplicate-name cases in `test_module4_streamlit.py` and `test_module5_streamlit.py` | Duplicate labels include a stable ID suffix | VERIFIED |
| T-08 | P1 | CSV errors | Safe actionable CSV errors were replaced by a generic message | Upload malformed/missing-column CSV | UI discarded `CSVNormalizationError`'s sanitized explanation | Module 4 malformed CSV Streamlit regression | Display the normalizer's safe message; backend exceptions remain sanitized | VERIFIED |
| T-09 | P0 | Onboarding UI | Active Streamlit app had no registration, business, account, or bridge setup screen | Load unauthenticated and authenticated app | Backend services existed but were not wired into the active entry point | Auth/business/account suites, bridge suite, smoke test, AppTest probes | Minimal registration and authenticated Setup tab | VERIFIED |
| T-10 | P1 | Health/report UI | Health, decision support, and authorized report had no active UI caller | Sign in and inspect tabs/actions | App rendered ingestion/analytics only; original PDF was synthetic | `tests/test_smoke_end_to_end.py`; authenticated AppTest probe | One action renders rule-based health/recommendations and selected-data PDF | VERIFIED |
| T-11 | P1 | Medical category | Reported automatic/default `Medical` category | Search tracked production/tests/data/history; query attached DB read-only; run seven category-isolation cases | No production Medical default found; tracked occurrences were explicit test inputs | `tests/test_csv_normalizer.py::test_medical_category_is_never_invented_or_leaked` | No category inference change was justified | NOT REPRODUCED |
| T-12 | P1 | Unknown Submit | Reported wrong information after an unspecified Submit action | Inventory all Streamlit/HTML buttons and active handlers | Active Streamlit app had no literal `Submit`; reporter's exact page/input/checkout was unavailable | Concrete stale/wrong-data paths are covered by T-02, T-05, T-07, and T-14 | No invented button-specific fix | NOT REPRODUCED |
| T-13 | P2 | Packaging/docs | Empty README, duplicated dependency list, malformed ignore bytes | Inspect tracked tree and install paths | Root documentation was empty; app requirements duplicated core/optional packages; `.gitignore` contained NUL bytes | Clean-install and static checks | Root README, optional `requirements-rag.txt`, corrected ignore/config examples, Windows verification script | VERIFIED |
| T-14 | P1 | CSV lineage | CSV category, payment mode, and description disappeared after ingestion | Normalize and ingest a CSV containing distinct metadata, then query authorized analytics/ledger | Ingestion passed only canonical identity fields into the legacy metadata row | `tests/test_module4_end_to_end.py::test_csv_metadata_reaches_ledger_and_analytics` | Persist normalized metadata while canonical money/direction identity remains authoritative | VERIFIED |
| T-15 | P1 | Configured DB path | A configured nested database parent was not created | Point `DATABASE_PATH` to a missing nested directory and initialize twice | Connection setup created `DATA_DIR`, not `DATABASE_PATH.parent` | `tests/test_db.py::test_configured_database_parent_is_created` | Create the configured parent before connecting | VERIFIED |

## Submit investigation

The active Streamlit controls on the starting commit were:

| Page/source | Button or trigger | Starting data flow |
| --- | --- | --- |
| Authentication | `Sign in`, `Sign out` | Input → auth service → users/sessions |
| Transactions | `Ingest transactions` | Upload → normalizer → validation/identity → SQLite |
| Analytics | `Refresh analytics` | Selected business/account/date → analytics service |
| Synthetic scheme area | Question text changed the app | Question → FAISS/Groq when available |
| Synthetic report | `Download PDF Report` | Bundled CSV KPIs + literal demo profile → PDF |
| Static `LoginPage/index.html` prototype | `Login`, `Create Account` | Not imported by Streamlit |

No active Streamlit button was literally named `Submit`, and the static HTML
prototype was not part of the runtime entry point. Therefore the exact reported
action is **NOT REPRODUCED**. A concrete misleading flow was reproduced on the
synthetic report: no uploaded input was consulted, so it could not reflect a
selected account. It is now named `Download synthetic PDF report`, sits under
`Synthetic scheme-matching demonstration`, and discloses Service, Maharashtra,
Micro, age 30, and bundled CSVs as assumptions. Authenticated reporting is a
separate action under `Analytics and reports` and uses the selected authorized
business, account, currency, and inclusive dates.

## Medical investigation

Case-insensitive searches covered tracked Python, CSV, JSON/configuration, scheme
documents, and the last 15 commit patches. On the starting commit, all tracked
`Medical` occurrences were explicit CSV values/assertions in
`tests/test_csv_normalizer.py`; none was a production default. Parameterized,
read-only aggregate queries found no Medical match in the attached database's
category/business-type fields; no row contents were displayed.

The regression test proves:

1. Explicit `Medical` remains `Medical`.
2. Explicit non-medical category remains unchanged.
3. A missing category is omitted and analytics uses its existing `Uncategorized` fallback.
4. An empty category follows that same omission contract.
5. A description containing “medicine” does not overwrite an explicit category.
6. Multiple uploaded rows retain independent categories.
7. A later upload does not inherit an earlier category.
8. Direction is independent of category.

Result: **NOT REPRODUCED**; no fake root cause or automatic-category change was made.

## Runtime inventory and data lineage

- Streamlit entry point: `finsight_app/app.py`; there is no multipage `pages/` tree.
- Database initialization: `database/db.py::initialize_database`.
- Active database path: `FINSIGHT_DATABASE_PATH` when set, otherwise
  `<repo>/data/finsight.db`.
- Active schema/query modules: `database/schema.sql`, `database/queries.py`.
  Runtime imports were resolved to this checkout. `tests/test_schema.sql` is test-only.
- No tracked database or FAISS index exists.
- Root `requirements.txt` is the core list; `requirements-rag.txt` is optional.
- RAG: `finsight_app/scheme_rag.py`; documents are under
  `finsight_app/scheme_docs/`.
- Backend reporting: `services/report_service.py`; PDF adapters are in
  `finsight_app/pdf_generator.py`.
- Synthetic CSVs used only by the labelled scheme demo are under
  `finsight_app/data/`. Examination uploads are under `sample_data/`.
- Tests are under `tests/`; all use temporary SQLite databases through the autouse
  fixture or an explicit temporary path.

| Visible result | Verified source |
| --- | --- |
| Registration/login | `users` and hashed `auth_sessions` via auth service |
| Business/account selectors | Membership-authorized active businesses/accounts |
| Upload counts | Normalizer → validation/identity → atomic ingestion result |
| Authenticated financial values | Integer-minor identities scoped by business/account/date/currency |
| Categories/payment modes | Metadata persisted from uploaded CSV and joined to identities |
| Health/recommendations | Same selected analytics; deterministic rules |
| Authenticated PDF | Authorized report service using the same selected scope |
| Scheme-demo summary/PDF | Clearly labelled bundled synthetic CSV/profile assumptions |
| RAG answer | Only bundled chunks tagged for the selected scheme; optional Groq call |

## Verification evidence

Environment used by the coding agent: Linux, Python 3.12.14, pip 26.2.1,
Git 2.51.1. Windows and Python 3.14 were not available and are not claimed.

- Baseline install: new `.venv`, pip upgrade, `pip install -r requirements.txt` → exit 0.
- Baseline suite: 498 collected/passed, 0 failed, 0 errors, 0 skipped.
- Current targeted database/RAG tests: 11 passed.
- Current unrelated-cwd AppTest: 1 passed, zero rendered exceptions.
- Current full suite before the final path test was added: 508 passed; a final full
  clean-room count is recorded in the final handoff.
- Seed in a fresh temporary DB: first run 12 inserted; second run 12 duplicates.
- Independently summed sample totals: income 37,100,000 minor, expense 12,500,000
  minor, net 24,600,000 minor, 12 transactions. The analytics service returned the
  same totals, with opening 1,000,000 and closing 25,600,000 minor.
- Compilation: `python -m compileall database services finsight_app scripts` → exit 0.
- Headless Streamlit health and clean-clone verification are repeated after final
  commits. Windows execution remains required on the student's machine using
  `scripts\verify_windows.ps1`.

## Known limitations

- The legacy general-ledger compatibility field remains SQLite `REAL`; canonical
  identities and authenticated analytics use integer minor units.
- Scheme matching remains an explicitly separate synthetic demonstration.
- RAG requires optional dependencies, model availability, and `GROQ_API_KEY`; it
  degrades safely when unavailable.
- SQLite is the current database. Five-million-row performance is not validated.
- Google sign-in has a backend boundary but no examination UI; local registration
  and sign-in are the verified demonstration path.
- Final Windows/Python 3.12 execution is still required; Python 3.14 is unverified.
