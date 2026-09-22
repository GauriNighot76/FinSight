import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest


BUSINESS_ID = "business-1"
ACCOUNT_ID = "account-1"


def _analytics_result(*, empty=False):
    if empty:
        return {
            "kpis": {
                "total_income_minor": 0,
                "total_expense_minor": 0,
                "net_cash_flow_minor": 0,
                "transaction_count": 0,
                "average_transaction_minor": Decimal("0"),
                "income_expense_ratio": None,
                "savings_rate": None,
                "opening_balance_minor": 0,
                "closing_balance_minor": 0,
            },
            "trends": {"daily": [], "weekly": [], "monthly": []},
            "categories": [],
            "payment_modes": [],
            "accounts": [],
        }
    return {
        "kpis": {
            "total_income_minor": 10000,
            "total_expense_minor": 3000,
            "net_cash_flow_minor": 7000,
            "transaction_count": 4,
            "average_transaction_minor": Decimal("3250"),
            "income_expense_ratio": Decimal("3.33"),
            "savings_rate": Decimal("70.00"),
            "opening_balance_minor": 5000,
            "closing_balance_minor": 12000,
        },
        "trends": {
            "daily": [
                {
                    "period": "2026-08-01",
                    "income_minor": 10000,
                    "expense_minor": 3000,
                    "net_cash_flow_minor": 7000,
                    "transaction_count": 4,
                }
            ],
            "weekly": [],
            "monthly": [],
        },
        "categories": [
            {
                "category": "Sales",
                "income_minor": 10000,
                "expense_minor": 0,
                "amount_minor": 10000,
                "count": 2,
                "percentage": Decimal("76.92"),
            }
        ],
        "payment_modes": [
            {
                "payment_mode": "UPI",
                "income_minor": 10000,
                "expense_minor": 3000,
                "amount_minor": 13000,
                "count": 4,
                "percentage": Decimal("100.00"),
            }
        ],
        "accounts": [
            {
                "account_id": ACCOUNT_ID,
                "opening_balance_minor": 5000,
                "closing_balance_minor": 12000,
                "total_income_minor": 10000,
                "total_expense_minor": 3000,
                "net_cash_flow_minor": 7000,
                "transaction_count": 4,
            }
        ],
    }


def _health_result(*, empty=False):
    return {
        "metrics": {
            "overall_financial_health_score": 82,
            "health_level": "Good",
            "health_rating": "Good",
            "cash_flow_stability": Decimal("80.00"),
            "expense_to_income_ratio": Decimal("0.30"),
            "savings_rate": Decimal("70.00"),
        },
        "anomalies": [] if empty else [
            {
                "type": "large_transaction",
                "severity": "HIGH",
                "business_id": BUSINESS_ID,
                "account_id": ACCOUNT_ID,
                "date_detected": "2026-08-01",
                "metric_value": 10000,
                "threshold": 5000,
                "explanation": "The amount is above the deterministic threshold.",
                "affected_period": "2026-08-01",
                "transaction_reference": "source-1",
            }
        ],
    }


def _authorized_context(monkeypatch, *, analytics=None, health=None):
    from services import report_service

    calls = {"access": [], "analytics": [], "health": []}
    monkeypatch.setattr(
        report_service.business_service,
        "require_business_access",
        lambda token, business_id, roles: calls["access"].append(
            (token, business_id, roles)
        )
        or {
            "success": True,
            "business": {
                "business_name": "Controlled Demo",
                "business_status": "active",
            },
            "membership": {
                "membership_role": "owner",
                "membership_status": "active",
            },
        },
    )
    monkeypatch.setattr(
        report_service.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: calls["analytics"].append(kwargs)
        or (analytics or _analytics_result()),
    )
    monkeypatch.setattr(
        report_service.business_health_service,
        "get_business_health",
        lambda **kwargs: calls["health"].append(kwargs)
        or (health or _health_result()),
    )
    return report_service, calls


