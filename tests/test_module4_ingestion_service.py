import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from database import queries
from services import ingestion_identity, ingestion_service


SOURCE_SYSTEM = "finsight_demo_bank_statement_v1"
CONTRACT_VERSION = "finsight_ingestion_v1"
BUSINESS_ID = "demo_business_001"
REGISTRY_BUSINESS_ID = "legacy_demo_business_001"
ACCOUNT_ID = "demo_account_001"


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def make_record(**overrides):
    record = {
        "transaction_date": "2026-08-31",
        "amount_minor": 1234,
        "direction": "income",
    }
    record.update(overrides)
    return record


def make_payload(records=None, **overrides):
    payload = {
        "contract_version": CONTRACT_VERSION,
        "source_system": SOURCE_SYSTEM,
        "records": [make_record()] if records is None else records,
    }
    payload.update(overrides)
    return payload


def insert_user(connection, user_id, role="standard_business", status="active"):
    connection.execute(
        """INSERT INTO users
           (user_id,username,email,contact_number,password_hash,role,account_status)
           VALUES (?, ?, ?, '9999999999', 'hash', ?, ?)""",
        (user_id, user_id, f"{user_id}@example.test", role, status),
    )


def insert_session(connection, user_id, token, *, expires_at=None, revoked_at=None):
    expires_at = expires_at or (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    connection.execute(
        """INSERT INTO auth_sessions
           (session_id,user_id,token_hash,expires_at,revoked_at)
           VALUES (?, ?, ?, ?, ?)""",
        (f"session_{user_id}_{token}", user_id, token_hash(token), expires_at, revoked_at),
    )


@pytest.fixture
def ingestion_repository(isolated_test_database):
    with isolated_test_database() as connection:
        insert_user(connection, "owner_user_001")
        insert_user(connection, "manager_user_001")
        insert_user(connection, "member_user_001")
        insert_user(connection, "viewer_user_001")
        insert_user(connection, "admin_user_001", role="administrator")
        insert_user(connection, "legacy_owner_001")
        insert_user(connection, "disabled_owner_001")

        for user_id in (
            "owner_user_001",
            "manager_user_001",
            "member_user_001",
            "viewer_user_001",
            "admin_user_001",
            "disabled_owner_001",
        ):
            insert_session(connection, user_id, f"token-{user_id}")
        insert_session(
            connection,
            "owner_user_001",
            "expired-token",
            expires_at=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        )

        connection.executemany(
            "INSERT INTO businesses (business_id,business_name,business_status) VALUES (?, ?, ?)",
            [
                (BUSINESS_ID, "Controlled Demo", "active"),
                ("other_business_001", "Other Business", "active"),
                ("disabled_business_001", "Disabled Business", "disabled"),
            ],
        )
        connection.executemany(
            """INSERT INTO business_memberships
               (membership_id,business_id,user_id,membership_role,membership_status)
               VALUES (?, ?, ?, ?, ?)""",
            [
                ("membership_owner", BUSINESS_ID, "owner_user_001", "owner", "active"),
                ("membership_manager", BUSINESS_ID, "manager_user_001", "manager", "active"),
                ("membership_member", BUSINESS_ID, "member_user_001", "member", "active"),
                ("membership_viewer", BUSINESS_ID, "viewer_user_001", "viewer", "active"),
                ("membership_disabled", BUSINESS_ID, "disabled_owner_001", "owner", "disabled"),
            ],
        )
        connection.execute(
            """INSERT INTO business_registry (business_id,user_id,business_name)
               VALUES (?, ?, 'Controlled Legacy Demo')""",
            (REGISTRY_BUSINESS_ID, "legacy_owner_001"),
        )
        connection.executemany(
            """INSERT INTO financial_accounts
               (account_id,business_id,account_name,account_type,currency,account_status)
               VALUES (?, ?, ?, 'bank', ?, ?)""",
            [
                (ACCOUNT_ID, BUSINESS_ID, "Demo Account", "INR", "active"),
                ("disabled_account_001", BUSINESS_ID, "Disabled Account", "INR", "disabled"),
                ("other_account_001", "other_business_001", "Other Account", "USD", "active"),
            ],
        )
        connection.execute(
            """INSERT INTO business_registry_bridges
               (bridge_id,business_id,registry_business_id,proposed_by_user_id,
                verified_by_user_id,bridge_status,proposed_at,verified_at)
               VALUES ('bridge_active', ?, ?, 'owner_user_001', 'admin_user_001',
                       'active', '2026-08-29T00:00:00+00:00',
                       '2026-08-29T00:01:00+00:00')""",
            (BUSINESS_ID, REGISTRY_BUSINESS_ID),
        )
    return isolated_test_database


def seed_identity(connection, *, source_transaction_id="SRC-001", values=None):
    values = {"transaction_date": "2026-08-31", "amount_minor": 1234, "direction": "income", **(values or {})}
    connection.execute(
        """INSERT INTO ingestion_attempts
           (attempt_id,business_id,registry_business_id,account_id,uploader_user_id,
            source_system,contract_version,currency,record_count,attempt_status)
           VALUES ('attempt_seed', ?, ?, ?, 'owner_user_001', ?, ?, 'INR', 1, 'processing')""",
        (BUSINESS_ID, REGISTRY_BUSINESS_ID, ACCOUNT_ID, SOURCE_SYSTEM, CONTRACT_VERSION),
    )
    connection.execute(
        """INSERT INTO transaction_general_ledger
           (transaction_id,business_id,user_id,transaction_date,amount,transaction_type,transaction_hash)
           VALUES ('transaction_seed', ?, 'legacy_owner_001', ?, 12.34, 'income', 'legacy-seed')""",
        (REGISTRY_BUSINESS_ID, values["transaction_date"]),
    )
    connection.execute(
        """INSERT INTO ingested_transaction_identities
           (identity_id,transaction_id,attempt_id,business_id,registry_business_id,
            account_id,source_system,source_transaction_id,transaction_date,amount_minor,
            direction,currency,canonical_identity_hash)
           VALUES ('identity_seed', 'transaction_seed', 'attempt_seed', ?, ?, ?, ?, ?, ?, ?, ?, 'INR', ?)""",
        (
            BUSINESS_ID,
            REGISTRY_BUSINESS_ID,
            ACCOUNT_ID,
            SOURCE_SYSTEM,
            source_transaction_id,
            values["transaction_date"],
            values["amount_minor"],
            values["direction"],
            ingestion_identity.build_canonical_identity_hash(
                ACCOUNT_ID,
                SOURCE_SYSTEM,
                "INR",
                values["transaction_date"],
                values["amount_minor"],
                values["direction"],
            ),
        ),
    )


def prepare_args(token="token-owner_user_001", business_id=BUSINESS_ID, account_id=ACCOUNT_ID, payload=None):
    return {
        "session_token": token,
        "business_id": business_id,
        "account_id": account_id,
        "payload": make_payload() if payload is None else payload,
    }


def assert_no_module4_writes(connection):
    assert connection.execute("SELECT COUNT(*) FROM ingestion_attempts").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM transaction_general_ledger").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM ingested_transaction_identities").fetchone()[0] == 0


