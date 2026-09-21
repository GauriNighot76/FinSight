"""Thin Streamlit adapter for the read-only Module 5 analytics service."""

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from services import account_service, analytics_service, auth_service, business_service


AUTHORIZED_MEMBERSHIP_ROLES = frozenset({"owner", "manager"})


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


def _active_accounts(result: Any) -> list[dict[str, Any]]:
    if not isinstance(result, dict) or result.get("success") is not True:
        return []
    accounts = result.get("accounts")
    if type(accounts) is not list:
        return []
    return [
        account
        for account in accounts
        if isinstance(account, dict)
        and type(account.get("account_id")) is str
        and type(account.get("account_name")) is str
        and type(account.get("currency")) is str
        and account.get("account_status") == "active"
    ]


def _date_value(value: Any) -> Optional[str]:
    if isinstance(value, date):
        return value.isoformat()
    if type(value) is str:
        return value
    return None


def _safe_error_message(error: Any) -> str:
    message = str(error)
    if "date range" in message:
        return "Choose a valid date range."
    if "currency" in message:
        return "The selected currency is inconsistent."
    if "financial account" in message:
        return "The selected financial account is unavailable."
    if "Authentication" in message:
        return "Sign in to view financial analytics."
    if "business" in message:
        return "You do not have access to the selected business."
    return "Analytics could not be loaded."


def _format_minor(value: Any, currency: str) -> str:
    if value is None:
        return "—"
    try:
        formatted = Decimal(value) / Decimal(100)
        return f"{currency} {formatted:,.2f}"
    except (ArithmeticError, TypeError, ValueError):
        return "—"


def _format_value(label: str, value: Any, currency: str) -> str:
    if label in {
        "Total Income",
        "Total Expense",
        "Net Cash Flow",
        "Average Transaction",
        "Largest Income",
        "Largest Expense",
        "Opening Balance",
        "Closing Balance",
    }:
        return _format_minor(value, currency)
    if value is None:
        return "—"
    return str(value)


def _safe_table_rows(rows: Any) -> list[dict[str, Any]]:
    if type(rows) is not list:
        return []
    safe_rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        safe_rows.append(
            {
                key: value
                for key, value in row.items()
                if key not in {"business_id", "account_id", "user_id"}
                and not key.endswith("_id")
            }
        )
    return safe_rows


def _render_kpis(st: Any, result: dict[str, Any], currency: str) -> None:
    kpis = result.get("kpis") if isinstance(result.get("kpis"), dict) else {}
    fields = (
        ("Total Income", "total_income_minor"),
        ("Total Expense", "total_expense_minor"),
        ("Net Cash Flow", "net_cash_flow_minor"),
        ("Transaction Count", "transaction_count"),
        ("Average Transaction", "average_transaction_minor"),
        ("Largest Income", "largest_income_minor"),
        ("Largest Expense", "largest_expense_minor"),
        ("Opening Balance", "opening_balance_minor"),
        ("Closing Balance", "closing_balance_minor"),
        ("Savings Rate", "savings_rate"),
        ("Income/Expense Ratio", "income_expense_ratio"),
    )
    for label, key in fields:
        st.metric(label, _format_value(label, kpis.get(key), currency))


def _render_analytics(st: Any, result: dict[str, Any], currency: str) -> None:
    _render_kpis(st, result, currency)
    kpis = result.get("kpis") if isinstance(result.get("kpis"), dict) else {}
    if kpis.get("transaction_count", 0) == 0:
        st.info("No transactions found for the selected period.")

    trends = result.get("trends") if isinstance(result.get("trends"), dict) else {}
    if kpis.get("transaction_count", 0) > 0:
        st.subheader("Daily trend")
        st.line_chart(trends.get("daily", []))
        st.subheader("Weekly trend")
        st.line_chart(trends.get("weekly", []))
        st.subheader("Monthly trend")
        st.line_chart(trends.get("monthly", []))

    st.subheader("Category summary")
    st.dataframe(_safe_table_rows(result.get("categories", [])), hide_index=True)
    st.subheader("Payment mode summary")
    st.dataframe(_safe_table_rows(result.get("payment_modes", [])), hide_index=True)
    st.subheader("Account summary")
    st.dataframe(_safe_table_rows(result.get("accounts", [])), hide_index=True)


def render_analytics_page(st: Any, session_token: Any, preferred_business_id: Any = None) -> bool:
    """Render analytics for an authenticated owner or manager."""
    try:
        auth = auth_service.validate_session(session_token)
    except Exception:
        st.error("Analytics could not be loaded.")
        return False
    if not isinstance(auth, dict) or auth.get("success") is not True:
        st.warning("Sign in to view financial analytics.")
        return False

    try:
        businesses = _authorized_businesses(
            business_service.list_user_businesses(session_token)
        )
    except Exception:
        st.error("Analytics could not be loaded.")
        return False
    if not businesses:
        st.error("No authorized business is available for analytics.")
        return False

    st.header("Financial analytics")
    business_labels = [business["business_name"] for business in businesses]
    preferred_index = next((i for i, b in enumerate(businesses) if b["business_id"] == preferred_business_id), 0)
    selected_business_label = st.selectbox("Business", business_labels, index=preferred_index)
    try:
        business_index = business_labels.index(selected_business_label)
    except ValueError:
        st.error("The selected business is unavailable.")
        return False
    selected_business = businesses[business_index]

    try:
        accounts = _active_accounts(
            account_service.list_business_accounts(
                session_token, selected_business["business_id"]
            )
        )
    except Exception:
        st.error("Analytics could not be loaded.")
        return False
    if not accounts:
        st.error("No active financial account is available for analytics.")
        return False

    account_labels = [
        f"{account['account_name']} ({account['currency']})" for account in accounts
    ]
    selected_account_label = st.selectbox("Account", account_labels)
    try:
        account_index = account_labels.index(selected_account_label)
    except ValueError:
        st.error("The selected financial account is unavailable.")
        return False
    selected_account = accounts[account_index]

    today = date.today()
    start_value = st.date_input("Start date", today.replace(day=1))
    end_value = st.date_input("End date", today)
    st.button("Refresh analytics")
    start_date = _date_value(start_value)
    end_date = _date_value(end_value)
    if start_date is None or end_date is None:
        st.error("Choose a valid date range.")
        return False

    try:
        result = analytics_service.get_financial_analytics(
            session_token=session_token,
            business_id=selected_business["business_id"],
            account_id=selected_account["account_id"],
            start_date=start_date,
            end_date=end_date,
            currency=selected_account["currency"],
        )
    except analytics_service.AnalyticsError as error:
        st.error(_safe_error_message(error))
        return False
    except Exception:
        st.error("Analytics could not be loaded.")
        return False

    _render_analytics(st, result, selected_account["currency"])
    return True


__all__ = ["AUTHORIZED_MEMBERSHIP_ROLES", "render_analytics_page"]
