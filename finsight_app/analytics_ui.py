"""Thin Streamlit adapter for the read-only Module 5 analytics service."""

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from services import account_service, analytics_service, auth_service, business_health_service, business_service


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
    if label == "Savings Rate":
        return f"{value}%"
    if label == "Income/Expense Ratio":
        return f"{Decimal(value):.2f}×"
    return str(value)


_FRIENDLY_COLUMNS = {
    "period": "Period",
    "transaction_date": "Date",
    "direction": "Type",
    "category": "Category",
    "payment_mode": "Payment method",
    "count": "Transactions",
    "percentage": "Share (%)",
    "reason": "Why this needs review",
    "severity": "Priority",
    "date": "Date",
}


def _friendly_rows(rows: Any, currency: str) -> list[dict[str, Any]]:
    result = []
    for row in _safe_table_rows(rows):
        item: dict[str, Any] = {}
        for key, value in row.items():
            if key in {"affected_transaction", "trigger_metric", "threshold", "metric_value", "date_detected", "explanation", "affected_period"}:
                continue
            label = _FRIENDLY_COLUMNS.get(key, key.replace("_minor", "").replace("_", " ").title())
            if key.endswith("_minor"):
                value = _format_minor(value, currency)
            elif key == "direction" and value:
                value = str(value).title()
            item[label] = value if value is not None else "—"
        result.append(item)
    return result


_REVIEW_LABELS = {
    "amount_outside_usual_range": "Amount outside the usual range",
    "monthly_expenses_doubled": "Monthly expenses doubled",
    "monthly_expense_increase": "Monthly expenses increased",
    "sudden_income_drop": "Monthly income decreased",
    "negative_cash_flow_period": "Loss-making month",
    "category_spike": "Category spending increased",
    "inactive_period": "Long period without transactions",
}


def _review_rows(anomalies: Any, currency: str) -> list[dict[str, Any]]:
    rows = []
    for anomaly in anomalies if isinstance(anomalies, list) else []:
        rows.append({
            "Finding": _REVIEW_LABELS.get(anomaly.get("type"), str(anomaly.get("type", "Review item")).replace("_", " ").title()),
            "Priority": str(anomaly.get("severity", "Medium")).title(),
            "Date or month": anomaly.get("date") or "—",
            "Why it was flagged": anomaly.get("reason") or anomaly.get("explanation") or "—",
        })
    return rows


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
    if not hasattr(st, "columns"):
        for label, key in fields:
            st.metric(label, _format_value(label, kpis.get(key), currency))
        return
    primary = fields[:4]
    for column, (label, key) in zip(st.columns(4), primary):
        column.metric(label, _format_value(label, kpis.get(key), currency))
    with st.expander("More financial indicators"):
        detail_columns = st.columns(3)
        for index, (label, key) in enumerate(fields[4:]):
            detail_columns[index % 3].metric(label, _format_value(label, kpis.get(key), currency))


def _render_analytics(st: Any, result: dict[str, Any], currency: str) -> None:
    _render_kpis(st, result, currency)
    kpis = result.get("kpis") if isinstance(result.get("kpis"), dict) else {}
    if kpis.get("transaction_count", 0) == 0:
        st.info("No transactions found for the selected period.")

    trends = result.get("trends") if isinstance(result.get("trends"), dict) else {}
    if not hasattr(st, "columns"):
        for label, name in (("Daily trend", "daily"), ("Weekly trend", "weekly"), ("Monthly trend", "monthly")):
            st.subheader(label)
            st.line_chart(trends.get(name, []))
        for label, name in (("Category summary", "categories"), ("Payment mode summary", "payment_modes"), ("Account summary", "accounts")):
            st.subheader(label)
            st.dataframe(_safe_table_rows(result.get(name, [])), hide_index=True)
        return

    st.subheader("Cash flow trend")
    monthly = []
    for row in trends.get("monthly", []):
        monthly.append({
            "Month": row.get("period"),
            "Income": float(Decimal(row.get("income_minor", 0)) / 100),
            "Expenses": float(Decimal(row.get("expense_minor", 0)) / 100),
            "Net cash flow": float(Decimal(row.get("net_cash_flow_minor", 0)) / 100),
        })
    if monthly:
        st.bar_chart(monthly, x="Month", y=["Income", "Expenses"])
        st.line_chart(monthly, x="Month", y="Net cash flow")
    else:
        st.info("Import transactions to see cash-flow trends.")

    left, right = st.columns(2)
    with left:
        st.subheader("Expense categories")
        categories = _friendly_rows(result.get("categories", []), currency)
        st.dataframe(categories, hide_index=True, use_container_width=True)
    with right:
        st.subheader("Payment methods")
        payments = _friendly_rows(result.get("payment_modes", []), currency)
        st.dataframe(payments, hide_index=True, use_container_width=True)
    with st.expander("Recent transactions"):
        st.dataframe(_friendly_rows(result.get("transactions", []), currency)[:100], hide_index=True, use_container_width=True)


