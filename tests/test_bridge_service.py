from services import bridge_service


def test_owner_can_request_approval(monkeypatch):
    monkeypatch.setattr(
        bridge_service.business_service,
        "require_business_access",
        lambda *_args, **_kwargs: {
            "success": True,
            "user": {"user_id": "owner-1"},
            "business": {"business_name": "Medical Shop"},
        },
    )
    monkeypatch.setattr(bridge_service.queries, "get_latest_bridge", lambda *_: None)
    created = []
    monkeypatch.setattr(
        bridge_service.queries,
        "create_registry_bridge_proposal",
        lambda *args: created.append(args) or "bridge-1",
    )
    result = bridge_service.request_approval("token", "business-1")
    assert result == {"success": True, "status": "pending"}
    assert created == [("business-1", "owner-1", "Medical Shop")]


def test_only_administrator_can_list_pending(monkeypatch):
    monkeypatch.setattr(
        bridge_service.auth_service,
        "require_role",
        lambda *_: {"success": False, "error": "FORBIDDEN"},
    )
    assert bridge_service.list_pending("token")["error"] == "FORBIDDEN"


def test_administrator_can_approve_independently(monkeypatch):
    monkeypatch.setattr(
        bridge_service.auth_service,
        "require_role",
        lambda *_: {"success": True, "user": {"user_id": "admin-1"}},
    )
    monkeypatch.setattr(
        bridge_service.queries,
        "review_registry_bridge",
        lambda bridge_id, admin_id, decision: (bridge_id, admin_id, decision)
        == ("bridge-1", "admin-1", "approve"),
    )
    assert bridge_service.review("token", "bridge-1", "approve") == {
        "success": True,
        "status": "active",
    }
