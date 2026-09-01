import hashlib
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


def test_existing_canonical_hash_is_classified_as_duplicate(ingestion_repository):
    with ingestion_repository() as connection:
        seed_identity(connection)
    result = ingestion_service.prepare_ingestion(
        **prepare_args(payload=make_payload([make_record(source_transaction_id="SRC-002")]))
    )
    assert result.records[0].outcome == ingestion_identity.IdentityOutcome.DUPLICATE_CANONICAL_IDENTITY


def test_within_batch_duplicate_is_classified_without_writes(ingestion_repository):
    record = make_record(source_transaction_id="SRC-NEW")
    second_record = dict(record, source_transaction_id="SRC-NEW-2")
    result = ingestion_service.prepare_ingestion(
        **prepare_args(payload=make_payload([record, second_record]))
    )
    assert [item.outcome for item in result.records] == [
        ingestion_identity.IdentityOutcome.UNIQUE,
        ingestion_identity.IdentityOutcome.DUPLICATE_CANONICAL_IDENTITY,
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
