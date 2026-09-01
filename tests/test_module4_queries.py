import sqlite3

import pytest

from database import queries


SOURCE_SYSTEM = "finsight_demo_bank_statement_v1"
CONTRACT_VERSION = "finsight_ingestion_v1"


def _insert_user(connection, user_id, role="standard_business", status="active"):
    connection.execute(
        """INSERT INTO users
           (user_id, username, email, contact_number, password_hash,
            role, account_status)
           VALUES (?, ?, ?, '9999999999', 'hash', ?, ?)""",
        (user_id, user_id, f"{user_id}@example.test", role, status),
    )


def _insert_membership(
    connection,
    membership_id,
    business_id,
    user_id,
    role="owner",
    status="active",
):
    connection.execute(
        """INSERT INTO business_memberships
           (membership_id, business_id, user_id, membership_role,
            membership_status)
           VALUES (?, ?, ?, ?, ?)""",
        (membership_id, business_id, user_id, role, status),
    )


def _insert_bridge(
    connection,
    bridge_id,
    business_id="demo_business_001",
    registry_business_id="legacy_demo_business_001",
    status="active",
    verified=True,
):
    verifier = "admin_user_001" if verified else None
    verified_at = "2026-08-29T00:01:00+00:00" if verified else None
    connection.execute(
        """INSERT INTO business_registry_bridges
           (bridge_id, business_id, registry_business_id,
            proposed_by_user_id, verified_by_user_id, bridge_status,
            proposed_at, verified_at, updated_at)
           VALUES (?, ?, ?, 'owner_user_001', ?, ?,
                   '2026-08-29T00:00:00+00:00', ?,
                   '2026-08-29T00:01:00+00:00')""",
        (
            bridge_id,
            business_id,
            registry_business_id,
            verifier,
            status,
            verified_at,
        ),
    )


@pytest.fixture
def module4_repository_seed(isolated_test_database):
    with isolated_test_database() as connection:
        _insert_user(connection, "owner_user_001")
        _insert_user(connection, "manager_user_001")
        _insert_user(connection, "member_user_001")
        _insert_user(connection, "admin_user_001", role="administrator")
        _insert_user(connection, "legacy_owner_001")

        connection.executemany(
            """INSERT INTO businesses (business_id, business_name, business_status)
               VALUES (?, ?, ?)""",
            [
                ("demo_business_001", "Controlled Demo", "active"),
                ("other_business_001", "Other Business", "active"),
                ("disabled_business_001", "Disabled Business", "disabled"),
            ],
        )
        _insert_membership(
            connection,
            "membership_owner",
            "demo_business_001",
            "owner_user_001",
            "owner",
        )
        _insert_membership(
            connection,
            "membership_manager",
            "demo_business_001",
            "manager_user_001",
            "manager",
        )
        _insert_membership(
            connection,
            "membership_member",
            "demo_business_001",
            "member_user_001",
            "member",
        )
        _insert_membership(
            connection,
            "membership_disabled",
            "demo_business_001",
            "admin_user_001",
            "owner",
            "disabled",
        )
        connection.execute(
            """INSERT INTO business_registry
               (business_id, user_id, business_name)
               VALUES ('legacy_demo_business_001', 'legacy_owner_001',
                       'Controlled Legacy Demo')"""
        )
        connection.executemany(
            """INSERT INTO financial_accounts
               (account_id, business_id, account_name, account_type,
                currency, account_status)
               VALUES (?, ?, ?, 'bank', ?, ?)""",
            [
                ("demo_account_001", "demo_business_001", "Demo Account", "INR", "active"),
                ("disabled_account_001", "demo_business_001", "Disabled Account", "INR", "disabled"),
                ("other_account_001", "other_business_001", "Other Account", "USD", "active"),
            ],
        )
        _insert_bridge(connection, "bridge_active")
    return isolated_test_database


def test_active_business_lookup_is_status_scoped(module4_repository_seed):
    row = queries.get_active_business("demo_business_001")

    assert row["business_id"] == "demo_business_001"
    assert row["business_status"] == "active"
    assert queries.get_active_business("disabled_business_001") is None
    assert queries.get_active_business("missing_business") is None


