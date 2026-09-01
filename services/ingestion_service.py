"""Module 4 authorization, identity preparation, and atomic write orchestration.

``prepare_ingestion`` is read-only.  ``ingest`` uses the repository's
caller-owned transaction boundary to persist an authorized attempt, legacy
ledger row, and canonical identity companion as one unit.  Callers that opt
into ``record_failure`` receive a sanitized failed-attempt record after a
service-owned financial transaction is rolled back.
"""

import hashlib
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from database import queries
from services import ingestion_identity, ingestion_validation


AUTHORIZED_MEMBERSHIP_ROLES = frozenset({"owner", "manager"})


class IngestionServiceError(ValueError):
    """Safe, deterministic service failure without raw database details."""

    _MESSAGES = {
        "AUTHENTICATION_FAILED": "Authentication is required for ingestion.",
        "BUSINESS_NOT_FOUND": "The selected business is unavailable.",
        "MEMBERSHIP_REQUIRED": "An active business membership is required.",
        "INGESTION_FORBIDDEN": "The current business role cannot ingest data.",
        "ACCOUNT_NOT_AUTHORIZED": "The selected financial account is unavailable.",
        "BRIDGE_NOT_VERIFIED": "The business registry relationship is unavailable.",
        "REGISTRY_BUSINESS_NOT_FOUND": "The linked registry business is unavailable.",
        "REGISTRY_OWNER_NOT_FOUND": "The linked registry owner is unavailable.",
        "VALIDATION_FAILED": "The ingestion payload is invalid.",
        "IDENTITY_CONFLICT": "The ingestion contains a conflicting transaction identity.",
        "STORAGE_FAILED": "The ingestion could not be completed.",
    }

    def __init__(self, code: str) -> None:
        if code not in self._MESSAGES:
            code = "VALIDATION_FAILED"
        self.code = code
        self.error = code
        self.success = False
        super().__init__(self._MESSAGES[code])


@dataclass(frozen=True)
class PreparedRecord:
    """Safe per-record classification returned by preparation."""

    index: int
    outcome: ingestion_identity.IdentityOutcome
    canonical_identity_hash: str
    existing_identity_id: Optional[str] = None

    @property
    def status(self) -> str:
        return self.outcome.value


@dataclass(frozen=True)
class PreparedIngestion:
    """Trusted context and identity plan for a later write phase."""

    uploader_user_id: str
    business_id: str
    registry_business_id: str
    legacy_owner_user_id: str
    account_id: str
    currency: str
    source_system: str
    contract_version: str
    records: tuple[PreparedRecord, ...]

    @property
    def record_count(self) -> int:
        return len(self.records)


@dataclass(frozen=True)
class IngestionWriteResult:
    """Safe bounded result for a completed atomic write operation."""

    status: str
    attempt_id: Optional[str]
    record_count: int
    inserted_count: int
    duplicate_count: int
    rejected_count: int
    retry_count: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == "completed"

    @property
    def failed_count(self) -> int:
        """Expose a bounded failure count without persisting another counter."""
        return 1 if self.status == "failed" else 0


def _raise(code: str) -> None:
    raise IngestionServiceError(code)


def _session_token_hash(session_token: Any) -> str:
    # Session tokens are credentials.  Only their one-way lookup value is
    # passed to the repository and no rejected value is interpolated into an
    # exception.
    if type(session_token) is not str or session_token == "":
        _raise("AUTHENTICATION_FAILED")
    return hashlib.sha256(session_token.encode("utf-8")).hexdigest()


def _require_context_id(value: Any, code: str) -> str:
    if type(value) is not str or value == "":
        _raise(code)
    return value


def _identity_conflict(classification: ingestion_identity.IdentityClassification) -> bool:
    return classification.outcome in {
        ingestion_identity.IdentityOutcome.SOURCE_IDENTITY_CONFLICT,
        ingestion_identity.IdentityOutcome.CANONICAL_IDENTITY_CONFLICT,
    }


def _duplicate_for_within_batch(
    classification: ingestion_identity.IdentityClassification,
    *,
    outcome: ingestion_identity.IdentityOutcome,
) -> ingestion_identity.IdentityClassification:
    return ingestion_identity.IdentityClassification(
        outcome,
        classification.canonical_identity_hash,
        classification.existing_identity_id,
    )