def test_owner_preparation_resolves_separate_uploader_and_legacy_owner(ingestion_repository):
    result = ingestion_service.prepare_ingestion(**prepare_args())

    assert result.uploader_user_id == "owner_user_001"
    assert result.legacy_owner_user_id == "legacy_owner_001"
    assert result.registry_business_id == REGISTRY_BUSINESS_ID
    assert result.account_id == ACCOUNT_ID
    assert result.records[0].outcome == ingestion_identity.IdentityOutcome.UNIQUE
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


def test_manager_is_authorized_and_legacy_owner_remains_registry_owner(ingestion_repository):
    result = ingestion_service.prepare_ingestion(
        **prepare_args(token="token-manager_user_001")
    )

    assert result.uploader_user_id == "manager_user_001"
    assert result.legacy_owner_user_id == "legacy_owner_001"


@pytest.mark.parametrize(
    "token",
    ["invalid-token", "expired-token", "token-member_user_001", "token-viewer_user_001", "token-admin_user_001", "token-disabled_owner_001"],
)
def test_unauthenticated_or_unauthorized_actor_fails_closed(ingestion_repository, token):
    with pytest.raises(ingestion_service.IngestionServiceError):
        ingestion_service.prepare_ingestion(**prepare_args(token=token))
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


@pytest.mark.parametrize("business_id", ["missing_business", "disabled_business_001"])
def test_business_must_exist_and_be_active(ingestion_repository, business_id):
    with pytest.raises(ingestion_service.IngestionServiceError):
        ingestion_service.prepare_ingestion(**prepare_args(business_id=business_id))
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


