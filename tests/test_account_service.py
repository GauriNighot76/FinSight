import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from database import queries
from services import account_service, auth_service, business_service


def user(name, email, phone):
    assert auth_service.signup(name, email, phone, "StrongPass1")["success"]
    return auth_service.login(email, "StrongPass1")["session"]["token"]


def business(token, name="Account Business"):
    result = business_service.create_business(token, {"business_name": name})
    assert result["success"]
    return result["business"]["business_id"]


def account(token, business_id, **changes):
    data = {
        "account_name": "HDFC Current Account", "account_type": "bank",
        "institution_name": "HDFC Bank", "account_identifier": "REF-1234",
        "currency": "INR", "opening_balance": "10500.75",
    }
    data.update(changes)
    result = account_service.create_account(token, business_id, data)
    assert result["success"], result
    return result["account"]


def add_role(owner_token, business_id, email, role):
    result = business_service.add_member(owner_token, business_id, email, role)
    assert result["success"]
    return result["membership"]


def test_create_account_exact_precision_and_safe_identifier(isolated_test_database):
    token = user("Owner", "owner@example.com", "9000000001")
    business_id = business(token)
    created = account(token, business_id)
    assert created["opening_balance"] == "10500.75"
    assert created["account_identifier"] == "****1234"
    with isolated_test_database() as connection:
        stored = connection.execute(
            "SELECT opening_balance_minor FROM financial_accounts WHERE account_id=?",
            (created["account_id"],),
        ).fetchone()[0]
    assert stored == 1050075