@dataclass(frozen=True)
class _VerifiedContext:
    uploader_user_id: str
    business_id: str
    registry_business_id: str
    legacy_owner_user_id: str
    account_id: str
    currency: str


def _resolve_verified_context(
    *,
    session_token: Any,
    business_id: Any,
    account_id: Any,
    connection: Optional[Any] = None,
) -> _VerifiedContext:
    session = queries.get_active_session(_session_token_hash(session_token))
    if session is None or session["account_status"] != "active":
        _raise("AUTHENTICATION_FAILED")
    uploader_user_id = session["user_id"]

    business_id = _require_context_id(business_id, "BUSINESS_NOT_FOUND")
    account_id = _require_context_id(account_id, "ACCOUNT_NOT_AUTHORIZED")

    business = queries.get_active_business(business_id, connection=connection)
    if business is None:
        _raise("BUSINESS_NOT_FOUND")

    membership = queries.get_active_business_membership(
        business_id, uploader_user_id, connection=connection
    )
    if membership is None:
        _raise("MEMBERSHIP_REQUIRED")
    if membership["membership_role"] not in AUTHORIZED_MEMBERSHIP_ROLES:
        _raise("INGESTION_FORBIDDEN")

    account = queries.get_active_financial_account(
        account_id, business_id, connection=connection
    )
    if account is None:
        _raise("ACCOUNT_NOT_AUTHORIZED")

    bridge = queries.get_active_bridge(business_id, connection=connection)
    if (
        bridge is None
        or bridge["proposed_by_user_id"] == bridge["verified_by_user_id"]
    ):
        _raise("BRIDGE_NOT_VERIFIED")
    registry_business_id = bridge["registry_business_id"]

    registry_business = queries.get_registry_business(
        registry_business_id, connection=connection
    )
    if registry_business is None:
        _raise("REGISTRY_BUSINESS_NOT_FOUND")
    legacy_owner_user_id = queries.get_registry_owner(
        registry_business_id, connection=connection
    )
    if legacy_owner_user_id is None:
        _raise("REGISTRY_OWNER_NOT_FOUND")

    return _VerifiedContext(
        uploader_user_id=uploader_user_id,
        business_id=business_id,
        registry_business_id=registry_business_id,
        legacy_owner_user_id=legacy_owner_user_id,
        account_id=account_id,
        currency=account["currency"],
    )


def _classify_records(
    *,
    context: _VerifiedContext,
    source_system: str,
    records: list[dict[str, Any]],
    connection: Optional[Any] = None,
) -> list[ingestion_identity.IdentityClassification]:
    classifications: list[ingestion_identity.IdentityClassification] = []
    seen_hashes: dict[str, int] = {}
    seen_source_ids: dict[str, tuple[str, int]] = {}

    for index, record in enumerate(records):
        try:
            classification = ingestion_identity.classify_transaction_identity(
                business_id=context.business_id,
                registry_business_id=context.registry_business_id,
                account_id=context.account_id,
                source_system=source_system,
                currency=context.currency,
                record=record,
                connection=connection,
            )
        except ingestion_identity.IdentityError:
            _raise("IDENTITY_CONFLICT")

        source_transaction_id = record.get("source_transaction_id")
        prior_source = (
            seen_source_ids.get(source_transaction_id)
            if source_transaction_id is not None
            else None
        )
        if prior_source is not None:
            prior_hash, _prior_index = prior_source
            if prior_hash != classification.canonical_identity_hash:
                _raise("IDENTITY_CONFLICT")
            if classification.outcome == ingestion_identity.IdentityOutcome.UNIQUE:
                classification = _duplicate_for_within_batch(
                    classification,
                    outcome=ingestion_identity.IdentityOutcome.DUPLICATE_SOURCE_ID,
                )

        if (
            classification.canonical_identity_hash in seen_hashes
            and classification.outcome == ingestion_identity.IdentityOutcome.UNIQUE
        ):
            classification = _duplicate_for_within_batch(
                classification,
                outcome=ingestion_identity.IdentityOutcome.DUPLICATE_CANONICAL_IDENTITY,
            )

        if _identity_conflict(classification):
            _raise("IDENTITY_CONFLICT")

        seen_hashes[classification.canonical_identity_hash] = index
        if source_transaction_id is not None:
            seen_source_ids[source_transaction_id] = (
                classification.canonical_identity_hash,
                index,
            )
        classifications.append(classification)

    return classifications