def test_active_membership_lookup_is_user_and_status_scoped(module4_repository_seed):
    owner = queries.get_active_business_membership(
        "demo_business_001", "owner_user_001"
    )

    assert owner["membership_role"] == "owner"
    assert owner["membership_status"] == "active"
    assert queries.get_active_business_membership(
        "demo_business_001", "admin_user_001"
    ) is None
    assert queries.get_active_business_membership(
        "other_business_001", "owner_user_001"
    ) is None


def test_active_financial_account_requires_exact_business(module4_repository_seed):
    row = queries.get_active_financial_account(
        "demo_account_001", "demo_business_001"
    )

    assert row["account_id"] == "demo_account_001"
    assert row["currency"] == "INR"
    assert queries.get_active_financial_account(
        "demo_account_001", "other_business_001"
    ) is None
    assert queries.get_active_financial_account(
        "other_account_001", "demo_business_001"
    ) is None
    assert queries.get_active_financial_account(
        "disabled_account_001", "demo_business_001"
    ) is None
    assert queries.get_active_financial_account(
        "missing_account", "demo_business_001"
    ) is None


@pytest.mark.parametrize("status", ["pending", "rejected", "disabled"])
def test_inactive_bridges_are_not_returned(module4_repository_seed, status):
    with module4_repository_seed() as connection:
        connection.execute(
            "UPDATE business_registry_bridges SET bridge_status=?",
            (status,),
        )

    assert queries.get_active_bridge("demo_business_001") is None


def test_active_bridge_returns_exact_registry_mapping(module4_repository_seed):
    row = queries.get_active_bridge("demo_business_001")

    assert row["bridge_id"] == "bridge_active"
    assert row["business_id"] == "demo_business_001"
    assert row["registry_business_id"] == "legacy_demo_business_001"


def test_registry_business_and_owner_lookup_are_exact(module4_repository_seed):
    row = queries.get_registry_business("legacy_demo_business_001")

    assert row["business_id"] == "legacy_demo_business_001"
    assert queries.get_registry_owner("legacy_demo_business_001") == "legacy_owner_001"
    assert queries.get_registry_business("missing_registry") is None
    assert queries.get_registry_owner("missing_registry") is None


