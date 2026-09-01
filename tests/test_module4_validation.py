import math
from decimal import Decimal

import pytest

from services import ingestion_validation


CONTRACT_VERSION = "finsight_ingestion_v1"
SOURCE_SYSTEM = "finsight_demo_bank_statement_v1"


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


def assert_validation_error(call, code):
    with pytest.raises(ingestion_validation.ValidationError) as exc_info:
        call()
    assert exc_info.value.code == code
    assert "1234" not in str(exc_info.value)
    assert "secret" not in str(exc_info.value)


def test_valid_minimum_payload_returns_detached_canonical_data():
    payload = make_payload()

    result = ingestion_validation.validate_ingestion_payload(payload)

    assert result == payload
    assert result is not payload
    assert result["records"] is not payload["records"]
    assert result["records"][0] is not payload["records"][0]


def test_valid_full_payload_preserves_supported_values_exactly():
    record = make_record(
        source_transaction_id="ABC123",
        category="Supplies",
        description="Coffee Shop",
        counterparty="Synthetic Counterparty",
        payment_method="bank_transfer",
        source_subtype="statement_line",
        source_record_reference="row-17",
        balance_after_minor=-500,
    )

    assert ingestion_validation.validate_ingestion_payload(make_payload([record])) == {
        "contract_version": CONTRACT_VERSION,
        "source_system": SOURCE_SYSTEM,
        "records": [record],
    }


@pytest.mark.parametrize(
    "payload,code",
    [
        ({"source_system": SOURCE_SYSTEM, "records": [make_record()]}, "MISSING_FIELD"),
        ({"contract_version": None, "source_system": SOURCE_SYSTEM, "records": [make_record()]}, "INVALID_FIELD"),
        ({"contract_version": "v1", "source_system": SOURCE_SYSTEM, "records": [make_record()]}, "UNSUPPORTED_CONTRACT_VERSION"),
        ({"contract_version": " " + CONTRACT_VERSION, "source_system": SOURCE_SYSTEM, "records": [make_record()]}, "UNSUPPORTED_CONTRACT_VERSION"),
        ({"contract_version": CONTRACT_VERSION, "records": [make_record()]}, "MISSING_FIELD"),
        ({"contract_version": CONTRACT_VERSION, "source_system": None, "records": [make_record()]}, "INVALID_FIELD"),
        ({"contract_version": CONTRACT_VERSION, "source_system": "demo_bank", "records": [make_record()]}, "UNSUPPORTED_SOURCE_SYSTEM"),
        ({"contract_version": CONTRACT_VERSION, "source_system": " " + SOURCE_SYSTEM, "records": [make_record()]}, "UNSUPPORTED_SOURCE_SYSTEM"),
        ({"contract_version": CONTRACT_VERSION, "source_system": SOURCE_SYSTEM}, "MISSING_FIELD"),
        ({"contract_version": CONTRACT_VERSION, "source_system": SOURCE_SYSTEM, "records": None}, "INVALID_RECORDS"),
        ({"contract_version": CONTRACT_VERSION, "source_system": SOURCE_SYSTEM, "records": ()}, "INVALID_RECORDS"),
        ({"contract_version": CONTRACT_VERSION, "source_system": SOURCE_SYSTEM, "records": {}}, "INVALID_RECORDS"),
        ({"contract_version": CONTRACT_VERSION, "source_system": SOURCE_SYSTEM, "records": "records"}, "INVALID_RECORDS"),
        ({"contract_version": CONTRACT_VERSION, "source_system": SOURCE_SYSTEM, "records": []}, "RECORD_COUNT_OUT_OF_RANGE"),
        ({"contract_version": CONTRACT_VERSION, "source_system": SOURCE_SYSTEM, "records": [make_record()], "account_id": "untrusted"}, "UNKNOWN_FIELD"),
    ],
)
def test_envelope_rejects_invalid_shape_and_values(payload, code):
    assert_validation_error(lambda: ingestion_validation.validate_ingestion_payload(payload), code)


def test_records_must_be_a_list_not_a_generator():
    payload = make_payload((record for record in [make_record()]))
    assert_validation_error(lambda: ingestion_validation.validate_ingestion_payload(payload), "INVALID_RECORDS")


def test_record_count_boundaries_are_inclusive():
    one = make_payload([make_record()])
    thousand = make_payload([make_record() for _ in range(1000)])

    assert len(ingestion_validation.validate_ingestion_payload(one)["records"]) == 1
    assert len(ingestion_validation.validate_ingestion_payload(thousand)["records"]) == 1000


