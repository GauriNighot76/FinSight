import hashlib
import json

import pytest

from database import queries
from services import ingestion_identity


ACCOUNT_ID = "demo_account_001"
SOURCE_SYSTEM = "finsight_demo_bank_statement_v1"
CURRENCY = "INR"
BUSINESS_ID = "demo_business_001"
REGISTRY_BUSINESS_ID = "legacy_demo_business_001"


def make_record(**overrides):
    record = {
        "transaction_date": "2026-08-31",
        "amount_minor": 1234,
        "direction": "income",
    }
    record.update(overrides)
    return record


def identity_args(**overrides):
    values = {
        "account_id": ACCOUNT_ID,
        "source_system": SOURCE_SYSTEM,
        "currency": CURRENCY,
        "transaction_date": "2026-08-31",
        "amount_minor": 1234,
        "direction": "income",
    }
    values.update(overrides)
    return values


def expected_serialization(**overrides):
    values = identity_args(**overrides)
    return json.dumps(
        [
            ingestion_identity.IDENTITY_VERSION,
            values["account_id"],
            values["source_system"],
            values["currency"],
            values["transaction_date"],
            values["amount_minor"],
            values["direction"],
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _insert_user(connection, user_id):
    connection.execute(
        """INSERT INTO users
           (user_id, username, email, contact_number, password_hash)
           VALUES (?, ?, ?, '9999999999', 'hash')""",
        (user_id, user_id, f"{user_id}@example.test"),
    )


@pytest.fixture
def identity_repository(isolated_test_database):
    with isolated_test_database() as connection:
        _insert_user(connection, "owner_user_001")
        _insert_user(connection, "legacy_owner_001")
        connection.execute(
            "INSERT INTO businesses (business_id,business_name) VALUES (?,?)",
            (BUSINESS_ID, "Controlled Demo"),
        )
        connection.execute(
            """INSERT INTO business_registry (business_id,user_id,business_name)
               VALUES (?, ?, ?)""",
            (REGISTRY_BUSINESS_ID, "legacy_owner_001", "Legacy Demo"),
        )
        connection.execute(
            """INSERT INTO financial_accounts
               (account_id,business_id,account_name,account_type,currency)
               VALUES (?, ?, 'Demo Account', 'bank', ?)""",
            (ACCOUNT_ID, BUSINESS_ID, CURRENCY),
        )
    return isolated_test_database


def seed_identity(connection, *, source_transaction_id, values=None, canonical_hash=None):
    values = identity_args() if values is None else {**identity_args(), **values}
    attempt_id = "attempt_identity"
    transaction_id = "transaction_identity"
    connection.execute(
        """INSERT INTO ingestion_attempts
           (attempt_id,business_id,registry_business_id,account_id,
            uploader_user_id,source_system,contract_version,currency,
            record_count,attempt_status)
           VALUES (?, ?, ?, ?, 'owner_user_001', ?, 'finsight_ingestion_v1', ?, 1,
                   'processing')""",
        (
            attempt_id,
            BUSINESS_ID,
            REGISTRY_BUSINESS_ID,
            ACCOUNT_ID,
            SOURCE_SYSTEM,
            CURRENCY,
        ),
    )
    connection.execute(
        """INSERT INTO transaction_general_ledger
           (transaction_id,business_id,user_id,transaction_date,amount,
            transaction_type,transaction_hash)
           VALUES (?, ?, 'legacy_owner_001', ?, 12.34, 'income', ?)""",
        (transaction_id, REGISTRY_BUSINESS_ID, values["transaction_date"], f"legacy-{source_transaction_id}"),
    )
    connection.execute(
        """INSERT INTO ingested_transaction_identities
           (identity_id,transaction_id,attempt_id,business_id,
            registry_business_id,account_id,source_system,source_transaction_id,
            transaction_date,amount_minor,direction,currency,canonical_identity_hash)
           VALUES ('identity_seed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            transaction_id,
            attempt_id,
            BUSINESS_ID,
            REGISTRY_BUSINESS_ID,
            ACCOUNT_ID,
            SOURCE_SYSTEM,
            source_transaction_id,
            values["transaction_date"],
            values["amount_minor"],
            values["direction"],
            CURRENCY,
            canonical_hash or ingestion_identity.build_canonical_identity_hash(**values),
        ),
    )


def classify_args(record, **overrides):
    values = {
        "business_id": BUSINESS_ID,
        "registry_business_id": REGISTRY_BUSINESS_ID,
        "account_id": ACCOUNT_ID,
        "source_system": SOURCE_SYSTEM,
        "currency": CURRENCY,
        "record": record,
    }
    values.update(overrides)
    return values


def test_serialization_is_exact_compact_ordered_json():
    serialized = ingestion_identity.serialize_canonical_identity(**identity_args())

    assert serialized == expected_serialization()
    assert serialized.startswith("[") and serialized.endswith("]")
    assert " " not in serialized
    assert "\n" not in serialized


def test_serialization_is_utf8_and_repeatably_deterministic():
    args = identity_args(account_id="acct-é")

    first = ingestion_identity.serialize_canonical_identity(**args)
    second = ingestion_identity.serialize_canonical_identity(**args)

    assert first == second
    assert first.encode("utf-8").decode("utf-8") == first


@pytest.mark.parametrize(
    "values",
    [
        identity_args(),
        identity_args(amount_minor=9999, direction="expense"),
        identity_args(amount_minor=1),
    ],
)
def test_hash_matches_sha256_of_exact_serialized_bytes(values):
    serialized = ingestion_identity.serialize_canonical_identity(**values)
    expected = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    assert ingestion_identity.build_canonical_identity_hash(**values) == expected


@pytest.mark.parametrize(
    "values,expected_hash",
    [
        (
            identity_args(),
            "16ee371b306727cac715b10ad160703cb7e26de448ca67fcee853a44582cc50f",
        ),
        (
            identity_args(amount_minor=9999, direction="expense"),
            "1a6b266d3f63c67fe5a8cad69ab214fe762f0bb9348e328dc3c8ad76cf629b8e",
        ),
        (
            identity_args(amount_minor=1),
            "5c50898d154945f7bbc9db9769b6c958d936ab212da08c5b02f5a5c2ddf2ca83",
        ),
    ],
)
def test_golden_vectors_remain_byte_for_byte_stable(values, expected_hash):
    assert ingestion_identity.build_canonical_identity_hash(**values) == expected_hash


def test_hash_is_lowercase_sha256_hex():
    result = ingestion_identity.build_canonical_identity_hash(**identity_args())

    assert len(result) == 64
    assert result == result.lower()
    assert all(character in "0123456789abcdef" for character in result)


@pytest.mark.parametrize(
    "field,value",
    [
        ("account_id", "other_account_001"),
        ("source_system", "another_source"),
        ("currency", "USD"),
        ("transaction_date", "2026-09-01"),
        ("amount_minor", 1235),
        ("direction", "expense"),
    ],
)
def test_each_approved_identity_field_changes_hash(field, value):
    changed = identity_args(**{field: value})

    assert ingestion_identity.build_canonical_identity_hash(**changed) != ingestion_identity.build_canonical_identity_hash(**identity_args())


def test_identity_version_is_part_of_serialization_and_has_exact_token():
    assert ingestion_identity.IDENTITY_VERSION == "finsight_transaction_identity_v1"
    assert ingestion_identity.serialize_canonical_identity(**identity_args()).split(",", 1)[0] == '["finsight_transaction_identity_v1"'

    with pytest.raises(ingestion_identity.IdentityError):
        ingestion_identity.serialize_canonical_identity(
            **identity_args(), identity_version="v1"
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("category", "Different Category"),
        ("description", "Different Description"),
        ("counterparty", "Different Counterparty"),
        ("payment_method", "cash"),
        ("source_subtype", "different_subtype"),
        ("source_record_reference", "row-99"),
        ("balance_after_minor", -500),
        ("uploader_user_id", "another_uploader"),
        ("attempt_id", "retry_attempt"),
        ("parent_attempt_id", "prior_attempt"),
        ("row_index", 99),
        ("business_id", "other_business_001"),
        ("registry_business_id", "other_registry_001"),
    ],
)
def test_excluded_record_and_operational_fields_do_not_change_hash(field, value):
    base = make_record(source_transaction_id="SRC-001", category="Base")
    changed = {**base, field: value}

    assert ingestion_identity.build_canonical_identity_hash_for_record(
        base, ACCOUNT_ID, SOURCE_SYSTEM, CURRENCY
    ) == ingestion_identity.build_canonical_identity_hash_for_record(
        changed, ACCOUNT_ID, SOURCE_SYSTEM, CURRENCY
    )


def test_source_transaction_id_changes_persisted_identity_hash():
    base = make_record(source_transaction_id="SRC-001")
    changed = make_record(source_transaction_id="SRC-002")

    assert ingestion_identity.build_canonical_identity_hash_for_record(
        base, ACCOUNT_ID, SOURCE_SYSTEM, CURRENCY
    ) != ingestion_identity.build_canonical_identity_hash_for_record(
        changed, ACCOUNT_ID, SOURCE_SYSTEM, CURRENCY
    )


def test_source_backed_hash_changes_when_same_source_id_changes_financial_components():
    base = make_record(source_transaction_id="SRC-001")
    changed = make_record(source_transaction_id="SRC-001", amount_minor=9999)

    assert ingestion_identity.build_canonical_identity_hash_for_record(
        base, ACCOUNT_ID, SOURCE_SYSTEM, CURRENCY
    ) != ingestion_identity.build_canonical_identity_hash_for_record(
        changed, ACCOUNT_ID, SOURCE_SYSTEM, CURRENCY
    )


def test_source_id_absent_and_null_have_same_fallback_identity():
    absent = make_record()
    null = make_record(source_transaction_id=None)

    assert ingestion_identity.build_canonical_identity_hash_for_record(
        absent, ACCOUNT_ID, SOURCE_SYSTEM, CURRENCY
    ) == ingestion_identity.build_canonical_identity_hash_for_record(
        null, ACCOUNT_ID, SOURCE_SYSTEM, CURRENCY
    )


@pytest.mark.parametrize("record_index", [0, 1, 99])
def test_record_position_does_not_change_identity(record_index):
    record = {**make_record(), "_diagnostic_record_index": record_index}

    assert ingestion_identity.build_canonical_identity_hash_for_record(
        record, ACCOUNT_ID, SOURCE_SYSTEM, CURRENCY
    ) == ingestion_identity.build_canonical_identity_hash_for_record(
        make_record(), ACCOUNT_ID, SOURCE_SYSTEM, CURRENCY
    )


@pytest.mark.parametrize(
    "values",
    [
        identity_args(amount_minor=True),
        identity_args(amount_minor=1.0),
        identity_args(amount_minor=-1),
        identity_args(account_id=""),
        identity_args(source_system=""),
    ],
)
def test_identity_builder_rejects_unsafe_critical_inputs(values):
    with pytest.raises(ingestion_identity.IdentityError):
        ingestion_identity.serialize_canonical_identity(**values)


def test_classifier_reports_unique_without_writing(identity_repository, monkeypatch):
    with identity_repository() as connection:
        monkeypatch.setattr(
            queries,
            "insert_ledger_transaction",
            lambda **_: pytest.fail("classification must not write ledger rows"),
        )
        monkeypatch.setattr(
            queries,
            "insert_transaction_identity",
            lambda **_: pytest.fail("classification must not write identity rows"),
        )
        result = ingestion_identity.classify_transaction_identity(
            **classify_args(make_record(source_transaction_id="new-source")),
            connection=connection,
        )

    assert result.outcome == ingestion_identity.IdentityOutcome.UNIQUE
    assert result.status == "UNIQUE"
    assert result.existing_identity_id is None


def test_classifier_uses_caller_owned_connection(identity_repository, monkeypatch):
    captured = {}
    original = queries.find_identity_by_hash

    def wrapped(**kwargs):
        captured["connection"] = kwargs["connection"]
        return original(**kwargs)

    monkeypatch.setattr(queries, "find_identity_by_hash", wrapped)
    with identity_repository() as connection:
        result = ingestion_identity.classify_transaction_identity(
            **classify_args(make_record()),
            connection=connection,
        )

    assert captured["connection"] is connection
    assert result.outcome == ingestion_identity.IdentityOutcome.UNIQUE


def test_classifier_reports_duplicate_source_id(identity_repository):
    with identity_repository() as connection:
        seed_identity(connection, source_transaction_id="SRC-001")
        result = ingestion_identity.classify_transaction_identity(
            **classify_args(make_record(source_transaction_id="SRC-001")),
            connection=connection,
        )

    assert result.outcome == ingestion_identity.IdentityOutcome.DUPLICATE_SOURCE_ID
    assert result.existing_identity_id == "identity_seed"


def test_classifier_reports_source_identity_conflict(identity_repository):
    with identity_repository() as connection:
        seed_identity(connection, source_transaction_id="SRC-001")
        result = ingestion_identity.classify_transaction_identity(
            **classify_args(make_record(source_transaction_id="SRC-001", amount_minor=9999)),
            connection=connection,
        )

    assert result.outcome == ingestion_identity.IdentityOutcome.SOURCE_IDENTITY_CONFLICT


def test_classifier_treats_different_source_id_same_financial_tuple_as_unique(
    identity_repository,
):
    with identity_repository() as connection:
        seed_identity(connection, source_transaction_id="SRC-001")
        result = ingestion_identity.classify_transaction_identity(
            **classify_args(make_record(source_transaction_id="SRC-002")),
            connection=connection,
        )

    assert result.outcome == ingestion_identity.IdentityOutcome.UNIQUE


def test_classifier_reports_duplicate_canonical_identity_without_source_id(
    identity_repository,
):
    with identity_repository() as connection:
        seed_identity(connection, source_transaction_id="SRC-001")
        result = ingestion_identity.classify_transaction_identity(
            **classify_args(make_record()),
            connection=connection,
        )

    assert result.outcome == ingestion_identity.IdentityOutcome.DUPLICATE_CANONICAL_IDENTITY


def test_classifier_reports_unique_for_new_canonical_identity_without_source_id(
    identity_repository,
):
    with identity_repository() as connection:
        seed_identity(connection, source_transaction_id="SRC-001")
        result = ingestion_identity.classify_transaction_identity(
            **classify_args(make_record(amount_minor=9999)),
            connection=connection,
        )

    assert result.outcome == ingestion_identity.IdentityOutcome.UNIQUE


def test_classifier_reports_unique_for_new_source_and_hash(identity_repository):
    with identity_repository() as connection:
        seed_identity(connection, source_transaction_id="SRC-001")
        result = ingestion_identity.classify_transaction_identity(
            **classify_args(make_record(source_transaction_id="SRC-002", amount_minor=9999)),
            connection=connection,
        )

    assert result.outcome == ingestion_identity.IdentityOutcome.UNIQUE


def test_classifier_reports_canonical_identity_conflict_when_components_differ(
    identity_repository, monkeypatch
):
    with identity_repository() as connection:
        seed_identity(connection, source_transaction_id=None)
        original_builder = ingestion_identity.build_canonical_identity_hash
        monkeypatch.setattr(
            ingestion_identity,
            "build_canonical_identity_hash",
            lambda *args, **kwargs: original_builder(**identity_args()),
        )
        result = ingestion_identity.classify_transaction_identity(
            **classify_args(make_record(amount_minor=9999)),
            connection=connection,
        )

    assert result.outcome == ingestion_identity.IdentityOutcome.CANONICAL_IDENTITY_CONFLICT


def test_classification_result_does_not_expose_payload_details(identity_repository):
    with identity_repository() as connection:
        result = ingestion_identity.classify_transaction_identity(
            **classify_args(make_record(description="secret customer narrative")),
            connection=connection,
        )

    assert "secret customer narrative" not in repr(result)
    assert "SRC" not in repr(result)
