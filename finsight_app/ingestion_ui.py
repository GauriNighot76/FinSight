"""Streamlit transaction-import adapter.

The authenticated application uses a guided CSV workflow while the backend
remains the sole authority for authorization, validation, duplicate identity
classification and persistence.  A small legacy adapter is retained for the
existing backend/UI regression tests and canonical JSON development surface.
"""

import json
from typing import Any, Optional

import pandas as pd

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
    "ACCOUNT_NOT_AUTHORIZED": "The internal business account is unavailable.",
    "BRIDGE_NOT_VERIFIED": "The business could not be prepared for transaction ingestion.",
    "REGISTRY_BUSINESS_NOT_FOUND": "The business could not be prepared for transaction ingestion.",
    "REGISTRY_OWNER_NOT_FOUND": "The business could not be prepared for transaction ingestion.",
    "VALIDATION_FAILED": "The ingestion payload is invalid.",
    "IDENTITY_CONFLICT": "The ingestion contains a conflicting transaction identity.",
    "STORAGE_FAILED": "The ingestion could not be completed.",
}

_FIELD_LABELS = {
    "ignore": "Ignore this column",
    "transaction_date": "Date",
    "description": "Description",
    "amount": "Amount",
    "direction": "Direction",
    "category": "Category",
    "payment_method": "Payment Mode",
    "source_transaction_id": "Transaction / Reference ID",
    "debit": "Debit Amount",
    "credit": "Credit Amount",
}
_LABEL_TO_FIELD = {label: key for key, label in _FIELD_LABELS.items()}


def _safe_error_message(code: Any) -> str:
    return _SAFE_ERROR_MESSAGES.get(code, "The transactions could not be processed.")


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


def _is_csv_upload(uploaded_file: Any) -> bool:
    name = getattr(uploaded_file, "name", None)
    if type(name) is str:
        if name.lower().endswith(".csv"):
            return True
        if name.lower().endswith(".json"):
            return False
    content_type = getattr(uploaded_file, "type", None)
    if type(content_type) is str:
        if content_type.lower() == "text/csv":
            return True
        if content_type.lower() == "application/json":
            return False
    try:
        raw = uploaded_file.getvalue()
    except Exception:
        return False
    if isinstance(raw, bytes):
        raw = raw.lstrip().decode("utf-8-sig", errors="ignore")
    return type(raw) is str and not raw.lstrip().startswith(("{", "["))


def _read_uploaded_payload(uploaded_file: Any) -> Any:
    if _is_csv_upload(uploaded_file):
        return csv_normalizer.normalize_csv(uploaded_file.getvalue())
    return _read_uploaded_json(uploaded_file)


def _render_result(st: Any, result: Any) -> bool:
    if not isinstance(result, ingestion_service.IngestionWriteResult):
        st.error(_safe_error_message("STORAGE_FAILED"))
        return False
    if result.status == "completed":
        st.success("Upload complete.")
        _display_counts(st, result)
        return True
    if result.status == "failed":
        st.error(_safe_error_message(result.error_code))
        _display_counts(st, result)
        return False
    st.error(_safe_error_message("STORAGE_FAILED"))
    return False


def _legacy_ingestion_page(
    st: Any,
    session_token: Any,
    businesses: list[dict[str, Any]],
) -> bool:
    """Keep the established canonical JSON/CSV adapter for regression tests."""
    st.header("Transaction ingestion")
    business_labels = [business["business_name"] for business in businesses]
    selected_business_label = st.selectbox("Business", business_labels)
    selected_business = businesses[business_labels.index(selected_business_label)]

    accounts_result = account_service.list_business_accounts(
        session_token, selected_business["business_id"]
    )
    accounts = [
        account
        for account in accounts_result.get("accounts", [])
        if isinstance(account, dict)
        and type(account.get("account_id")) is str
        and account.get("account_status") == "active"
    ] if isinstance(accounts_result, dict) and accounts_result.get("success") else []
    if not accounts:
        st.error("No active financial account is available for ingestion.")
        return False

    account_labels = [
        f"{account['account_name']} ({account['currency']})" for account in accounts
    ]
    selected_account_label = st.selectbox("Account", account_labels)
    selected_account = accounts[account_labels.index(selected_account_label)]

    uploaded_file = st.file_uploader(
        "Upload canonical JSON or CSV payload",
        type=["json", "csv"],
        accept_multiple_files=False,
    )
    if uploaded_file is None or not st.button("Ingest transactions"):
        return False
    try:
        payload = _read_uploaded_payload(uploaded_file)
    except csv_normalizer.CSVNormalizationError:
        st.error("The uploaded CSV could not be normalized.")
        return False
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
        st.error(
            "The uploaded CSV could not be normalized."
            if _is_csv_upload(uploaded_file)
            else "The uploaded canonical JSON could not be read."
        )
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


def _wizard_keys(business_id: str) -> dict[str, str]:
    prefix = f"upload_{business_id}_"
    return {
        "step": prefix + "step",
        "bytes": prefix + "bytes",
        "name": prefix + "name",
        "inspection": prefix + "inspection",
        "mapping": prefix + "mapping",
        "preview": prefix + "preview",
        "validation": prefix + "validation",
        "result": prefix + "result",
    }


