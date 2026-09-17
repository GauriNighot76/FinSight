"""Thin Streamlit adapter for the Module 4 ingestion service.

The adapter deliberately receives a Streamlit-like object so its security and
rendering behavior can be tested without importing Streamlit.  Authorization,
validation, identity, duplicate handling, and persistence remain backend
responsibilities.
"""

import json
from typing import Any, Optional

from services import (
    account_service,
    auth_service,
    bridge_service,
    business_service,
    csv_normalizer,
    flexible_import,
    ingestion_service,
)


AUTHORIZED_MEMBERSHIP_ROLES = frozenset({"owner", "manager"})

_SAFE_ERROR_MESSAGES = {
    "AUTHENTICATION_FAILED": "Authentication is required for ingestion.",
    "BUSINESS_NOT_FOUND": "The selected business is unavailable.",
    "MEMBERSHIP_REQUIRED": "An active business membership is required.",
    "INGESTION_FORBIDDEN": "The current business role cannot ingest data.",
    "ACCOUNT_NOT_AUTHORIZED": "The selected financial account is unavailable.",
    "BRIDGE_NOT_VERIFIED": "Finish the business setup before importing transactions.",
    "REGISTRY_BUSINESS_NOT_FOUND": "The linked registry business is unavailable.",
    "REGISTRY_OWNER_NOT_FOUND": "The linked registry owner is unavailable.",
    "VALIDATION_FAILED": "The ingestion payload is invalid.",
    "IDENTITY_CONFLICT": "The ingestion contains a conflicting transaction identity.",
    "STORAGE_FAILED": "The ingestion could not be completed.",
}


def _safe_error_message(code: Any) -> str:
    return _SAFE_ERROR_MESSAGES.get(code, "The ingestion could not be completed.")


def _membership_role(business: dict[str, Any]) -> Optional[str]:
    membership = business.get("membership")
    if isinstance(membership, dict):
        role = membership.get("membership_role")
        return role if type(role) is str else None
    role = business.get("membership_role")
    return role if type(role) is str else None


def _authorized_businesses(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict) or result.get("success") is not True:
        return []
    businesses = result.get("businesses")
    if type(businesses) is not list:
        return []
    return [
        business
        for business in businesses
        if isinstance(business, dict)
        and type(business.get("business_id")) is str
        and type(business.get("business_name")) is str
        and business.get("business_status") == "active"
        and isinstance(business.get("membership"), dict)
        and business["membership"].get("membership_status") == "active"
        and _membership_role(business) in AUTHORIZED_MEMBERSHIP_ROLES
    ]


def _display_counts(st: Any, result: ingestion_service.IngestionWriteResult) -> None:
    st.caption(f"Rows detected: {result.record_count}")
    st.caption(f"Rows accepted: {result.inserted_count}")
    st.caption(f"Rows rejected: {result.rejected_count}")
    st.metric("Records", result.record_count)
    st.metric("Inserted", result.inserted_count)
    st.metric("Duplicates", result.duplicate_count)
    st.metric("Rejected", result.rejected_count)
    if result.retry_count:
        st.caption(f"Retry count: {result.retry_count}")


def _read_uploaded_json(uploaded_file: Any) -> Any:
    raw = uploaded_file.getvalue()
    if type(raw) is bytes:
        raw = raw.decode("utf-8")
    if type(raw) is not str:
        raise ValueError
    return json.loads(raw)


def _is_tabular_upload(uploaded_file: Any) -> bool:
    name = getattr(uploaded_file, "name", None)
    if type(name) is str:
        lowered_name = name.lower()
        if lowered_name.endswith((".csv", ".xml")):
            return True
        if lowered_name.endswith(".json"):
            return False
    content_type = getattr(uploaded_file, "type", None)
    if type(content_type) is str:
        lowered_type = content_type.lower()
        if lowered_type in {"text/csv", "application/xml", "text/xml"}:
            return True
        if lowered_type == "application/json" or lowered_type.endswith("+json"):
            return False
    try:
        raw = uploaded_file.getvalue()
    except Exception:
        return False
    if isinstance(raw, bytes):
        raw = raw.lstrip().decode("utf-8-sig", errors="ignore")
    if type(raw) is str:
        return not raw.lstrip().startswith(("{", "["))
    return False


def _read_uploaded_payload(uploaded_file: Any) -> Any:
    if _is_tabular_upload(uploaded_file):
        analysis = flexible_import.analyze_upload(
            uploaded_file.getvalue(), getattr(uploaded_file, "name", "upload.csv")
        )
        return flexible_import.normalize_analysis(analysis, analysis.mapping)
    return _read_uploaded_json(uploaded_file)


