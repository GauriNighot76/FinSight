import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest


BUSINESS_ID = "business-1"
ACCOUNT_ID = "account-1"
GENERATED_AT = "2026-09-02T12:00:00+00:00"


def _analytics(*, empty=False, income=10000, expense=3000, count=4):
    if empty:
        income = expense = count = 0
    return {
        "kpis": {
            "total_income_minor": income,
            "total_expense_minor": expense,
            "net_cash_flow_minor": income - expense,
            "transaction_count": count,
            "average_transaction_minor": (
                Decimal(income + expense) / Decimal(count)
                if count
                else Decimal("0")
            ),
            "income_expense_ratio": (
                Decimal(income) / Decimal(expense) if expense else None
            ),
            "savings_rate": (
                Decimal(income - expense) * Decimal(100) / Decimal(income)
                if income
                else None
            ),
            "closing_balance_minor": 12000 if count else 0,
        },
        "trends": {
            "daily": [],
            "weekly": [],
            "monthly": [],
        },
        "categories": [],
        "payment_modes": [],
        "accounts": [],
        "transactions": [],
    }


def _health(*, metrics=None, anomalies=None):
    base = {
        "overall_financial_health_score": 82,
        "health_level": "Good",
        "health_rating": "Good",
        "cash_flow_stability": Decimal("80.00"),
        "expense_to_income_ratio": Decimal("0.30"),
        "savings_rate": Decimal("70.00"),
        "monthly_growth": Decimal("0.00"),
        "monthly_decline": Decimal("0.00"),
        "recurring_expense_burden": Decimal("10.00"),
        "category_concentration": Decimal("20.00"),
        "transaction_count": 4,
    }
    if metrics:
        base.update(metrics)
    return {"metrics": base, "anomalies": anomalies or []}


def _report():
    return {
        "report_type": "combined_executive_report",
        "business": {"name": "Controlled Demo"},
        "date_range": {"start_date": "2026-01-01", "end_date": "2026-12-31"},
        "currency": "INR",
        "sections": {},
    }


def _context(monkeypatch, *, analytics=None, health=None, report=None):
    from services import decision_support_service

    calls = {"access": [], "analytics": [], "health": [], "report": []}
    monkeypatch.setattr(
        decision_support_service.business_service,
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
        decision_support_service.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: calls["analytics"].append(kwargs)
        or (analytics or _analytics()),
    )
    monkeypatch.setattr(
        decision_support_service.business_health_service,
        "get_business_health",
        lambda **kwargs: calls["health"].append(kwargs)
        or (health or _health()),
    )
    monkeypatch.setattr(
        decision_support_service.report_service,
        "build_report",
        lambda **kwargs: calls["report"].append(kwargs)
        or (report or _report()),
    )
    return decision_support_service, calls


def _support(service, **overrides):
    args = {
        "session_token": "session-token",
        "business_id": BUSINESS_ID,
        "account_id": ACCOUNT_ID,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "currency": "INR",
        "generated_at": GENERATED_AT,
    }
    args.update(overrides)
    return service.get_decision_support(**args)


def _find(results, category):
    return next(item for item in results if item["category"] == category)


def test_empty_data_returns_no_recommendations_and_json_ready(monkeypatch):
    service, calls = _context(
        monkeypatch,
        analytics=_analytics(empty=True),
        health=_health(
            metrics={
                "overall_financial_health_score": 0,
                "health_level": "Critical",
                "health_rating": "Critical",
                "transaction_count": 0,
            }
        ),
    )

    result = _support(service)

    assert result["recommendations"] == []
    assert result["business"] == {"name": "Controlled Demo"}
    json.dumps(result)
    assert len(calls["analytics"]) == 1
    assert len(calls["health"]) == 1
    assert len(calls["report"]) == 1