def prepare_ingestion(
    *,
    session_token: Any,
    business_id: str,
    account_id: str,
    payload: Any,
) -> PreparedIngestion:
    """Authorize, validate, and classify a canonical ingestion request.

    The function is intentionally read-only: it creates no attempt, ledger
    row, identity row, or transaction.  All context identifiers are supplied
    explicitly and verified through repository lookups; canonical records
    cannot override the selected business or account.
    """
    context = _resolve_verified_context(
        session_token=session_token,
        business_id=business_id,
        account_id=account_id,
    )

    try:
        validated_payload = ingestion_validation.validate_ingestion_payload(payload)
    except ingestion_validation.ValidationError:
        _raise("VALIDATION_FAILED")

    source_system = validated_payload["source_system"]
    contract_version = validated_payload["contract_version"]
    classifications = _classify_records(
        context=context,
        source_system=source_system,
        records=validated_payload["records"],
    )
    prepared_records = [
        PreparedRecord(
            index=index,
            outcome=classification.outcome,
            canonical_identity_hash=classification.canonical_identity_hash,
            existing_identity_id=classification.existing_identity_id,
        )
        for index, classification in enumerate(classifications)
    ]

    return PreparedIngestion(
        uploader_user_id=context.uploader_user_id,
        business_id=context.business_id,
        registry_business_id=context.registry_business_id,
        legacy_owner_user_id=context.legacy_owner_user_id,
        account_id=context.account_id,
        currency=context.currency,
        source_system=source_system,
        contract_version=contract_version,
        records=tuple(prepared_records),
    )


def _legacy_amount(amount_minor: int) -> float:
    """Project exact minor units into the unchanged legacy REAL column."""
    return float(Decimal(amount_minor) / Decimal(100))


def _retry_count(parent_attempt_id: Optional[str], *, connection: Any) -> int:
    """Derive retry ordinal from immutable attempt parent links."""
    if parent_attempt_id is None:
        return 0
    if type(parent_attempt_id) is not str or parent_attempt_id == "":
        _raise("STORAGE_FAILED")

    count = 0
    current_id: Optional[str] = parent_attempt_id
    seen: set[str] = set()
    while current_id is not None:
        if current_id in seen:
            _raise("STORAGE_FAILED")
        seen.add(current_id)
        row = queries.get_ingestion_attempt(current_id, connection=connection)
        if row is None:
            _raise("STORAGE_FAILED")
        count += 1
        current_id = row["parent_attempt_id"]
    return count


def _record_failed_attempt(
    *,
    prepared: PreparedIngestion,
    parent_attempt_id: Optional[str],
    record_count: int,
) -> tuple[str, int]:
    """Persist only sanitized failure metadata after financial rollback."""
    safe_error = IngestionServiceError("STORAGE_FAILED")
    with queries.module4_transaction() as connection:
        retry_count = _retry_count(parent_attempt_id, connection=connection)
        attempt_id = queries.create_ingestion_attempt(
            business_id=prepared.business_id,
            registry_business_id=prepared.registry_business_id,
            account_id=prepared.account_id,
            uploader_user_id=prepared.uploader_user_id,
            source_system=prepared.source_system,
            contract_version=prepared.contract_version,
            currency=prepared.currency,
            record_count=record_count,
            parent_attempt_id=parent_attempt_id,
            connection=connection,
        )
        if not queries.fail_ingestion_attempt(
            attempt_id,
            inserted_count=0,
            duplicate_count=0,
            rejected_count=0,
            public_error_code=safe_error.code,
            public_error_message=str(safe_error),
            connection=connection,
        ):
            _raise("STORAGE_FAILED")
    return attempt_id, retry_count


