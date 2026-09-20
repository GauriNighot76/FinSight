"""Read-only financial analytics for accepted Module 4 transactions."""

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from database import queries
from services import auth_service


class AnalyticsError(ValueError):
    """Safe error raised for invalid analytics requests."""


_SCOPE = """
FROM ingested_transaction_identities i
JOIN transaction_general_ledger t
  ON t.transaction_id=i.transaction_id
WHERE i.business_id=? AND i.account_id=?
  AND i.transaction_date BETWEEN ? AND ?
"""

_KPI_SQL = f"""
SELECT
    COUNT(*) AS transaction_count,
    COALESCE(SUM(CASE WHEN i.direction='income'
                      THEN i.amount_minor ELSE 0 END), 0) AS total_income_minor,
    COALESCE(SUM(CASE WHEN i.direction='expense'
                      THEN i.amount_minor ELSE 0 END), 0) AS total_expense_minor,
    MAX(CASE WHEN i.direction='income' THEN i.amount_minor END)
        AS largest_income_minor,
    MIN(CASE WHEN i.direction='income' THEN i.amount_minor END)
        AS smallest_income_minor,
    MAX(CASE WHEN i.direction='expense' THEN i.amount_minor END)
        AS largest_expense_minor,
    MIN(CASE WHEN i.direction='expense' THEN i.amount_minor END)
        AS smallest_expense_minor,
    COALESCE(SUM(CASE WHEN i.currency <> ? THEN 1 ELSE 0 END), 0)
        AS currency_mismatch_count
{_SCOPE}
"""

_DAILY_SQL = f"""
SELECT
    i.transaction_date AS period,
    COALESCE(SUM(CASE WHEN i.direction='income'
                      THEN i.amount_minor ELSE 0 END), 0) AS income_minor,
    COALESCE(SUM(CASE WHEN i.direction='expense'
                      THEN i.amount_minor ELSE 0 END), 0) AS expense_minor,
    COUNT(*) AS transaction_count
{_SCOPE}
GROUP BY i.transaction_date
ORDER BY i.transaction_date
"""

_CATEGORY_SQL = f"""
SELECT
    CASE WHEN t.category IS NULL OR t.category = ''
         THEN 'Uncategorized' ELSE t.category END AS label,
    i.direction AS direction,
    SUM(i.amount_minor) AS total_minor,
    COUNT(*) AS n
{_SCOPE}
GROUP BY label, i.direction
"""

_PAYMENT_MODE_SQL = f"""
SELECT
    CASE WHEN t.payment_mode IN ('Cash','UPI','Card','Bank')
         THEN t.payment_mode ELSE 'Other' END AS label,
    i.direction AS direction,
    SUM(i.amount_minor) AS total_minor,
    COUNT(*) AS n
{_SCOPE}
GROUP BY label, i.direction
"""

_TRANSACTIONS_SQL = f"""
SELECT i.transaction_date, i.amount_minor, i.direction, i.currency,
       i.identity_id, t.category, t.payment_mode
{_SCOPE}
ORDER BY i.transaction_date, i.identity_id
"""


def _percentage(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) * Decimal(100) / Decimal(denominator)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _validate_date_range(start_date: Any, end_date: Any) -> tuple[str, str]:
    if type(start_date) is not str or type(end_date) is not str:
        raise AnalyticsError("The analytics date range is invalid.")
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as error:
        raise AnalyticsError("The analytics date range is invalid.") from error
    if start > end:
        raise AnalyticsError("The analytics date range is invalid.")
    return start.isoformat(), end.isoformat()


def _require_authorized_session(session_token: Any, business_id: Any) -> None:
    if type(session_token) is not str or not session_token:
        raise AnalyticsError("Authentication is required for analytics.")
    try:
        session = auth_service.validate_session(session_token)
    except Exception as error:
        raise AnalyticsError("Authentication is required for analytics.") from error
    if not isinstance(session, dict) or session.get("success") is not True:
        raise AnalyticsError("Authentication is required for analytics.")
    user = session.get("user")
    if (
        not isinstance(user, dict)
        or type(user.get("user_id")) is not str
        or not user["user_id"]
    ):
        raise AnalyticsError("Authentication is required for analytics.")
    if type(business_id) is not str or not business_id:
        raise AnalyticsError("The selected business is unavailable.")
    try:
        membership = queries.get_business_membership(business_id, user["user_id"])
    except Exception as error:
        raise AnalyticsError("The selected business is unavailable.") from error
    if membership is None:
        raise AnalyticsError("The selected business is unavailable.")
    try:
        business_status = membership["business_status"]
        membership_status = membership["membership_status"]
        membership_role = membership["membership_role"]
    except (KeyError, TypeError, IndexError) as error:
        raise AnalyticsError("The selected business is unavailable.") from error
    if (
        business_status != "active"
        or membership_status != "active"
        or membership_role not in {"owner", "manager"}
    ):
        raise AnalyticsError("The selected business is unavailable.")


