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
    business_service,
    csv_normalizer,
    ingestion_service,
)


AUTHORIZED_MEMBERSHIP_ROLES = frozenset({"owner", "manager"})

_SAFE_ERROR_MESSAGES = {
    "AUTHENTICATION_FAILED": "Authentication is required for ingestion.",
    "BUSINESS_NOT_FOUND": "The selected business is unavailable.",
    "MEMBERSHIP_REQUIRED": "An active business membership is required.",
    "INGESTION_FORBIDDEN": "The current business role cannot ingest data.",
    "ACCOUNT_NOT_AUTHORIZED": "The selected financial account is unavailable.",
    "BRIDGE_NOT_VERIFIED": (
        "This business is awaiting registry verification. Use the seeded demo "
        "business or ask an administrator to approve the relationship."
    ),
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


def _selection_labels(items: list[dict[str, Any]], name_key: str, id_key: str) -> list[str]:
    names = [item[name_key] for item in items]
    return [
        f"{name} · {item[id_key][-8:]}" if names.count(name) > 1 else name
        for item, name in zip(items, names)
    ]


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


def _is_csv_upload(uploaded_file: Any) -> bool:
    name = getattr(uploaded_file, "name", None)
    if type(name) is str:
        lowered_name = name.lower()
        if lowered_name.endswith(".csv"):
            return True
        if lowered_name.endswith(".json"):
            return False
    content_type = getattr(uploaded_file, "type", None)
    if type(content_type) is str:
        lowered_type = content_type.lower()
        if lowered_type == "text/csv":
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
    if _is_csv_upload(uploaded_file):
        return csv_normalizer.normalize_csv(uploaded_file.getvalue())
    return _read_uploaded_json(uploaded_file)


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

    st.header("Transaction ingestion")
    business_labels = _selection_labels(businesses, "business_name", "business_id")
    selected_business_label = st.selectbox(
        "Business", business_labels, key="ingestion_business"
    )
    try:
        business_index = business_labels.index(selected_business_label)
    except ValueError:
        st.error("The selected business is unavailable.")
        return False
    selected_business = businesses[business_index]

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

    accounts_for_labels = [
        {**account, "display_name": f"{account['account_name']} ({account['currency']})"}
        for account in accounts
    ]
    account_labels = _selection_labels(accounts_for_labels, "display_name", "account_id")
    selected_account_label = st.selectbox(
        "Account", account_labels, key="ingestion_account"
    )
    try:
        account_index = account_labels.index(selected_account_label)
    except ValueError:
        st.error("The selected financial account is unavailable.")
        return False
    selected_account = accounts[account_index]

    uploaded_file = st.file_uploader(
        "Upload canonical JSON or CSV payload",
        type=["json", "csv"],
        accept_multiple_files=False,
        key="ingestion_file",
    )
    if uploaded_file is None or not st.button(
        "Ingest transactions", key="ingestion_submit"
    ):
        return False

    try:
        payload = _read_uploaded_payload(uploaded_file)
    except csv_normalizer.CSVNormalizationError as error:
        st.error(str(error))
        return False
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
        if _is_csv_upload(uploaded_file):
            st.error("The uploaded CSV could not be normalized.")
        else:
            st.error("The uploaded canonical JSON could not be read.")
        return False

    try:
        result = ingestion_service.ingest(
            session_token=session_token,
            business_id=selected_business["business_id"],
            account_id=selected_account["account_id"],
            payload=payload,
            record_failure=True,
        )
    except ingestion_service.IngestionServiceError as error:
        st.error(_safe_error_message(error.code))
        return False
    except Exception:
        st.error(_safe_error_message("STORAGE_FAILED"))
        return False

    return _render_result(st, result)


__all__ = ["AUTHORIZED_MEMBERSHIP_ROLES", "render_ingestion_page"]
