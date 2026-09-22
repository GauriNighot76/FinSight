import sqlite3

import pytest

from database import queries
from services import ingestion_identity, ingestion_service
from test_module4_ingestion_service import (
    ACCOUNT_ID,
    BUSINESS_ID,
    CONTRACT_VERSION,
    REGISTRY_BUSINESS_ID,
    SOURCE_SYSTEM,
    assert_no_module4_writes,
    ingestion_repository,
    make_payload,
    make_record,
    prepare_args,
    seed_identity,
    _module4_counts,
)


def test_single_controlled_demo_ingestion_persists_complete_flow(ingestion_repository):
    result = ingestion_service.ingest(
        **prepare_args(
            payload=make_payload(
                [make_record(source_transaction_id="E2E-SINGLE")]
            )
        )
    )

    assert result.status == "completed"
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
    assert attempt["business_id"] == BUSINESS_ID
    assert attempt["registry_business_id"] == REGISTRY_BUSINESS_ID
    assert attempt["account_id"] == ACCOUNT_ID
    assert attempt["currency"] == "INR"
    assert ledger["business_id"] == REGISTRY_BUSINESS_ID
    assert ledger["user_id"] == "legacy_owner_001"
    assert ledger["transaction_type"] == "income"
    assert ledger["amount"] == pytest.approx(12.34)
    assert identity["transaction_id"] == ledger["transaction_id"]
    assert identity["attempt_id"] == result.attempt_id
    assert identity["source_transaction_id"] == "E2E-SINGLE"
    assert identity["amount_minor"] == 1234
    assert identity["currency"] == "INR"



def test_ingestion_preserves_category_payment_method_and_description(ingestion_repository):
    record = make_record(
        source_transaction_id="E2E-METADATA",
        category="Rent",
        payment_method="Bank",
        description="Monthly office rent",
    )
    result = ingestion_service.ingest(
        **prepare_args(payload=make_payload([record]))
    )
    assert result.inserted_count == 1
    with ingestion_repository() as connection:
        ledger = connection.execute(
            "SELECT category,payment_mode,description FROM transaction_general_ledger"
        ).fetchone()
    assert ledger["category"] == "Rent"
    assert ledger["payment_mode"] == "Bank"
    assert ledger["description"] == "Monthly office rent"


def test_multiple_record_batch_preserves_order_and_aggregates_counts(ingestion_repository):
    records = [
        make_record(source_transaction_id="E2E-INCOME", amount_minor=1200),
        make_record(source_transaction_id="E2E-EXPENSE", amount_minor=500, direction="expense"),
    ]
    result = ingestion_service.ingest(
        **prepare_args(payload=make_payload(records))
    )

    assert (result.record_count, result.inserted_count,
            result.duplicate_count, result.rejected_count) == (2, 2, 0, 0)
    with ingestion_repository() as connection:
        rows = connection.execute(
            "SELECT transaction_date,amount,transaction_type,user_id "
            "FROM transaction_general_ledger ORDER BY rowid"
        ).fetchall()
    assert [(row["amount"], row["transaction_type"], row["user_id"]) for row in rows] == [
        (pytest.approx(12.0), "income", "legacy_owner_001"),
        (pytest.approx(5.0), "expense", "legacy_owner_001"),
    ]


def test_duplicate_source_id_does_not_create_second_financial_record(ingestion_repository):
    with ingestion_repository() as connection:
        seed_identity(connection, source_transaction_id="E2E-SOURCE")

    result = ingestion_service.ingest(
        **prepare_args(payload=make_payload([make_record(source_transaction_id="E2E-SOURCE")]))
    )

    assert result.status == "completed"
    assert result.inserted_count == 0
    assert result.duplicate_count == 1
    with ingestion_repository() as connection:
        assert _module4_counts(connection) == (2, 1, 1)


def test_duplicate_canonical_identity_without_source_id_is_idempotent(ingestion_repository):
    with ingestion_repository() as connection:
        seed_identity(connection, source_transaction_id="E2E-SOURCE")

    result = ingestion_service.ingest(
        **prepare_args(payload=make_payload([make_record()]))
    )

    assert result.status == "completed"
    assert result.inserted_count == 0
    assert result.duplicate_count == 1
    with ingestion_repository() as connection:
        assert _module4_counts(connection) == (2, 1, 1)


def test_source_conflict_fails_closed_without_new_rows(ingestion_repository):
    with ingestion_repository() as connection:
        seed_identity(connection, source_transaction_id="E2E-CONFLICT", values={"amount_minor": 9999})

    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(
            **prepare_args(payload=make_payload([make_record(source_transaction_id="E2E-CONFLICT")]))
        )
    assert exc_info.value.code == "IDENTITY_CONFLICT"
    with ingestion_repository() as connection:
        assert _module4_counts(connection) == (1, 1, 1)


def test_fallback_canonical_conflict_fails_closed_without_new_rows(
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
            (ingestion_identity.build_canonical_identity_hash(
                ACCOUNT_ID, SOURCE_SYSTEM, "INR", "2026-08-31", 1234, "income"
            ),),
        )

    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(
            **prepare_args(payload=make_payload([make_record()]))
        )
    assert exc_info.value.code == "IDENTITY_CONFLICT"
    with ingestion_repository() as connection:
        assert _module4_counts(connection) == (1, 1, 1)


