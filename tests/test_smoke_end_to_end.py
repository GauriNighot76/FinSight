from pathlib import Path

import pytest
from database import db, queries

from finsight_app.pdf_generator import generate_authenticated_report
from services import (
    account_service,
    analytics_service,
    auth_service,
    business_health_service,
    business_service,
    csv_normalizer,
    decision_support_service,
    ingestion_service,
    report_service,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "ValidPass123!"


def test_complete_synthetic_service_flow(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "fresh" / "finsight.db")
    monkeypatch.setattr(queries, "get_connection", db.get_connection)
    db.initialize_database()
    assert auth_service.signup(
        "Demo Owner", "owner@example.test", "9999999991", PASSWORD
    )["success"]
    owner_token = auth_service.login("owner@example.test", PASSWORD)["session"]["token"]
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
    assert business["business_status"] == "active"
    membership = queries.get_business_membership(business["business_id"], auth_service.validate_session(owner_token)["user"]["user_id"])
    assert membership["membership_role"] == "owner"
    assert membership["membership_status"] == "active"
    bridge = queries.get_active_bridge(business["business_id"])
    assert bridge is not None
    assert bridge["proposed_by_user_id"] == bridge["verified_by_user_id"]
    with db.get_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM users WHERE role='administrator'").fetchone()[0] == 0

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
    assert analytics["kpis"]["total_income_minor"] == 37100000
    assert analytics["kpis"]["total_expense_minor"] == 12500000
    assert analytics["kpis"]["net_cash_flow_minor"] == 24600000
    assert analytics["payment_modes"]
    assert analytics["trends"]["daily"]
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

    with pytest.raises(csv_normalizer.CSVNormalizationError):
        csv_normalizer.normalize_csv((PROJECT_ROOT / "sample_data" / "invalid_transactions.csv").read_bytes())
    assert analytics_service.get_financial_analytics(**args)["kpis"] == analytics["kpis"]
    assert report["sections"]["financial_summary"]["net_cash_flow_minor"] == 24600000
    assert auth_service.signup("Second User", "other@example.test", "9999999993", PASSWORD)["success"]
    other = auth_service.login("other@example.test", PASSWORD)["session"]["token"]
    assert not business_service.get_business(other, business["business_id"])["success"]
    assert not business_service.add_member(other, business["business_id"], "other@example.test", "manager")["success"]
    assert not account_service.create_account(other, business["business_id"], {"account_name": "Intruder", "account_type": "bank"})["success"]
    assert not account_service.get_account(other, account["account_id"])["success"]
    assert not account_service.update_account(other, account["account_id"], {"account_name": "Changed"})["success"]
    with pytest.raises(ingestion_service.IngestionServiceError):
        ingestion_service.ingest(session_token=other, business_id=business["business_id"], account_id=account["account_id"], payload=payload)
    outsider_args = {**args, "session_token": other}
    for service, error in [(analytics_service.get_financial_analytics, analytics_service.AnalyticsError),
                           (business_health_service.get_business_health, business_health_service.BusinessHealthError),
                           (decision_support_service.get_decision_support, decision_support_service.DecisionSupportError),
                           (report_service.build_report, report_service.ReportError)]:
        with pytest.raises(error):
            service(**outsider_args)
    empty_args = {**args, "start_date": "2025-01-01", "end_date": "2025-01-31"}
    assert analytics_service.get_financial_analytics(**empty_args)["kpis"]["transaction_count"] == 0
    business_health_service.get_business_health(**empty_args)
    decision_support_service.get_decision_support(**empty_args)
    assert generate_authenticated_report(report_service.build_report(**empty_args)).getvalue().startswith(b"%PDF")
    assert auth_service.logout(owner_token)["success"]
    assert auth_service.validate_session(owner_token)["success"] is False


def test_report_handles_literal_markup_in_business_name():
    # Business names are user text, not ReportLab XML or file references.
    pdf = generate_authenticated_report({
        'business': {'name': 'ABC <font> & <img src="missing"> Traders'},
        'sections': {'financial_summary': {'savings_rate': 0}},
    }).getvalue()
    assert pdf.startswith(b'%PDF')
