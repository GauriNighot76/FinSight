import sqlite3
from unittest.mock import Mock

import pytest

from database import queries
from services import account_service, business_service, csv_normalizer, ingestion_service
from tests.test_business_service import account, create


@pytest.fixture
def owned():
    _, token = account("Owner", "owner@example.com", "9000000001")
    business = create(token)["business"]
    return token, business


def test_soft_delete_preserves_financial_history_and_other_business(owned, isolated_test_database):
    token, business = owned
    bid = business["business_id"]
    other = create(token, "Other Business")["business"]
    extra = account_service.create_account(token, bid, {
        "account_name": "Bank", "account_type": "bank", "currency": "INR",
        "institution_name": "Bank", "account_identifier": "extra", "opening_balance": "0",
    })
    assert extra["success"]
    payload = csv_normalizer.normalize_csv(
        "Date,Amount,Direction\n2026-01-01,100,income\n2026-01-02,20,expense\n"
    )
    for current in (business, other):
        ready = business_service.ensure_business_ready(token, current["business_id"])
        result = ingestion_service.ingest(session_token=token, business_id=current["business_id"],
                                          account_id=ready["account_id"], payload=payload)
        assert result.inserted_count == 2
    tables = ("financial_accounts", "transaction_general_ledger", "ingestion_attempts",
              "ingested_transaction_identities", "business_memberships", "business_registry",
              "business_registry_bridges")
    def snapshot():
        with isolated_test_database() as connection:
            return {table: [tuple(row) for row in connection.execute(f'SELECT * FROM {table}')]
                    for table in tables}
    before = snapshot()
    # New businesses use their direct ledger link; legacy bridges may be empty.
    assert all(before[table] for table in tables if table != "business_registry_bridges")
    other_before = dict(queries.get_module2_business(other["business_id"]))
    assert business_service.delete_business(token, bid, "  Acme MSME  ")["success"]
    assert snapshot() == before
    assert queries.get_module2_business(bid)["business_status"] == "disabled"
    assert dict(queries.get_module2_business(other["business_id"])) == other_before
    assert [b["business_id"] for b in business_service.list_user_businesses(token)["businesses"]] == [other["business_id"]]
    assert business_service.require_business_access(token, bid)["error"] == "BUSINESS_DISABLED"
    assert account_service.get_account(token, extra["account"]["account_id"])["error"] == "BUSINESS_DISABLED"
    assert business_service.delete_business(token, bid, "Acme MSME")["error"] == "BUSINESS_DISABLED"


@pytest.mark.parametrize("role", ["manager", "member", "viewer"])
def test_nonowners_cannot_delete_and_lose_listing_when_owner_deletes(owned, role):
    token, business = owned
    _, member_token = account("Member", "member@example.com", "9000000002")
    bid = business["business_id"]
    assert business_service.add_member(token, bid, "member@example.com", role)["success"]
    assert business_service.delete_business(member_token, bid, "Acme MSME")["error"] == "FORBIDDEN"
    assert queries.get_module2_business(bid)["business_status"] == "active"
    assert business_service.delete_business(token, bid, "Acme MSME")["success"]
    assert business_service.list_user_businesses(member_token)["businesses"] == []
    assert business_service.require_business_access(member_token, bid)["error"] == "BUSINESS_DISABLED"


@pytest.mark.parametrize("name", ["", "  ", "Acme", "acme msme", "DELETE", None])
def test_wrong_confirmation_never_updates(owned, monkeypatch, name):
    token, business = owned
    update = Mock()
    monkeypatch.setattr(queries, "set_module2_business_status", update)
    assert business_service.delete_business(token, business["business_id"], name)["error"] == "CONFIRMATION_MISMATCH"
    update.assert_not_called()


@pytest.mark.parametrize("token", ["", "invalid"])
def test_unauthenticated_delete_fails(owned, token):
    _, business = owned
    assert not business_service.delete_business(token, business["business_id"], "Acme MSME")["success"]
    assert queries.get_module2_business(business["business_id"])["business_status"] == "active"


def test_storage_error_is_sanitized_and_missing_business_is_safe(owned, monkeypatch):
    token, business = owned
    assert business_service.delete_business(token, "missing", "Acme MSME")["error"] == "BUSINESS_NOT_FOUND"
    monkeypatch.setattr(queries, "set_module2_business_status", Mock(side_effect=sqlite3.OperationalError("secret SQL")))
    result = business_service.delete_business(token, business["business_id"], "Acme MSME")
    assert result["error"] == "BUSINESS_DELETE_FAILED"
    assert "secret" not in str(result)


def test_delete_final_business_and_conditional_status_guard(owned):
    token, business = owned
    bid = business["business_id"]
    assert business_service.delete_business(token, bid, "Acme MSME")["success"]
    assert business_service.list_user_businesses(token)["businesses"] == []
    assert not queries.set_module2_business_status(bid, "active", expected_status="active")
    assert queries.get_module2_business(bid)["business_status"] == "disabled"
