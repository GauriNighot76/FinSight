import pytest

from database import queries
from services import auth_service, business_service, csv_normalizer, ingestion_service
from tests.test_business_service import account, create

PHRASE = "DELETE MY ACCOUNT"


@pytest.fixture
def user():
    return account("User", "user@example.com", "9000000001")


def test_deactivate_revokes_every_session_and_denies_future_login(user):
    row, token = user
    second = auth_service.login(row["email"], "StrongPass1")["session"]["token"]
    assert auth_service.delete_account(token, f" {PHRASE} ", "StrongPass1")["success"]
    assert queries.get_user_by_id(row["user_id"])["account_status"] == "disabled"
    with queries.get_connection() as connection:
        sessions = connection.execute("SELECT revoked_at FROM auth_sessions WHERE user_id=?", (row["user_id"],)).fetchall()
    assert len(sessions) == 2 and all(s[0] for s in sessions)
    assert not auth_service.validate_session(token)["success"]
    assert not auth_service.validate_session(second)["success"]
    assert auth_service.login(row["email"], "StrongPass1")["error"] == "ACCOUNT_DISABLED"
    assert not auth_service.delete_account(token, PHRASE, "StrongPass1")["success"]


@pytest.mark.parametrize("confirmation", ["", "DELETE", "yes", "delete my account", None])
def test_bad_confirmation_has_no_side_effects(user, confirmation):
    row, token = user
    assert auth_service.delete_account(token, confirmation, "StrongPass1")["error"] == "CONFIRMATION_MISMATCH"
    assert auth_service.validate_session(token)["success"]
    assert queries.get_user_by_id(row["user_id"])["account_status"] == "active"


@pytest.mark.parametrize("password", [None, "", "wrong"])
def test_bad_password_keeps_account_active(user, password):
    _, token = user
    assert auth_service.delete_account(token, PHRASE, password)["error"] == "INVALID_PASSWORD"
    assert auth_service.validate_session(token)["success"]


@pytest.mark.parametrize("token", ["", "fake"])
def test_invalid_session(token):
    assert auth_service.delete_account(token, PHRASE, "StrongPass1")["error"] == "SESSION_INVALID"


def test_active_ownership_blocks_without_mutation(user):
    _, token = user
    first = create(token, "Business A")["business"]
    create(token, "Business B")
    result = auth_service.delete_account(token, PHRASE, "StrongPass1")
    assert result["error"] == "ACTIVE_BUSINESSES_OWNED"
    assert result["owned_businesses"] == ["Business A", "Business B"]
    assert auth_service.validate_session(token)["success"]
    assert queries.get_module2_business(first["business_id"])["business_status"] == "active"


def test_deleted_business_owner_can_deactivate(user):
    _, token = user
    business = create(token)["business"]
    assert business_service.delete_business(token, business["business_id"], business["business_name"])["success"]
    assert auth_service.delete_account(token, PHRASE, "StrongPass1")["success"]


def test_google_only_needs_no_password_and_cannot_reactivate():
    verifier = lambda _: {"sub": "google-user", "email": "google@example.com", "email_verified": True}
    login = auth_service.google_sign_in("verified", verifier=verifier)
    token = login["session"]["token"]
    assert auth_service.get_account_deletion_requirements(token) == {"success": True, "requires_password": False}
    assert auth_service.delete_account(token, PHRASE)["success"]
    assert auth_service.google_sign_in("verified", verifier=verifier)["error"] == "ACCOUNT_DISABLED"


def test_local_user_linked_to_google_still_requires_password(user):
    row, token = user
    verifier = lambda _: {"sub": "linked", "email": row["email"], "email_verified": True}
    assert auth_service.google_sign_in("verified", verifier=verifier)["success"]
    assert auth_service.get_account_deletion_requirements(token)["requires_password"]
    assert auth_service.delete_account(token, PHRASE)["error"] == "INVALID_PASSWORD"
    assert auth_service.delete_account(token, PHRASE, "StrongPass1")["success"]
    assert auth_service.google_sign_in("verified", verifier=verifier)["error"] == "ACCOUNT_DISABLED"


@pytest.mark.parametrize("role", ["manager", "member", "viewer"])
def test_membership_deactivation_preserves_business_and_history(user, role):
    row, token = user
    owner, owner_token = account("Owner", "owner@example.com", "9000000002")
    business = create(owner_token)["business"]
    bid = business["business_id"]
    business_service.add_member(owner_token, bid, row["email"], role)
    ready = business_service.ensure_business_ready(owner_token, bid)
    result = ingestion_service.ingest(session_token=owner_token, business_id=bid, account_id=ready["account_id"],
        payload=csv_normalizer.normalize_csv("Date,Amount,Direction\n2026-01-01,100,income\n"))
    assert result.inserted_count == 1
    doc = queries.create_document(row["user_id"], "audit.txt")
    queries.create_document_chunk(doc, row["user_id"], 0, "Retained audit text")
    tables = ("businesses", "financial_accounts", "transaction_general_ledger", "ingestion_attempts",
              "ingested_transaction_identities", "business_registry", "documents", "document_chunks")
    def snapshot():
        with queries.get_connection() as conn:
            return {t: [tuple(r) for r in conn.execute(f'SELECT * FROM {t}')] for t in tables}
    before = snapshot()
    assert all(before.values())
    assert auth_service.delete_account(token, PHRASE, "StrongPass1")["success"]
    assert before == snapshot()
    assert queries.get_business_membership(bid, row["user_id"])["membership_status"] == "disabled"
    assert queries.get_business_membership(bid, owner["user_id"])["membership_status"] == "active"
    assert business_service.require_business_access(owner_token, bid)["success"]
    assert auth_service.validate_session(owner_token)["success"]


@pytest.mark.parametrize("table", ["business_memberships", "users", "auth_sessions"])
def test_failure_rolls_back_all_changes(user, table):
    row, token = user
    _, owner_token = account("Owner", "owner@example.com", "9000000002")
    bid = create(owner_token)["business"]["business_id"]
    business_service.add_member(owner_token, bid, row["email"], "member")
    with queries.get_connection() as conn:
        conn.execute(f"CREATE TRIGGER fail_delete BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT, 'private SQL failure'); END")
    result = auth_service.delete_account(token, PHRASE, "StrongPass1")
    assert result["error"] == "ACCOUNT_DELETE_FAILED"
    assert "private" not in str(result)
    assert queries.get_user_by_id(row["user_id"])["account_status"] == "active"
    assert queries.get_business_membership(bid, row["user_id"])["membership_status"] == "active"
    assert auth_service.validate_session(token)["success"]


def test_transaction_rechecks_ownership_after_service_precheck(user, monkeypatch):
    _, token = user
    create(token)
    monkeypatch.setattr(queries, "list_active_owned_businesses", lambda _: [])
    assert auth_service.delete_account(token, PHRASE, "StrongPass1")["error"] == "ACTIVE_BUSINESSES_OWNED"
    assert auth_service.validate_session(token)["success"]