def test_create_ingestion_attempt_starts_processing_with_context(module4_repository_seed):
    attempt_id = queries.create_ingestion_attempt(
        business_id="demo_business_001",
        registry_business_id="legacy_demo_business_001",
        account_id="demo_account_001",
        uploader_user_id="manager_user_001",
        source_system=SOURCE_SYSTEM,
        contract_version=CONTRACT_VERSION,
        currency="INR",
        record_count=2,
    )

    with module4_repository_seed() as connection:
        row = connection.execute(
            "SELECT * FROM ingestion_attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()

    assert attempt_id.startswith("att_")
    assert row["attempt_status"] == "processing"
    assert row["business_id"] == "demo_business_001"
    assert row["registry_business_id"] == "legacy_demo_business_001"
    assert row["account_id"] == "demo_account_001"
    assert row["uploader_user_id"] == "manager_user_001"
    assert row["record_count"] == 2
    assert row["inserted_count"] == 0
    assert row["duplicate_count"] == 0
    assert row["rejected_count"] == 0


def test_retry_attempt_preserves_parent_attempt_id(module4_repository_seed):
    parent_id = queries.create_ingestion_attempt(
        business_id="demo_business_001",
        registry_business_id="legacy_demo_business_001",
        account_id="demo_account_001",
        uploader_user_id="owner_user_001",
        source_system=SOURCE_SYSTEM,
        contract_version=CONTRACT_VERSION,
        currency="INR",
        record_count=1,
    )
    retry_id = queries.create_ingestion_attempt(
        business_id="demo_business_001",
        registry_business_id="legacy_demo_business_001",
        account_id="demo_account_001",
        uploader_user_id="owner_user_001",
        source_system=SOURCE_SYSTEM,
        contract_version=CONTRACT_VERSION,
        currency="INR",
        record_count=1,
        parent_attempt_id=parent_id,
    )

    assert retry_id != parent_id
    with module4_repository_seed() as connection:
        row = connection.execute(
            "SELECT parent_attempt_id FROM ingestion_attempts WHERE attempt_id=?",
            (retry_id,),
        ).fetchone()
    assert row["parent_attempt_id"] == parent_id


def test_complete_attempt_updates_counts_and_is_one_way(module4_repository_seed):
    with module4_repository_seed() as connection:
        connection.execute(
            """INSERT INTO ingestion_attempts
               (attempt_id, business_id, registry_business_id, account_id,
                uploader_user_id, source_system, contract_version, currency,
                record_count, attempt_status)
               VALUES ('attempt_complete', 'demo_business_001',
                       'legacy_demo_business_001', 'demo_account_001',
                       'owner_user_001', ?, ?, 'INR', 3, 'processing')""",
            (SOURCE_SYSTEM, CONTRACT_VERSION),
        )

    assert queries.complete_ingestion_attempt(
        "attempt_complete", inserted_count=1, duplicate_count=1, rejected_count=1
    )
    assert not queries.complete_ingestion_attempt(
        "attempt_complete", inserted_count=3, duplicate_count=0, rejected_count=0
    )

    with module4_repository_seed() as connection:
        row = connection.execute(
            "SELECT * FROM ingestion_attempts WHERE attempt_id='attempt_complete'"
        ).fetchone()
    assert row["attempt_status"] == "completed"
    assert (row["inserted_count"], row["duplicate_count"], row["rejected_count"]) == (1, 1, 1)
    assert row["completed_at"] is not None
    assert row["public_error_code"] is None
    assert row["public_error_message"] is None


def test_fail_attempt_updates_safe_error_and_is_one_way(module4_repository_seed):
    with module4_repository_seed() as connection:
        connection.execute(
            """INSERT INTO ingestion_attempts
               (attempt_id, business_id, registry_business_id, account_id,
                uploader_user_id, source_system, contract_version, currency,
                record_count, attempt_status)
               VALUES ('attempt_fail', 'demo_business_001',
                       'legacy_demo_business_001', 'demo_account_001',
                       'owner_user_001', ?, ?, 'INR', 1, 'processing')""",
            (SOURCE_SYSTEM, CONTRACT_VERSION),
        )

    assert queries.fail_ingestion_attempt(
        "attempt_fail",
        inserted_count=0,
        duplicate_count=0,
        rejected_count=1,
        public_error_code="INGESTION_STORAGE_FAILED",
        public_error_message="Ingestion could not be completed.",
    )
    assert not queries.complete_ingestion_attempt(
        "attempt_fail", inserted_count=1, duplicate_count=0, rejected_count=0
    )

    with module4_repository_seed() as connection:
        row = connection.execute(
            "SELECT * FROM ingestion_attempts WHERE attempt_id='attempt_fail'"
        ).fetchone()
    assert row["attempt_status"] == "failed"
    assert row["public_error_code"] == "INGESTION_STORAGE_FAILED"
    assert row["public_error_message"] == "Ingestion could not be completed."
    assert row["completed_at"] is not None


def _seed_identity(connection, source_transaction_id, canonical_hash):
    connection.execute(
        """INSERT INTO ingestion_attempts
           (attempt_id, business_id, registry_business_id, account_id,
            uploader_user_id, source_system, contract_version, currency,
            record_count, attempt_status)
           VALUES ('attempt_identity', 'demo_business_001',
                   'legacy_demo_business_001', 'demo_account_001',
                   'owner_user_001', ?, ?, 'INR', 1, 'processing')""",
        (SOURCE_SYSTEM, CONTRACT_VERSION),
    )
    connection.execute(
        """INSERT INTO transaction_general_ledger
           (transaction_id, business_id, user_id, transaction_date,
            amount, transaction_type, transaction_hash)
           VALUES ('transaction_identity', 'legacy_demo_business_001',
                   'legacy_owner_001', '2026-08-30', 12.34,
                   'income', 'legacy-hash')"""
    )
    connection.execute(
        """INSERT INTO ingested_transaction_identities
           (identity_id, transaction_id, attempt_id, business_id,
            registry_business_id, account_id, source_system,
            source_transaction_id, transaction_date, amount_minor,
            direction, currency, canonical_identity_hash)
           VALUES ('identity_seed', 'transaction_identity', 'attempt_identity',
                   'demo_business_001', 'legacy_demo_business_001',
                   'demo_account_001', ?, ?, '2026-08-30', 1234,
                   'income', 'INR', ?)""",
        (SOURCE_SYSTEM, source_transaction_id, canonical_hash),
    )


def test_identity_lookup_by_hash_is_business_scoped(module4_repository_seed):
    with module4_repository_seed() as connection:
        _seed_identity(connection, "source-001", "canonical-001")

    row = queries.find_identity_by_hash(
        business_id="demo_business_001",
        registry_business_id="legacy_demo_business_001",
        account_id="demo_account_001",
        source_system=SOURCE_SYSTEM,
        canonical_identity_hash="canonical-001",
    )
    assert row["identity_id"] == "identity_seed"
    assert queries.find_identity_by_hash(
        business_id="other_business_001",
        registry_business_id="legacy_demo_business_001",
        account_id="demo_account_001",
        source_system=SOURCE_SYSTEM,
        canonical_identity_hash="canonical-001",
    ) is None


def test_identity_lookup_by_optional_source_id_is_scoped(module4_repository_seed):
    with module4_repository_seed() as connection:
        _seed_identity(connection, "source-001", "canonical-001")

    row = queries.find_identity_by_source(
        business_id="demo_business_001",
        registry_business_id="legacy_demo_business_001",
        account_id="demo_account_001",
        source_system=SOURCE_SYSTEM,
        source_transaction_id="source-001",
    )
    assert row["identity_id"] == "identity_seed"
    assert queries.find_identity_by_source(
        business_id="demo_business_001",
        registry_business_id="legacy_demo_business_001",
        account_id="other_account_001",
        source_system=SOURCE_SYSTEM,
        source_transaction_id="source-001",
    ) is None
    assert queries.find_identity_by_source(
        business_id="demo_business_001",
        registry_business_id="legacy_demo_business_001",
        account_id="demo_account_001",
        source_system=SOURCE_SYSTEM,
        source_transaction_id=None,
    ) is None


def test_ledger_insert_preserves_legacy_business_and_owner(module4_repository_seed):
    transaction_id = queries.insert_ledger_transaction(
        registry_business_id="legacy_demo_business_001",
        legacy_owner_user_id="legacy_owner_001",
        transaction_date="2026-08-31",
        amount="12.34",
        transaction_type="expense",
        transaction_hash="ledger-hash-001",
        category="Supplies",
        payment_mode="bank_transfer",
        description="Synthetic purchase",
    )

    with module4_repository_seed() as connection:
        row = connection.execute(
            "SELECT * FROM transaction_general_ledger WHERE transaction_id=?",
            (transaction_id,),
        ).fetchone()
    assert transaction_id.startswith("txn_")
    assert row["business_id"] == "legacy_demo_business_001"
    assert row["user_id"] == "legacy_owner_001"
    assert row["transaction_type"] == "expense"
    assert row["amount"] == pytest.approx(12.34)


def test_identity_insert_preserves_exact_metadata(module4_repository_seed):
    with module4_repository_seed() as connection:
        connection.execute(
            """INSERT INTO ingestion_attempts
               (attempt_id, business_id, registry_business_id, account_id,
                uploader_user_id, source_system, contract_version, currency,
                record_count, attempt_status)
               VALUES ('attempt_insert', 'demo_business_001',
                       'legacy_demo_business_001', 'demo_account_001',
                       'owner_user_001', ?, ?, 'INR', 1, 'processing')""",
            (SOURCE_SYSTEM, CONTRACT_VERSION),
        )
        connection.execute(
            """INSERT INTO transaction_general_ledger
               (transaction_id, business_id, user_id, transaction_date,
                amount, transaction_type, transaction_hash)
               VALUES ('transaction_insert', 'legacy_demo_business_001',
                       'legacy_owner_001', '2026-08-31', 12.34,
                       'income', 'legacy-hash-insert')"""
        )

    identity_id = queries.insert_transaction_identity(
        transaction_id="transaction_insert",
        attempt_id="attempt_insert",
        business_id="demo_business_001",
        registry_business_id="legacy_demo_business_001",
        account_id="demo_account_001",
        source_system=SOURCE_SYSTEM,
        source_transaction_id=None,
        transaction_date="2026-08-31",
        amount_minor=1234,
        direction="income",
        currency="INR",
        canonical_identity_hash="canonical-insert-001",
    )

    with module4_repository_seed() as connection:
        row = connection.execute(
            "SELECT * FROM ingested_transaction_identities WHERE identity_id=?",
            (identity_id,),
        ).fetchone()
    assert identity_id.startswith("iti_")
    assert row["transaction_id"] == "transaction_insert"
    assert row["source_transaction_id"] is None
    assert row["amount_minor"] == 1234
    assert row["canonical_identity_hash"] == "canonical-insert-001"


def test_module4_transaction_commits_coordinated_writes(module4_repository_seed):
    with queries.module4_transaction() as connection:
        attempt_id = queries.create_ingestion_attempt(
            business_id="demo_business_001",
            registry_business_id="legacy_demo_business_001",
            account_id="demo_account_001",
            uploader_user_id="owner_user_001",
            source_system=SOURCE_SYSTEM,
            contract_version=CONTRACT_VERSION,
            currency="INR",
            record_count=1,
            connection=connection,
        )
        transaction_id = queries.insert_ledger_transaction(
            registry_business_id="legacy_demo_business_001",
            legacy_owner_user_id="legacy_owner_001",
            transaction_date="2026-08-31",
            amount="12.34",
            transaction_type="income",
            transaction_hash="ledger-transaction-001",
            connection=connection,
        )
        queries.insert_transaction_identity(
            transaction_id=transaction_id,
            attempt_id=attempt_id,
            business_id="demo_business_001",
            registry_business_id="legacy_demo_business_001",
            account_id="demo_account_001",
            source_system=SOURCE_SYSTEM,
            source_transaction_id="source-commit-001",
            transaction_date="2026-08-31",
            amount_minor=1234,
            direction="income",
            currency="INR",
            canonical_identity_hash="canonical-commit-001",
            connection=connection,
        )
        assert queries.complete_ingestion_attempt(
            attempt_id,
            inserted_count=1,
            duplicate_count=0,
            rejected_count=0,
            connection=connection,
        )

    with module4_repository_seed() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM ingestion_attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM transaction_general_ledger WHERE transaction_id=?",
            (transaction_id,),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM ingested_transaction_identities WHERE transaction_id=?",
            (transaction_id,),
        ).fetchone()[0] == 1


