"""Small Streamlit setup surface for the verified examination flow."""

from typing import Any

from services import account_service, auth_service, bridge_service, business_service


def _label(name: str, identifier: str) -> str:
    return f"{name} · {identifier[-8:]}"


def render_setup_page(st: Any, token: str) -> bool:
    session = auth_service.validate_session(token)
    if not session.get("success"):
        st.warning("Sign in to configure FinSight.")
        return False
    st.header("Business and account setup")

    businesses_result = business_service.list_user_businesses(token)
    businesses = businesses_result.get("businesses", []) if businesses_result.get("success") else []

    with st.expander("Create business", expanded=not businesses):
        name = st.text_input("Business name", key="setup_business_name")
        if st.button("Create business", key="setup_create_business"):
            result = business_service.create_business(token, {"business_name": name})
            if result.get("success"):
                st.success("Business created.")
                st.rerun()
            st.error(result.get("message", "Business creation failed."))

    if not businesses:
        st.info("Create a business before adding a financial account.")
        return False

    business_labels = [
        _label(item["business_name"], item["business_id"]) for item in businesses
    ]
    selected_label = st.selectbox("Setup business", business_labels, key="setup_business")
    business = businesses[business_labels.index(selected_label)]

    bridge = bridge_service.get_bridge_status(token, business["business_id"])
    bridge_row = bridge.get("bridge") if bridge.get("success") else None
    if bridge_row is None or bridge_row["bridge_status"] != "active":
        st.warning("The internal business mapping is unavailable. Existing restrictions may require maintenance.")

    accounts_result = account_service.list_business_accounts(token, business["business_id"])
    accounts = accounts_result.get("accounts", []) if accounts_result.get("success") else []
    if accounts:
        st.caption("Active accounts: " + ", ".join(account["account_name"] for account in accounts))
    with st.expander("Create financial account", expanded=not accounts):
        account_name = st.text_input("Account name", key="setup_account_name")
        account_type = st.selectbox(
            "Account type",
            ["bank", "cash", "credit_card", "loan", "other"],
            key="setup_account_type",
        )
        currency = st.text_input("Currency", value="INR", key="setup_currency")
        opening_balance = st.text_input(
            "Opening balance", value="0.00", key="setup_opening_balance"
        )
        if st.button("Create account", key="setup_create_account"):
            result = account_service.create_account(
                token,
                business["business_id"],
                {
                    "account_name": account_name,
                    "account_type": account_type,
                    "currency": currency,
                    "opening_balance": opening_balance,
                },
            )
            if result.get("success"):
                st.success("Financial account created.")
                st.rerun()
            st.error(result.get("message", "Financial account creation failed."))
    return True


__all__ = ["render_setup_page"]