@pytest.mark.parametrize("account_id", ["missing_account", "disabled_account_001", "other_account_001"])
def test_account_must_be_active_and_belong_to_selected_business(ingestion_repository, account_id):
    with pytest.raises(ingestion_service.IngestionServiceError):
        ingestion_service.prepare_ingestion(**prepare_args(account_id=account_id))
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


@pytest.mark.parametrize("status", ["pending", "rejected", "disabled"])
def test_bridge_must_be_active_and_verified(ingestion_repository, status):
    with ingestion_repository() as connection:
        connection.execute(
            "UPDATE business_registry_bridges SET bridge_status=? WHERE bridge_id='bridge_active'",
            (status,),
        )
    with pytest.raises(ingestion_service.IngestionServiceError):
        ingestion_service.prepare_ingestion(**prepare_args())
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


def test_bridge_verification_must_be_independent(ingestion_repository):
    with ingestion_repository() as connection:
        connection.execute(
            "UPDATE business_registry_bridges "
            "SET proposed_by_user_id=verified_by_user_id "
            "WHERE bridge_id='bridge_active'"
        )

    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.prepare_ingestion(**prepare_args())
    assert exc_info.value.code == "BRIDGE_NOT_VERIFIED"


def test_missing_registry_business_fails_closed(ingestion_repository, monkeypatch):
    monkeypatch.setattr(queries, "get_registry_business", lambda *_args, **_kwargs: None)

    with pytest.raises(ingestion_service.IngestionServiceError):
        ingestion_service.prepare_ingestion(**prepare_args())


def test_missing_registry_owner_fails_closed(ingestion_repository, monkeypatch):
    monkeypatch.setattr(queries, "get_registry_owner", lambda *_args, **_kwargs: None)

    with pytest.raises(ingestion_service.IngestionServiceError):
        ingestion_service.prepare_ingestion(**prepare_args())


def test_invalid_payload_is_rejected_without_writes(ingestion_repository):
    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.prepare_ingestion(
            **prepare_args(payload=make_payload([make_record(amount_minor=0)]))
        )

    assert exc_info.value.code == "VALIDATION_FAILED"
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


def test_existing_source_id_is_classified_as_duplicate(ingestion_repository):
    with ingestion_repository() as connection:
        seed_identity(connection)
    result = ingestion_service.prepare_ingestion(
        **prepare_args(payload=make_payload([make_record(source_transaction_id="SRC-001")]))
    )
    assert result.records[0].outcome == ingestion_identity.IdentityOutcome.DUPLICATE_SOURCE_ID


def test_different_source_id_same_financial_tuple_is_unique(ingestion_repository):
    with ingestion_repository() as connection:
        seed_identity(connection)
    result = ingestion_service.prepare_ingestion(
        **prepare_args(payload=make_payload([make_record(source_transaction_id="SRC-002")]))
    )
    assert result.records[0].outcome == ingestion_identity.IdentityOutcome.UNIQUE


