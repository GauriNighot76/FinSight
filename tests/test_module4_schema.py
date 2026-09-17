import sqlite3

import pytest

from database import db


MODULE4_TABLES = {
    "business_registry_bridges",
    "ingestion_attempts",
    "ingested_transaction_identities",
}


def _table_names(connection):
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _insert_user(connection, user_id, email, role="standard_business"):
    connection.execute(
        """INSERT INTO users
           (user_id, username, email, contact_number, password_hash, role, account_status)
           VALUES (?, ?, ?, '9999999999', 'hash', ?, 'active')""",
        (user_id, user_id, email, role),
    )


def _insert_module2_business(connection, business_id):
    connection.execute(
        """INSERT INTO businesses
           (business_id, business_name, business_status)
           VALUES (?, ?, 'active')""",
        (business_id, business_id),
    )


def _insert_legacy_business(connection, business_id, owner_user_id):
    connection.execute(
        """INSERT INTO business_registry
           (business_id, user_id, business_name)
           VALUES (?, ?, ?)""",
        (business_id, owner_user_id, business_id),
    )


def _insert_account(connection, account_id, business_id, currency="INR"):
    connection.execute(
        """INSERT INTO financial_accounts
           (account_id, business_id, account_name, account_type, currency, account_status)
           VALUES (?, ?, 'Demo Account', 'bank', ?, 'active')""",
        (account_id, business_id, currency),
    )


def _insert_active_bridge(
    connection,
    bridge_id,
    business_id,
    registry_business_id,
    proposed_by_user_id,
    verified_by_user_id,
):
    connection.execute(
        """INSERT INTO business_registry_bridges
           (bridge_id, business_id, registry_business_id,
            proposed_by_user_id, verified_by_user_id,
            bridge_status, proposed_at, verified_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'active',
                   '2026-08-29T00:00:00+00:00',
                   '2026-08-29T00:01:00+00:00',
                   '2026-08-29T00:01:00+00:00')""",
        (
            bridge_id,
            business_id,
            registry_business_id,
            proposed_by_user_id,
            verified_by_user_id,
        ),
    )


def _insert_attempt(
    connection,
    attempt_id,
    business_id,
    registry_business_id,
    account_id,
    uploader_user_id,
    *,
    source_system="finsight_demo_bank_statement_v1",
    currency="INR",
    status="processing",
):
    connection.execute(
        """INSERT INTO ingestion_attempts
           (attempt_id, business_id, registry_business_id, account_id,
            uploader_user_id, source_system, contract_version, currency,
            record_count, inserted_count, duplicate_count, rejected_count,
            attempt_status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'v1', ?,
                   1, 0, 0, 0, ?, '2026-08-29T00:02:00+00:00')""",
        (
            attempt_id,
            business_id,
            registry_business_id,
            account_id,
            uploader_user_id,
            source_system,
            currency,
            status,
        ),
    )


@pytest.fixture
def module4_seed(isolated_test_database):
    """Create only the minimum authoritative relationships needed by D18 tests."""
    with isolated_test_database() as connection:
        _insert_user(
            connection,
            "demo_owner_001",
            "demo-owner@example.test",
        )
        _insert_user(
            connection,
            "demo_admin_001",
            "demo-admin@example.test",
            role="administrator",
        )
        _insert_module2_business(connection, "demo_business_001")
        connection.execute(
            """INSERT INTO business_memberships
               (membership_id, business_id, user_id, membership_role, membership_status)
               VALUES ('demo_membership_001', 'demo_business_001',
                       'demo_owner_001', 'owner', 'active')"""
        )
        _insert_legacy_business(
            connection,
            "legacy_demo_business_001",
            "demo_owner_001",
        )
        _insert_account(
            connection,
            "demo_account_001",
            "demo_business_001",
            "INR",
        )
    return isolated_test_database


def test_module4_tables_exist(isolated_test_database):
    with isolated_test_database() as connection:
        assert MODULE4_TABLES <= _table_names(connection)


