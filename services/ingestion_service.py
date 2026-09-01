"""Authorization and read-only orchestration for Module 4 ingestion.

This module deliberately stops before attempt creation or financial writes.  It
establishes the trusted context, validates the canonical payload, and performs
identity classification so a later write phase can operate on a fully checked
plan.
"""

import hashlib
from dataclasses import dataclass
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
    }

    def __init__(self, code: str) -> None:
        if code not in self._MESSAGES:
            code = "VALIDATION_FAILED"
        self.code = code
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
    session = queries.get_active_session(_session_token_hash(session_token))
    if session is None or session["account_status"] != "active":
        _raise("AUTHENTICATION_FAILED")
    uploader_user_id = session["user_id"]

    business_id = _require_context_id(business_id, "BUSINESS_NOT_FOUND")
    account_id = _require_context_id(account_id, "ACCOUNT_NOT_AUTHORIZED")

    business = queries.get_active_business(business_id)
    if business is None:
        _raise("BUSINESS_NOT_FOUND")

    membership = queries.get_active_business_membership(business_id, uploader_user_id)
    if membership is None:
        _raise("MEMBERSHIP_REQUIRED")
    if membership["membership_role"] not in AUTHORIZED_MEMBERSHIP_ROLES:
        _raise("INGESTION_FORBIDDEN")

    account = queries.get_active_financial_account(account_id, business_id)
    if account is None:
        _raise("ACCOUNT_NOT_AUTHORIZED")

    bridge = queries.get_active_bridge(business_id)
    if (
        bridge is None
        or bridge["proposed_by_user_id"] == bridge["verified_by_user_id"]
    ):
        _raise("BRIDGE_NOT_VERIFIED")
    registry_business_id = bridge["registry_business_id"]

    registry_business = queries.get_registry_business(registry_business_id)
    if registry_business is None:
        _raise("REGISTRY_BUSINESS_NOT_FOUND")
    legacy_owner_user_id = queries.get_registry_owner(registry_business_id)
    if legacy_owner_user_id is None:
        _raise("REGISTRY_OWNER_NOT_FOUND")

    try:
        validated_payload = ingestion_validation.validate_ingestion_payload(payload)
    except ingestion_validation.ValidationError:
        _raise("VALIDATION_FAILED")

    source_system = validated_payload["source_system"]
    contract_version = validated_payload["contract_version"]
    currency = account["currency"]

    prepared_records: list[PreparedRecord] = []
    seen_hashes: dict[str, int] = {}
    seen_source_ids: dict[str, tuple[str, int]] = {}

    for index, record in enumerate(validated_payload["records"]):
        try:
            classification = ingestion_identity.classify_transaction_identity(
                business_id=business_id,
                registry_business_id=registry_business_id,
                account_id=account_id,
                source_system=source_system,
                currency=currency,
                record=record,
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

        prior_hash_index = seen_hashes.get(classification.canonical_identity_hash)
        if (
            prior_hash_index is not None
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
        prepared_records.append(
            PreparedRecord(
                index=index,
                outcome=classification.outcome,
                canonical_identity_hash=classification.canonical_identity_hash,
                existing_identity_id=classification.existing_identity_id,
            )
        )

    return PreparedIngestion(
        uploader_user_id=uploader_user_id,
        business_id=business_id,
        registry_business_id=registry_business_id,
        legacy_owner_user_id=legacy_owner_user_id,
        account_id=account_id,
        currency=currency,
        source_system=source_system,
        contract_version=contract_version,
        records=tuple(prepared_records),
    )


__all__ = [
    "AUTHORIZED_MEMBERSHIP_ROLES",
    "IngestionServiceError",
    "PreparedIngestion",
    "PreparedRecord",
    "prepare_ingestion",
]