def test_more_than_maximum_records_is_rejected_without_truncation():
    payload = make_payload([make_record() for _ in range(1001)])
    assert_validation_error(
        lambda: ingestion_validation.validate_ingestion_payload(payload),
        "RECORD_COUNT_OUT_OF_RANGE",
    )


@pytest.mark.parametrize("missing", ["transaction_date", "amount_minor", "direction"])
def test_required_record_fields_must_be_present(missing):
    record = make_record()
    del record[missing]
    assert_validation_error(
        lambda: ingestion_validation.validate_ingestion_payload(make_payload([record])),
        "MISSING_FIELD",
    )


@pytest.mark.parametrize("field", ["transaction_date", "amount_minor", "direction"])
def test_required_record_fields_must_not_be_null(field):
    assert_validation_error(
        lambda: ingestion_validation.validate_ingestion_payload(
            make_payload([make_record(**{field: None})])
        ),
        "INVALID_FIELD",
    )


@pytest.mark.parametrize(
    "field",
    [
        "account_id",
        "account_name",
        "account_number",
        "business_id",
        "registry_business_id",
        "currency",
        "uploader_user_id",
        "filename",
        "file_path",
        "employee_id",
        "employee_name",
        "salary",
        "gross_salary",
        "net_salary",
        "payroll_period",
        "pan",
        "aadhaar",
    ],
)
def test_unknown_account_currency_and_payroll_fields_fail_closed(field):
    assert_validation_error(
        lambda: ingestion_validation.validate_ingestion_payload(
            make_payload([make_record(**{field: "untrusted"})])
        ),
        "UNKNOWN_FIELD",
    )


@pytest.mark.parametrize(
    "value,code",
    [
        (1, None),
        (99_999_999_999_999, None),
        (0, "AMOUNT_OUT_OF_RANGE"),
        (-1, "AMOUNT_OUT_OF_RANGE"),
        (100_000_000_000_000, "AMOUNT_OUT_OF_RANGE"),
        (True, "INVALID_FIELD"),
        (False, "INVALID_FIELD"),
        (1.0, "INVALID_FIELD"),
        ("1234", "INVALID_FIELD"),
        (None, "INVALID_FIELD"),
        (math.nan, "INVALID_FIELD"),
        (math.inf, "INVALID_FIELD"),
        (-math.inf, "INVALID_FIELD"),
    ],
)
def test_amount_minor_is_exact_positive_builtin_integer(value, code):
    call = lambda: ingestion_validation.validate_ingestion_payload(
        make_payload([make_record(amount_minor=value)])
    )
    if code is None:
        assert call()["records"][0]["amount_minor"] == value
    else:
        assert_validation_error(call, code)


@pytest.mark.parametrize("value", [Decimal("1234"), b"1234", bytearray(b"1234")])
def test_amount_minor_rejects_non_json_integer_scalars(value):
    assert_validation_error(
        lambda: ingestion_validation.validate_ingestion_payload(
            make_payload([make_record(amount_minor=value)])
        ),
        "INVALID_FIELD",
    )


@pytest.mark.parametrize(
    "direction,valid",
    [("income", True), ("expense", True), ("Income", False), (" INCOME", False),
     ("expense ", False), ("debit", False), ("credit", False), ("", False),
     (None, False), (1, False)],
)
def test_direction_uses_exact_approved_vocabulary(direction, valid):
    call = lambda: ingestion_validation.validate_ingestion_payload(
        make_payload([make_record(direction=direction)])
    )
    if valid:
        assert call()["records"][0]["direction"] == direction
    else:
        assert_validation_error(call, "INVALID_FIELD")


@pytest.mark.parametrize(
    "date_value,valid",
    [("2026-08-31", True), ("2024-02-29", True), ("2023-02-29", False),
     ("2026-02-30", False), ("01/02/2026", False), ("31-01-2026", False),
     ("2026-08-31T00:00:00Z", False), (" 2026-08-31", False),
     ("2026-08-31 ", False), ("", False), (None, False)],
)
def test_transaction_date_requires_exact_real_calendar_date(date_value, valid):
    call = lambda: ingestion_validation.validate_ingestion_payload(
        make_payload([make_record(transaction_date=date_value)])
    )
    if valid:
        assert call()["records"][0]["transaction_date"] == date_value
    else:
        assert_validation_error(call, "INVALID_FIELD")


