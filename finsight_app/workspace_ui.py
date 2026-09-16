"""Plain-language business onboarding for the Streamlit application."""

from typing import Any

from services import account_service, bridge_service, business_service


def _businesses(token: str) -> list[dict[str, Any]]:
    result = business_service.list_user_businesses(token)
    return result.get("businesses", []) if result.get("success") else []


def _source_label(account: dict[str, Any]) -> str:
    kind = str(account.get("account_type") or "other").replace("_", " ").title()
    institution = account.get("institution_name")
    prefix = f"{institution} - " if institution else ""
    return f"{prefix}{account['account_name']} ({kind}, {account['currency']})"


def render_workspace_setup(st: Any, session_token: str) -> None:
    st.title("Set up your business")
    st.caption("Add your business once, then upload sales, expense, or bank data.")
    businesses = _businesses(session_token)

    if not businesses:
        st.subheader("1. Business details")
        with st.form("first_business_form"):
            name = st.text_input("Business name", placeholder="Example: Sunrise Medical Clinic")
            with st.expander("Optional business details"):
                legal_identifier = st.text_input("GSTIN, Udyam number, or other registration")
                contact_email = st.text_input("Business email")
                contact_phone = st.text_input("Business phone")
            submitted = st.form_submit_button("Create business and continue", type="primary")
        if submitted:
            result = business_service.create_business(
                session_token,
                {
                    "business_name": name,
                    "legal_identifier": legal_identifier,
                    "contact_email": contact_email,
                    "contact_phone": contact_phone,
                },
            )
            if not result.get("success"):
                st.error(result.get("message", "The business could not be created."))
                return
            account = account_service.create_account(
                session_token,
                result["business"]["business_id"],
                {
                    "account_name": "Primary data source",
                    "account_type": "other",
                    "currency": "INR",
                    "opening_balance": "0.00",
                },
            )
            if account.get("success"):
                st.success("Your workspace is ready. Open Import to add transactions.")
                st.rerun()
            st.warning("The business was created, but its first data source could not be added.")
        return

    labels = [business["business_name"] for business in businesses]
    selected = businesses[labels.index(st.selectbox("Business", labels))]
    readiness = bridge_service.bridge_status(session_token, selected["business_id"])
    if readiness.get("status") != "active":
        if st.button("Finish setup", type="primary"):
            result = bridge_service.activate_imports(session_token, selected["business_id"])
            if result.get("success"):
                st.rerun()
            st.error(result.get("message", "Setup could not be completed."))
    else:
        st.success("Ready to import transactions")

    accounts_result = account_service.list_business_accounts(session_token, selected["business_id"])
    accounts = accounts_result.get("accounts", []) if accounts_result.get("success") else []
    st.subheader("Data sources")
    st.caption("A data source keeps bank, cash, card, or bookkeeping files separate. Most users need only one.")
    for account in accounts:
        st.write(f"• {_source_label(account)}")
    if not accounts:
        st.info("Add one data source before importing transactions.")

    with st.expander("Add another data source", expanded=not accounts):
        with st.form("create_account_form"):
            account_name = st.text_input("Name", placeholder="Example: Main bank account")
            account_type = st.selectbox(
                "Type",
                ["bank", "cash", "credit_card", "loan", "other"],
                format_func=lambda value: value.replace("_", " ").title(),
            )
            currency = st.selectbox("Currency", ["INR"])
            with st.expander("Advanced options"):
                institution = st.text_input("Bank or institution")
                identifier = st.text_input("Last four digits or reference", help="Never enter a PIN, CVV, password, or complete banking credential.")
                opening = st.text_input("Opening balance", value="0.00")
            submitted = st.form_submit_button("Add data source", type="primary")
        if submitted:
            result = account_service.create_account(
                session_token,
                selected["business_id"],
                {
                    "account_name": account_name,
                    "account_type": account_type,
                    "institution_name": institution,
                    "account_identifier": identifier,
                    "currency": currency,
                    "opening_balance": opening,
                },
            )
            if result.get("success"):
                st.success("Data source added.")
                st.rerun()
            st.error(result.get("message", "The data source could not be added."))

    with st.expander("Add another business"):
        st.caption("Use this only when you manage a separate legal business.")
        with st.form("additional_business_form"):
            name = st.text_input("New business name")
            submitted = st.form_submit_button("Add business")
        if submitted:
            result = business_service.create_business(session_token, {"business_name": name})
            if result.get("success"):
                st.rerun()
            st.error(result.get("message", "The business could not be created."))


__all__ = ["render_workspace_setup"]