def test_negative_cash_flow_creates_explainable_recommendation(monkeypatch):
    service, _calls = _context(
        monkeypatch,
        analytics=_analytics(income=1000, expense=2500, count=3),
        health=_health(
            metrics={
                "net_cash_flow_minor": -1500,
                "savings_rate": Decimal("-150.00"),
                "expense_to_income_ratio": Decimal("2.50"),
            }
        ),
    )

    results = _support(service)["recommendations"]
    recommendation = _find(results, "Cash Flow")

    assert recommendation["priority"] in {"HIGH", "CRITICAL"}
    assert recommendation["severity"] in {"HIGH", "CRITICAL"}
    assert recommendation["confidence"] == 95
    assert recommendation["recommended_action"]
    assert "cash" in recommendation["explanation"].lower()
    assert recommendation["business_id"] == BUSINESS_ID
    assert recommendation["account_id"] == ACCOUNT_ID


def test_high_expense_ratio_and_low_savings_are_reported(monkeypatch):
    service, _calls = _context(
        monkeypatch,
        analytics=_analytics(income=1000, expense=900, count=4),
        health=_health(
            metrics={
                "expense_to_income_ratio": Decimal("0.90"),
                "savings_rate": Decimal("10.00"),
            }
        ),
    )

    results = _support(service)["recommendations"]

    assert any(item["category"] == "Expense" for item in results)
    assert any(item["category"] == "Savings" for item in results)