def _persist_ingestion(
    *,
    session_token: Any,
    business_id: Any,
    account_id: Any,
    payload: Any,
    parent_attempt_id: Optional[str],
    connection: Any,
) -> IngestionWriteResult:
    """Perform the write path on the caller's connection only."""
    context = _resolve_verified_context(
        session_token=session_token,
        business_id=business_id,
        account_id=account_id,
        connection=connection,
    )
    try:
        validated_payload = ingestion_validation.validate_ingestion_payload(payload)
    except ingestion_validation.ValidationError:
        _raise("VALIDATION_FAILED")

    source_system = validated_payload["source_system"]
    contract_version = validated_payload["contract_version"]
    records = validated_payload["records"]
    classifications = _classify_records(
        context=context,
        source_system=source_system,
        records=records,
        connection=connection,
    )
    retry_count = _retry_count(parent_attempt_id, connection=connection)

    attempt_id = queries.create_ingestion_attempt(
        business_id=context.business_id,
        registry_business_id=context.registry_business_id,
        account_id=context.account_id,
        uploader_user_id=context.uploader_user_id,
        source_system=source_system,
        contract_version=contract_version,
        currency=context.currency,
        record_count=len(records),
        parent_attempt_id=parent_attempt_id,
        connection=connection,
    )

    inserted_count = 0
    duplicate_count = 0
    for record, classification in zip(records, classifications):
        if classification.outcome in {
            ingestion_identity.IdentityOutcome.DUPLICATE_SOURCE_ID,
            ingestion_identity.IdentityOutcome.DUPLICATE_CANONICAL_IDENTITY,
        }:
            duplicate_count += 1
            continue
        if _identity_conflict(classification):
            _raise("IDENTITY_CONFLICT")

        transaction_id = queries.insert_ledger_transaction(
            registry_business_id=context.registry_business_id,
            legacy_owner_user_id=context.legacy_owner_user_id,
            transaction_date=record["transaction_date"],
            amount=_legacy_amount(record["amount_minor"]),
            transaction_type=record["direction"],
            transaction_hash=classification.canonical_identity_hash,
            connection=connection,
        )
        queries.insert_transaction_identity(
            transaction_id=transaction_id,
            attempt_id=attempt_id,
            business_id=context.business_id,
            registry_business_id=context.registry_business_id,
            account_id=context.account_id,
            source_system=source_system,
            source_transaction_id=record.get("source_transaction_id"),
            transaction_date=record["transaction_date"],
            amount_minor=record["amount_minor"],
            direction=record["direction"],
            currency=context.currency,
            canonical_identity_hash=classification.canonical_identity_hash,
            connection=connection,
        )
        inserted_count += 1

    if not queries.complete_ingestion_attempt(
        attempt_id,
        inserted_count=inserted_count,
        duplicate_count=duplicate_count,
        rejected_count=0,
        connection=connection,
    ):
        _raise("STORAGE_FAILED")

    return IngestionWriteResult(
        status="completed",
        attempt_id=attempt_id,
        record_count=len(records),
        inserted_count=inserted_count,
        duplicate_count=duplicate_count,
        rejected_count=0,
        retry_count=retry_count,
    )


def _reclassify_after_rollback(
    *,
    session_token: Any,
    business_id: Any,
    account_id: Any,
    payload: Any,
) -> Optional[IngestionWriteResult]:
    """Interpret a post-check uniqueness failure without exposing SQLite."""
    try:
        context = _resolve_verified_context(
            session_token=session_token,
            business_id=business_id,
            account_id=account_id,
        )
        validated_payload = ingestion_validation.validate_ingestion_payload(payload)
        records = validated_payload["records"]
        classifications = _classify_records(
            context=context,
            source_system=validated_payload["source_system"],
            records=records,
        )
    except IngestionServiceError as error:
        if error.code == "IDENTITY_CONFLICT":
            raise
        return None
    except (ingestion_validation.ValidationError, ingestion_identity.IdentityError):
        return None

    if any(_identity_conflict(classification) for classification in classifications):
        _raise("IDENTITY_CONFLICT")
    if not classifications or not all(
        classification.outcome
        in {
            ingestion_identity.IdentityOutcome.DUPLICATE_SOURCE_ID,
            ingestion_identity.IdentityOutcome.DUPLICATE_CANONICAL_IDENTITY,
        }
        for classification in classifications
    ):
        return None

    return IngestionWriteResult(
        status="completed",
        attempt_id=None,
        record_count=len(records),
        inserted_count=0,
        duplicate_count=len(records),
        rejected_count=0,
    )


