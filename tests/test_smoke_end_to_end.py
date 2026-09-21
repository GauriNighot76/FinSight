from pathlib import Path

from finsight_app.pdf_generator import generate_authenticated_report
from services import (
    account_service,
    analytics_service,
    auth_service,
    bridge_service,
    business_health_service,
    business_service,
    csv_normalizer,
    decision_support_service,
    ingestion_service,
    report_service,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "ValidPass123!"


def test_complete_synthetic_service_flow(monkeypatch):
    assert auth_service.signup(
        "Demo Owner", "owner@example.test", "9999999991", PASSWORD
    )["success"]
    monkeypatch.setenv("FINSIGHT_ALLOW_DEMO_SEED", "1")
    assert auth_service.provision_demo_administrator(
        "Demo Admin", "admin@demo.finsight.local", "9999999992", PASSWORD
    )["success"]

    owner_token = auth_service.login("owner@example.test", PASSWORD)["session"]["token"]
    admin_token = auth_service.login("admin@demo.finsight.local", PASSWORD)["session"]["token"]
    business = business_service.create_business(
        owner_token, {"business_name": "Synthetic Store"}
    )["business"]
    account = account_service.create_account(
        owner_token,
        business["business_id"],
        {
            "account_name": "Synthetic Account",
            "account_type": "bank",
            "currency": "INR",
            "opening_balance": "10000.00",
        },
    )["account"]
    bridge = bridge_service.propose_bridge(owner_token, business["business_id"])["bridge"]
    assert bridge_service.approve_bridge(admin_token, bridge["bridge_id"])["success"]

    payload = csv_normalizer.normalize_csv(
        (PROJECT_ROOT / "sample_data" / "valid_transactions.csv").read_bytes()
    )
    first = ingestion_service.ingest(
        session_token=owner_token,
        business_id=business["business_id"],
        account_id=account["account_id"],
        payload=payload,
    )
    second = ingestion_service.ingest(
        session_token=owner_token,
        business_id=business["business_id"],
        account_id=account["account_id"],
        payload=payload,
    )
    assert first.inserted_count == len(payload["records"])
    assert second.inserted_count == 0
    assert second.duplicate_count == len(payload["records"])

    args = {
        "session_token": owner_token,
        "business_id": business["business_id"],
        "account_id": account["account_id"],
        "start_date": "2026-03-01",
        "end_date": "2026-09-20",
        "currency": "INR",
    }
    analytics = analytics_service.get_financial_analytics(**args)
    assert analytics["kpis"]["transaction_count"] == len(payload["records"])
    assert {row["category"] for row in analytics["categories"]} >= {
        "Sales",
        "Office supplies",
    }
    health = business_health_service.get_business_health(**args)
    support = decision_support_service.get_decision_support(**args)
    report = report_service.build_report(**args)
    pdf = generate_authenticated_report(report).getvalue()
    assert isinstance(health["metrics"]["overall_financial_health_score"], int)
    assert isinstance(support["recommendations"], list)
    assert pdf.startswith(b"%PDF")

    assert auth_service.logout(owner_token)["success"]
    assert auth_service.validate_session(owner_token)["success"] is False
