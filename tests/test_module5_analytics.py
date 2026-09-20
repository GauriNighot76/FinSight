from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from database import db
from services import analytics_service
from services import ingestion_identity
from test_module4_ingestion_service import (
    ACCOUNT_ID,
    BUSINESS_ID,
    CONTRACT_VERSION,
    REGISTRY_BUSINESS_ID,
    SOURCE_SYSTEM,
    ingestion_repository,
)


def _seed_accepted_transaction(
    connection,
    transaction_id,
    *,
    business_id=BUSINESS_ID,
    registry_business_id=REGISTRY_BUSINESS_ID,
    account_id=ACCOUNT_ID,
    transaction_date="2026-08-15",
    amount_minor=1000,
    direction="income",
    currency="INR",
    include_identity=True,
):
    attempt_id = f"analytics_attempt_{transaction_id}"
    connection.execute(
        """INSERT INTO ingestion_attempts
           (attempt_id,business_id,registry_business_id,account_id,uploader_user_id,
            source_system,contract_version,currency,record_count,inserted_count,
            attempt_status,completed_at)
           VALUES (?, ?, ?, ?, 'owner_user_001', ?, ?, ?, 1, ?, 'completed',
                   CURRENT_TIMESTAMP)""",
        (
            attempt_id,
            business_id,
            registry_business_id,
            account_id,
            SOURCE_SYSTEM,
            CONTRACT_VERSION,
            currency,
            1 if include_identity else 0,
        ),
    )
    connection.execute(
        """INSERT INTO transaction_general_ledger
           (transaction_id,business_id,user_id,transaction_date,amount,
            transaction_type,description,transaction_hash)
           VALUES (?, ?, 'legacy_owner_001', ?, ?, ?, ?, ?)""",
        (
            transaction_id,
            registry_business_id,
            transaction_date,
            amount_minor / 100,
            direction,
            "analytics fixture",
            f"legacy-{transaction_id}",
        ),
    )
    if include_identity:
        canonical_hash = ingestion_identity.build_canonical_identity_hash(
            account_id,
            SOURCE_SYSTEM,
            currency,
            transaction_date,
            amount_minor,
            direction,
        )
        connection.execute(
            """INSERT INTO ingested_transaction_identities
               (identity_id,transaction_id,attempt_id,business_id,
                registry_business_id,account_id,source_system,
                source_transaction_id,transaction_date,amount_minor,
                direction,currency,canonical_identity_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f"analytics_identity_{transaction_id}",
                transaction_id,
                attempt_id,
                business_id,
                registry_business_id,
                account_id,
                SOURCE_SYSTEM,
                f"SRC-{transaction_id}",
                transaction_date,
                amount_minor,
                direction,
                currency,
                canonical_hash,
            ),
        )


def _analytics(
    *,
    session_token="token-owner_user_001",
    business_id=BUSINESS_ID,
    account_id=ACCOUNT_ID,
    start_date="2026-01-01",
    end_date="2026-12-31",
    currency="INR",
    include_transactions=True,
):
    return analytics_service.get_financial_analytics(
        session_token=session_token,
        business_id=business_id,
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        currency=currency,
        include_transactions=include_transactions,
    )


def _legacy_percentage(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return (Decimal(numerator) * Decimal(100) / Decimal(denominator)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _legacy_empty_trends() -> dict[str, list[dict[str, Any]]]:
    return {"daily": [], "weekly": [], "monthly": []}


def _legacy_trend_row(period: str, rows: list[Any]) -> dict[str, Any]:
    income = sum(row["amount_minor"] for row in rows if row["direction"] == "income")
    expense = sum(row["amount_minor"] for row in rows if row["direction"] == "expense")
    return {
        "period": period,
        "income_minor": income,
        "expense_minor": expense,
        "net_cash_flow_minor": income - expense,
        "transaction_count": len(rows),
    }


def _legacy_build_trends(rows: list[Any]) -> dict[str, list[dict[str, Any]]]:
    if not rows:
        return _legacy_empty_trends()

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
        "daily": [
            _legacy_trend_row(period, daily_groups[period])
            for period in sorted(daily_groups)
        ],
        "weekly": [
            _legacy_trend_row(period, weekly_groups[period])
            for period in sorted(weekly_groups)
        ],
        "monthly": [
            _legacy_trend_row(period, monthly_groups[period])
            for period in sorted(monthly_groups)
        ],
    }


def _legacy_build_category_summary(rows: list[Any]) -> list[dict[str, Any]]:
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
                "percentage": _legacy_percentage(amount, total_amount),
            }
        )
    return sorted(result, key=lambda item: (-item["amount_minor"], item["category"]))


def _legacy_build_payment_mode_summary(rows: list[Any]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        payment_mode = row["payment_mode"]
        if payment_mode not in analytics_service._PAYMENT_MODE_ORDER:
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
                "percentage": _legacy_percentage(amount, total_amount),
            }
        )
    return sorted(
        result,
        key=lambda item: analytics_service._PAYMENT_MODE_ORDER[item["payment_mode"]],
    )


def _legacy_build_account_summary(
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


def _legacy_build_transaction_rows(rows: list[Any]) -> list[dict[str, Any]]:
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


def _legacy_contract(
    *,
    account_id: str,
    account: Any,
    rows: list[Any],
) -> dict[str, Any]:
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
            "savings_rate": _legacy_percentage(
                total_income - total_expense, total_income
            ),
        },
        "trends": _legacy_build_trends(rows),
        "categories": _legacy_build_category_summary(rows),
        "payment_modes": _legacy_build_payment_mode_summary(rows),
        "accounts": _legacy_build_account_summary(account_id, account, rows),
        "transactions": _legacy_build_transaction_rows(rows),
    }


def test_core_kpis_use_exact_minor_units(ingestion_repository):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(
            connection,
            "income-1",
            amount_minor=2500,
            direction="income",
        )
        _seed_accepted_transaction(
            connection,
            "income-2",
            transaction_date="2026-08-16",
            amount_minor=1500,
            direction="income",
        )
        _seed_accepted_transaction(
            connection,
            "expense-1",
            transaction_date="2026-08-17",
            amount_minor=1000,
            direction="expense",
        )

    kpis = _analytics()["kpis"]
    assert kpis["total_income_minor"] == 4000
    assert kpis["total_expense_minor"] == 1000
    assert kpis["net_cash_flow_minor"] == 3000
    assert kpis["transaction_count"] == 3
    assert kpis["average_transaction_minor"] == Decimal(5000) / Decimal(3)
    assert kpis["largest_income_minor"] == 2500
    assert kpis["smallest_income_minor"] == 1500
    assert kpis["largest_expense_minor"] == 1000
    assert kpis["smallest_expense_minor"] == 1000
    assert kpis["income_expense_ratio"] == Decimal("4")
    assert kpis["savings_rate"] == Decimal("75.00")


def test_opening_and_closing_balances_are_minor_units(ingestion_repository):
    with ingestion_repository() as connection:
        connection.execute(
            "UPDATE financial_accounts SET opening_balance_minor=? WHERE account_id=?",
            (10000, ACCOUNT_ID),
        )
        _seed_accepted_transaction(
            connection,
            "balance-income",
            amount_minor=2500,
            direction="income",
        )
        _seed_accepted_transaction(
            connection,
            "balance-expense",
            amount_minor=500,
            direction="expense",
        )

    kpis = _analytics()["kpis"]
    assert kpis["opening_balance_minor"] == 10000
    assert kpis["closing_balance_minor"] == 12000


def test_date_range_is_inclusive(ingestion_repository):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(
            connection,
            "date-before",
            transaction_date="2026-08-09",
            amount_minor=100,
        )
        _seed_accepted_transaction(
            connection,
            "date-start",
            transaction_date="2026-08-10",
            amount_minor=200,
        )
        _seed_accepted_transaction(
            connection,
            "date-end",
            transaction_date="2026-08-20",
            amount_minor=300,
        )
        _seed_accepted_transaction(
            connection,
            "date-after",
            transaction_date="2026-08-21",
            amount_minor=400,
        )

    kpis = _analytics(start_date="2026-08-10", end_date="2026-08-20")["kpis"]
    assert kpis["transaction_count"] == 2
    assert kpis["total_income_minor"] == 500


def test_empty_dataset_returns_zero_values(ingestion_repository):
    result = _analytics()
    kpis = result["kpis"]

    assert kpis["total_income_minor"] == 0
    assert kpis["total_expense_minor"] == 0
    assert kpis["net_cash_flow_minor"] == 0
    assert kpis["transaction_count"] == 0
    assert kpis["average_transaction_minor"] == Decimal("0")
    assert kpis["largest_income_minor"] is None
    assert kpis["smallest_income_minor"] is None
    assert kpis["largest_expense_minor"] is None
    assert kpis["smallest_expense_minor"] is None
    assert kpis["opening_balance_minor"] == 0
    assert kpis["closing_balance_minor"] == 0
    assert kpis["income_expense_ratio"] is None
    assert kpis["savings_rate"] is None


def test_duplicate_legacy_rows_without_identity_are_excluded(ingestion_repository):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(
            connection,
            "accepted-row",
            amount_minor=1000,
            direction="income",
        )
        _seed_accepted_transaction(
            connection,
            "legacy-only-row",
            amount_minor=9000,
            direction="expense",
            include_identity=False,
        )

    kpis = _analytics()["kpis"]
    assert kpis["transaction_count"] == 1
    assert kpis["total_income_minor"] == 1000
    assert kpis["total_expense_minor"] == 0


def test_business_and_account_scope_is_enforced(ingestion_repository):
    with ingestion_repository() as connection:
        connection.execute(
            """INSERT INTO users
               (user_id,username,email,contact_number,password_hash)
               VALUES ('other-owner','other-owner','other@example.test','9999999998','hash')"""
        )
        connection.execute(
            """INSERT INTO businesses
               (business_id,business_name,business_status)
               VALUES ('other-business','Other Business','active')"""
        )
        connection.execute(
            """INSERT INTO business_memberships
               (membership_id,business_id,user_id,membership_role,membership_status)
               VALUES ('other-membership','other-business','other-owner','owner','active')"""
        )
        connection.execute(
            """INSERT INTO business_registry
               (business_id,user_id,business_name)
               VALUES ('other-registry','other-owner','Other Registry')"""
        )
        connection.execute(
            """INSERT INTO financial_accounts
               (account_id,business_id,account_name,account_type,currency,account_status)
               VALUES ('other-account','other-business','Other Account','bank','INR','active')"""
        )
        _seed_accepted_transaction(
            connection,
            "other-row",
            business_id="other-business",
            registry_business_id="other-registry",
            account_id="other-account",
            amount_minor=9000,
            direction="expense",
        )
        _seed_accepted_transaction(
            connection,
            "selected-row",
            amount_minor=1000,
            direction="income",
        )

    kpis = _analytics()["kpis"]
    assert kpis["transaction_count"] == 1
    assert kpis["total_income_minor"] == 1000
    assert kpis["total_expense_minor"] == 0

    with pytest.raises(analytics_service.AnalyticsError):
        _analytics(account_id="other-account")


def test_currency_mismatch_and_invalid_range_fail_closed(ingestion_repository):
    with pytest.raises(analytics_service.AnalyticsError):
        _analytics(currency="USD")
    with pytest.raises(analytics_service.AnalyticsError):
        _analytics(start_date="2026-09-01", end_date="2026-08-01")


def test_persisted_mixed_currency_is_rejected(ingestion_repository):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(
            connection,
            "mixed-currency-row",
            amount_minor=1000,
            currency="USD",
        )

    with pytest.raises(analytics_service.AnalyticsError):
        _analytics()


def test_analytics_is_read_only_and_invalid_session_is_rejected(ingestion_repository):
    with ingestion_repository() as connection:
        before = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "ingestion_attempts",
                "transaction_general_ledger",
                "ingested_transaction_identities",
            )
        }

    with pytest.raises(analytics_service.AnalyticsError):
        _analytics(session_token="invalid-session")

    _analytics()
    with ingestion_repository() as connection:
        after = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "ingestion_attempts",
                "transaction_general_ledger",
                "ingested_transaction_identities",
            )
        }
    assert after == before


def _add_ledger_dimensions(connection, transaction_id, *, category=None, payment_mode=None):
    connection.execute(
        """UPDATE transaction_general_ledger
           SET category=?, payment_mode=?
           WHERE transaction_id=?""",
        (category, payment_mode, transaction_id),
    )


def test_daily_trends_are_chronological_and_exact(ingestion_repository):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(
            connection, "daily-late", transaction_date="2026-08-12", amount_minor=700,
        )
        _add_ledger_dimensions(connection, "daily-late", category="sales", payment_mode="UPI")
        _seed_accepted_transaction(
            connection, "daily-early-income", transaction_date="2026-08-10",
            amount_minor=1000, direction="income",
        )
        _add_ledger_dimensions(
            connection, "daily-early-income", category="sales", payment_mode="Cash"
        )
        _seed_accepted_transaction(
            connection, "daily-early-expense", transaction_date="2026-08-10",
            amount_minor=250, direction="expense",
        )
        _add_ledger_dimensions(
            connection, "daily-early-expense", category="rent", payment_mode="Bank"
        )

    daily = _analytics()["trends"]["daily"]
    assert [row["period"] for row in daily] == ["2026-08-10", "2026-08-12"]
    assert daily[0] == {
        "period": "2026-08-10",
        "income_minor": 1000,
        "expense_minor": 250,
        "net_cash_flow_minor": 750,
        "transaction_count": 2,
    }
    assert daily[1]["income_minor"] == 700
    assert daily[1]["transaction_count"] == 1


def test_weekly_trends_use_iso_weeks(ingestion_repository):
    with ingestion_repository() as connection:
        for transaction_id, transaction_date, amount_minor, direction in (
            ("week-1", "2026-01-01", 100, "income"),
            ("week-2", "2026-01-04", 40, "expense"),
            ("week-3", "2026-01-05", 200, "income"),
        ):
            _seed_accepted_transaction(
                connection,
                transaction_id,
                transaction_date=transaction_date,
                amount_minor=amount_minor,
                direction=direction,
            )

    weekly = _analytics()["trends"]["weekly"]
    assert [row["period"] for row in weekly] == ["2026-W01", "2026-W02"]
    assert weekly[0]["income_minor"] == 100
    assert weekly[0]["expense_minor"] == 40
    assert weekly[0]["net_cash_flow_minor"] == 60
    assert weekly[1]["transaction_count"] == 1


def test_monthly_trends_are_chronological(ingestion_repository):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(
            connection, "month-jan", transaction_date="2026-01-31", amount_minor=1000,
        )
        _seed_accepted_transaction(
            connection, "month-feb", transaction_date="2026-02-01", amount_minor=400,
            direction="expense",
        )
        _seed_accepted_transaction(
            connection, "month-mar", transaction_date="2026-03-01", amount_minor=800,
        )

    monthly = _analytics()["trends"]["monthly"]
    assert [row["period"] for row in monthly] == ["2026-01", "2026-02", "2026-03"]
    assert monthly[1]["net_cash_flow_minor"] == -400
    assert monthly[2]["transaction_count"] == 1


def test_category_summary_contains_income_expense_and_percentages(ingestion_repository):
    with ingestion_repository() as connection:
        fixtures = (
            ("category-sales-income", "sales", "income", 2000),
            ("category-sales-expense", "sales", "expense", 500),
            ("category-rent", "rent", "expense", 1000),
        )
        for transaction_id, category, direction, amount_minor in fixtures:
            _seed_accepted_transaction(
                connection, transaction_id, direction=direction, amount_minor=amount_minor,
            )
            _add_ledger_dimensions(connection, transaction_id, category=category)

    categories = _analytics()["categories"]
    assert [row["category"] for row in categories] == ["sales", "rent"]
    assert categories[0]["income_minor"] == 2000
    assert categories[0]["expense_minor"] == 500
    assert categories[0]["count"] == 2
    assert categories[0]["percentage"] == Decimal("71.43")
    assert categories[1]["percentage"] == Decimal("28.57")


def test_payment_mode_summary_uses_known_modes_and_other(ingestion_repository):
    with ingestion_repository() as connection:
        fixtures = (
            ("mode-cash", "Cash", "income", 100),
            ("mode-upi", "UPI", "income", 200),
            ("mode-card", "Card", "expense", 50),
            ("mode-bank", "Bank", "expense", 75),
            ("mode-other", "Cheque", "expense", 25),
        )
        for transaction_id, payment_mode, direction, amount_minor in fixtures:
            _seed_accepted_transaction(
                connection, transaction_id, direction=direction, amount_minor=amount_minor,
            )
            _add_ledger_dimensions(connection, transaction_id, payment_mode=payment_mode)

    modes = _analytics()["payment_modes"]
    assert {row["payment_mode"] for row in modes} == {"Cash", "UPI", "Card", "Bank", "Other"}
    other = next(row for row in modes if row["payment_mode"] == "Other")
    assert other["count"] == 1
    assert other["amount_minor"] == 25
    assert next(row for row in modes if row["payment_mode"] == "UPI")["amount_minor"] == 200


def test_account_summary_is_scoped_to_selected_account(ingestion_repository):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(
            connection, "account-selected", amount_minor=900, direction="income",
        )
        connection.execute(
            """INSERT INTO financial_accounts
               (account_id,business_id,account_name,account_type,currency,account_status)
               VALUES ('analytics-other-account', ?, 'Other Account', 'cash', 'INR', 'active')""",
            (BUSINESS_ID,),
        )
        _seed_accepted_transaction(
            connection, "account-other", account_id="analytics-other-account",
            amount_minor=9000, direction="expense",
        )

    accounts = _analytics()["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["account_id"] == ACCOUNT_ID
    assert accounts[0]["transaction_count"] == 1
    assert accounts[0]["total_income_minor"] == 900
    assert accounts[0]["total_expense_minor"] == 0
    assert accounts[0]["net_cash_flow_minor"] == 900


def test_phase_two_empty_outputs_are_stable_lists(ingestion_repository):
    result = _analytics()
    assert result["trends"] == {"daily": [], "weekly": [], "monthly": []}
    assert result["categories"] == []
    assert result["payment_modes"] == []
    assert result["accounts"] == []


def test_date_filter_applies_to_trends_and_summaries(ingestion_repository):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(
            connection, "filter-in", transaction_date="2026-08-01", amount_minor=100,
        )
        _add_ledger_dimensions(connection, "filter-in", category="included", payment_mode="UPI")
        _seed_accepted_transaction(
            connection, "filter-out", transaction_date="2026-08-02", amount_minor=900,
        )
        _add_ledger_dimensions(connection, "filter-out", category="excluded", payment_mode="Card")

    result = _analytics(start_date="2026-08-01", end_date="2026-08-01")
    assert result["trends"]["daily"][0]["transaction_count"] == 1
    assert [row["category"] for row in result["categories"]] == ["included"]
    assert [row["payment_mode"] for row in result["payment_modes"]] == ["UPI"]


def test_summary_outputs_are_chart_and_export_ready(ingestion_repository):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(connection, "shape-row", amount_minor=123)
        _add_ledger_dimensions(connection, "shape-row", category="sales", payment_mode="Cash")

    result = _analytics()
    assert set(result) >= {"kpis", "trends", "categories", "payment_modes", "accounts"}
    assert set(result["trends"]) == {"daily", "weekly", "monthly"}
    assert all(isinstance(row, dict) for row in result["trends"]["daily"])
    assert all(isinstance(row, dict) for row in result["categories"])
    assert all(isinstance(row, dict) for row in result["payment_modes"])
    assert all(isinstance(row, dict) for row in result["accounts"])


def _seed_rich_equivalence_fixture(ingestion_repository):
    with ingestion_repository() as connection:
        connection.execute(
            "UPDATE financial_accounts SET opening_balance_minor=? WHERE account_id=?",
            (5000, ACCOUNT_ID),
        )
        fixtures = (
            ("rich-start", "2025-12-29", 101, "income", None, None),
            ("rich-jan-1", "2026-01-01", 203, "income", "", "cash"),
            ("rich-jan-4", "2026-01-04", 307, "expense", "Food", "Cheque"),
            ("rich-alpha", "2026-02-01", 700, "income", "Alpha", "Cash"),
            ("rich-beta", "2026-02-02", 700, "expense", "Beta", "UPI"),
            ("rich-income-only", "2026-05-10", 401, "income", "Sales", "UPI"),
            ("rich-expense-only", "2026-06-10", 409, "expense", "Rent", "Bank"),
            ("rich-same-a", "2026-07-15", 111, "income", "Misc A", "Cash"),
            ("rich-same-b", "2026-07-15", 222, "expense", "Misc B", "Card"),
            ("rich-same-c", "2026-07-15", 333, "income", "Misc C", "NEFT"),
            ("rich-dec-31", "2026-12-31", 503, "income", "Year", "UPI"),
            ("rich-end", "2027-01-03", 509, "expense", "Year", "Bank"),
        )
        for (
            transaction_id,
            transaction_date,
            amount_minor,
            direction,
            category,
            payment_mode,
        ) in fixtures:
            _seed_accepted_transaction(
                connection,
                transaction_id,
                transaction_date=transaction_date,
                amount_minor=amount_minor,
                direction=direction,
            )
            _add_ledger_dimensions(
                connection,
                transaction_id,
                category=category,
                payment_mode=payment_mode,
            )

        connection.execute(
            """INSERT INTO financial_accounts
               (account_id,business_id,account_name,account_type,currency,account_status)
               VALUES ('rich-other-account', ?, 'Other Account', 'bank', 'INR', 'active')""",
            (BUSINESS_ID,),
        )
        _seed_accepted_transaction(
            connection,
            "rich-other-account-row",
            account_id="rich-other-account",
            transaction_date="2026-07-15",
            amount_minor=9001,
        )

        connection.execute(
            """INSERT INTO businesses
               (business_id,business_name,business_status)
               VALUES ('rich-other-business','Other Business','active')"""
        )
        connection.execute(
            """INSERT INTO business_registry
               (business_id,user_id,business_name)
               VALUES ('rich-other-registry','legacy_owner_001','Other Registry')"""
        )
        connection.execute(
            """INSERT INTO financial_accounts
               (account_id,business_id,account_name,account_type,currency,account_status)
               VALUES ('rich-other-business-account','rich-other-business',
                       'Other Business Account','bank','INR','active')"""
        )
        _seed_accepted_transaction(
            connection,
            "rich-other-business-row",
            business_id="rich-other-business",
            registry_business_id="rich-other-registry",
            account_id="rich-other-business-account",
            transaction_date="2026-07-15",
            amount_minor=9002,
        )


def test_sql_aggregation_matches_legacy_full_contract(ingestion_repository):
    _seed_rich_equivalence_fixture(ingestion_repository)
    start_date = "2025-12-29"
    end_date = "2027-01-03"
    account = analytics_service._load_account(ACCOUNT_ID, BUSINESS_ID, "INR")
    rows = analytics_service._load_accepted_rows(
        business_id=BUSINESS_ID,
        account_id=ACCOUNT_ID,
        start_date=start_date,
        end_date=end_date,
    )
    expected = _legacy_contract(account_id=ACCOUNT_ID, account=account, rows=rows)

    actual = _analytics(start_date=start_date, end_date=end_date)

    for key in (
        "kpis",
        "trends",
        "categories",
        "payment_modes",
        "accounts",
        "transactions",
    ):
        assert actual[key] == expected[key]
    assert [
        row["category"]
        for row in actual["categories"]
        if row["category"] in {"Alpha", "Beta"}
    ] == ["Alpha", "Beta"]
    other = next(
        row for row in actual["payment_modes"] if row["payment_mode"] == "Other"
    )
    assert other["count"] == 4


def test_iso_week_boundaries_match_python_semantics(ingestion_repository):
    with ingestion_repository() as connection:
        for transaction_id, transaction_date, amount_minor in (
            ("iso-2025-12-29", "2025-12-29", 101),
            ("iso-2026-01-01", "2026-01-01", 102),
            ("iso-2026-01-04", "2026-01-04", 103),
            ("iso-2026-12-31", "2026-12-31", 104),
            ("iso-2027-01-03", "2027-01-03", 105),
        ):
            _seed_accepted_transaction(
                connection,
                transaction_id,
                transaction_date=transaction_date,
                amount_minor=amount_minor,
            )

    weekly = _analytics(
        start_date="2025-12-29",
        end_date="2027-01-03",
    )["trends"]["weekly"]

    assert [row["period"] for row in weekly] == ["2026-W01", "2026-W53"]
    assert weekly[0]["transaction_count"] == 3
    assert weekly[1]["transaction_count"] == 2


def test_empty_range_preserves_complete_contract(ingestion_repository):
    result = _analytics(start_date="2030-01-01", end_date="2030-01-31")

    assert result["kpis"] == {
        "total_income_minor": 0,
        "total_expense_minor": 0,
        "net_cash_flow_minor": 0,
        "transaction_count": 0,
        "average_transaction_minor": Decimal("0"),
        "largest_income_minor": None,
        "smallest_income_minor": None,
        "largest_expense_minor": None,
        "smallest_expense_minor": None,
        "opening_balance_minor": 0,
        "closing_balance_minor": 0,
        "income_expense_ratio": None,
        "savings_rate": None,
    }
    assert result["trends"] == {"daily": [], "weekly": [], "monthly": []}
    assert result["categories"] == []
    assert result["payment_modes"] == []
    assert result["accounts"] == []
    assert result["transactions"] == []


def test_currency_mismatch_fails_before_other_aggregate_queries(
    ingestion_repository, monkeypatch
):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(
            connection,
            "sql-currency-mismatch",
            amount_minor=1000,
            currency="USD",
        )

    monkeypatch.setattr(
        analytics_service,
        "_query_daily",
        lambda *args, **kwargs: pytest.fail(
            "daily aggregation ran after a currency mismatch"
        ),
    )
    with pytest.raises(
        analytics_service.AnalyticsError,
        match=r"^The selected analytics currency is inconsistent\.$",
    ):
        _analytics()


def test_kpi_parameter_order_uses_currency_first(ingestion_repository):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(
            connection,
            "parameter-order",
            amount_minor=1234,
            currency="INR",
        )

    result = _analytics()

    assert result["kpis"]["transaction_count"] == 1
    assert result["kpis"]["total_income_minor"] == 1234


def test_include_transactions_false_preserves_every_other_key(ingestion_repository):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(
            connection,
            "without-transactions",
            amount_minor=1234,
        )
        _add_ledger_dimensions(
            connection,
            "without-transactions",
            category="Sales",
            payment_mode="UPI",
        )

    included = _analytics(include_transactions=True)
    excluded = _analytics(include_transactions=False)

    assert excluded["transactions"] == []
    assert included["transactions"]
    assert {
        key: value for key, value in excluded.items() if key != "transactions"
    } == {key: value for key, value in included.items() if key != "transactions"}


def test_aggregate_queries_share_one_explicit_snapshot(
    ingestion_repository, monkeypatch
):
    with ingestion_repository() as connection:
        _seed_accepted_transaction(connection, "snapshot-row", amount_minor=100)

    observations = []
    originals = {
        name: getattr(analytics_service, name)
        for name in (
            "_query_kpis",
            "_query_daily",
            "_query_groups",
            "_query_transactions",
        )
    }

    for name, original in originals.items():
        def wrapper(*args, _name=name, _original=original, **kwargs):
            connection = args[0]
            observations.append((_name, id(connection), connection.in_transaction))
            return _original(*args, **kwargs)

        monkeypatch.setattr(analytics_service, name, wrapper)

    _analytics()

    assert [name for name, _, _ in observations] == [
        "_query_kpis",
        "_query_daily",
        "_query_groups",
        "_query_groups",
        "_query_transactions",
    ]
    assert len({connection_id for _, connection_id, _ in observations}) == 1
    assert all(in_transaction for _, _, in_transaction in observations)


def test_composite_index_is_used_for_kpi_scope(ingestion_repository):
    row_count = 3000
    with ingestion_repository() as connection:
        connection.execute(
            """INSERT INTO ingestion_attempts
               (attempt_id,business_id,registry_business_id,account_id,uploader_user_id,
                source_system,contract_version,currency,record_count,inserted_count,
                attempt_status,completed_at)
               VALUES ('analytics-plan-attempt', ?, ?, ?, 'owner_user_001', ?, ?,
                       'INR', ?, ?, 'completed', CURRENT_TIMESTAMP)""",
            (
                BUSINESS_ID,
                REGISTRY_BUSINESS_ID,
                ACCOUNT_ID,
                SOURCE_SYSTEM,
                CONTRACT_VERSION,
                row_count,
                row_count,
            ),
        )
        ledger_rows = []
        identity_rows = []
        for index in range(row_count):
            transaction_id = f"plan-transaction-{index:04d}"
            transaction_date = f"2026-08-{(index % 28) + 1:02d}"
            amount_minor = index + 1
            direction = "income" if index % 2 == 0 else "expense"
            ledger_rows.append(
                (
                    transaction_id,
                    REGISTRY_BUSINESS_ID,
                    transaction_date,
                    amount_minor / 100,
                    direction,
                    f"plan-ledger-hash-{index}",
                )
            )
            identity_rows.append(
                (
                    f"plan-identity-{index:04d}",
                    transaction_id,
                    BUSINESS_ID,
                    REGISTRY_BUSINESS_ID,
                    ACCOUNT_ID,
                    SOURCE_SYSTEM,
                    f"PLAN-{index}",
                    transaction_date,
                    amount_minor,
                    direction,
                    f"plan-canonical-hash-{index}",
                )
            )
        connection.executemany(
            """INSERT INTO transaction_general_ledger
               (transaction_id,business_id,user_id,transaction_date,amount,
                transaction_type,transaction_hash)
               VALUES (?, ?, 'legacy_owner_001', ?, ?, ?, ?)""",
            ledger_rows,
        )
        connection.executemany(
            """INSERT INTO ingested_transaction_identities
               (identity_id,transaction_id,attempt_id,business_id,
                registry_business_id,account_id,source_system,
                source_transaction_id,transaction_date,amount_minor,
                direction,currency,canonical_identity_hash)
               VALUES (?, ?, 'analytics-plan-attempt', ?, ?, ?, ?, ?, ?, ?, ?,
                       'INR', ?)""",
            identity_rows,
        )
        connection.execute("ANALYZE")
        plan = connection.execute(
            "EXPLAIN QUERY PLAN " + analytics_service._KPI_SQL,
            ("INR", BUSINESS_ID, ACCOUNT_ID, "2026-08-01", "2026-08-31"),
        ).fetchall()

    plan_text = "\n".join(str(row[3]) for row in plan)
    assert "idx_ingested_identity_business_account_date" in plan_text


def test_existing_database_receives_composite_index_on_initialize(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "old-finsight.db"
    schema_path = Path(__file__).resolve().parent.parent / "database" / "schema.sql"
    index_sql = """CREATE INDEX IF NOT EXISTS idx_ingested_identity_business_account_date
ON ingested_transaction_identities(business_id, account_id, transaction_date);
"""
    old_schema = schema_path.read_text(encoding="utf-8").replace(index_sql, "")
    with sqlite3.connect(database_path) as connection:
        connection.executescript(old_schema)
        before = connection.execute(
            """SELECT name FROM sqlite_master
               WHERE type='index'
                 AND name='idx_ingested_identity_business_account_date'"""
        ).fetchone()
    assert before is None

    monkeypatch.setattr(db, "DATABASE_PATH", database_path)
    db.initialize_database()

    with sqlite3.connect(database_path) as connection:
        after = connection.execute(
            """SELECT name FROM sqlite_master
               WHERE type='index'
                 AND name='idx_ingested_identity_business_account_date'"""
        ).fetchone()
    assert after == ("idx_ingested_identity_business_account_date",)