def test_within_batch_different_source_ids_same_tuple_are_both_unique(ingestion_repository):
    record = make_record(source_transaction_id="SRC-NEW")
    second_record = dict(record, source_transaction_id="SRC-NEW-2")
    result = ingestion_service.prepare_ingestion(
        **prepare_args(payload=make_payload([record, second_record]))
    )
    assert [item.outcome for item in result.records] == [
        ingestion_identity.IdentityOutcome.UNIQUE,
        ingestion_identity.IdentityOutcome.UNIQUE,
    ]
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


def test_conflicting_source_ids_fail_closed(ingestion_repository):
    records = [
        make_record(source_transaction_id="SRC-CONFLICT", amount_minor=100),
        make_record(source_transaction_id="SRC-CONFLICT", amount_minor=200),
    ]
    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.prepare_ingestion(
            **prepare_args(payload=make_payload(records))
        )
    assert exc_info.value.code == "IDENTITY_CONFLICT"
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


def test_record_level_account_override_is_rejected_by_validation(ingestion_repository):
    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.prepare_ingestion(
            **prepare_args(payload=make_payload([make_record(account_id="other_account_001")]))
        )
    assert exc_info.value.code == "VALIDATION_FAILED"


def test_identity_conflict_is_fail_closed_and_does_not_write(ingestion_repository, monkeypatch):
    conflict = ingestion_identity.IdentityClassification(
        ingestion_identity.IdentityOutcome.CANONICAL_IDENTITY_CONFLICT,
        "a" * 64,
    )
    monkeypatch.setattr(
        ingestion_identity,
        "classify_transaction_identity",
        lambda **_kwargs: conflict,
    )

    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.prepare_ingestion(**prepare_args())
    assert exc_info.value.code == "IDENTITY_CONFLICT"
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


def test_validation_and_identity_layers_are_reused(ingestion_repository, monkeypatch):
    calls = {"validation": 0, "identity": 0}
    original_validation = ingestion_service.ingestion_validation.validate_ingestion_payload
    original_identity = ingestion_service.ingestion_identity.classify_transaction_identity

    def wrapped_validation(payload):
        calls["validation"] += 1
        return original_validation(payload)

    def wrapped_identity(**kwargs):
        calls["identity"] += 1
        return original_identity(**kwargs)

    monkeypatch.setattr(ingestion_service.ingestion_validation, "validate_ingestion_payload", wrapped_validation)
    monkeypatch.setattr(ingestion_service.ingestion_identity, "classify_transaction_identity", wrapped_identity)

    ingestion_service.prepare_ingestion(**prepare_args())

    assert calls == {"validation": 1, "identity": 1}


def _module4_counts(connection):
    return tuple(
        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "ingestion_attempts",
            "transaction_general_ledger",
            "ingested_transaction_identities",
        )
    )


def test_ingest_commits_attempt_ledger_and_identity_together(ingestion_repository):
    result = ingestion_service.ingest(**prepare_args())

    assert result.status == "completed"
    assert result.attempt_id is not None
    assert (result.record_count, result.inserted_count,
            result.duplicate_count, result.rejected_count) == (1, 1, 0, 0)
    with ingestion_repository() as connection:
        attempt = connection.execute(
            "SELECT * FROM ingestion_attempts WHERE attempt_id=?",
            (result.attempt_id,),
        ).fetchone()
        ledger = connection.execute(
            "SELECT * FROM transaction_general_ledger"
        ).fetchone()
        identity = connection.execute(
            "SELECT * FROM ingested_transaction_identities"
        ).fetchone()

    assert attempt["attempt_status"] == "completed"
    assert attempt["uploader_user_id"] == "owner_user_001"
    assert ledger["business_id"] == REGISTRY_BUSINESS_ID
    assert ledger["user_id"] == "legacy_owner_001"
    assert ledger["transaction_type"] == "income"
    assert ledger["amount"] == pytest.approx(12.34)
    assert identity["transaction_id"] == ledger["transaction_id"]
    assert identity["attempt_id"] == result.attempt_id
    assert identity["amount_minor"] == 1234
    assert identity["direction"] == "income"
    assert identity["currency"] == "INR"
    assert identity["canonical_identity_hash"] == ingestion_identity.build_canonical_identity_hash(
        ACCOUNT_ID, SOURCE_SYSTEM, "INR", "2026-08-31", 1234, "income"
    )