def test_bridge_foreign_keys(module4_seed):
    with module4_seed() as connection:
        _insert_active_bridge(
            connection,
            "bridge_ok",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_owner_001",
            "demo_admin_001",
        )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_active_bridge(
                connection,
                "bridge_missing_module2",
                "missing_business",
                "legacy_demo_business_001",
                "demo_owner_001",
                "demo_admin_001",
            )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_active_bridge(
                connection,
                "bridge_missing_registry",
                "demo_business_001",
                "missing_registry",
                "demo_owner_001",
                "demo_admin_001",
            )


def test_bridge_status_constraint(module4_seed):
    with module4_seed() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO business_registry_bridges
                   (bridge_id, business_id, registry_business_id,
                    proposed_by_user_id, bridge_status, proposed_at, updated_at)
                   VALUES ('bad_status', 'demo_business_001',
                           'legacy_demo_business_001', 'demo_owner_001',
                           'invented_status',
                           '2026-08-29T00:00:00+00:00',
                           '2026-08-29T00:00:00+00:00')"""
            )


def test_active_bridge_requires_verification(module4_seed):
    with module4_seed() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO business_registry_bridges
                   (bridge_id, business_id, registry_business_id,
                    proposed_by_user_id, bridge_status, proposed_at, updated_at)
                   VALUES ('unverified_active', 'demo_business_001',
                           'legacy_demo_business_001', 'demo_owner_001',
                           'active',
                           '2026-08-29T00:00:00+00:00',
                           '2026-08-29T00:00:00+00:00')"""
            )


def test_only_one_active_bridge_per_module2_business(module4_seed):
    with module4_seed() as connection:
        _insert_legacy_business(
            connection,
            "legacy_demo_business_002",
            "demo_owner_001",
        )
        _insert_active_bridge(
            connection,
            "bridge_1",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_owner_001",
            "demo_admin_001",
        )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_active_bridge(
                connection,
                "bridge_2",
                "demo_business_001",
                "legacy_demo_business_002",
                "demo_owner_001",
                "demo_admin_001",
            )


def test_only_one_active_bridge_per_legacy_business(module4_seed):
    with module4_seed() as connection:
        _insert_module2_business(connection, "demo_business_002")
        _insert_active_bridge(
            connection,
            "bridge_1",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_owner_001",
            "demo_admin_001",
        )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_active_bridge(
                connection,
                "bridge_2",
                "demo_business_002",
                "legacy_demo_business_001",
                "demo_owner_001",
                "demo_admin_001",
            )


def test_disabled_bridge_does_not_consume_active_uniqueness(module4_seed):
    with module4_seed() as connection:
        connection.execute(
            """INSERT INTO business_registry_bridges
               (bridge_id, business_id, registry_business_id,
                proposed_by_user_id, verified_by_user_id,
                bridge_status, proposed_at, verified_at, updated_at)
               VALUES ('old_bridge', 'demo_business_001',
                       'legacy_demo_business_001', 'demo_owner_001',
                       'demo_admin_001', 'disabled',
                       '2026-08-29T00:00:00+00:00',
                       '2026-08-29T00:01:00+00:00',
                       '2026-08-29T00:02:00+00:00')"""
        )

        _insert_active_bridge(
            connection,
            "new_bridge",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_owner_001",
            "demo_admin_001",
        )


def test_ingestion_attempt_foreign_keys(module4_seed):
    with module4_seed() as connection:
        _insert_attempt(
            connection,
            "attempt_ok",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_account_001",
            "demo_owner_001",
        )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_attempt(
                connection,
                "attempt_missing_account",
                "demo_business_001",
                "legacy_demo_business_001",
                "missing_account",
                "demo_owner_001",
            )