def _mapping_editor(st: Any, analysis: flexible_import.ImportAnalysis) -> dict[str, Any]:
    st.caption(
        f"Detected {analysis.file_type} with {len(analysis.rows):,} rows. "
        + ("A few fields need your confirmation." if analysis.needs_review else "All required fields were recognized automatically.")
    )
    options = [None, *analysis.headers]
    mapping = dict(analysis.mapping)
    with st.expander("Advanced: review detected fields", expanded=analysis.needs_review):
        if hasattr(st, "dataframe"):
            st.dataframe(flexible_import.preview_rows(analysis), use_container_width=True)
        essentials = ("transaction_date", "description", "amount", "direction")
        controls = st.columns(2)
        for index, field in enumerate(essentials):
            label = flexible_import.FIELD_LABELS[field]
            detected = analysis.mapping.get(field)
            index = options.index(detected) if detected in options else 0
            mapping[field] = controls[list(essentials).index(field) % 2].selectbox(
                f"{label} (confidence {analysis.confidence.get(field, 0)}%)",
                options,
                index=index,
                format_func=lambda value: "— Not mapped —" if value is None else value,
                key=f"ingestion_mapping_{field}",
            )
        st.caption("Use the next two fields only when the file has separate money-out and money-in columns. Otherwise leave them blank.")
        amount_columns = st.columns(2)
        for index, field in enumerate(("debit", "credit")):
            detected = analysis.mapping.get(field)
            mapping[field] = amount_columns[index].selectbox(
                flexible_import.FIELD_LABELS[field], options,
                index=options.index(detected) if detected in options else 0,
                format_func=lambda value: "— Not mapped —" if value is None else value,
                key=f"ingestion_mapping_{field}",
            )
        if st.checkbox("Adjust optional columns", value=False):
            optional_columns = st.columns(2)
            optional = ("category", "payment_method", "source_transaction_id", "counterparty", "balance")
            for index, field in enumerate(optional):
                detected = analysis.mapping.get(field)
                mapping[field] = optional_columns[index % 2].selectbox(
                    flexible_import.FIELD_LABELS[field], options,
                    index=options.index(detected) if detected in options else 0,
                    format_func=lambda value: "— Not mapped —" if value is None else value,
                    key=f"ingestion_mapping_{field}",
                )
    return mapping


def _payload_summary(payloads: list[dict[str, Any]]) -> dict[str, int]:
    records = [record for payload in payloads for record in payload.get("records", [])]
    income = sum(record["amount_minor"] for record in records if record["direction"] == "income")
    expenses = sum(record["amount_minor"] for record in records if record["direction"] == "expense")
    return {"rows": len(records), "income": income, "expenses": expenses}


def _money(minor: int) -> str:
    return f"₹{minor / 100:,.2f}"


def _render_result(st: Any, result: Any) -> bool:
    if not isinstance(result, ingestion_service.IngestionWriteResult):
        st.error(_safe_error_message("STORAGE_FAILED"))
        return False
    if result.status == "completed":
        st.success("Ingestion completed successfully.")
        _display_counts(st, result)
        return True
    if result.status == "failed":
        st.error(_safe_error_message(result.error_code))
        _display_counts(st, result)
        return False
    st.error(_safe_error_message("STORAGE_FAILED"))
    return False


def _canonical_batches(payload: Any) -> list[dict[str, Any]]:
    """Split canonical JSON without changing its envelope or record order."""
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        return [payload]
    records = payload["records"]
    size = 1000
    if len(records) <= size:
        return [payload]
    return [
        {**payload, "records": records[start : start + size]}
        for start in range(0, len(records), size)
    ]


def _json_batches(uploaded_file: Any) -> list[dict[str, Any]]:
    """Read a canonical JSON transaction file and reject unusable envelopes early."""
    payload = _read_uploaded_json(uploaded_file)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise flexible_import.FlexibleImportError(
            "JSON must contain a top-level 'records' list of transactions."
        )
    if not payload["records"]:
        raise flexible_import.FlexibleImportError("The JSON file contains no transaction records.")
    if len(payload["records"]) > 10000:
        raise flexible_import.FlexibleImportError("Import up to 10,000 JSON records at a time.")
    return _canonical_batches(payload)


def _ingest_batches(
    st: Any,
    *,
    session_token: str,
    business_id: str,
    account_id: str,
    payloads: list[dict[str, Any]],
) -> ingestion_service.IngestionWriteResult:
    totals = {"record_count": 0, "inserted_count": 0, "duplicate_count": 0, "rejected_count": 0, "retry_count": 0}
    progress = st.progress(0, text="Validating and importing transactions…") if len(payloads) > 1 and hasattr(st, "progress") else None
    for index, payload in enumerate(payloads, start=1):
        result = ingestion_service.ingest(
            session_token=session_token,
            business_id=business_id,
            account_id=account_id,
            payload=payload,
            record_failure=True,
        )
        if result.status != "completed":
            return result
        for name in totals:
            totals[name] += getattr(result, name)
        if progress is not None:
            progress.progress(index / len(payloads), text=f"Imported batch {index} of {len(payloads)}")
    return ingestion_service.IngestionWriteResult(status="completed", attempt_id=None, **totals)