def test_ingest_manager_writes_legacy_owner_not_uploader(ingestion_repository):
    result = ingestion_service.ingest(
        **prepare_args(token="token-manager_user_001")
    )

    with ingestion_repository() as connection:
        attempt = connection.execute(
            "SELECT uploader_user_id FROM ingestion_attempts WHERE attempt_id=?",
            (result.attempt_id,),
        ).fetchone()
        ledger = connection.execute(
            "SELECT user_id FROM transaction_general_ledger"
        ).fetchone()
    assert attempt["uploader_user_id"] == "manager_user_001"
    assert ledger["user_id"] == "legacy_owner_001"


def test_same_source_id_does_not_insert_financial_row_twice(ingestion_repository):
    with ingestion_repository() as connection:
        seed_identity(connection)
    with ingestion_repository() as connection:
        before = _module4_counts(connection)

    result = ingestion_service.ingest(
        **prepare_args(
            payload=make_payload(
                [make_record(source_transaction_id="SRC-001")]
            )
        )
    )

    assert result.status == "completed"
    assert result.inserted_count == 0
    assert result.duplicate_count == 1
    with ingestion_repository() as connection:
        after = _module4_counts(connection)
    assert after == (before[0] + 1, before[1], before[2])


def test_different_source_ids_same_tuple_both_insert_and_exact_reupload_dedupes(
    ingestion_repository,
):
    records = [
        make_record(source_transaction_id="SRC-A"),
        make_record(source_transaction_id="SRC-B"),
    ]

    first = ingestion_service.ingest(
        **prepare_args(payload=make_payload(records))
    )
    assert (first.inserted_count, first.duplicate_count) == (2, 0)

    second = ingestion_service.ingest(
        **prepare_args(payload=make_payload(records))
    )
    assert (second.inserted_count, second.duplicate_count) == (0, 2)

    with ingestion_repository() as connection:
        rows = connection.execute(
            """SELECT source_transaction_id, canonical_identity_hash
               FROM ingested_transaction_identities
               ORDER BY source_transaction_id"""
        ).fetchall()
    assert [row["source_transaction_id"] for row in rows] == ["SRC-A", "SRC-B"]
    assert len({row["canonical_identity_hash"] for row in rows}) == 2


def test_source_identity_conflict_fails_without_partial_writes(ingestion_repository):
    with ingestion_repository() as connection:
        seed_identity(connection, values={"amount_minor": 9999})

    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(
            **prepare_args(
                payload=make_payload(
                    [make_record(source_transaction_id="SRC-001")]
                )
            )
        )
    assert exc_info.value.code == "IDENTITY_CONFLICT"
    with ingestion_repository() as connection:
        assert _module4_counts(connection) == (1, 1, 1)


def test_fallback_canonical_identity_conflict_fails_without_partial_writes(
    ingestion_repository,
):
    with ingestion_repository() as connection:
        seed_identity(
            connection,
            source_transaction_id=None,
            values={"amount_minor": 9999},
        )
        connection.execute(
            "UPDATE ingested_transaction_identities SET canonical_identity_hash=?",
            (
                ingestion_identity.build_canonical_identity_hash(
                    ACCOUNT_ID,
                    SOURCE_SYSTEM,
                    "INR",
                    "2026-08-31",
                    1234,
                    "income",
                ),
            ),
        )

    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(
            **prepare_args(
                payload=make_payload(
                    [make_record()]
                )
            )
        )
    assert exc_info.value.code == "IDENTITY_CONFLICT"
    with ingestion_repository() as connection:
        assert _module4_counts(connection) == (1, 1, 1)