def test_ingestion_attempt_count_constraints(module4_seed):
    with module4_seed() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO ingestion_attempts
                   (attempt_id, business_id, registry_business_id, account_id,
                    uploader_user_id, source_system, contract_version, currency,
                    record_count, inserted_count, duplicate_count, rejected_count,
                    attempt_status, created_at)
                   VALUES ('bad_count', 'demo_business_001',
                           'legacy_demo_business_001', 'demo_account_001',
                           'demo_owner_001', 'finsight_demo_bank_statement_v1',
                           'v1', 'INR', -1, 0, 0, 0, 'processing',
                           '2026-08-29T00:02:00+00:00')"""
            )


def test_ingestion_attempt_status_constraint(module4_seed):
    with module4_seed() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            _insert_attempt(
                connection,
                "attempt_bad_status",
                "demo_business_001",
                "legacy_demo_business_001",
                "demo_account_001",
                "demo_owner_001",
                status="invented_status",
            )


def test_completed_attempt_requires_completed_at(module4_seed):
    with module4_seed() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            _insert_attempt(
                connection,
                "completed_without_time",
                "demo_business_001",
                "legacy_demo_business_001",
                "demo_account_001",
                "demo_owner_001",
                status="completed",
            )


def test_ingestion_attempt_currency_format_constraint(module4_seed):
    with module4_seed() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            _insert_attempt(
                connection,
                "attempt_bad_currency",
                "demo_business_001",
                "legacy_demo_business_001",
                "demo_account_001",
                "demo_owner_001",
                currency="inr",
            )


def test_ingestion_attempt_source_system_is_controlled(module4_seed):
    with module4_seed() as connection:
        _insert_attempt(
            connection,
            "attempt_allowed_source",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_account_001",
            "demo_owner_001",
            source_system="finsight_demo_bank_statement_v1",
        )

        with pytest.raises(sqlite3.IntegrityError):
            _insert_attempt(
                connection,
                "attempt_unknown_source",
                "demo_business_001",
                "legacy_demo_business_001",
                "demo_account_001",
                "demo_owner_001",
                source_system="unknown_source",
            )


def test_ingested_identity_uses_integer_minor_units(module4_seed):
    with module4_seed() as connection:
        _insert_attempt(
            connection,
            "attempt_1",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_account_001",
            "demo_owner_001",
        )
        connection.execute(
            """INSERT INTO transaction_general_ledger
               (transaction_id, business_id, user_id, transaction_date,
                amount, transaction_type, transaction_hash)
               VALUES ('tx_1', 'legacy_demo_business_001', 'demo_owner_001',
                       '2026-08-29', 123.45, 'income', 'legacy-hash-1')"""
        )
        connection.execute(
            """INSERT INTO ingested_transaction_identities
               (identity_id, transaction_id, attempt_id, business_id,
                registry_business_id, account_id, source_system,
                source_transaction_id, transaction_date, amount_minor,
                direction, currency, canonical_identity_hash, created_at)
               VALUES ('identity_1', 'tx_1', 'attempt_1',
                       'demo_business_001', 'legacy_demo_business_001',
                       'demo_account_001', 'finsight_demo_bank_statement_v1',
                       'src_tx_1', '2026-08-29', 12345, 'income', 'INR',
                       'canonical-hash-1', '2026-08-29T00:03:00+00:00')"""
        )

        row = connection.execute(
            """SELECT amount_minor, typeof(amount_minor)
               FROM ingested_transaction_identities
               WHERE identity_id='identity_1'"""
        ).fetchone()

        assert row[0] == 12345
        assert row[1] == "integer"


def test_ingested_identity_rejects_negative_amount_minor(module4_seed):
    with module4_seed() as connection:
        _insert_attempt(
            connection,
            "attempt_1",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_account_001",
            "demo_owner_001",
        )
        connection.execute(
            """INSERT INTO transaction_general_ledger
               (transaction_id, business_id, user_id, transaction_date,
                amount, transaction_type, transaction_hash)
               VALUES ('tx_1', 'legacy_demo_business_001', 'demo_owner_001',
                       '2026-08-29', 1.00, 'income', 'legacy-hash-1')"""
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO ingested_transaction_identities
                   (identity_id, transaction_id, attempt_id, business_id,
                    registry_business_id, account_id, source_system,
                    source_transaction_id, transaction_date, amount_minor,
                    direction, currency, canonical_identity_hash, created_at)
                   VALUES ('identity_bad', 'tx_1', 'attempt_1',
                           'demo_business_001', 'legacy_demo_business_001',
                           'demo_account_001', 'finsight_demo_bank_statement_v1',
                           'src_tx_bad', '2026-08-29', -1, 'income', 'INR',
                           'canonical-hash-bad',
                           '2026-08-29T00:03:00+00:00')"""
            )