@pytest.mark.parametrize(
    "token,business_id,account_id,expected_code",
    [
        ("invalid-token", BUSINESS_ID, ACCOUNT_ID, "AUTHENTICATION_FAILED"),
        ("token-owner_user_001", "missing-business", ACCOUNT_ID, "BUSINESS_NOT_FOUND"),
        ("token-owner_user_001", "disabled_business_001", ACCOUNT_ID, "BUSINESS_NOT_FOUND"),
        ("token-member_user_001", BUSINESS_ID, ACCOUNT_ID, "INGESTION_FORBIDDEN"),
        ("token-owner_user_001", BUSINESS_ID, "missing-account", "ACCOUNT_NOT_AUTHORIZED"),
        ("token-owner_user_001", BUSINESS_ID, "disabled_account_001", "ACCOUNT_NOT_AUTHORIZED"),
        ("token-owner_user_001", BUSINESS_ID, "other_account_001", "ACCOUNT_NOT_AUTHORIZED"),
    ],
)
def test_authorization_failures_leave_all_module4_tables_empty(
    ingestion_repository, token, business_id, account_id, expected_code
):
    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(
            **prepare_args(token=token, business_id=business_id, account_id=account_id)
        )
    assert exc_info.value.code == expected_code
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


@pytest.mark.parametrize("bridge_status", ["pending", "rejected", "disabled"])
def test_unverified_bridge_fails_closed_without_writes(ingestion_repository, bridge_status):
    with ingestion_repository() as connection:
        connection.execute(
            "UPDATE business_registry_bridges SET bridge_status=? WHERE bridge_id='bridge_active'",
            (bridge_status,),
        )

    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(**prepare_args())
    assert exc_info.value.code == "BRIDGE_NOT_VERIFIED"
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


def test_inactive_membership_and_missing_registry_owner_fail_closed(ingestion_repository, monkeypatch):
    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(
            **prepare_args(token="token-disabled_owner_001")
        )
    assert exc_info.value.code == "MEMBERSHIP_REQUIRED"
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)

    monkeypatch.setattr(queries, "get_registry_owner", lambda *_args, **_kwargs: None)
    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(**prepare_args())
    assert exc_info.value.code == "REGISTRY_OWNER_NOT_FOUND"
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


def test_validation_failure_is_before_attempt_and_financial_writes(ingestion_repository):
    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(
            **prepare_args(payload=make_payload([make_record(amount_minor=0)]))
        )
    assert exc_info.value.code == "VALIDATION_FAILED"
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


def test_database_failure_rolls_back_attempt_ledger_and_identity(ingestion_repository, monkeypatch):
    monkeypatch.setattr(
        queries,
        "insert_transaction_identity",
        lambda **_kwargs: (_ for _ in ()).throw(
            sqlite3.IntegrityError("simulated integration failure")
        ),
    )
    with pytest.raises(ingestion_service.IngestionServiceError) as exc_info:
        ingestion_service.ingest(**prepare_args())
    assert exc_info.value.code == "STORAGE_FAILED"
    with ingestion_repository() as connection:
        assert_no_module4_writes(connection)


def test_retry_links_attempts_and_preserves_idempotency(ingestion_repository):
    first = ingestion_service.ingest(**prepare_args())
    second = ingestion_service.ingest(
        **prepare_args(), parent_attempt_id=first.attempt_id
    )

    assert first.attempt_id != second.attempt_id
    assert second.retry_count == 1
    assert second.duplicate_count == 1
    with ingestion_repository() as connection:
        row = connection.execute(
            "SELECT parent_attempt_id,attempt_status FROM ingestion_attempts WHERE attempt_id=?",
            (second.attempt_id,),
        ).fetchone()
        assert row["parent_attempt_id"] == first.attempt_id
        assert row["attempt_status"] == "completed"
        assert connection.execute("SELECT COUNT(*) FROM transaction_general_ledger").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM ingested_transaction_identities").fetchone()[0] == 1


def test_caller_owned_connection_has_no_hidden_commit_or_rollback(ingestion_repository, monkeypatch):
    with ingestion_repository() as connection:
        result = ingestion_service.ingest(**prepare_args(), connection=connection)
        assert connection.in_transaction
        with ingestion_repository() as separate:
            assert _module4_counts(separate) == (0, 0, 0)
        connection.commit()
        assert result.status == "completed"

    monkeypatch.setattr(
        queries,
        "insert_ledger_transaction",
        lambda **_kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("do not rollback caller")),
    )
    with ingestion_repository() as connection:
        with pytest.raises(ingestion_service.IngestionServiceError):
            ingestion_service.ingest(
                **prepare_args(payload=make_payload([make_record(amount_minor=4321)])),
                connection=connection,
            )
        assert connection.in_transaction
        connection.rollback()
    with ingestion_repository() as connection:
        assert _module4_counts(connection) == (1, 1, 1)


def test_sanitized_failure_and_retry_after_failure(ingestion_repository, monkeypatch):
    original_insert = queries.insert_ledger_transaction
    monkeypatch.setattr(
        queries,
        "insert_ledger_transaction",
        lambda **_kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("SQL / private payload")),
    )
    failed = ingestion_service.ingest(**prepare_args(), record_failure=True)
    assert failed.status == "failed"
    assert failed.error_code == "STORAGE_FAILED"
    assert failed.error_message == "The ingestion could not be completed."

    monkeypatch.setattr(queries, "insert_ledger_transaction", original_insert)
    retried = ingestion_service.ingest(
        **prepare_args(), parent_attempt_id=failed.attempt_id
    )
    assert retried.status == "completed"
    assert retried.retry_count == 1
    with ingestion_repository() as connection:
        rows = connection.execute(
            "SELECT attempt_id,attempt_status,public_error_message FROM ingestion_attempts"
        ).fetchall()
        assert len(rows) == 2
        by_id = {row["attempt_id"]: row for row in rows}
        assert by_id[failed.attempt_id]["attempt_status"] == "failed"
        assert by_id[failed.attempt_id]["public_error_message"] == "The ingestion could not be completed."
        assert by_id[retried.attempt_id]["attempt_status"] == "completed"