@pytest.mark.parametrize("failure_point", ["attempt", "ledger", "identity"])
def test_financial_failure_rolls_back_attempt_and_all_rows(
    ingestion_repository, monkeypatch, failure_point
):
    if failure_point == "attempt":
        original = queries.create_ingestion_attempt

        def fail_after_attempt(**kwargs):
            original(**kwargs)
            raise sqlite3.IntegrityError("simulated attempt failure")

        monkeypatch.setattr(queries, "create_ingestion_attempt", fail_after_attempt)
    elif failure_point == "ledger":
        monkeypatch.setattr(
            queries,
            "insert_ledger_transaction",
            lambda **_kwargs: (_ for _ in ()).throw(
                sqlite3.OperationalError("simulated ledger failure")
            ),
        )
    else:
        original = queries.insert_transaction_identity

        def fail_after_identity(**kwargs):
            original(**kwargs)
            raise sqlite3.IntegrityError("simulated identity failure")

        monkeypatch.setattr(queries, "insert_transaction_identity", fail_after_identity)

    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(**prepare_args())
    assert exc_info.value.code == "STORAGE_FAILED"
    assert "simulated" not in str(exc_info.value)
    with ingestion_repository() as connection:
        assert _module4_counts(connection) == (0, 0, 0)


def test_caller_owned_connection_has_no_hidden_commit(ingestion_repository):
    with ingestion_repository() as connection:
        result = ingestion_service.ingest(**prepare_args(), connection=connection)
        assert connection.in_transaction
        with ingestion_repository() as separate_connection:
            assert _module4_counts(separate_connection) == (0, 0, 0)
        connection.commit()
        assert result.attempt_id is not None

    with ingestion_repository() as connection:
        assert _module4_counts(connection) == (1, 1, 1)


def test_caller_owned_connection_has_no_hidden_rollback(ingestion_repository, monkeypatch):
    monkeypatch.setattr(
        queries,
        "insert_ledger_transaction",
        lambda **_kwargs: (_ for _ in ()).throw(
            sqlite3.OperationalError("simulated ledger failure")
        ),
    )
    with ingestion_repository() as connection:
        with pytest.raises(ingestion_service.IngestionServiceError):
            ingestion_service.ingest(**prepare_args(), connection=connection)
        assert connection.in_transaction
        assert connection.execute("SELECT COUNT(*) FROM ingestion_attempts").fetchone()[0] == 1
        connection.rollback()

    with ingestion_repository() as connection:
        assert _module4_counts(connection) == (0, 0, 0)


def test_retry_attempt_uses_new_id_and_parent_lineage(ingestion_repository):
    parent = queries.create_ingestion_attempt(
        business_id=BUSINESS_ID,
        registry_business_id=REGISTRY_BUSINESS_ID,
        account_id=ACCOUNT_ID,
        uploader_user_id="owner_user_001",
        source_system=SOURCE_SYSTEM,
        contract_version=CONTRACT_VERSION,
        currency="INR",
        record_count=1,
    )
    result = ingestion_service.ingest(**prepare_args(), parent_attempt_id=parent)

    with ingestion_repository() as connection:
        row = connection.execute(
            "SELECT parent_attempt_id FROM ingestion_attempts WHERE attempt_id=?",
            (result.attempt_id,),
        ).fetchone()
    assert result.attempt_id != parent
    assert row["parent_attempt_id"] == parent


def test_rejected_database_error_is_safe_and_rolls_back(ingestion_repository, monkeypatch):
    monkeypatch.setattr(
        queries,
        "insert_transaction_identity",
        lambda **_kwargs: (_ for _ in ()).throw(
            sqlite3.IntegrityError("SQLITE_SECRET_PATH / raw payload")
        ),
    )
    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(**prepare_args())
    assert exc_info.value.code == "STORAGE_FAILED"
    assert "SQLITE" not in str(exc_info.value)
    assert "raw payload" not in str(exc_info.value)
    with ingestion_repository() as connection:
        assert _module4_counts(connection) == (0, 0, 0)