def test_ingested_identity_direction_constraint(module4_seed):
    with module4_seed() as connection:
        _insert_attempt(
            connection,
            "attempt_1",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_account_001",
            "demo_owner_001",
        )
        connection.execute(
            """INSERT INTO transaction_general_ledger
               (transaction_id, business_id, user_id, transaction_date,
                amount, transaction_type, transaction_hash)
               VALUES ('tx_1', 'legacy_demo_business_001', 'demo_owner_001',
                       '2026-08-29', 1.00, 'income', 'legacy-hash-1')"""
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO ingested_transaction_identities
                   (identity_id, transaction_id, attempt_id, business_id,
                    registry_business_id, account_id, source_system,
                    source_transaction_id, transaction_date, amount_minor,
                    direction, currency, canonical_identity_hash, created_at)
                   VALUES ('identity_bad_direction', 'tx_1', 'attempt_1',
                           'demo_business_001', 'legacy_demo_business_001',
                           'demo_account_001', 'finsight_demo_bank_statement_v1',
                           'src_tx_bad_direction', '2026-08-29', 100,
                           'debit', 'INR', 'canonical-hash-direction',
                           '2026-08-29T00:03:00+00:00')"""
            )


def test_canonical_identity_hash_allows_distinct_source_transactions(module4_seed):
    with module4_seed() as connection:
        _insert_attempt(
            connection,
            "attempt_1",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_account_001",
            "demo_owner_001",
        )

        for tx_id, tx_hash in (
            ("tx_1", "legacy-hash-1"),
            ("tx_2", "legacy-hash-2"),
        ):
            connection.execute(
                """INSERT INTO transaction_general_ledger
                   (transaction_id, business_id, user_id, transaction_date,
                    amount, transaction_type, transaction_hash)
                   VALUES (?, 'legacy_demo_business_001', 'demo_owner_001',
                           '2026-08-29', 10.00, 'income', ?)""",
                (tx_id, tx_hash),
            )

        connection.execute(
            """INSERT INTO ingested_transaction_identities
               (identity_id, transaction_id, attempt_id, business_id,
                registry_business_id, account_id, source_system,
                source_transaction_id, transaction_date, amount_minor,
                direction, currency, canonical_identity_hash, created_at)
               VALUES ('identity_1', 'tx_1', 'attempt_1',
                       'demo_business_001', 'legacy_demo_business_001',
                       'demo_account_001', 'finsight_demo_bank_statement_v1',
                       'src_tx_1', '2026-08-29', 1000, 'income', 'INR',
                       'same-canonical-hash',
                       '2026-08-29T00:03:00+00:00')"""
        )

        connection.execute(
                """INSERT INTO ingested_transaction_identities
                   (identity_id, transaction_id, attempt_id, business_id,
                    registry_business_id, account_id, source_system,
                    source_transaction_id, transaction_date, amount_minor,
                    direction, currency, canonical_identity_hash, created_at)
                   VALUES ('identity_2', 'tx_2', 'attempt_1',
                           'demo_business_001', 'legacy_demo_business_001',
                           'demo_account_001', 'finsight_demo_bank_statement_v1',
                           'src_tx_2', '2026-08-29', 1000, 'income', 'INR',
                           'same-canonical-hash',
                           '2026-08-29T00:04:00+00:00')"""
            )
        count = connection.execute(
            "SELECT COUNT(*) FROM ingested_transaction_identities"
        ).fetchone()[0]
        assert count == 2


def test_source_identity_scope_is_unique(module4_seed):
    with module4_seed() as connection:
        _insert_attempt(
            connection,
            "attempt_1",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_account_001",
            "demo_owner_001",
        )

        for tx_id, tx_hash in (
            ("tx_1", "legacy-hash-1"),
            ("tx_2", "legacy-hash-2"),
        ):
            connection.execute(
                """INSERT INTO transaction_general_ledger
                   (transaction_id, business_id, user_id, transaction_date,
                    amount, transaction_type, transaction_hash)
                   VALUES (?, 'legacy_demo_business_001', 'demo_owner_001',
                           '2026-08-29', 10.00, 'income', ?)""",
                (tx_id, tx_hash),
            )

        connection.execute(
            """INSERT INTO ingested_transaction_identities
               (identity_id, transaction_id, attempt_id, business_id,
                registry_business_id, account_id, source_system,
                source_transaction_id, transaction_date, amount_minor,
                direction, currency, canonical_identity_hash, created_at)
               VALUES ('identity_1', 'tx_1', 'attempt_1',
                       'demo_business_001', 'legacy_demo_business_001',
                       'demo_account_001', 'finsight_demo_bank_statement_v1',
                       'src_same', '2026-08-29', 1000, 'income', 'INR',
                       'canonical-hash-1',
                       '2026-08-29T00:03:00+00:00')"""
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO ingested_transaction_identities
                   (identity_id, transaction_id, attempt_id, business_id,
                    registry_business_id, account_id, source_system,
                    source_transaction_id, transaction_date, amount_minor,
                    direction, currency, canonical_identity_hash, created_at)
                   VALUES ('identity_2', 'tx_2', 'attempt_1',
                           'demo_business_001', 'legacy_demo_business_001',
                           'demo_account_001', 'finsight_demo_bank_statement_v1',
                           'src_same', '2026-08-29', 1000, 'income', 'INR',
                           'canonical-hash-2',
                           '2026-08-29T00:04:00+00:00')"""
            )