def _load_account(account_id: Any, business_id: str, currency: Any):
    if type(account_id) is not str or not account_id:
        raise AnalyticsError("The selected financial account is unavailable.")
    if type(currency) is not str or not currency:
        raise AnalyticsError("The selected analytics currency is invalid.")
    with queries.get_connection() as connection:
        account = connection.execute(
            """SELECT opening_balance_minor, currency
               FROM financial_accounts
               WHERE account_id=? AND business_id=? AND account_status='active'""",
            (account_id, business_id),
        ).fetchone()
    if account is None:
        raise AnalyticsError("The selected financial account is unavailable.")
    if account["currency"] != currency:
        raise AnalyticsError("The selected analytics currency is invalid.")
    return account


def _load_accepted_rows(
    *,
    business_id: str,
    account_id: str,
    start_date: str,
    end_date: str,
) -> list[Any]:
    with queries.get_connection() as connection:
        return connection.execute(
            """SELECT i.transaction_date, i.amount_minor, i.direction, i.currency,
                      i.identity_id, t.category, t.payment_mode
               FROM ingested_transaction_identities i
               JOIN transaction_general_ledger t
                 ON t.transaction_id=i.transaction_id
               WHERE i.business_id=? AND i.account_id=?
                 AND i.transaction_date BETWEEN ? AND ?
               ORDER BY i.transaction_date, i.identity_id""",
            (business_id, account_id, start_date, end_date),
        ).fetchall()


def _query_kpis(
    connection: Any,
    business_id: str,
    account_id: str,
    start_date: str,
    end_date: str,
    currency: str,
):
    return connection.execute(
        _KPI_SQL,
        (currency, business_id, account_id, start_date, end_date),
    ).fetchone()


def _query_daily(
    connection: Any,
    business_id: str,
    account_id: str,
    start_date: str,
    end_date: str,
) -> list[Any]:
    return connection.execute(
        _DAILY_SQL,
        (business_id, account_id, start_date, end_date),
    ).fetchall()


def _query_groups(
    connection: Any,
    sql: str,
    business_id: str,
    account_id: str,
    start_date: str,
    end_date: str,
) -> list[Any]:
    return connection.execute(
        sql,
        (business_id, account_id, start_date, end_date),
    ).fetchall()


def _query_transactions(
    connection: Any,
    business_id: str,
    account_id: str,
    start_date: str,
    end_date: str,
) -> list[Any]:
    return connection.execute(
        _TRANSACTIONS_SQL,
        (business_id, account_id, start_date, end_date),
    ).fetchall()


def _empty_trends() -> dict[str, list[dict[str, Any]]]:
    return {"daily": [], "weekly": [], "monthly": []}


def _trend_row(period: str, rows: list[Any]) -> dict[str, Any]:
    income = sum(row["amount_minor"] for row in rows if row["direction"] == "income")
    expense = sum(row["amount_minor"] for row in rows if row["direction"] == "expense")
    return {
        "period": period,
        "income_minor": income,
        "expense_minor": expense,
        "net_cash_flow_minor": income - expense,
        "transaction_count": len(rows),
    }


def _build_trends(rows: list[Any]) -> dict[str, list[dict[str, Any]]]:
    if not rows:
        return _empty_trends()

    daily_groups: dict[str, list[Any]] = defaultdict(list)
    weekly_groups: dict[str, list[Any]] = defaultdict(list)
    monthly_groups: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        transaction_date = date.fromisoformat(row["transaction_date"])
        day = transaction_date.isoformat()
        week = f"{transaction_date:%G}-W{transaction_date:%V}"
        month = transaction_date.strftime("%Y-%m")
        daily_groups[day].append(row)
        weekly_groups[week].append(row)
        monthly_groups[month].append(row)

    return {
        "daily": [_trend_row(period, daily_groups[period]) for period in sorted(daily_groups)],
        "weekly": [_trend_row(period, weekly_groups[period]) for period in sorted(weekly_groups)],
        "monthly": [
            _trend_row(period, monthly_groups[period])
            for period in sorted(monthly_groups)
        ],
    }


def _aggregate_trend_row(
    period: str,
    income_minor: int,
    expense_minor: int,
    transaction_count: int,
) -> dict[str, Any]:
    return {
        "period": period,
        "income_minor": income_minor,
        "expense_minor": expense_minor,
        "net_cash_flow_minor": income_minor - expense_minor,
        "transaction_count": transaction_count,
    }


