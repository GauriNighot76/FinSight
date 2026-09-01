"""Read-only financial analytics for accepted Module 4 transactions."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from database import queries
from services import auth_service


class AnalyticsError(ValueError):
    """Safe error raised for invalid analytics requests."""


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
    session = auth_service.validate_session(session_token)
    if not isinstance(session, dict) or session.get("success") is not True:
        raise AnalyticsError("Authentication is required for analytics.")
    if type(business_id) is not str or not business_id:
        raise AnalyticsError("The selected business is unavailable.")
    membership = queries.get_business_membership(
        business_id, session["user"]["user_id"]
    )
    if (
        membership is None
        or membership["business_status"] != "active"
        or membership["membership_status"] != "active"
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
            """SELECT transaction_date, amount_minor, direction, currency
               FROM ingested_transaction_identities
               WHERE business_id=? AND account_id=?
                 AND transaction_date BETWEEN ? AND ?
               ORDER BY transaction_date, identity_id""",
            (business_id, account_id, start_date, end_date),
        ).fetchall()


def get_financial_analytics(
    *,
    session_token: str,
    business_id: str,
    account_id: str,
    start_date: str,
    end_date: str,
    currency: str,
) -> dict[str, dict[str, Any]]:
    """Return KPI aggregates without modifying any FinSight data."""
    _require_authorized_session(session_token, business_id)
    start_date, end_date = _validate_date_range(start_date, end_date)
    account = _load_account(account_id, business_id, currency)
    rows = _load_accepted_rows(
        business_id=business_id,
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
    )
    if any(row["currency"] != currency for row in rows):
        raise AnalyticsError("The selected analytics currency is inconsistent.")

    incomes = [row["amount_minor"] for row in rows if row["direction"] == "income"]
    expenses = [row["amount_minor"] for row in rows if row["direction"] == "expense"]
    total_income = sum(incomes)
    total_expense = sum(expenses)
    transaction_count = len(rows)
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
            "largest_income_minor": max(incomes) if incomes else None,
            "smallest_income_minor": min(incomes) if incomes else None,
            "largest_expense_minor": max(expenses) if expenses else None,
            "smallest_expense_minor": min(expenses) if expenses else None,
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
        }
    }


__all__ = ["AnalyticsError", "get_financial_analytics"]