def test_source_transaction_id_may_be_absent(module4_seed):
    with module4_seed() as connection:
        _insert_attempt(
            connection,
            "attempt_no_source_id",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_account_001",
            "demo_owner_001",
        )
        connection.execute(
            """INSERT INTO transaction_general_ledger
               (transaction_id, business_id, user_id, transaction_date,
                amount, transaction_type, transaction_hash)
               VALUES ('tx_no_source_id', 'legacy_demo_business_001',
                       'demo_owner_001', '2026-08-29', 10.00, 'income',
                       'legacy-hash-no-source-id')"""
        )
        connection.execute(
            """INSERT INTO ingested_transaction_identities
               (identity_id, transaction_id, attempt_id, business_id,
                registry_business_id, account_id, source_system,
                source_transaction_id, transaction_date, amount_minor,
                direction, currency, canonical_identity_hash, created_at)
               VALUES ('identity_no_source_id', 'tx_no_source_id',
                       'attempt_no_source_id', 'demo_business_001',
                       'legacy_demo_business_001', 'demo_account_001',
                       'finsight_demo_bank_statement_v1', NULL,
                       '2026-08-29', 1000, 'income', 'INR',
                       'canonical-hash-no-source-id',
                       '2026-08-29T00:03:00+00:00')"""
        )
        assert connection.execute(
            "SELECT source_transaction_id FROM ingested_transaction_identities "
            "WHERE identity_id='identity_no_source_id'"
        ).fetchone()[0] is None


