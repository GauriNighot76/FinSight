from decimal import Decimal

import pytest

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
):
    return analytics_service.get_financial_analytics(
        session_token=session_token,
        business_id=business_id,
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        currency=currency,
    )


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
    assert categories[0]["income_count"] == 1
    assert categories[0]["expense_count"] == 1
    assert categories[0]["count"] == 2
    assert categories[0]["income_percentage"] == Decimal("100.00")
    assert categories[0]["expense_percentage"] == Decimal("33.33")
    assert categories[0]["percentage"] == Decimal("71.43")
    assert categories[1]["income_percentage"] == Decimal("0.00")
    assert categories[1]["expense_percentage"] == Decimal("66.67")
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
    assert other["expense_count"] == 1
    assert other["income_count"] == 0
    assert other["amount_minor"] == 25
    upi = next(row for row in modes if row["payment_mode"] == "UPI")
    assert upi["amount_minor"] == 200
    assert upi["income_minor"] == 200
    assert upi["expense_minor"] == 0
    assert upi["income_percentage"] == Decimal("66.67")
    assert upi["expense_percentage"] == Decimal("0.00")


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