def render_ingestion_page(st: Any, session_token: Any) -> bool:
    """Render and submit the authenticated canonical JSON ingestion surface."""
    auth = auth_service.validate_session(session_token)
    if not isinstance(auth, dict) or auth.get("success") is not True:
        st.warning("Sign in to access transaction ingestion.")
        return False

    businesses_result = business_service.list_user_businesses(session_token)
    businesses = _authorized_businesses(businesses_result)
    if not businesses:
        st.error("No authorized business is available for ingestion.")
        return False

    st.header("Import transactions")
    st.caption("Upload a file and FinSight will identify the columns and check the totals before saving anything.")
    st.info(
        "Transaction imports support CSV, JSON, and XML. PDF statements are not "
        "transaction data files, so they cannot be imported here yet. Files up to "
        "5 MB are supported; larger imports are processed in safe 1,000-row batches."
    )
    business_labels = [business["business_name"] for business in businesses]
    selected_business_label = st.selectbox("Business", business_labels)
    try:
        business_index = business_labels.index(selected_business_label)
    except ValueError:
        st.error("The selected business is unavailable.")
        return False
    selected_business = businesses[business_index]

    readiness = bridge_service.bridge_status(
        session_token, selected_business["business_id"]
    )
    if readiness.get("status") != "active":
        status = readiness.get("status")
        if status == "pending":
            st.info("Open Setup and select Finish setup.")
        else:
            st.warning("This business is not ready yet. Open Setup and select Finish setup.")
        return False

    accounts_result = account_service.list_business_accounts(
        session_token, selected_business["business_id"]
    )
    if not isinstance(accounts_result, dict) or accounts_result.get("success") is not True:
        st.error("No active financial account is available for ingestion.")
        return False
    accounts = [
        account
        for account in accounts_result.get("accounts", [])
        if isinstance(account, dict)
        and type(account.get("account_id")) is str
        and account.get("account_status") == "active"
        and type(account.get("account_name")) is str
        and type(account.get("currency")) is str
    ]
    if not accounts:
        st.error("No active financial account is available for ingestion.")
        return False

    account_labels = [
        f"{account['account_name']} ({account['currency']})"
        for account in accounts
    ]
    selected_account_label = st.selectbox("Data source", account_labels)
    try:
        account_index = account_labels.index(selected_account_label)
    except ValueError:
        st.error("The selected financial account is unavailable.")
        return False
    selected_account = accounts[account_index]

    uploaded_file = st.file_uploader(
        "Choose a transaction file (CSV, JSON, or XML)",
        type=["json", "csv", "xml"],
        accept_multiple_files=False,
    )
    if uploaded_file is None:
        return False

    try:
        if _is_tabular_upload(uploaded_file):
            analysis = flexible_import.analyze_upload(
                uploaded_file.getvalue(), getattr(uploaded_file, "name", "upload.csv")
            )
            mapping = _mapping_editor(st, analysis) if hasattr(st, "expander") else analysis.mapping
            payloads = flexible_import.normalize_analysis_batches(analysis, mapping)
            summary = _payload_summary(payloads)
            columns = st.columns(3) if hasattr(st, "columns") else [st, st, st]
            columns[0].metric("Transactions found", f"{summary['rows']:,}")
            columns[1].metric("Money received", _money(summary["income"]))
            columns[2].metric("Money spent", _money(summary["expenses"]))
            st.caption("Nothing is saved until you confirm the import.")
            if not st.button("Ingest transactions", type="primary"):
                return False
        else:
            payloads = _json_batches(uploaded_file)
            summary = _payload_summary(payloads)
            columns = st.columns(3) if hasattr(st, "columns") else [st, st, st]
            columns[0].metric("Transactions found", f"{summary['rows']:,}")
            columns[1].metric("Money received", _money(summary["income"]))
            columns[2].metric("Money spent", _money(summary["expenses"]))
            st.caption("Nothing is saved until you confirm the import.")
            if not st.button("Ingest transactions", type="primary"):
                return False
    except flexible_import.FlexibleImportError as error:
        st.error(str(error))
        return False
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
        st.error("The uploaded file could not be read.")
        return False

    try:
        result = _ingest_batches(
            st,
            session_token=session_token,
            business_id=selected_business["business_id"],
            account_id=selected_account["account_id"],
            payloads=payloads,
        )
    except ingestion_service.IngestionServiceError as error:
        st.error(_safe_error_message(error.code))
        return False
    except Exception:
        st.error(_safe_error_message("STORAGE_FAILED"))
        return False

    return _render_result(st, result)


__all__ = ["AUTHORIZED_MEMBERSHIP_ROLES", "render_ingestion_page"]