def _render_health(st: Any, health: dict[str, Any], currency: str) -> None:
    metrics = health.get("metrics", {})
    anomalies = health.get("anomalies", [])
    st.subheader("Business health")
    score, status, reserve = st.columns(3)
    score.metric("Health score", f"{metrics.get('health_score', 0)}/100")
    status.metric("Health rating", metrics.get("health_rating", "—"))
    reserve.metric("Cash reserve", _format_minor(metrics.get("cash_reserve_estimate_minor"), currency))
    with st.expander(f"Transactions to review ({len(anomalies)})", expanded=False):
        if anomalies:
            st.caption("A review item is not proof of fraud or an accounting error.")
            st.dataframe(_review_rows(anomalies, currency), hide_index=True, use_container_width=True)
        else:
            st.success("No material anomaly flags were found for this period.")


def render_analytics_page(
    st: Any, session_token: Any, *, return_scope: bool = False
) -> bool | dict[str, Any]:
    """Render analytics for an authenticated owner or manager.

    The default return value remains a boolean for compatibility with the
    existing adapter tests.  The application can request the selected scope
    and already-loaded analytics result by passing ``return_scope=True``;
    this lets downstream dashboard/report views use exactly the same
    business, account, date range, and currency selection.
    """
    session_state = getattr(st, "session_state", None)
    if session_state is not None:
        session_state.pop("_finsight_analytics_scope", None)
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
    selected_business_label = st.selectbox("Business", business_labels, key="analytics_business_select")
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
    selected_account_label = st.selectbox("Account", account_labels, key="analytics_account_select")
    try:
        account_index = account_labels.index(selected_account_label)
    except ValueError:
        st.error("The selected financial account is unavailable.")
        return False
    selected_account = accounts[account_index]

    today = date.today()
    default_start, default_end = today.replace(day=1), today
    try:
        first_date, last_date = analytics_service.get_available_date_range(
            session_token=session_token,
            business_id=selected_business["business_id"],
            account_id=selected_account["account_id"],
            currency=selected_account["currency"],
        )
        if first_date and last_date:
            default_start, default_end = date.fromisoformat(first_date), date.fromisoformat(last_date)
    except Exception:
        pass
    date_columns = st.columns(2) if hasattr(st, "columns") else [st, st]
    start_value = date_columns[0].date_input("Start date", default_start)
    end_value = date_columns[1].date_input("End date", default_end)
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
    if hasattr(st, "columns"):
        try:
            health = business_health_service.get_business_health(
                session_token=session_token,
                business_id=selected_business["business_id"],
                account_id=selected_account["account_id"],
                start_date=start_date,
                end_date=end_date,
                currency=selected_account["currency"],
            )
            _render_health(st, health, selected_account["currency"])
        except Exception:
            st.info("Business-health indicators are temporarily unavailable.")
    scope = {
        "business": selected_business,
        "account": selected_account,
        "business_id": selected_business["business_id"],
        "account_id": selected_account["account_id"],
        "start_date": start_date,
        "end_date": end_date,
        "currency": selected_account["currency"],
        "analytics": result,
    }
    if session_state is not None:
        session_state["_finsight_analytics_scope"] = scope
    if return_scope:
        return scope
    return True


__all__ = ["AUTHORIZED_MEMBERSHIP_ROLES", "render_analytics_page"]