def test_parent_attempt_delete_is_restricted(module4_seed):
    with module4_seed() as connection:
        _insert_attempt(
            connection,
            "attempt_parent",
            "demo_business_001",
            "legacy_demo_business_001",
            "demo_account_001",
            "demo_owner_001",
        )
        connection.execute(
            """INSERT INTO ingestion_attempts
               (attempt_id, parent_attempt_id, business_id,
                registry_business_id, account_id, uploader_user_id,
                source_system, contract_version, currency, record_count,
                inserted_count, duplicate_count, rejected_count,
                attempt_status, created_at)
               VALUES ('attempt_retry', 'attempt_parent', 'demo_business_001',
                       'legacy_demo_business_001', 'demo_account_001',
                       'demo_owner_001', 'finsight_demo_bank_statement_v1',
                       'v1', 'INR', 1, 0, 0, 0, 'processing',
                       '2026-08-29T00:05:00+00:00')"""
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM ingestion_attempts WHERE attempt_id='attempt_parent'"
            )

def test_module4_migration_is_idempotent(tmp_path, monkeypatch):
    database_path = tmp_path / "module4.db"
    monkeypatch.setattr(db, "DATABASE_PATH", database_path)

    db.initialize_database()
    db.initialize_database()

    with sqlite3.connect(database_path) as connection:
        assert MODULE4_TABLES <= _table_names(connection)


def test_module4_migration_preserves_existing_module0_to_3_data(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "pre_module4.db"
    monkeypatch.setattr(db, "DATABASE_PATH", database_path)

    db.initialize_database()

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_user(
            connection,
            "usr_keep",
            "keep@example.com",
        )
        _insert_module2_business(connection, "biz_keep")
        connection.execute(
            """INSERT INTO business_memberships
               (membership_id, business_id, user_id,
                membership_role, membership_status)
               VALUES ('mem_keep', 'biz_keep', 'usr_keep',
                       'owner', 'active')"""
        )
        _insert_legacy_business(connection, "legacy_keep", "usr_keep")
        _insert_account(connection, "acc_keep", "biz_keep", "INR")
        connection.execute(
            """INSERT INTO transaction_general_ledger
               (transaction_id, business_id, user_id, transaction_date,
                amount, transaction_type, transaction_hash)
               VALUES ('tx_keep', 'legacy_keep', 'usr_keep',
                       '2026-01-01', 100.50, 'income', 'legacy-keep-hash')"""
        )

    db.initialize_database()

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT email FROM users WHERE user_id='usr_keep'"
        ).fetchone()[0] == "keep@example.com"
        assert connection.execute(
            "SELECT membership_role FROM business_memberships "
            "WHERE membership_id='mem_keep'"
        ).fetchone()[0] == "owner"
        assert connection.execute(
            "SELECT currency FROM financial_accounts WHERE account_id='acc_keep'"
        ).fetchone()[0] == "INR"
        assert connection.execute(
            "SELECT amount FROM transaction_general_ledger "
            "WHERE transaction_id='tx_keep'"
        ).fetchone()[0] == 100.50
        assert MODULE4_TABLES <= _table_names(connection)


def test_module4_migration_does_not_backfill_legacy_transactions(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "legacy_no_backfill.db"
    monkeypatch.setattr(db, "DATABASE_PATH", database_path)

    db.initialize_database()

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _insert_user(
            connection,
            "legacy_owner",
            "legacy-owner@example.com",
        )
        _insert_legacy_business(
            connection,
            "legacy_business",
            "legacy_owner",
        )
        connection.execute(
            """INSERT INTO transaction_general_ledger
               (transaction_id, business_id, user_id, transaction_date,
                amount, transaction_type, transaction_hash)
               VALUES ('legacy_tx', 'legacy_business', 'legacy_owner',
                       '2026-01-01', 50.00, 'expense',
                       'legacy-transaction-hash')"""
        )

    db.initialize_database()

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            """SELECT COUNT(*)
               FROM ingested_transaction_identities
               WHERE transaction_id='legacy_tx'"""
        ).fetchone()[0] == 0