@pytest.mark.parametrize(
    "value,valid,code",
    [(None, True, None), ("SRC-001", True, None), ("", False, "INVALID_FIELD"),
     (" ", False, "INVALID_FIELD"), (" SRC-001", False, "INVALID_FIELD"),
     ("SRC-001 ", False, "INVALID_FIELD"), (123, False, "INVALID_FIELD"),
     ("x" * 128, True, None), ("x" * 129, False, "TEXT_TOO_LONG")],
)
def test_source_transaction_id_is_optional_but_strict_when_present(value, valid, code):
    record = make_record(source_transaction_id=value)
    call = lambda: ingestion_validation.validate_ingestion_payload(make_payload([record]))
    if valid:
        assert call()["records"][0]["source_transaction_id"] == value
    else:
        assert_validation_error(call, code)


OPTIONAL_TEXT_LIMITS = {
    "category": 100,
    "description": 500,
    "counterparty": 200,
    "payment_method": 50,
    "source_subtype": 100,
    "source_record_reference": 128,
}


@pytest.mark.parametrize("field,max_length", OPTIONAL_TEXT_LIMITS.items())
def test_optional_text_field_accepts_exact_limit(field, max_length):
    value = "x" * max_length
    result = ingestion_validation.validate_ingestion_payload(
        make_payload([make_record(**{field: value})])
    )
    assert result["records"][0][field] == value


@pytest.mark.parametrize("field,max_length", OPTIONAL_TEXT_LIMITS.items())
@pytest.mark.parametrize("value", [None, "", " ", "  value", "value  ", "x"])
def test_optional_text_field_rejects_null_blank_or_surrounding_whitespace(
    field, max_length, value
):
    if value == "x":
        return
    assert_validation_error(
        lambda: ingestion_validation.validate_ingestion_payload(
            make_payload([make_record(**{field: value})])
        ),
        "INVALID_FIELD",
    )


@pytest.mark.parametrize("field,max_length", OPTIONAL_TEXT_LIMITS.items())
def test_optional_text_field_rejects_values_over_limit(field, max_length):
    assert_validation_error(
        lambda: ingestion_validation.validate_ingestion_payload(
            make_payload([make_record(**{field: "x" * (max_length + 1)})])
        ),
        "TEXT_TOO_LONG",
    )


@pytest.mark.parametrize(
    "value,valid,code",
    [
        (-99_999_999_999_999, True, None),
        (0, True, None),
        (99_999_999_999_999, True, None),
        (-100_000_000_000_000, False, "BALANCE_OUT_OF_RANGE"),
        (100_000_000_000_000, False, "BALANCE_OUT_OF_RANGE"),
        (True, False, "INVALID_FIELD"),
        (1.0, False, "INVALID_FIELD"),
        ("100", False, "INVALID_FIELD"),
        (None, False, "INVALID_FIELD"),
    ],
)
def test_balance_after_minor_is_optional_signed_integer(value, valid, code):
    record = make_record()
    record["balance_after_minor"] = value
    call = lambda: ingestion_validation.validate_ingestion_payload(make_payload([record]))
    if valid:
        assert call()["records"][0]["balance_after_minor"] == value
    else:
        assert_validation_error(call, code)


def test_balance_after_minor_absent_is_valid_and_not_added():
    result = ingestion_validation.validate_ingestion_payload(make_payload())
    assert "balance_after_minor" not in result["records"][0]


def test_input_is_not_mutated_by_validation():
    payload = make_payload([make_record(category="Supplies")])
    original = {**payload, "records": [dict(payload["records"][0])]}

    result = ingestion_validation.validate_ingestion_payload(payload)
    result["records"][0]["category"] = "changed"

    assert payload == original


def test_validation_does_not_open_database_connections(monkeypatch):
    from database import queries

    monkeypatch.setattr(
        queries,
        "get_connection",
        lambda: pytest.fail("canonical validation must not open SQLite"),
    )

    assert ingestion_validation.validate_ingestion_payload(make_payload())["records"]


def test_validation_error_does_not_include_sensitive_payload_values():
    payload = make_payload([make_record(description="secret customer narrative")])
    payload["unexpected"] = "secret"

    with pytest.raises(ingestion_validation.ValidationError) as exc_info:
        ingestion_validation.validate_ingestion_payload(payload)

    assert exc_info.value.code == "UNKNOWN_FIELD"
    assert "secret customer narrative" not in str(exc_info.value)
    assert "secret" not in str(exc_info.value)
