"""Canonical transaction identity and duplicate classification for Module 4."""

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from database import queries


IDENTITY_VERSION = "finsight_transaction_identity_v1"
SOURCE_IDENTITY_VERSION = "finsight_source_transaction_identity_v1"


class IdentityError(ValueError):
    """Safe error raised when trusted identity inputs violate invariants."""

    def __init__(self, message: str = "Canonical identity input is invalid.") -> None:
        super().__init__(message)


class IdentityOutcome(str, Enum):
    UNIQUE = "UNIQUE"
    DUPLICATE_SOURCE_ID = "DUPLICATE_SOURCE_ID"
    DUPLICATE_CANONICAL_IDENTITY = "DUPLICATE_CANONICAL_IDENTITY"
    SOURCE_IDENTITY_CONFLICT = "SOURCE_IDENTITY_CONFLICT"
    CANONICAL_IDENTITY_CONFLICT = "CANONICAL_IDENTITY_CONFLICT"


@dataclass(frozen=True)
class IdentityClassification:
    outcome: IdentityOutcome
    canonical_identity_hash: str
    existing_identity_id: Optional[str] = None

    @property
    def status(self) -> str:
        return self.outcome.value


def _require_text(value: Any) -> str:
    if type(value) is not str or value == "":
        raise IdentityError()
    return value


def _require_identity_inputs(
    account_id: Any,
    source_system: Any,
    currency: Any,
    transaction_date: Any,
    amount_minor: Any,
    direction: Any,
    identity_version: Any,
) -> list[Any]:
    if identity_version != IDENTITY_VERSION or type(identity_version) is not str:
        raise IdentityError()
    values = [
        _require_text(account_id),
        _require_text(source_system),
        _require_text(currency),
        _require_text(transaction_date),
        amount_minor,
        _require_text(direction),
    ]
    if type(amount_minor) is not int or amount_minor <= 0:
        raise IdentityError()
    return [identity_version, *values]