# Phase: batch outcomes, sanitized failure logging, and retry lifecycle.
def test_batch_outcome_aggregates_inserted_and_duplicate_records(ingestion_repository):
    with ingestion_repository() as connection:
        seed_identity(connection, source_transaction_id="SRC-EXISTING")

    records = [
        make_record(source_transaction_id="SRC-EXISTING"),
        make_record(source_transaction_id="SRC-NEW", amount_minor=4321),
    ]
    result = ingestion_service.ingest(
        **prepare_args(payload=make_payload(records)),
    )

    assert result.status == "completed"
    assert (result.record_count, result.inserted_count,
            result.duplicate_count, result.rejected_count) == (2, 1, 1, 0)
    with ingestion_repository() as connection:
        attempt = connection.execute(
            "SELECT record_count,inserted_count,duplicate_count,rejected_count,attempt_status "
            "FROM ingestion_attempts WHERE attempt_id=?",
            (result.attempt_id,),
        ).fetchone()
    assert tuple(attempt) == (2, 1, 1, 0, "completed")


def test_retry_number_and_parent_lineage_increase_across_retries(ingestion_repository):
    first = ingestion_service.ingest(**prepare_args())
    second = ingestion_service.ingest(**prepare_args(), parent_attempt_id=first.attempt_id)
    third = ingestion_service.ingest(**prepare_args(), parent_attempt_id=second.attempt_id)

    assert first.retry_count == 0
    assert second.retry_count == 1
    assert third.retry_count == 2
    with ingestion_repository() as connection:
        rows = connection.execute(
            "SELECT attempt_id,parent_attempt_id,attempt_status FROM ingestion_attempts "
            "ORDER BY created_at,attempt_id"
        ).fetchall()
    assert {row["attempt_id"] for row in rows} >= {
        first.attempt_id, second.attempt_id, third.attempt_id,
    }
    assert next(row["parent_attempt_id"] for row in rows if row["attempt_id"] == second.attempt_id) == first.attempt_id
    assert next(row["parent_attempt_id"] for row in rows if row["attempt_id"] == third.attempt_id) == second.attempt_id


@pytest.mark.parametrize(
    "failure,code_message",
    [
        (sqlite3.IntegrityError("private SQL / source id"), "STORAGE_FAILED"),
        (sqlite3.OperationalError("/secret/path payload"), "STORAGE_FAILED"),
        (RuntimeError("unexpected stack trace and token"), "STORAGE_FAILED"),
    ],
)
def test_storage_failure_can_be_finalized_as_sanitized_failed_attempt(
    ingestion_repository, monkeypatch, failure, code_message
):
    monkeypatch.setattr(
        queries,
        "insert_ledger_transaction",
        lambda **_kwargs: (_ for _ in ()).throw(failure),
    )

    result = ingestion_service.ingest(**prepare_args(), record_failure=True)

    assert result.status == "failed"
    assert result.error_code == code_message
    assert result.error_message == "The ingestion could not be completed."
    assert result.attempt_id is not None
    assert "private" not in result.error_message
    assert "secret" not in result.error_message
    assert "token" not in result.error_message
    with ingestion_repository() as connection:
        attempt = connection.execute(
            "SELECT attempt_status,public_error_code,public_error_message,completed_at "
            "FROM ingestion_attempts WHERE attempt_id=?",
            (result.attempt_id,),
        ).fetchone()
        assert attempt["attempt_status"] == "failed"
        assert attempt["public_error_code"] == code_message
        assert attempt["public_error_message"] == result.error_message
        assert attempt["completed_at"] is not None
        assert _module4_counts(connection)[1:] == (0, 0)


