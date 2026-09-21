"""Pure validation for the controlled Module 4 canonical payload."""

from datetime import date
from typing import Any, Optional


CONTRACT_VERSION = "finsight_ingestion_v1"
SOURCE_SYSTEM = "finsight_demo_bank_statement_v1"

MIN_RECORD_COUNT = 1
# Bounded for the current single-transaction, per-record identity workflow.
MAX_RECORD_COUNT = 5000
MIN_AMOUNT_MINOR = 1
MAX_AMOUNT_MINOR = 99_999_999_999_999
MIN_BALANCE_AFTER_MINOR = -99_999_999_999_999
MAX_BALANCE_AFTER_MINOR = 99_999_999_999_999

ENVELOPE_FIELDS = frozenset({"contract_version", "source_system", "records"})
REQUIRED_RECORD_FIELDS = ("transaction_date", "amount_minor", "direction")
OPTIONAL_RECORD_FIELDS = (
    "source_transaction_id",
    "category",
    "description",
    "counterparty",
    "payment_method",
    "source_subtype",
    "source_record_reference",
    "balance_after_minor",
)
RECORD_FIELDS = frozenset(REQUIRED_RECORD_FIELDS + OPTIONAL_RECORD_FIELDS)
OPTIONAL_TEXT_LIMITS = {
    "category": 100,
    "description": 500,
    "counterparty": 200,
    "payment_method": 50,
    "source_subtype": 100,
    "source_record_reference": 128,
    "source_transaction_id": 128,
}
ALLOWED_DIRECTIONS = frozenset({"income", "expense"})


