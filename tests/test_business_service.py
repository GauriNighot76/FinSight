import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from database import queries
from services import auth_service, business_service


def account(name, email, phone):
    result = auth_service.signup(name, email, phone, "StrongPass1")
    assert result["success"]
    return result["user"], auth_service.login(email, "StrongPass1")["session"]["token"]


def create(token, name="Acme MSME"):
    result = business_service.create_business(token, {
        "business_name": name, "legal_identifier": "GST-TEST",
        "contact_email": "office@example.com", "contact_phone": "9876543210",
        "membership_role": "viewer",
    })
    assert result["success"]
    return result


def test_valid_creation_is_atomic_and_creator_is_owner():
    user, token = account("Owner", "owner@example.com", "9000000001")
    result = create(token)
    assert result["membership"]["user_id"] == user["user_id"]
    assert result["membership"]["membership_role"] == "owner"
    assert result["business"]["business_status"] == "active"


def test_creation_rejects_missing_invalid_expired_and_revoked_sessions():
    assert business_service.create_business("", {"business_name": "Acme"})["success"] is False
    assert business_service.create_business("fake", {"business_name": "Acme"})["success"] is False
    user, token = account("Owner", "owner@example.com", "9000000001")
    expired = "expired-token"
    queries.create_session(user["user_id"], hashlib.sha256(expired.encode()).hexdigest(),
                           (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
    assert business_service.create_business(expired, {"business_name": "Acme"})["success"] is False
    auth_service.logout(token)
    assert business_service.create_business(token, {"business_name": "Acme"})["success"] is False


@pytest.mark.parametrize("data", [
    {}, {"business_name": "A"}, {"business_name": "Acme", "contact_email": "bad"},
    {"business_name": "Acme", "contact_phone": "abc"},
])
def test_creation_validates_input(data):
    _, token = account("Owner", "owner@example.com", "9000000001")
    assert business_service.create_business(token, data)["error"] == "INVALID_INPUT"


def test_creation_rolls_back_if_owner_membership_fails(isolated_test_database):
    user, _ = account("Owner", "owner@example.com", "9000000001")
    with isolated_test_database() as connection:
        connection.execute(
            """CREATE TRIGGER reject_owner BEFORE INSERT ON business_memberships
               BEGIN SELECT RAISE(ABORT, 'test failure'); END"""
        )
    with pytest.raises(sqlite3.IntegrityError):
        queries.create_business_with_owner(user["user_id"], "Atomic Business")
    with isolated_test_database() as connection:
        assert connection.execute("SELECT COUNT(*) FROM businesses").fetchone()[0] == 0


def test_get_business_authorization_status_and_membership_status():
    _, owner_token = account("Owner", "owner@example.com", "9000000001")
    _, outsider_token = account("Outsider", "outside@example.com", "9000000002")
    business = create(owner_token)["business"]
    assert business_service.get_business(owner_token, business["business_id"])["success"]
    assert business_service.get_business(outsider_token, business["business_id"])["error"] == "FORBIDDEN"
    assert business_service.get_business(owner_token, "missing")["error"] == "BUSINESS_NOT_FOUND"
    queries.set_module2_business_status(business["business_id"], "disabled")
    assert business_service.get_business(owner_token, business["business_id"])["error"] == "BUSINESS_DISABLED"
    queries.set_module2_business_status(business["business_id"], "active")
    owner_membership = queries.get_business_membership(business["business_id"],
                                                        auth_service.validate_session(owner_token)["user"]["user_id"])
    queries.set_membership_status(owner_membership["membership_id"], "disabled")
    assert business_service.get_business(owner_token, business["business_id"])["error"] == "MEMBERSHIP_DISABLED"


def test_list_only_active_related_businesses():
    _, token_a = account("User A", "a@example.com", "9000000001")
    _, token_b = account("User B", "b@example.com", "9000000002")
    business_a = create(token_a, "Business A")["business"]
    create(token_b, "Business B")
    listed = business_service.list_user_businesses(token_a)["businesses"]
    assert [row["business_id"] for row in listed] == [business_a["business_id"]]


def test_disabled_membership_is_excluded_from_user_business_list():
    _, owner_token = account("Owner", "owner@example.com", "9000000001")
    member, member_token = account("Member", "member@example.com", "9000000002")
    business_id = create(owner_token)["business"]["business_id"]
    added = business_service.add_member(owner_token, business_id, member["email"], "member")
    queries.set_membership_status(added["membership"]["membership_id"], "disabled")
    assert business_service.list_user_businesses(member_token)["businesses"] == []


def test_cross_business_isolation():
    _, token_a = account("User A", "a@example.com", "9000000001")
    _, token_b = account("User B", "b@example.com", "9000000002")
    business_a = create(token_a, "Business A")["business"]["business_id"]
    business_b = create(token_b, "Business B")["business"]["business_id"]
    assert business_service.get_business(token_a, business_a)["success"]
    assert business_service.get_business(token_b, business_b)["success"]
    assert business_service.get_business(token_a, business_b)["error"] == "FORBIDDEN"
    assert business_service.get_business(token_b, business_a)["error"] == "FORBIDDEN"


def test_owner_membership_management_duplicate_and_last_owner_protection():
    _, owner_token = account("Owner", "owner@example.com", "9000000001")
    member, member_token = account("Member", "member@example.com", "9000000002")
    business = create(owner_token)["business"]["business_id"]
    added = business_service.add_member(owner_token, business, member["email"], "member")
    assert added["success"]
    assert business_service.add_member(owner_token, business, member["email"], "viewer")["error"] == "DUPLICATE_MEMBERSHIP"
    assert business_service.list_members(owner_token, business)["success"]
    assert business_service.add_member(member_token, business, "owner@example.com", "viewer")["error"] == "FORBIDDEN"
    assert business_service.add_member(owner_token, business, member["email"], "owner")["error"] == "INVALID_INPUT"
    owner_id = business_service.get_business(owner_token, business)["membership"]["membership_id"]
    assert business_service.remove_member(owner_token, business, owner_id)["error"] == "OWNER_REQUIRED"
    assert business_service.remove_member(member_token, business, added["membership"]["membership_id"])["error"] == "FORBIDDEN"
    assert business_service.remove_member(owner_token, business, added["membership"]["membership_id"])["success"]
    assert business_service.get_business(member_token, business)["error"] == "MEMBERSHIP_DISABLED"


def test_manager_can_manage_ordinary_roles_but_not_escalate():
    _, owner_token = account("Owner", "owner@example.com", "9000000001")
    manager, manager_token = account("Manager", "manager@example.com", "9000000002")
    member, _ = account("Member", "member@example.com", "9000000003")
    business = create(owner_token)["business"]["business_id"]
    assert business_service.add_member(owner_token, business, manager["email"], "manager")["success"]
    assert business_service.add_member(manager_token, business, member["email"], "member")["success"]
    assert business_service.add_member(manager_token, business, "owner@example.com", "manager")["error"] == "FORBIDDEN"


def test_viewer_cannot_manage_memberships():
    _, owner_token = account("Owner", "owner@example.com", "9000000001")
    viewer, viewer_token = account("Viewer", "viewer@example.com", "9000000002")
    account("Target", "target@example.com", "9000000003")
    business = create(owner_token)["business"]["business_id"]
    business_service.add_member(owner_token, business, viewer["email"], "viewer")
    assert business_service.add_member(viewer_token, business, "target@example.com", "member")["error"] == "FORBIDDEN"
    assert business_service.list_members(viewer_token, business)["error"] == "FORBIDDEN"