def test_failed_attempt_does_not_log_payload_or_operational_identifiers(
    ingestion_repository, monkeypatch
):
    monkeypatch.setattr(
        queries,
        "insert_ledger_transaction",
        lambda **_kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("raw SQL")),
    )

    result = ingestion_service.ingest(
        **prepare_args(
            payload=make_payload(
                [make_record(source_transaction_id="PRIVATE-SOURCE", description="PRIVATE-DESCRIPTION")]
            )
        ),
        record_failure=True,
    )

    with ingestion_repository() as connection:
        row = connection.execute(
            "SELECT public_error_code,public_error_message FROM ingestion_attempts WHERE attempt_id=?",
            (result.attempt_id,),
        ).fetchone()
    assert row["public_error_code"] == "STORAGE_FAILED"
    assert row["public_error_message"] == "The ingestion could not be completed."
    assert "PRIVATE" not in row["public_error_message"]
    assert "raw SQL" not in row["public_error_message"]


def test_validation_failure_is_not_recorded_as_attempt(ingestion_repository):
    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(
            **prepare_args(payload=make_payload([make_record(amount_minor=0)])),
            record_failure=True,
        )
    assert exc_info.value.code == "VALIDATION_FAILED"
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


def test_retry_after_failed_attempt_links_to_failed_parent(ingestion_repository, monkeypatch):
    original_insert = queries.insert_ledger_transaction
    monkeypatch.setattr(
        queries,
        "insert_ledger_transaction",
        lambda **_kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("temporary")),
    )
    failed = ingestion_service.ingest(**prepare_args(), record_failure=True)
    assert failed.status == "failed"

    monkeypatch.setattr(queries, "insert_ledger_transaction", original_insert)
    retried = ingestion_service.ingest(
        **prepare_args(), parent_attempt_id=failed.attempt_id
    )

    assert retried.status == "completed"
    assert retried.retry_count == 1
    with ingestion_repository() as connection:
        row = connection.execute(
            "SELECT parent_attempt_id,attempt_status FROM ingestion_attempts WHERE attempt_id=?",
            (retried.attempt_id,),
        ).fetchone()
    assert row["parent_attempt_id"] == failed.attempt_id
    assert row["attempt_status"] == "completed"


def test_retry_after_duplicate_is_a_new_completed_attempt(ingestion_repository):
    first = ingestion_service.ingest(**prepare_args())
    duplicate = ingestion_service.ingest(
        **prepare_args(), parent_attempt_id=first.attempt_id
    )

    assert duplicate.status == "completed"
    assert duplicate.inserted_count == 0
    assert duplicate.duplicate_count == 1
    assert duplicate.retry_count == 1
    with ingestion_repository() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM transaction_general_ledger"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM ingested_transaction_identities"
        ).fetchone()[0] == 1


def test_failed_attempt_is_terminal(ingestion_repository):
    attempt_id = queries.create_ingestion_attempt(
        business_id=BUSINESS_ID,
        registry_business_id=REGISTRY_BUSINESS_ID,
        account_id=ACCOUNT_ID,
        uploader_user_id="owner_user_001",
        source_system=SOURCE_SYSTEM,
        contract_version=CONTRACT_VERSION,
        currency="INR",
        record_count=1,
    )
    assert queries.fail_ingestion_attempt(
        attempt_id,
        inserted_count=0,
        duplicate_count=0,
        rejected_count=1,
        public_error_code="STORAGE_FAILED",
        public_error_message="The ingestion could not be completed.",
    )
    assert not queries.complete_ingestion_attempt(
        attempt_id,
        inserted_count=1,
        duplicate_count=0,
        rejected_count=0,
    )
    assert not queries.fail_ingestion_attempt(
        attempt_id,
        inserted_count=0,
        duplicate_count=0,
        rejected_count=1,
        public_error_code="STORAGE_FAILED",
        public_error_message="The ingestion could not be completed.",
    )