class ValidationError(ValueError):
    """Safe, deterministic validation failure for later service mapping."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        field: Optional[str] = None,
        record_index: Optional[int] = None,
    ) -> None:
        self.code = code
        self.field = field
        self.record_index = record_index
        super().__init__(message)


_SAFE_MESSAGES = {
    "INVALID_PAYLOAD": "The ingestion payload is invalid.",
    "MISSING_FIELD": "A required ingestion field is missing.",
    "UNKNOWN_FIELD": "The ingestion payload contains an unsupported field.",
    "INVALID_FIELD": "An ingestion field has an invalid value.",
    "UNSUPPORTED_CONTRACT_VERSION": "The ingestion contract version is not supported.",
    "UNSUPPORTED_SOURCE_SYSTEM": "The ingestion source system is not supported.",
    "INVALID_RECORDS": "The ingestion records collection is invalid.",
    "RECORD_COUNT_OUT_OF_RANGE": "The ingestion record count is outside the supported range.",
    "AMOUNT_OUT_OF_RANGE": "The transaction amount is outside the supported range.",
    "BALANCE_OUT_OF_RANGE": "The balance is outside the supported range.",
    "TEXT_TOO_LONG": "An ingestion text field exceeds its supported length.",
}


def _raise(
    code: str,
    *,
    field: Optional[str] = None,
    record_index: Optional[int] = None,
) -> None:
    raise ValidationError(
        code,
        _SAFE_MESSAGES[code],
        field=field,
        record_index=record_index,
    )


def _validate_exact_text(
    field: str,
    value: Any,
    *,
    record_index: Optional[int],
    allow_null: bool = False,
) -> Optional[str]:
    if value is None and allow_null:
        return None
    if type(value) is not str or value == "" or value.strip() == "":
        _raise("INVALID_FIELD", field=field, record_index=record_index)
    if value != value.strip():
        _raise("INVALID_FIELD", field=field, record_index=record_index)
    if len(value) > OPTIONAL_TEXT_LIMITS[field]:
        _raise("TEXT_TOO_LONG", field=field, record_index=record_index)
    return value


def _validate_transaction_date(value: Any, record_index: int) -> str:
    if type(value) is not str or len(value) != 10:
        _raise("INVALID_FIELD", field="transaction_date", record_index=record_index)
    if (
        value[4] != "-"
        or value[7] != "-"
        or not value[:4].isdigit()
        or not value[5:7].isdigit()
        or not value[8:].isdigit()
        or any(character not in "0123456789-" for character in value)
    ):
        _raise("INVALID_FIELD", field="transaction_date", record_index=record_index)
    try:
        date.fromisoformat(value)
    except ValueError:
        _raise("INVALID_FIELD", field="transaction_date", record_index=record_index)
    return value


def _validate_amount_minor(value: Any, record_index: int) -> int:
    if type(value) is not int:
        _raise("INVALID_FIELD", field="amount_minor", record_index=record_index)
    if not MIN_AMOUNT_MINOR <= value <= MAX_AMOUNT_MINOR:
        _raise("AMOUNT_OUT_OF_RANGE", field="amount_minor", record_index=record_index)
    return value


def _validate_direction(value: Any, record_index: int) -> str:
    if type(value) is not str or value not in ALLOWED_DIRECTIONS:
        _raise("INVALID_FIELD", field="direction", record_index=record_index)
    return value


def _validate_balance_after_minor(value: Any, record_index: int) -> int:
    if type(value) is not int:
        _raise("INVALID_FIELD", field="balance_after_minor", record_index=record_index)
    if not MIN_BALANCE_AFTER_MINOR <= value <= MAX_BALANCE_AFTER_MINOR:
        _raise(
            "BALANCE_OUT_OF_RANGE",
            field="balance_after_minor",
            record_index=record_index,
        )
    return value


def validate_canonical_record(record: Any, record_index: int = 0) -> dict[str, Any]:
    """Validate and detach one already-standardized canonical record."""
    if type(record) is not dict:
        _raise("INVALID_RECORDS", record_index=record_index)

    if any(type(field) is not str or field not in RECORD_FIELDS for field in record):
        _raise("UNKNOWN_FIELD", record_index=record_index)

    for field in REQUIRED_RECORD_FIELDS:
        if field not in record:
            _raise("MISSING_FIELD", field=field, record_index=record_index)
        if record[field] is None:
            _raise("INVALID_FIELD", field=field, record_index=record_index)

    validated: dict[str, Any] = {
        "transaction_date": _validate_transaction_date(
            record["transaction_date"], record_index
        ),
        "amount_minor": _validate_amount_minor(record["amount_minor"], record_index),
        "direction": _validate_direction(record["direction"], record_index),
    }

    for field in OPTIONAL_RECORD_FIELDS:
        if field not in record:
            continue
        value = record[field]
        if field == "source_transaction_id":
            validated[field] = _validate_exact_text(
                field,
                value,
                record_index=record_index,
                allow_null=True,
            )
        elif field == "balance_after_minor":
            validated[field] = _validate_balance_after_minor(value, record_index)
        else:
            validated[field] = _validate_exact_text(
                field,
                value,
                record_index=record_index,
            )

    return validated


def validate_ingestion_payload(payload: Any) -> dict[str, Any]:
    """Validate and return a detached controlled-V1 canonical payload."""
    if type(payload) is not dict:
        _raise("INVALID_PAYLOAD")

    if any(type(field) is not str or field not in ENVELOPE_FIELDS for field in payload):
        _raise("UNKNOWN_FIELD")

    for field in ("contract_version", "source_system", "records"):
        if field not in payload:
            _raise("MISSING_FIELD", field=field)
    for field in ("contract_version", "source_system"):
        if payload[field] is None:
            _raise("INVALID_FIELD", field=field)

    contract_version = payload["contract_version"]
    if type(contract_version) is not str:
        _raise("INVALID_FIELD", field="contract_version")
    if contract_version != CONTRACT_VERSION:
        _raise("UNSUPPORTED_CONTRACT_VERSION", field="contract_version")

    source_system = payload["source_system"]
    if type(source_system) is not str:
        _raise("INVALID_FIELD", field="source_system")
    if source_system != SOURCE_SYSTEM:
        _raise("UNSUPPORTED_SOURCE_SYSTEM", field="source_system")

    records = payload["records"]
    if type(records) is not list:
        _raise("INVALID_RECORDS", field="records")
    if not MIN_RECORD_COUNT <= len(records) <= MAX_RECORD_COUNT:
        _raise("RECORD_COUNT_OUT_OF_RANGE", field="records")

    return {
        "contract_version": contract_version,
        "source_system": source_system,
        "records": [
            validate_canonical_record(record, record_index=index)
            for index, record in enumerate(records)
        ],
    }


__all__ = [
    "ALLOWED_DIRECTIONS",
    "CONTRACT_VERSION",
    "ENVELOPE_FIELDS",
    "MAX_AMOUNT_MINOR",
    "MAX_BALANCE_AFTER_MINOR",
    "MAX_RECORD_COUNT",
    "MIN_AMOUNT_MINOR",
    "MIN_BALANCE_AFTER_MINOR",
    "MIN_RECORD_COUNT",
    "OPTIONAL_RECORD_FIELDS",
    "OPTIONAL_TEXT_LIMITS",
    "RECORD_FIELDS",
    "SOURCE_SYSTEM",
    "ValidationError",
    "validate_canonical_record",
    "validate_ingestion_payload",
]