def _build_aggregate_trends(
    daily_rows: list[Any],
) -> dict[str, list[dict[str, Any]]]:
    if not daily_rows:
        return _empty_trends()

    daily: list[dict[str, Any]] = []
    weekly: dict[str, dict[str, int]] = {}
    monthly: dict[str, dict[str, int]] = {}
    for row in daily_rows:
        period = row["period"]
        income = row["income_minor"]
        expense = row["expense_minor"]
        count = row["transaction_count"]
        daily.append(_aggregate_trend_row(period, income, expense, count))

        transaction_date = date.fromisoformat(period)
        iso_year, iso_week, _ = transaction_date.isocalendar()
        week = f"{iso_year}-W{iso_week:02d}"
        month = period[:7]
        for groups, key in ((weekly, week), (monthly, month)):
            group = groups.setdefault(
                key,
                {"income_minor": 0, "expense_minor": 0, "transaction_count": 0},
            )
            group["income_minor"] += income
            group["expense_minor"] += expense
            group["transaction_count"] += count

    return {
        "daily": daily,
        "weekly": [
            _aggregate_trend_row(
                period,
                group["income_minor"],
                group["expense_minor"],
                group["transaction_count"],
            )
            for period, group in weekly.items()
        ],
        "monthly": [
            _aggregate_trend_row(
                period,
                group["income_minor"],
                group["expense_minor"],
                group["transaction_count"],
            )
            for period, group in monthly.items()
        ],
    }


