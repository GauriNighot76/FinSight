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