def ingest(
    *,
    session_token: Any,
    business_id: str,
    account_id: str,
    payload: Any,
    parent_attempt_id: Optional[str] = None,
    connection: Optional[Any] = None,
    record_failure: bool = False,
) -> IngestionWriteResult:
    """Persist a validated batch atomically, or raise a safe service error.

    With no connection supplied, this function owns the Module 4 transaction
    and guarantees rollback on every failure.  A supplied connection remains
    caller-owned: this function never commits or rolls it back.
    """
    # Run the read-only preparation first so unauthorized and malformed
    # requests cannot create an attempt.  The write transaction then repeats
    # all sensitive lookups and identity classification on its own connection.
    try:
        prepared = prepare_ingestion(
            session_token=session_token,
            business_id=business_id,
            account_id=account_id,
            payload=payload,
        )
    except IngestionServiceError:
        raise
    except (sqlite3.IntegrityError, sqlite3.OperationalError):
        _raise("STORAGE_FAILED")
    except Exception:
        _raise("STORAGE_FAILED")

    try:
        if connection is not None:
            return _persist_ingestion(
                session_token=session_token,
                business_id=business_id,
                account_id=account_id,
                payload=payload,
                parent_attempt_id=parent_attempt_id,
                connection=connection,
            )
        with queries.module4_transaction() as transaction_connection:
            return _persist_ingestion(
                session_token=session_token,
                business_id=business_id,
                account_id=account_id,
                payload=payload,
                parent_attempt_id=parent_attempt_id,
                connection=transaction_connection,
            )
    except IngestionServiceError as error:
        if error.code == "STORAGE_FAILED" and record_failure and connection is None:
            try:
                attempt_id, retry_count = _record_failed_attempt(
                    prepared=prepared,
                    parent_attempt_id=parent_attempt_id,
                    record_count=prepared.record_count,
                )
            except Exception:
                _raise("STORAGE_FAILED")
            return IngestionWriteResult(
                status="failed",
                attempt_id=attempt_id,
                record_count=prepared.record_count,
                inserted_count=0,
                duplicate_count=0,
                rejected_count=0,
                retry_count=retry_count,
                error_code=error.code,
                error_message=str(error),
            )
        raise
    except (sqlite3.IntegrityError, sqlite3.OperationalError):
        if connection is None:
            try:
                reclassified = _reclassify_after_rollback(
                    session_token=session_token,
                    business_id=business_id,
                    account_id=account_id,
                    payload=payload,
                )
            except IngestionServiceError:
                raise
            except Exception:
                # Reclassification is best-effort.  A failure while reading
                # the race state must still map to the fixed storage outcome.
                reclassified = None
            if reclassified is not None:
                return reclassified
            if record_failure:
                try:
                    attempt_id, retry_count = _record_failed_attempt(
                        prepared=prepared,
                        parent_attempt_id=parent_attempt_id,
                        record_count=prepared.record_count,
                    )
                except Exception:
                    _raise("STORAGE_FAILED")
                error = IngestionServiceError("STORAGE_FAILED")
                return IngestionWriteResult(
                    status="failed",
                    attempt_id=attempt_id,
                    record_count=prepared.record_count,
                    inserted_count=0,
                    duplicate_count=0,
                    rejected_count=0,
                    retry_count=retry_count,
                    error_code=error.code,
                    error_message=str(error),
                )
        _raise("STORAGE_FAILED")
    except Exception:
        if record_failure and connection is None:
            try:
                attempt_id, retry_count = _record_failed_attempt(
                    prepared=prepared,
                    parent_attempt_id=parent_attempt_id,
                    record_count=prepared.record_count,
                )
            except Exception:
                _raise("STORAGE_FAILED")
            error = IngestionServiceError("STORAGE_FAILED")
            return IngestionWriteResult(
                status="failed",
                attempt_id=attempt_id,
                record_count=prepared.record_count,
                inserted_count=0,
                duplicate_count=0,
                rejected_count=0,
                retry_count=retry_count,
                error_code=error.code,
                error_message=str(error),
            )
        _raise("STORAGE_FAILED")


__all__ = [
    "AUTHORIZED_MEMBERSHIP_ROLES",
    "IngestionServiceError",
    "IngestionWriteResult",
    "PreparedIngestion",
    "PreparedRecord",
    "ingest",
    "prepare_ingestion",
]