def test_module4_transaction_rolls_back_every_coordinated_write(module4_repository_seed):
    with pytest.raises(sqlite3.IntegrityError):
        with queries.module4_transaction() as connection:
            attempt_id = queries.create_ingestion_attempt(
                business_id="demo_business_001",
                registry_business_id="legacy_demo_business_001",
                account_id="demo_account_001",
                uploader_user_id="owner_user_001",
                source_system=SOURCE_SYSTEM,
                contract_version=CONTRACT_VERSION,
                currency="INR",
                record_count=1,
                connection=connection,
            )
            transaction_id = queries.insert_ledger_transaction(
                registry_business_id="legacy_demo_business_001",
                legacy_owner_user_id="legacy_owner_001",
                transaction_date="2026-08-31",
                amount="12.34",
                transaction_type="income",
                transaction_hash="ledger-rollback-001",
                connection=connection,
            )
            queries.insert_transaction_identity(
                transaction_id=transaction_id,
                attempt_id=attempt_id,
                business_id="demo_business_001",
                registry_business_id="legacy_demo_business_001",
                account_id="demo_account_001",
                source_system=SOURCE_SYSTEM,
                source_transaction_id="source-rollback-001",
                transaction_date="2026-08-31",
                amount_minor=1234,
                direction="income",
                currency="INR",
                canonical_identity_hash="canonical-rollback-001",
                connection=connection,
            )
            queries.insert_transaction_identity(
                transaction_id=transaction_id,
                attempt_id=attempt_id,
                business_id="demo_business_001",
                registry_business_id="legacy_demo_business_001",
                account_id="demo_account_001",
                source_system=SOURCE_SYSTEM,
                source_transaction_id="source-rollback-002",
                transaction_date="2026-08-31",
                amount_minor=1234,
                direction="income",
                currency="INR",
                canonical_identity_hash="canonical-rollback-001",
                connection=connection,
            )

    with module4_repository_seed() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM ingestion_attempts"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM transaction_general_ledger"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM ingested_transaction_identities"
        ).fetchone()[0] == 0