def _build_category_summary(rows: list[Any]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        category = row["category"] or "Uncategorized"
        group = groups.setdefault(
            category,
            {"income_minor": 0, "expense_minor": 0, "count": 0},
        )
        group["count"] += 1
        group[f"{row['direction']}_minor"] += row["amount_minor"]

    total_amount = sum(row["amount_minor"] for row in rows)
    result = []
    for category, group in groups.items():
        amount = group["income_minor"] + group["expense_minor"]
        result.append(
            {
                "category": category,
                "income_minor": group["income_minor"],
                "expense_minor": group["expense_minor"],
                "amount_minor": amount,
                "count": group["count"],
                "percentage": _percentage(amount, total_amount),
            }
        )
    return sorted(result, key=lambda item: (-item["amount_minor"], item["category"]))


_PAYMENT_MODE_ORDER = {
    mode: index
    for index, mode in enumerate(("Cash", "UPI", "Card", "Bank", "Other"))
}


def _build_payment_mode_summary(rows: list[Any]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        payment_mode = row["payment_mode"]
        if payment_mode not in _PAYMENT_MODE_ORDER:
            payment_mode = "Other"
        group = groups.setdefault(
            payment_mode,
            {"income_minor": 0, "expense_minor": 0, "count": 0},
        )
        group["count"] += 1
        group[f"{row['direction']}_minor"] += row["amount_minor"]

    total_amount = sum(row["amount_minor"] for row in rows)
    result = []
    for payment_mode, group in groups.items():
        amount = group["income_minor"] + group["expense_minor"]
        result.append(
            {
                "payment_mode": payment_mode,
                "income_minor": group["income_minor"],
                "expense_minor": group["expense_minor"],
                "amount_minor": amount,
                "count": group["count"],
                "percentage": _percentage(amount, total_amount),
            }
        )
    return sorted(result, key=lambda item: _PAYMENT_MODE_ORDER[item["payment_mode"]])


def _build_aggregate_summary(
    rows: list[Any],
    *,
    key_name: str,
    total_amount: int,
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, int]] = {}
    for row in rows:
        group = groups.setdefault(
            row["label"],
            {"income_minor": 0, "expense_minor": 0, "count": 0},
        )
        group["count"] += row["n"]
        group[f"{row['direction']}_minor"] += row["total_minor"]

    result = []
    for label, group in groups.items():
        amount = group["income_minor"] + group["expense_minor"]
        result.append(
            {
                key_name: label,
                "income_minor": group["income_minor"],
                "expense_minor": group["expense_minor"],
                "amount_minor": amount,
                "count": group["count"],
                "percentage": _percentage(amount, total_amount),
            }
        )
    return result


def _build_aggregate_categories(
    rows: list[Any], total_amount: int
) -> list[dict[str, Any]]:
    result = _build_aggregate_summary(
        rows,
        key_name="category",
        total_amount=total_amount,
    )
    return sorted(result, key=lambda item: (-item["amount_minor"], item["category"]))


def _build_aggregate_payment_modes(
    rows: list[Any], total_amount: int
) -> list[dict[str, Any]]:
    result = _build_aggregate_summary(
        rows,
        key_name="payment_mode",
        total_amount=total_amount,
    )
    return sorted(result, key=lambda item: _PAYMENT_MODE_ORDER[item["payment_mode"]])


def _build_account_summary(
    account_id: str, account: Any, rows: list[Any]
) -> list[dict[str, Any]]:
    if not rows:
        return []
    income = sum(row["amount_minor"] for row in rows if row["direction"] == "income")
    expense = sum(row["amount_minor"] for row in rows if row["direction"] == "expense")
    net = income - expense
    opening = account["opening_balance_minor"]
    return [
        {
            "account_id": account_id,
            "opening_balance_minor": opening,
            "closing_balance_minor": opening + net if opening is not None else None,
            "total_income_minor": income,
            "total_expense_minor": expense,
            "net_cash_flow_minor": net,
            "transaction_count": len(rows),
        }
    ]


def _build_aggregate_account_summary(
    account_id: str,
    account: Any,
    *,
    total_income: int,
    total_expense: int,
    transaction_count: int,
) -> list[dict[str, Any]]:
    if not transaction_count:
        return []
    net = total_income - total_expense
    opening = account["opening_balance_minor"]
    return [
        {
            "account_id": account_id,
            "opening_balance_minor": opening,
            "closing_balance_minor": opening + net if opening is not None else None,
            "total_income_minor": total_income,
            "total_expense_minor": total_expense,
            "net_cash_flow_minor": net,
            "transaction_count": transaction_count,
        }
    ]


def _build_transaction_rows(rows: list[Any]) -> list[dict[str, Any]]:
    """Expose only non-sensitive accepted fields for downstream read-only analysis."""
    return [
        {
            "transaction_date": row["transaction_date"],
            "amount_minor": row["amount_minor"],
            "direction": row["direction"],
            "category": row["category"],
            "payment_mode": row["payment_mode"],
        }
        for row in rows
    ]


def get_financial_analytics(
    *,
    session_token: str,
    business_id: str,
    account_id: str,
    start_date: str,
    end_date: str,
    currency: str,
    include_transactions: bool = True,
) -> dict[str, Any]:
    """Return KPI aggregates without modifying any FinSight data."""
    _require_authorized_session(session_token, business_id)
    start_date, end_date = _validate_date_range(start_date, end_date)
    account = _load_account(account_id, business_id, currency)
    connection = queries.get_connection()
    try:
        connection.execute("BEGIN")
        try:
            kpi_row = _query_kpis(
                connection,
                business_id,
                account_id,
                start_date,
                end_date,
                currency,
            )
            if kpi_row["currency_mismatch_count"] > 0:
                raise AnalyticsError(
                    "The selected analytics currency is inconsistent."
                )
            daily_rows = _query_daily(
                connection, business_id, account_id, start_date, end_date
            )
            category_rows = _query_groups(
                connection,
                _CATEGORY_SQL,
                business_id,
                account_id,
                start_date,
                end_date,
            )
            payment_mode_rows = _query_groups(
                connection,
                _PAYMENT_MODE_SQL,
                business_id,
                account_id,
                start_date,
                end_date,
            )
            transaction_rows = (
                _query_transactions(
                    connection, business_id, account_id, start_date, end_date
                )
                if include_transactions
                else []
            )
        finally:
            connection.rollback()
    finally:
        connection.close()

    total_income = kpi_row["total_income_minor"]
    total_expense = kpi_row["total_expense_minor"]
    transaction_count = kpi_row["transaction_count"]
    total_amount = total_income + total_expense
    opening_balance = account["opening_balance_minor"]

    return {
        "kpis": {
            "total_income_minor": total_income,
            "total_expense_minor": total_expense,
            "net_cash_flow_minor": total_income - total_expense,
            "transaction_count": transaction_count,
            "average_transaction_minor": (
                Decimal(total_income + total_expense) / Decimal(transaction_count)
                if transaction_count
                else Decimal("0")
            ),
            "largest_income_minor": kpi_row["largest_income_minor"],
            "smallest_income_minor": kpi_row["smallest_income_minor"],
            "largest_expense_minor": kpi_row["largest_expense_minor"],
            "smallest_expense_minor": kpi_row["smallest_expense_minor"],
            "opening_balance_minor": opening_balance,
            "closing_balance_minor": (
                opening_balance + total_income - total_expense
                if opening_balance is not None
                else None
            ),
            "income_expense_ratio": (
                Decimal(total_income) / Decimal(total_expense)
                if total_expense
                else None
            ),
            "savings_rate": _percentage(total_income - total_expense, total_income),
        },
        "trends": _build_aggregate_trends(daily_rows),
        "categories": _build_aggregate_categories(category_rows, total_amount),
        "payment_modes": _build_aggregate_payment_modes(
            payment_mode_rows, total_amount
        ),
        "accounts": _build_aggregate_account_summary(
            account_id,
            account,
            total_income=total_income,
            total_expense=total_expense,
            transaction_count=transaction_count,
        ),
        "transactions": _build_transaction_rows(transaction_rows),
    }


__all__ = ["AnalyticsError", "get_financial_analytics"]