def serialize_canonical_identity(
    account_id: Any,
    source_system: Any,
    currency: Any,
    transaction_date: Any,
    amount_minor: Any,
    direction: Any,
    identity_version: Any = IDENTITY_VERSION,
) -> str:
    """Return the exact compact JSON identity serialization as text."""
    values = _require_identity_inputs(
        account_id,
        source_system,
        currency,
        transaction_date,
        amount_minor,
        direction,
        identity_version,
    )
    return json.dumps(
        values,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def build_canonical_identity_hash(
    account_id: Any,
    source_system: Any,
    currency: Any,
    transaction_date: Any,
    amount_minor: Any,
    direction: Any,
    identity_version: Any = IDENTITY_VERSION,
) -> str:
    """Hash the exact canonical serialization with SHA-256."""
    serialized = serialize_canonical_identity(
        account_id,
        source_system,
        currency,
        transaction_date,
        amount_minor,
        direction,
        identity_version,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def serialize_source_identity(
    account_id: Any,
    source_system: Any,
    source_transaction_id: Any,
    currency: Any,
    transaction_date: Any,
    amount_minor: Any,
    direction: Any,
    identity_version: Any = SOURCE_IDENTITY_VERSION,
) -> str:
    """Serialize a source-backed transaction identity deterministically.

    A trustworthy source transaction ID has precedence over the fallback
    financial tuple.  The financial components remain in the serialization so
    reusing one source ID for different transaction data is a conflict rather
    than a duplicate.
    """
    if identity_version != SOURCE_IDENTITY_VERSION or type(identity_version) is not str:
        raise IdentityError()
    source_transaction_id = _require_text(source_transaction_id)
    values = _require_identity_inputs(
        account_id,
        source_system,
        currency,
        transaction_date,
        amount_minor,
        direction,
        IDENTITY_VERSION,
    )
    return json.dumps(
        [identity_version, values[1], values[2], source_transaction_id, *values[3:]],
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def build_source_identity_hash(
    account_id: Any,
    source_system: Any,
    source_transaction_id: Any,
    currency: Any,
    transaction_date: Any,
    amount_minor: Any,
    direction: Any,
) -> str:
    """Hash a source-backed identity scoped to account and source system."""
    serialized = serialize_source_identity(
        account_id,
        source_system,
        source_transaction_id,
        currency,
        transaction_date,
        amount_minor,
        direction,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_canonical_identity_hash_for_record(
    record: Any,
    account_id: Any,
    source_system: Any,
    currency: Any,
    identity_version: Any = IDENTITY_VERSION,
) -> str:
    """Build the persisted identity hash using source-ID-first precedence.

    Records with a trustworthy source transaction ID use a source-backed hash.
    Records without one retain the legacy date/amount/direction fallback hash.
    """
    if type(record) is not dict:
        raise IdentityError()
    try:
        transaction_date = record["transaction_date"]
        amount_minor = record["amount_minor"]
        direction = record["direction"]
    except (KeyError, TypeError):
        raise IdentityError() from None

    source_transaction_id = _source_transaction_id(record)
    if source_transaction_id is not None:
        return build_source_identity_hash(
            account_id,
            source_system,
            source_transaction_id,
            currency,
            transaction_date,
            amount_minor,
            direction,
        )

    return build_canonical_identity_hash(
        account_id,
        source_system,
        currency,
        transaction_date,
        amount_minor,
        direction,
        identity_version,
    )


def _source_transaction_id(record: dict[str, Any]) -> Optional[str]:
    if "source_transaction_id" not in record:
        return None
    value = record["source_transaction_id"]
    if value is None:
        return None
    if type(value) is not str or value == "" or value.strip() == "" or value != value.strip():
        raise IdentityError()
    return value


def _persisted_components_match(
    row: Any,
    *,
    account_id: str,
    source_system: str,
    currency: str,
    transaction_date: str,
    amount_minor: int,
    direction: str,
) -> bool:
    expected = {
        "account_id": account_id,
        "source_system": source_system,
        "currency": currency,
        "transaction_date": transaction_date,
        "amount_minor": amount_minor,
        "direction": direction,
    }
    try:
        return all(row[field] == value for field, value in expected.items())
    except (KeyError, IndexError, TypeError):
        return False


def _identity_id(row: Any) -> Optional[str]:
    try:
        value = row["identity_id"]
    except (KeyError, IndexError, TypeError):
        return None
    return value if type(value) is str else None


def classify_transaction_identity(
    *,
    business_id: str,
    registry_business_id: str,
    account_id: str,
    source_system: str,
    currency: str,
    record: dict[str, Any],
    connection: Optional[Any] = None,
) -> IdentityClassification:
    """Classify a validated record using existing read-only identity queries."""
    business_id = _require_text(business_id)
    registry_business_id = _require_text(registry_business_id)
    account_id = _require_text(account_id)
    source_system = _require_text(source_system)
    currency = _require_text(currency)
    if type(record) is not dict:
        raise IdentityError()

    source_transaction_id = _source_transaction_id(record)
    canonical_hash = build_canonical_identity_hash_for_record(
        record,
        account_id,
        source_system,
        currency,
    )
    identity_values = {
        "account_id": account_id,
        "source_system": source_system,
        "currency": currency,
        "transaction_date": record["transaction_date"],
        "amount_minor": record["amount_minor"],
        "direction": record["direction"],
    }

    if source_transaction_id is not None:
        source_match = queries.find_identity_by_source(
            business_id=business_id,
            registry_business_id=registry_business_id,
            account_id=account_id,
            source_system=source_system,
            source_transaction_id=source_transaction_id,
            connection=connection,
        )
        if source_match is not None:
            if _persisted_components_match(source_match, **identity_values):
                return IdentityClassification(
                    IdentityOutcome.DUPLICATE_SOURCE_ID,
                    canonical_hash,
                    _identity_id(source_match),
                )
            return IdentityClassification(
                IdentityOutcome.SOURCE_IDENTITY_CONFLICT,
                canonical_hash,
                _identity_id(source_match),
            )

    canonical_match = queries.find_identity_by_hash(
        business_id=business_id,
        registry_business_id=registry_business_id,
        account_id=account_id,
        source_system=source_system,
        canonical_identity_hash=canonical_hash,
        connection=connection,
    )
    if canonical_match is None:
        return IdentityClassification(IdentityOutcome.UNIQUE, canonical_hash)
    if _persisted_components_match(canonical_match, **identity_values):
        return IdentityClassification(
            IdentityOutcome.DUPLICATE_CANONICAL_IDENTITY,
            canonical_hash,
            _identity_id(canonical_match),
        )
    return IdentityClassification(
        IdentityOutcome.CANONICAL_IDENTITY_CONFLICT,
        canonical_hash,
        _identity_id(canonical_match),
    )


__all__ = [
    "IDENTITY_VERSION",
    "SOURCE_IDENTITY_VERSION",
    "IdentityClassification",
    "IdentityError",
    "IdentityOutcome",
    "build_canonical_identity_hash",
    "build_canonical_identity_hash_for_record",
    "build_source_identity_hash",
    "classify_transaction_identity",
    "serialize_canonical_identity",
    "serialize_source_identity",
]