def _reset_wizard(st: Any, keys: dict[str, str]) -> None:
    for key in keys.values():
        st.session_state.pop(key, None)


def _back_next(st: Any, *, back_label: str = "Back", next_label: str = "Next"):
    left, right = st.columns(2)
    return left.button(back_label), right.button(next_label, type="primary")


def _render_csv_wizard(
    st: Any,
    session_token: str,
    business: dict[str, Any],
) -> bool:
    business_id = business["business_id"]
    ready = business_service.ensure_business_ready(session_token, business_id)
    if not isinstance(ready, dict) or ready.get("success") is not True:
        st.error(
            ready.get(
                "message",
                "The business could not be prepared for transaction ingestion.",
            ) if isinstance(ready, dict) else
            "The business could not be prepared for transaction ingestion."
        )
        return False

    account_id = ready["account_id"]
    accounts_result = account_service.list_business_accounts(session_token, business_id)
    accounts = accounts_result.get("accounts", []) if isinstance(accounts_result, dict) else []
    account = next(
        (item for item in accounts if item.get("account_id") == account_id),
        None,
    )
    if account is None:
        st.error("The internal business account is unavailable.")
        return False

    keys = _wizard_keys(business_id)
    step = int(st.session_state.get(keys["step"], 1))
    st.header("Upload Transactions")
    st.caption(
        f"Import transaction data for {business['business_name']}. "
        "FinSight validates the file before anything is saved."
    )
    st.progress(min(max(step, 1), 5) / 5)
    st.caption(f"Step {step} of 5")

    if step == 1:
        st.subheader("1. Choose CSV file")
        uploaded_file = st.file_uploader(
            "Upload your transaction data",
            type=["csv"],
            accept_multiple_files=False,
            key=f"{business_id}_csv_upload",
        )
        if uploaded_file is None:
            st.info(
                "Choose a CSV exported from your accounting, banking, POS, "
                "billing or spreadsheet system."
            )
            return False
        try:
            raw = uploaded_file.getvalue()
            inspection = csv_normalizer.inspect_csv(raw)
            suggestion = csv_normalizer.suggest_column_mapping(raw)
        except csv_normalizer.CSVNormalizationError as error:
            st.error(str(error))
            return False
        st.caption(f"Rows detected: {inspection['row_count']}")
        if hasattr(st, "dataframe"):
            st.dataframe(
                inspection["rows"][:8],
                hide_index=True,
                use_container_width=True,
            )
        if st.button("Next: Map Columns", type="primary"):
            st.session_state[keys["bytes"]] = raw
            st.session_state[keys["name"]] = getattr(uploaded_file, "name", "transactions.csv")
            st.session_state[keys["inspection"]] = inspection
            st.session_state[keys["mapping"]] = suggestion
            st.session_state[keys["step"]] = 2
            st.rerun()
        return False

    raw = st.session_state.get(keys["bytes"])
    inspection = st.session_state.get(keys["inspection"])
    if not isinstance(raw, (bytes, str)) or not isinstance(inspection, dict):
        _reset_wizard(st, keys)
        st.warning("Please choose the CSV again.")
        st.rerun()

    if step == 2:
        st.subheader("2. Map Columns")
        st.write(
            "Review FinSight's suggestions. Required transaction fields must "
            "be mapped before continuing."
        )
        suggestion = st.session_state.get(keys["mapping"], {})
        chosen_mapping: dict[str, str] = {}
        options = list(_FIELD_LABELS.values())
        for header in inspection["headers"]:
            suggested_field = suggestion.get(header, "ignore")
            suggested_label = _FIELD_LABELS.get(suggested_field, _FIELD_LABELS["ignore"])
            index = options.index(suggested_label)
            selected_label = st.selectbox(
                f"{header} →",
                options,
                index=index,
                key=f"{business_id}_map_{header}",
            )
            chosen_mapping[header] = _LABEL_TO_FIELD[selected_label]

        selected_fields = [
            value for value in chosen_mapping.values()
            if value != csv_normalizer.MAPPING_IGNORE
        ]
        duplicate_fields = len(selected_fields) != len(set(selected_fields))
        if duplicate_fields:
            st.warning("Each FinSight field can be mapped from only one CSV column.")

        back, next_clicked = _back_next(st, next_label="Next: Preview")
        if back:
            st.session_state[keys["step"]] = 1
            st.rerun()
        if next_clicked:
            if duplicate_fields:
                return False
            try:
                preview = csv_normalizer.preview_csv_with_mapping(raw, chosen_mapping)
            except csv_normalizer.CSVNormalizationError as error:
                st.error(
                    f"Column mapping is not ready: {error} "
                    "Map a Date column and Amount (or Debit/Credit). "
                    "Direction can come from a mapped direction column, debit/credit columns, "
                    "or a signed amount file."
                )
                return False
            st.session_state[keys["mapping"]] = chosen_mapping
            st.session_state[keys["preview"]] = preview
            st.session_state[keys["validation"]] = None
            st.session_state[keys["step"]] = 3
            st.rerun()
        return False

    if step == 3:
        st.subheader("3. Preview and Edit")
        st.caption(
            "Correct transaction values before validation. Editing here changes "
            "only this pending import."
        )
        preview = st.session_state.get(keys["preview"], [])
        frame = pd.DataFrame(preview)
        edited = st.data_editor(
            frame,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key=f"{business_id}_transaction_editor",
        )
        back, validate_clicked = _back_next(st, next_label="Validate Transactions")
        if back:
            st.session_state[keys["step"]] = 2
            st.rerun()
        if validate_clicked:
            edited_rows = edited.to_dict(orient="records")
            validation = csv_normalizer.validate_preview_rows(edited_rows)
            st.session_state[keys["preview"]] = edited_rows
            st.session_state[keys["validation"]] = validation
            st.session_state[keys["step"]] = 4
            st.rerun()
        return False

    if step == 4:
        st.subheader("4. Validation Result")
        validation = st.session_state.get(keys["validation"])
        if not isinstance(validation, dict):
            st.warning("Validate the preview before importing.")
            st.session_state[keys["step"]] = 3
            st.rerun()
        total_rows = inspection.get("row_count", 0)
        valid_count = int(validation.get("valid_count", 0))
        invalid_count = int(validation.get("invalid_count", 0))
        a, b, c = st.columns(3)
        a.metric("Rows detected", total_rows)
        b.metric("Rows valid", valid_count)
        c.metric("Rows invalid", invalid_count)

        errors = validation.get("errors", [])
        if errors:
            st.error("Fix invalid rows before importing.")
            for item in errors[:20]:
                st.write(f"Row {item.get('row', '—')} — {item.get('message', 'Invalid row')}")
            if st.button("Back to Preview"):
                st.session_state[keys["step"]] = 3
                st.rerun()
            return False

        payload = validation.get("payload")
        try:
            prepared = ingestion_service.prepare_ingestion(
                session_token=session_token,
                business_id=business_id,
                account_id=account_id,
                payload=payload,
            )
        except ingestion_service.IngestionServiceError as error:
            st.error(_safe_error_message(error.code))
            return False
        duplicate_count = sum(
            1 for item in prepared.records if item.status.startswith("DUPLICATE")
        )
        new_count = sum(1 for item in prepared.records if item.status == "UNIQUE")
        st.metric("New transactions", new_count)
        st.metric("Duplicates that will be ignored", duplicate_count)
        st.success("Validation passed. No transaction has been saved yet.")

        back, confirm = _back_next(st, next_label="Confirm Import")
        if back:
            st.session_state[keys["step"]] = 3
            st.rerun()
        if confirm:
            try:
                result = ingestion_service.ingest(
                    session_token=session_token,
                    business_id=business_id,
                    account_id=account_id,
                    payload=payload,
                    record_failure=True,
                )
            except ingestion_service.IngestionServiceError as error:
                st.error(_safe_error_message(error.code))
                return False
            except Exception:
                st.error(_safe_error_message("STORAGE_FAILED"))
                return False
            st.session_state[keys["result"]] = result
            st.session_state[keys["step"]] = 5
            st.rerun()
        return False

    st.subheader("5. Import Complete")
    result = st.session_state.get(keys["result"])
    if not isinstance(result, ingestion_service.IngestionWriteResult):
        st.warning("Import result is unavailable. Start a new upload.")
        if st.button("Start New Upload"):
            _reset_wizard(st, keys)
            st.rerun()
        return False
    _render_result(st, result)
    left, middle, right = st.columns(3)
    if left.button("Go to Overview"):
        st.session_state["pending_page"] = "Overview"
        _reset_wizard(st, keys)
        st.rerun()
    if middle.button("View Analytics"):
        st.session_state["pending_page"] = "Financial Analytics"
        _reset_wizard(st, keys)
        st.rerun()
    if right.button("Upload Another File"):
        _reset_wizard(st, keys)
        st.rerun()
    return True


def render_ingestion_page(
    st: Any,
    session_token: Any,
    preferred_business_id: Any = None,
) -> bool:
    """Render the transaction import surface for an authenticated business."""
    auth = auth_service.validate_session(session_token)
    if not isinstance(auth, dict) or auth.get("success") is not True:
        st.warning("Sign in to access transaction ingestion.")
        return False

    businesses = _authorized_businesses(
        business_service.list_user_businesses(session_token)
    )
    if not businesses:
        st.error("No authorized business is available for ingestion.")
        return False

    # The app always supplies the selected business id.  Keeping the original
    # selector when no id is supplied preserves the tested development adapter.
    if preferred_business_id is None:
        return _legacy_ingestion_page(st, session_token, businesses)

    business = next(
        (item for item in businesses if item["business_id"] == preferred_business_id),
        None,
    )
    if business is None:
        st.error("The selected business is unavailable.")
        return False
    return _render_csv_wizard(st, session_token, business)


__all__ = ["AUTHORIZED_MEMBERSHIP_ROLES", "render_ingestion_page"]