def test_health_and_anomaly_rules_produce_stable_priority_order(monkeypatch):
    anomalies = [
        {
            "type": "expense_explosion",
            "severity": "CRITICAL",
            "date_detected": "2026-08-31",
            "metric_value": Decimal("120.00"),
            "threshold": Decimal("100.00"),
            "explanation": "Expenses doubled.",
        },
        {
            "type": "large_transaction",
            "severity": "HIGH",
            "date_detected": "2026-08-30",
            "metric_value": 9000,
            "threshold": 5000,
            "explanation": "A payment exceeded the threshold.",
        },
        {
            "type": "category_spike",
            "severity": "MEDIUM",
            "date_detected": "2026-08-29",
            "metric_value": Decimal("60.00"),
            "threshold": Decimal("50.00"),
            "explanation": "Category spending increased.",
        },
    ]
    service, _calls = _context(
        monkeypatch,
        health=_health(
            metrics={
                "expense_to_income_ratio": Decimal("1.20"),
                "monthly_decline": Decimal("35.00"),
                "recurring_expense_burden": Decimal("60.00"),
                "category_concentration": Decimal("70.00"),
            },
            anomalies=anomalies,
        ),
    )

    first = _support(service)["recommendations"]
    second = _support(service)["recommendations"]

    assert first == second
    assert [item["priority"] for item in first] == sorted(
        (item["priority"] for item in first),
        key={"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get,
    )
    assert len(first) >= 5
    for item in first:
        assert set(item) >= {
            "id",
            "title",
            "category",
            "priority",
            "severity",
            "confidence",
            "reason",
            "explanation",
            "supporting_metrics",
            "recommended_action",
            "business_id",
            "date_generated",
        }
        assert 0 <= item["confidence"] <= 100
        assert item["date_generated"] == GENERATED_AT


def test_growth_and_positive_trend_generate_low_priority_advice(monkeypatch):
    service, _calls = _context(
        monkeypatch,
        health=_health(
            metrics={
                "monthly_growth": Decimal("25.00"),
                "income_trend": Decimal("25.00"),
                "cash_flow_stability": Decimal("100.00"),
                "overall_financial_health_score": 90,
                "health_level": "Excellent",
            }
        ),
    )

    results = _support(service)["recommendations"]

    assert any(item["category"] == "Growth" for item in results)
    assert any(item["category"] == "Business Health" for item in results)
    assert all(item["priority"] == "LOW" for item in results)


def test_stable_business_generates_maintenance_advice(monkeypatch):
    service, _calls = _context(
        monkeypatch,
        health=_health(
            metrics={
                "health_level": "Stable",
                "health_rating": "Stable",
                "cash_flow_stability": Decimal("85.00"),
                "expense_to_income_ratio": Decimal("0.40"),
                "savings_rate": Decimal("35.00"),
            }
        ),
    )

    results = _support(service)["recommendations"]

    assert any(item["category"] == "Business Health" for item in results)
    assert any("stable" in item["title"].lower() for item in results)


def test_inactive_business_anomaly_generates_operational_advice(monkeypatch):
    service, _calls = _context(
        monkeypatch,
        health=_health(
            anomalies=[
                {
                    "type": "inactive_business",
                    "severity": "MEDIUM",
                    "date_detected": "2026-08-31",
                    "metric_value": 31,
                    "threshold": 30,
                    "explanation": "No activity was recorded for 31 days.",
                }
            ]
        ),
    )

    results = _support(service)["recommendations"]

    assert any(item["category"] == "Operational" for item in results)


def test_payment_mode_and_cash_reserve_rules(monkeypatch):
    analytics = _analytics()
    analytics["payment_modes"] = [
        {
            "payment_mode": "UPI",
            "amount_minor": 9500,
            "count": 9,
            "percentage": Decimal("95.00"),
        },
        {
            "payment_mode": "Cash",
            "amount_minor": 500,
            "count": 1,
            "percentage": Decimal("5.00"),
        },
    ]
    service, _calls = _context(
        monkeypatch,
        analytics=analytics,
        health=_health(
            metrics={
                "cash_reserve_estimate_minor": 500,
                "total_expense_minor": 3000,
            }
        ),
    )

    results = _support(service)["recommendations"]

    assert any(item["category"] == "Payment Behaviour" for item in results)
    assert any(item["category"] == "Risk" for item in results)


def test_income_interruption_and_duplicate_anomaly_are_mapped_safely(monkeypatch):
    anomalies = [
        {
            "type": "income_interruption",
            "severity": "CRITICAL",
            "date_detected": "2026-08",
            "metric_value": 0,
            "threshold": 0,
            "explanation": "No income was recorded.",
            "business_id": BUSINESS_ID,
            "account_id": ACCOUNT_ID,
            "transaction_reference": "secret-source",
        },
        {
            "type": "duplicate_pattern",
            "severity": "MEDIUM",
            "date_detected": "2026-08-10",
            "metric_value": 3,
            "threshold": 2,
            "explanation": "Repeated transactions were observed.",
        },
    ]
    service, _calls = _context(monkeypatch, health=_health(anomalies=anomalies))

    results = _support(service)["recommendations"]
    rendered = repr(results)

    assert any(item["category"] == "Income" for item in results)
    assert any(item["category"] == "Risk" for item in results)
    assert "secret-source" not in rendered
    assert "session-token" not in rendered


def test_unauthorized_access_returns_safe_error_without_service_calls(monkeypatch):
    from services import decision_support_service

    calls = []
    monkeypatch.setattr(
        decision_support_service.business_service,
        "require_business_access",
        lambda *args: {"success": False, "error": "FORBIDDEN"},
    )
    monkeypatch.setattr(
        decision_support_service.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: calls.append("analytics"),
    )

    with pytest.raises(decision_support_service.DecisionSupportError) as error:
        _support(decision_support_service)

    assert "permission" in str(error.value).lower()
    assert calls == []


def test_scope_and_currency_are_forwarded_to_all_existing_services(monkeypatch):
    service, calls = _context(monkeypatch)

    _support(
        service,
        business_id="scoped-business",
        account_id=None,
        start_date="2026-02-01",
        end_date="2026-03-31",
        currency="USD",
    )

    for name in ("analytics", "health", "report"):
        assert calls[name][0]["business_id"] == "scoped-business"
        assert calls[name][0]["account_id"] is None
        assert calls[name][0]["start_date"] == "2026-02-01"
        assert calls[name][0]["end_date"] == "2026-03-31"
        assert calls[name][0]["currency"] == "USD"


def test_datetime_timestamp_is_serializable_and_repeated_ids_are_stable(monkeypatch):
    service, _calls = _context(monkeypatch)
    timestamp = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)

    first = _support(service, generated_at=timestamp)
    second = _support(service, generated_at=timestamp)

    assert first == second
    assert json.dumps(first)


def test_invalid_date_and_currency_fail_before_downstream_calls(monkeypatch):
    service, calls = _context(monkeypatch)

    with pytest.raises(service.DecisionSupportError):
        _support(service, start_date="2026-12-31", end_date="2026-01-01")
    with pytest.raises(service.DecisionSupportError):
        _support(service, currency="inr")

    assert calls["analytics"] == []
    assert calls["health"] == []
    assert calls["report"] == []