def _build(service, **overrides):
    args = {
        "session_token": "session-token",
        "business_id": BUSINESS_ID,
        "account_id": ACCOUNT_ID,
        "start_date": "2026-08-01",
        "end_date": "2026-08-31",
        "currency": "INR",
        "generated_at": "2026-09-02T12:00:00+00:00",
    }
    args.update(overrides)
    return service.build_report(**args)


def test_executive_report_uses_existing_services_once_and_has_required_sections(monkeypatch):
    service, calls = _authorized_context(monkeypatch)

    report = _build(service, report_type="executive")

    assert len(calls["analytics"]) == 1
    assert len(calls["health"]) == 1
    assert report["business"] == {"name": "Controlled Demo"}
    assert report["date_range"] == {
        "start_date": "2026-08-01",
        "end_date": "2026-08-31",
    }
    assert report["currency"] == "INR"
    assert report["generated_at"] == "2026-09-02T12:00:00+00:00"
    assert set(report["sections"]) >= {
        "financial_summary",
        "income_statement",
        "expense_summary",
        "cash_flow_summary",
        "category_report",
        "payment_mode_report",
        "account_summary",
        "business_health_report",
        "anomaly_report",
    }


@pytest.mark.parametrize(
    "report_type",
    [
        "financial_summary",
        "income_statement",
        "expense_summary",
        "cash_flow_summary",
        "category_report",
        "payment_mode_report",
        "account_summary",
        "business_health_report",
        "anomaly_report",
        "combined_executive_report",
    ],
)
def test_each_report_type_is_supported(monkeypatch, report_type):
    service, _calls = _authorized_context(monkeypatch)

    report = _build(service, report_type=report_type)

    assert report["report_type"] == report_type
    assert isinstance(report["sections"], dict)


def test_report_forwards_business_account_date_and_currency_scope(monkeypatch):
    service, calls = _authorized_context(monkeypatch)

    _build(
        service,
        business_id="scoped-business",
        account_id="scoped-account",
        start_date="2026-01-01",
        end_date="2026-03-31",
        currency="USD",
    )

    assert calls["analytics"][0]["business_id"] == "scoped-business"
    assert calls["analytics"][0]["account_id"] == "scoped-account"
    assert calls["analytics"][0]["start_date"] == "2026-01-01"
    assert calls["analytics"][0]["end_date"] == "2026-03-31"
    assert calls["analytics"][0]["currency"] == "USD"
    assert calls["health"][0]["business_id"] == "scoped-business"


def test_report_exports_are_json_csv_and_chart_ready(monkeypatch):
    service, _calls = _authorized_context(monkeypatch)
    report = _build(service)

    json_report = service.report_to_json(report)
    json.dumps(json_report)
    csv_rows = service.report_to_csv_rows(report)
    chart_data = service.report_to_chart_datasets(report)

    assert isinstance(csv_rows, list)
    assert all(isinstance(row, dict) for row in csv_rows)
    assert set(chart_data) >= {"daily", "weekly", "monthly"}
    assert chart_data["daily"][0]["period"] == "2026-08-01"


def test_empty_report_returns_deterministic_empty_structures(monkeypatch):
    service, _calls = _authorized_context(
        monkeypatch,
        analytics=_analytics_result(empty=True),
        health=_health_result(empty=True),
    )

    first = _build(service)
    second = _build(service)

    assert first == second
    assert first["sections"]["category_report"] == []
    assert first["sections"]["payment_mode_report"] == []
    assert first["sections"]["anomaly_report"] == []
    assert first["sections"]["financial_summary"]["total_income_minor"] == 0


def test_report_rejects_unauthorized_access_safely(monkeypatch):
    from services import report_service

    monkeypatch.setattr(
        report_service.business_service,
        "require_business_access",
        lambda *args: {"success": False, "error": "FORBIDDEN"},
    )

    with pytest.raises(report_service.ReportError) as error:
        _build(report_service)
    assert "permission" in str(error.value).lower() or "access" in str(error.value).lower()


def test_report_does_not_expose_sensitive_identifiers(monkeypatch):
    service, _calls = _authorized_context(monkeypatch)
    report = _build(service)
    rendered = repr(report)

    assert BUSINESS_ID not in rendered
    assert ACCOUNT_ID not in rendered
    assert "canonical_identity_hash" not in rendered
    assert "session-token" not in rendered
    assert "source-1" not in rendered


