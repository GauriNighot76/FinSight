# FinSight Streamlit application

The application is launched from the repository root:

```bash
python -m streamlit run finsight_app/app.py
```

`app.py` initializes the database, protects all application content behind a
validated session, and connects the following UI adapters:

- `ingestion_ui.py` — authenticated CSV/XML/JSON ingestion with automatic,
  reviewable column mapping through `services.flexible_import`, followed by
  strict validation and `services.ingestion_service`.
- `analytics_ui.py` — business/account/date selection and read-only analytics
  through `services.analytics_service`.
- `dashboard_ui.py` — financial summary, scheme matching, and report controls
  using the selected backend analytics scope.
- `workspace_ui.py` — authenticated business and financial-account setup.
- `pdf_generator.py` — presentation-only PDF generation from a backend report.
- `scheme_rag.py` — optional scheme-document question answering.

The dashboard does not calculate financial totals from the static CSV demo
files. It uses accepted transaction data returned by the backend services.
Static CSV files remain only as legacy/demo assets and scheme-reference data.
