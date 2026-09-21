from services import auth_service, bridge_service, business_service


DEMO_PASSWORD = "ValidPass123!"


def _create_admin(monkeypatch):
    monkeypatch.setenv("FINSIGHT_ALLOW_DEMO_SEED", "1")
    result = auth_service.provision_demo_administrator(
        "Demo Admin", "admin@demo.finsight.local", "9999999992", DEMO_PASSWORD
    )
    assert result["success"] is True
    return auth_service.login("admin@demo.finsight.local", DEMO_PASSWORD)["session"]["token"]


def test_owner_proposes_and_independent_admin_approves_bridge(monkeypatch):
    assert auth_service.signup(
        "Owner", "owner@example.test", "9999999991", DEMO_PASSWORD
    )["success"]
    owner_token = auth_service.login("owner@example.test", DEMO_PASSWORD)["session"]["token"]
    admin_token = _create_admin(monkeypatch)
    business = business_service.create_business(
        owner_token, {"business_name": "Synthetic Store"}
    )["business"]

    proposed = bridge_service.propose_bridge(owner_token, business["business_id"])
    assert proposed["success"] is True
    assert proposed["bridge"]["bridge_status"] == "pending"

    approved = bridge_service.approve_bridge(
        admin_token, proposed["bridge"]["bridge_id"]
    )
    assert approved["success"] is True
    assert approved["bridge"]["bridge_status"] == "active"


def test_non_administrator_cannot_approve_bridge():
    assert auth_service.signup(
        "Owner", "owner@example.test", "9999999991", DEMO_PASSWORD
    )["success"]
    assert auth_service.signup(
        "Second User", "second@example.test", "9999999993", DEMO_PASSWORD
    )["success"]
    owner_token = auth_service.login("owner@example.test", DEMO_PASSWORD)["session"]["token"]
    second_token = auth_service.login("second@example.test", DEMO_PASSWORD)["session"]["token"]
    business = business_service.create_business(
        owner_token, {"business_name": "Synthetic Store"}
    )["business"]
    bridge = bridge_service.propose_bridge(owner_token, business["business_id"])["bridge"]

    result = bridge_service.approve_bridge(second_token, bridge["bridge_id"])
    assert result["success"] is False
    assert result["error"] == "FORBIDDEN"