def test_report_preserves_backend_values_without_recalculating(monkeypatch):
    analytics = _analytics_result()
    analytics["kpis"]["net_cash_flow_minor"] = 7777
    service, calls = _authorized_context(monkeypatch, analytics=analytics)

    report = _build(service)

    assert report["sections"]["financial_summary"]["net_cash_flow_minor"] == 7777
    assert calls["analytics"][0]["business_id"] == BUSINESS_ID


def test_invalid_date_range_is_rejected_before_service_calls(monkeypatch):
    service, calls = _authorized_context(monkeypatch)

    with pytest.raises(service.ReportError):
        _build(service, start_date="2026-09-01", end_date="2026-08-01")
    assert calls["analytics"] == []
    assert calls["health"] == []


def test_generated_timestamp_accepts_datetime_and_remains_serializable(monkeypatch):
    service, _calls = _authorized_context(monkeypatch)
    generated_at = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)

    report = _build(service, generated_at=generated_at)

    assert report["generated_at"] == "2026-09-02T12:00:00+00:00"
    json.dumps(service.report_to_json(report))


def test_advisory_anomaly_summary_uses_service_findings_without_redetection(monkeypatch):
    health = _health_result(empty=True)
    health["anomalies"] = [
        {
            "anomaly_id": f"anomaly-{index}",
            "type": (
                "unusually_large_expense"
                if index < 2
                else "negative_cash_flow_period"
            ),
            "severity": "HIGH" if index < 2 else "LOW",
            "affected_period": f"2026-08-{index + 1:02d}",
            "explanation": f"Finding detail {index}",
            "detection_context": (
                {"category": "Inventory"}
                if index < 2
                else {"period_kind": "daily"}
            ),
        }
        for index in range(12)
    ]
    service, _calls = _authorized_context(monkeypatch, health=health)

    report = _build(service)
    advisory = service.build_advisory_model(report, [])
    anomaly_summary = advisory["anomaly_summary"]

    assert report["sections"]["anomaly_report"] == [
        {
            key: value
            for key, value in item.items()
            if key not in {"business_id", "account_id", "transaction_reference"}
        }
        for item in health["anomalies"]
    ]
    assert anomaly_summary["total"] == 12
    assert anomaly_summary["severity_counts"]["HIGH"] == 2
    assert anomaly_summary["severity_counts"]["LOW"] == 10
    assert anomaly_summary["type_counts"]["unusually_large_expense"] == 2
    assert anomaly_summary["type_counts"]["negative_cash_flow_period"] == 10
    assert len(anomaly_summary["material_examples"]) == 5
    assert anomaly_summary["additional_count"] == 7
    assert {
        item["anomaly_id"] for item in anomaly_summary["material_examples"]
    } <= {
        item["anomaly_id"] for item in report["sections"]["anomaly_report"]
    }


def test_pdf_anomaly_section_is_summary_not_full_finding_dump(monkeypatch):
    from finsight_app.pdf_generator import generate_business_report

    health = _health_result(empty=True)
    health["anomalies"] = [
        {
            "anomaly_id": f"anomaly-{index}",
            "type": "negative_cash_flow_period",
            "severity": "LOW",
            "affected_period": f"2026-08-{index + 1:02d}",
            "explanation": f"Unique anomaly detail {index}",
            "detection_context": {"period_kind": "daily"},
        }
        for index in range(12)
    ]
    service, _calls = _authorized_context(monkeypatch, health=health)
    report = _build(service)

    pdf = generate_business_report(
        business={
            "business_name": "Controlled Demo",
            "business_type": "Retail",
        },
        report=report,
        decision_support={"recommendations": []},
        scheme_results=[],
    ).getvalue()

    assert pdf.startswith(b"%PDF")
    assert b"Risk / Anomaly Summary" in pdf
    assert b"additional finding" in pdf
    assert b"Unique anomaly detail 0" in pdf
    assert b"Unique anomaly detail 3" not in pdf