def test_creation_rejects_invalid_expired_revoked_and_disabled_user_sessions(isolated_test_database):
    token = user("Owner", "owner@example.com", "9000000001")
    business_id = business(token)
    data = {"account_name": "Cash", "account_type": "cash", "currency": "INR"}
    assert account_service.create_account("invalid", business_id, data)["error"] == "SESSION_INVALID"
    user_id = auth_service.validate_session(token)["user"]["user_id"]
    expired = "expired"
    queries.create_session(user_id, hashlib.sha256(expired.encode()).hexdigest(),
                           (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    assert account_service.create_account(expired, business_id, data)["error"] == "SESSION_INVALID"
    revoked = auth_service.login("owner@example.com", "StrongPass1")["session"]["token"]
    auth_service.logout(revoked)
    assert account_service.create_account(revoked, business_id, data)["error"] == "SESSION_INVALID"
    with isolated_test_database() as connection:
        connection.execute("UPDATE users SET account_status='disabled' WHERE user_id=?", (user_id,))
    assert account_service.create_account(token, business_id, data)["error"] == "SESSION_INVALID"


@pytest.mark.parametrize("changes", [
    {"account_name": " "}, {"account_type": "crypto"}, {"currency": "12"},
    {"opening_balance": "10.001"}, {"opening_balance": "not-money"},
])
def test_creation_validation(changes):
    token = user("Owner", "owner@example.com", "9000000001")
    business_id = business(token)
    data = {"account_name": "Cash Drawer", "account_type": "cash", "currency": "INR"}
    data.update(changes)
    assert account_service.create_account(token, business_id, data)["error"] == "INVALID_INPUT"


def test_owner_and_manager_create_but_member_and_viewer_cannot():
    owner = user("Owner", "owner@example.com", "9000000001")
    manager = user("Manager", "manager@example.com", "9000000002")
    member = user("Member", "member@example.com", "9000000003")
    viewer = user("Viewer", "viewer@example.com", "9000000004")
    business_id = business(owner)
    add_role(owner, business_id, "manager@example.com", "manager")
    add_role(owner, business_id, "member@example.com", "member")
    add_role(owner, business_id, "viewer@example.com", "viewer")
    assert account_service.create_account(manager, business_id, {
        "account_name": "Manager Cash", "account_type": "cash", "currency": "INR"
    })["success"]
    for token in (member, viewer):
        result = account_service.create_account(token, business_id, {
            "account_name": "Claimed Owner", "account_type": "cash", "currency": "INR",
            "membership_role": "owner",
        })
        assert result["error"] == "FORBIDDEN"


def test_duplicate_identifier_is_business_scoped():
    owner = user("Owner", "owner@example.com", "9000000001")
    first_business = business(owner, "First")
    second_business = business(owner, "Second")
    account(owner, first_business)
    duplicate = account_service.create_account(owner, first_business, {
        "account_name": "Another", "account_type": "bank", "currency": "INR",
        "account_identifier": "REF-1234",
    })
    assert duplicate["error"] == "DUPLICATE_ACCOUNT"
    assert account(owner, second_business)["business_id"] == second_business


def test_get_account_status_and_membership_protection():
    owner = user("Owner", "owner@example.com", "9000000001")
    member = user("Member", "member@example.com", "9000000002")
    business_id = business(owner)
    membership = add_role(owner, business_id, "member@example.com", "member")
    created = account(owner, business_id)
    assert account_service.get_account(member, created["account_id"])["success"]
    queries.set_membership_status(membership["membership_id"], "disabled")
    assert account_service.get_account(member, created["account_id"])["error"] == "MEMBERSHIP_DISABLED"
    queries.set_module2_business_status(business_id, "disabled")
    assert account_service.get_account(owner, created["account_id"])["error"] == "BUSINESS_DISABLED"
    assert account_service.get_account(owner, "missing")["error"] == "ACCOUNT_NOT_FOUND"


def test_cross_business_account_isolation():
    user_a = user("User A", "a@example.com", "9000000001")
    user_b = user("User B", "b@example.com", "9000000002")
    business_a, business_b = business(user_a, "A Business"), business(user_b, "B Business")
    account_a = account(user_a, business_a, account_identifier="A-1")
    account_b = account(user_b, business_b, account_identifier="B-1")
    assert account_service.get_account(user_a, account_a["account_id"])["success"]
    assert account_service.get_account(user_b, account_b["account_id"])["success"]
    assert account_service.get_account(user_a, account_b["account_id"])["error"] == "FORBIDDEN"
    assert account_service.get_account(user_b, account_a["account_id"])["error"] == "FORBIDDEN"


def test_list_is_business_scoped_and_excludes_disabled_accounts():
    owner = user("Owner", "owner@example.com", "9000000001")
    first, second = business(owner, "First"), business(owner, "Second")
    active = account(owner, first, account_identifier="ACTIVE")
    disabled = account(owner, first, account_identifier="DISABLED")
    account(owner, second, account_identifier="OTHER")
    assert account_service.disable_account(owner, disabled["account_id"])["success"]
    rows = account_service.list_business_accounts(owner, first)["accounts"]
    assert [row["account_id"] for row in rows] == [active["account_id"]]
    assert account_service.get_account(owner, disabled["account_id"])["error"] == "ACCOUNT_DISABLED"


def test_owner_manager_update_member_viewer_forbidden_and_ids_immutable():
    owner = user("Owner", "owner@example.com", "9000000001")
    manager = user("Manager", "manager@example.com", "9000000002")
    member = user("Member", "member@example.com", "9000000003")
    viewer = user("Viewer", "viewer@example.com", "9000000004")
    business_id = business(owner)
    add_role(owner, business_id, "manager@example.com", "manager")
    add_role(owner, business_id, "member@example.com", "member")
    add_role(owner, business_id, "viewer@example.com", "viewer")
    created = account(owner, business_id)
    assert account_service.update_account(owner, created["account_id"], {"account_name": "Owner Updated"})["success"]
    assert account_service.update_account(manager, created["account_id"], {"currency": "USD"})["success"]
    for token in (member, viewer):
        assert account_service.update_account(token, created["account_id"], {
            "account_name": "Unauthorized", "membership_role": "owner"
        })["error"] == "FORBIDDEN"
    for field in ("account_id", "business_id", "created_at"):
        assert account_service.update_account(owner, created["account_id"], {field: "changed"})["error"] == "INVALID_INPUT"
    assert queries.get_financial_account(created["account_id"])["business_id"] == business_id


def test_owner_manager_disable_member_viewer_forbidden():
    owner = user("Owner", "owner@example.com", "9000000001")
    manager = user("Manager", "manager@example.com", "9000000002")
    member = user("Member", "member@example.com", "9000000003")
    viewer = user("Viewer", "viewer@example.com", "9000000004")
    business_id = business(owner)
    add_role(owner, business_id, "manager@example.com", "manager")
    add_role(owner, business_id, "member@example.com", "member")
    add_role(owner, business_id, "viewer@example.com", "viewer")
    for token in (member, viewer):
        target = account(owner, business_id, account_identifier=f"{token[-5:]}-target")
        assert account_service.disable_account(token, target["account_id"])["error"] == "FORBIDDEN"
    owner_target = account(owner, business_id, account_identifier="OWNER-DISABLE")
    manager_target = account(owner, business_id, account_identifier="MANAGER-DISABLE")
    assert account_service.disable_account(owner, owner_target["account_id"])["success"]
    assert account_service.disable_account(manager, manager_target["account_id"])["success"]
