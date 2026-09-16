from decimal import Decimal

import pytest


BUSINESS_ID = "business-1"
ACCOUNT_ID = "account-1"


def _analysis_result(
    *,
    income=10000,
    expense=3000,
    transaction_count=4,
    trends=None,
    categories=None,
    payment_modes=None,
    transactions=None,
):
    return {
        "kpis": {
            "total_income_minor": income,
            "total_expense_minor": expense,
            "net_cash_flow_minor": income - expense,
            "transaction_count": transaction_count,
            "average_transaction_minor": Decimal(income + expense)
            / Decimal(transaction_count)
            if transaction_count
            else Decimal("0"),
            "largest_income_minor": income if income else None,
            "smallest_income_minor": income if income else None,
            "largest_expense_minor": expense if expense else None,
            "smallest_expense_minor": expense if expense else None,
            "opening_balance_minor": 5000,
            "closing_balance_minor": 5000 + income - expense,
            "income_expense_ratio": Decimal(income) / Decimal(expense) if expense else None,
            "savings_rate": Decimal(income - expense) * Decimal(100) / Decimal(income)
            if income
            else None,
        },
        "trends": trends or {"daily": [], "weekly": [], "monthly": []},
        "categories": categories or [],
        "payment_modes": payment_modes or [],
        "accounts": [{"account_id": ACCOUNT_ID}],
        "transactions": transactions or [],
    }


def _authorized_context(monkeypatch, analysis=None):
    from services import business_health_service

    monkeypatch.setattr(
        business_health_service.auth_service,
        "validate_session",
        lambda token: {
            "success": True,
            "user": {"user_id": "owner-user", "username": "Owner"},
        },
    )
    monkeypatch.setattr(
        business_health_service.queries,
        "get_business_membership",
        lambda business_id, user_id: {
            "business_status": "active",
            "membership_status": "active",
            "membership_role": "owner",
        },
    )
    monkeypatch.setattr(
        business_health_service.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: analysis or _analysis_result(),
    )
    return business_health_service


def _health(service, **overrides):
    args = {
        "session_token": "session-token",
        "business_id": BUSINESS_ID,
        "account_id": ACCOUNT_ID,
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "currency": "INR",
    }
    args.update(overrides)
    return service.get_business_health(**args)


def test_healthy_business_returns_structured_health_metrics(monkeypatch):
    service = _authorized_context(monkeypatch)

    result = _health(service)

    assert set(result) == {"metrics", "anomalies"}
    assert result["metrics"]["overall_financial_health_score"] >= 70
    assert result["metrics"]["health_level"] in {"Excellent", "Good"}
    assert result["metrics"]["expense_to_income_ratio"] == Decimal("0.30")
    assert result["metrics"]["savings_rate"] == Decimal("70.00")
    assert isinstance(result["anomalies"], list)


def test_negative_cash_flow_has_poor_or_critical_health(monkeypatch):
    service = _authorized_context(
        monkeypatch,
        _analysis_result(income=1000, expense=2500, transaction_count=2),
    )

    metrics = _health(service)["metrics"]

    assert metrics["net_cash_flow_minor"] == -1500
    assert metrics["savings_rate"] == Decimal("-150.00")
    assert metrics["health_level"] in {"Poor", "Critical"}


def test_cash_flow_stability_is_deterministic_percentage(monkeypatch):
    trends = {
        "daily": [
            {"period": "2026-08-01", "net_cash_flow_minor": 100},
            {"period": "2026-08-02", "net_cash_flow_minor": -20},
            {"period": "2026-08-03", "net_cash_flow_minor": 50},
        ],
        "weekly": [],
        "monthly": [],
    }
    service = _authorized_context(monkeypatch, _analysis_result(trends=trends))

    stability = _health(service)["metrics"]["cash_flow_stability"]

    assert stability == Decimal("66.67")


def test_monthly_growth_and_decline_are_reported(monkeypatch):
    trends = {
        "daily": [],
        "weekly": [],
        "monthly": [
            {
                "period": "2026-01",
                "income_minor": 1000,
                "expense_minor": 100,
                "net_cash_flow_minor": 900,
                "transaction_count": 1,
            },
            {
                "period": "2026-02",
                "income_minor": 1500,
                "expense_minor": 300,
                "net_cash_flow_minor": 1200,
                "transaction_count": 2,
            },
        ],
    }
    service = _authorized_context(monkeypatch, _analysis_result(trends=trends))

    metrics = _health(service)["metrics"]

    assert metrics["monthly_growth"] == Decimal("50.00")
    assert metrics["monthly_decline"] == Decimal("0.00")


def test_category_concentration_and_largest_percentages(monkeypatch):
    categories = [
        {
            "category": "Rent",
            "income_minor": 0,
            "expense_minor": 6000,
            "amount_minor": 6000,
            "count": 1,
        },
        {
            "category": "Sales",
            "income_minor": 10000,
            "expense_minor": 0,
            "amount_minor": 10000,
            "count": 3,
        },
    ]
    service = _authorized_context(
        monkeypatch,
        _analysis_result(income=10000, expense=6000, categories=categories),
    )

    metrics = _health(service)["metrics"]

    assert metrics["category_concentration"] == Decimal("62.50")
    assert metrics["largest_expense_percentage"] == Decimal("100.00")
    assert metrics["largest_income_percentage"] == Decimal("100.00")


def test_recurring_expense_burden_uses_repeated_expense_categories(monkeypatch):
    transactions = [
        {"transaction_date": "2026-01-02", "amount_minor": 1000, "direction": "expense", "category": "Rent"},
        {"transaction_date": "2026-02-02", "amount_minor": 1000, "direction": "expense", "category": "Rent"},
        {"transaction_date": "2026-03-02", "amount_minor": 1000, "direction": "expense", "category": "Rent"},
        {"transaction_date": "2026-03-03", "amount_minor": 1000, "direction": "income", "category": "Sales"},
    ]
    service = _authorized_context(
        monkeypatch,
        _analysis_result(
            income=1000,
            expense=3000,
            transaction_count=4,
            transactions=transactions,
        ),
    )

    metrics = _health(service)["metrics"]

    assert metrics["recurring_expense_burden"] == Decimal("100.00")


def test_anomalies_are_explainable_and_do_not_expose_transaction_ids(monkeypatch):
    transactions = [
        {
            "transaction_id": "secret-1",
            "transaction_date": "2026-08-01",
            "amount_minor": 100,
            "direction": "expense",
            "category": "Food",
            "payment_mode": "UPI",
        },
        {
            "transaction_id": "secret-2",
            "transaction_date": "2026-08-02",
            "amount_minor": 100,
            "direction": "expense",
            "category": "Food",
            "payment_mode": "UPI",
        },
        {
            "transaction_id": "secret-3",
            "transaction_date": "2026-08-03",
            "amount_minor": 1000,
            "direction": "expense",
            "category": "Food",
            "payment_mode": "Cash",
        },
    ]
    service = _authorized_context(
        monkeypatch,
        _analysis_result(income=1000, expense=1200, transaction_count=3, transactions=transactions),
    )

    anomalies = _health(service)["anomalies"]

    # A three-row sample is too small for responsible statistical flagging.
    assert not any(anomaly["type"] == "unusually_large_expense" for anomaly in anomalies)
    assert not any(anomaly["type"] == "repeated_identical_transactions" for anomaly in anomalies)
    for anomaly in anomalies:
        assert set(anomaly) >= {
            "type",
            "severity",
            "date",
            "affected_transaction",
            "reason",
            "trigger_metric",
            "threshold",
        }
        assert "secret-" not in repr(anomaly)


def test_payment_mode_anomaly_and_income_interruption(monkeypatch):
    trends = {
        "daily": [],
        "weekly": [],
        "monthly": [
            {
                "period": "2026-01",
                "income_minor": 1000,
                "expense_minor": 200,
                "net_cash_flow_minor": 800,
                "transaction_count": 2,
            },
            {
                "period": "2026-02",
                "income_minor": 0,
                "expense_minor": 500,
                "net_cash_flow_minor": -500,
                "transaction_count": 1,
            },
        ],
    }
    payment_modes = [
        {"payment_mode": "UPI", "count": 4, "amount_minor": 900},
        {"payment_mode": "Cash", "count": 1, "amount_minor": 100},
    ]
    service = _authorized_context(
        monkeypatch,
        _analysis_result(
            income=1000,
            expense=700,
            transaction_count=5,
            trends=trends,
            payment_modes=payment_modes,
        ),
    )

    anomalies = _health(service)["anomalies"]

    assert not any(anomaly["type"] == "unexpected_payment_mode" for anomaly in anomalies)
    assert any(anomaly["type"] == "income_interruption" for anomaly in anomalies)


def test_health_results_are_deterministic(monkeypatch):
    service = _authorized_context(monkeypatch)

    first = _health(service)
    second = _health(service)

    assert first == second


def test_empty_analytics_returns_stable_zero_health(monkeypatch):
    service = _authorized_context(
        monkeypatch,
        _analysis_result(income=0, expense=0, transaction_count=0),
    )

    result = _health(service)

    assert result["metrics"]["net_cash_flow_minor"] == 0
    assert result["metrics"]["health_level"] == "Critical"
    assert result["anomalies"] == []


def test_invalid_session_is_rejected_without_service_call(monkeypatch):
    from services import business_health_service

    monkeypatch.setattr(
        business_health_service.auth_service,
        "validate_session",
        lambda token: {"success": False, "error": "SESSION_INVALID"},
    )
    called = []
    monkeypatch.setattr(
        business_health_service.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: called.append(kwargs),
    )

    with pytest.raises(business_health_service.BusinessHealthError):
        _health(business_health_service)
    assert called == []


def test_business_and_account_scope_are_forwarded(monkeypatch):
    from services import business_health_service

    _authorized_context(monkeypatch)
    calls = []
    monkeypatch.setattr(
        business_health_service.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: calls.append(kwargs) or _analysis_result(),
    )

    _health(business_health_service, business_id="scoped-business", account_id="scoped-account")

    assert calls[0]["business_id"] == "scoped-business"
    assert calls[0]["account_id"] == "scoped-account"
    assert calls[0]["currency"] == "INR"


def test_currency_error_from_analytics_is_safe(monkeypatch):
    from services import business_health_service

    _authorized_context(monkeypatch)
    monkeypatch.setattr(
        business_health_service.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: (_ for _ in ()).throw(
            business_health_service.analytics_service.AnalyticsError(
                "The selected analytics currency is inconsistent."
            )
        ),
    )

    with pytest.raises(business_health_service.BusinessHealthError) as error:
        _health(business_health_service)
    assert "currency" in str(error.value).lower()
    assert "SELECT" not in str(error.value)


def test_monthly_decline_and_expense_trend_are_reported(monkeypatch):
    trends = {
        "daily": [],
        "weekly": [],
        "monthly": [
            {
                "period": "2026-01",
                "income_minor": 2000,
                "expense_minor": 100,
                "net_cash_flow_minor": 1900,
                "transaction_count": 2,
            },
            {
                "period": "2026-02",
                "income_minor": 1000,
                "expense_minor": 500,
                "net_cash_flow_minor": 500,
                "transaction_count": 2,
            },
        ],
    }
    service = _authorized_context(monkeypatch, _analysis_result(trends=trends))

    metrics = _health(service)["metrics"]

    assert metrics["monthly_decline"] == Decimal("50.00")
    assert metrics["monthly_growth"] == Decimal("0.00")
    assert metrics["income_trend"] == Decimal("-50.00")
    assert metrics["expense_trend"] == Decimal("400.00")


def test_sudden_expense_spike_is_detected(monkeypatch):
    trends = {
        "daily": [],
        "weekly": [],
        "monthly": [
            {"period": "2026-01", "income_minor": 1000, "expense_minor": 100},
            {"period": "2026-02", "income_minor": 1000, "expense_minor": 150},
        ],
    }
    service = _authorized_context(monkeypatch, _analysis_result(trends=trends))

    anomalies = _health(service)["anomalies"]

    spike = next(item for item in anomalies if item["type"] == "monthly_expense_increase")
    assert spike["severity"] == "HIGH"
    assert spike["threshold"] == Decimal("50.00")


def test_critical_health_is_assigned_for_unsustainable_finances(monkeypatch):
    service = _authorized_context(
        monkeypatch,
        _analysis_result(income=100, expense=1000, transaction_count=1),
    )

    metrics = _health(service)["metrics"]

    assert metrics["overall_financial_health_score"] < 25
    assert metrics["health_level"] == "Critical"


def test_health_score_level_boundaries_are_deterministic(monkeypatch):
    service = _authorized_context(monkeypatch, _analysis_result(income=1000, expense=0))

    metrics = _health(service)["metrics"]

    assert metrics["health_level"] == "Good"
    assert metrics["overall_financial_health_score"] == 75


def test_cash_reserve_estimate_uses_closing_balance(monkeypatch):
    service = _authorized_context(monkeypatch)

    metrics = _health(service)["metrics"]

    assert metrics["cash_reserve_estimate_minor"] == 12000


def test_anomaly_threshold_is_not_triggered_by_equal_amount(monkeypatch):
    transactions = [
        {"transaction_date": "2026-08-01", "amount_minor": 100, "direction": "expense"},
        {"transaction_date": "2026-08-02", "amount_minor": 100, "direction": "expense"},
        {"transaction_date": "2026-08-03", "amount_minor": 200, "direction": "expense"},
    ]
    service = _authorized_context(
        monkeypatch,
        _analysis_result(expense=400, income=1000, transaction_count=3, transactions=transactions),
    )

    anomalies = _health(service)["anomalies"]

    assert not any(item["type"] == "unusually_large_expense" for item in anomalies)


def test_anomaly_results_are_sorted_and_read_only(monkeypatch):
    transactions = [
        {"transaction_date": "2026-08-03", "amount_minor": 900, "direction": "expense"},
        {"transaction_date": "2026-08-01", "amount_minor": 100, "direction": "expense"},
    ]
    service = _authorized_context(
        monkeypatch,
        _analysis_result(income=100, expense=1000, transaction_count=2, transactions=transactions),
    )

    first = _health(service)
    second = _health(service)

    assert first == second
    assert [item["date"] for item in first["anomalies"]] == sorted(
        item["date"] for item in first["anomalies"]
    )


def test_category_spike_inactive_period_and_expense_explosion(monkeypatch):
    trends = {
        "daily": [
            {"period": "2026-01-01", "net_cash_flow_minor": 100},
            {"period": "2026-01-10", "net_cash_flow_minor": -100},
        ],
        "weekly": [],
        "monthly": [
            {"period": "2026-01", "income_minor": 1000, "expense_minor": 100},
            {"period": "2026-02", "income_minor": 1000, "expense_minor": 250},
        ],
    }
    transactions = [
        {
            "transaction_date": "2026-01-02",
            "amount_minor": 100,
            "direction": "expense",
            "category": "Food",
        },
        {
            "transaction_date": "2026-02-02",
            "amount_minor": 250,
            "direction": "expense",
            "category": "Food",
        },
    ]
    service = _authorized_context(
        monkeypatch,
        _analysis_result(
            income=2000,
            expense=350,
            transaction_count=2,
            trends=trends,
            transactions=transactions,
        ),
    )

    anomalies = _health(service)["anomalies"]
    anomaly_types = {item["type"] for item in anomalies}

    assert "category_spike" in anomaly_types
    assert "inactive_period" in anomaly_types
    assert "monthly_expenses_doubled" in anomaly_types


def _phase2_analysis(*, income=1000, expense=300, trends=None, transactions=None):
    transaction_rows = transactions or []
    return {
        "kpis": {
            "total_income_minor": income,
            "total_expense_minor": expense,
            "net_cash_flow_minor": income - expense,
            "transaction_count": len(transaction_rows),
            "closing_balance_minor": 5000 + income - expense,
            "savings_rate": Decimal(income - expense) * Decimal(100) / Decimal(income)
            if income
            else Decimal("0.00"),
        },
        "trends": trends or {"daily": [], "weekly": [], "monthly": []},
        "categories": [
            {
                "category": "Food",
                "income_minor": 0,
                "expense_minor": expense,
                "amount_minor": expense,
                "count": len(transaction_rows),
            }
        ]
        if transaction_rows
        else [],
        "payment_modes": [
            {
                "payment_mode": "UPI",
                "count": len(transaction_rows),
                "amount_minor": expense,
            }
        ]
        if transaction_rows
        else [],
        "accounts": [{"account_id": ACCOUNT_ID}],
        "transactions": transaction_rows,
    }


def test_phase2_anomalies_have_required_safe_metadata(monkeypatch):
    transactions = [
        {
            "transaction_date": "2026-08-01",
            "amount_minor": 100,
            "direction": "expense",
            "category": "Food",
            "payment_mode": "UPI",
            "source_transaction_id": "source-1",
        },
        {
            "transaction_date": "2026-08-02",
            "amount_minor": 100,
            "direction": "expense",
            "category": "Food",
            "payment_mode": "UPI",
            "source_transaction_id": "source-2",
        },
        {
            "transaction_date": "2026-08-03",
            "amount_minor": 1000,
            "direction": "expense",
            "category": "Food",
            "payment_mode": "UPI",
            "source_transaction_id": "source-3",
        },
    ]
    service = _authorized_context(
        monkeypatch,
        _phase2_analysis(income=1000, expense=1200, transactions=transactions),
    )

    anomalies = _health(service)["anomalies"]

    assert not any(item["type"] == "large_transaction" for item in anomalies)
    for anomaly in anomalies:
        assert anomaly["severity"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
        assert anomaly["business_id"] == BUSINESS_ID
        assert anomaly["account_id"] == ACCOUNT_ID
        assert set(anomaly) >= {
            "type",
            "severity",
            "business_id",
            "account_id",
            "date_detected",
            "metric_value",
            "threshold",
            "explanation",
            "affected_period",
            "transaction_reference",
        }


def test_phase2_period_rules_are_all_detected(monkeypatch):
    trends = {
        "daily": [
            {"period": "2026-01-01", "income_minor": 100, "expense_minor": 0},
            {"period": "2026-01-10", "income_minor": 0, "expense_minor": 100},
        ],
        "weekly": [],
        "monthly": [
            {"period": "2026-01", "income_minor": 1000, "expense_minor": 100},
            {"period": "2026-02", "income_minor": 0, "expense_minor": 250},
        ],
    }
    transactions = [
        {
            "transaction_date": "2026-01-02",
            "amount_minor": 100,
            "direction": "expense",
            "category": "Food",
            "payment_mode": "UPI",
        },
        {
            "transaction_date": "2026-02-02",
            "amount_minor": 250,
            "direction": "expense",
            "category": "Food",
            "payment_mode": "Cash",
        },
    ]
    analysis = _phase2_analysis(
        income=1000,
        expense=350,
        trends=trends,
        transactions=transactions,
    )
    analysis["payment_modes"] = [
        {"payment_mode": "UPI", "count": 3, "amount_minor": 100},
        {"payment_mode": "Cash", "count": 1, "amount_minor": 250},
    ]
    service = _authorized_context(monkeypatch, analysis)

    anomaly_types = {item["type"] for item in _health(service)["anomalies"]}

    assert {
        "monthly_expenses_doubled",
        "sudden_income_drop",
        "negative_cash_flow_period",
        "category_spike",
        "inactive_period",
        "income_interruption",
    } <= anomaly_types


def test_phase2_ratio_and_stability_rules_use_strict_boundaries(monkeypatch):
    trends = {
        "daily": [
            {"period": "2026-08-01", "net_cash_flow_minor": -10},
            {"period": "2026-08-02", "net_cash_flow_minor": -20},
            {"period": "2026-08-03", "net_cash_flow_minor": -30},
            {"period": "2026-08-04", "net_cash_flow_minor": 40},
        ],
        "weekly": [],
        "monthly": [],
    }
    service = _authorized_context(
        monkeypatch,
        _phase2_analysis(income=100, expense=150, trends=trends),
    )

    result = _health(service)
    anomaly_types = {item["type"] for item in result["anomalies"]}

    assert result["metrics"]["expense_to_income_ratio"] == Decimal("1.50")
    assert "high_expense_ratio" in anomaly_types
    assert "cash_flow_instability" in anomaly_types


def test_phase2_duplicate_pattern_and_recurring_growth_are_deterministic(monkeypatch):
    transactions = [
        {
            "transaction_date": "2026-01-01",
            "amount_minor": 100,
            "direction": "expense",
            "category": "Rent",
            "payment_mode": "Bank",
        },
        {
            "transaction_date": "2026-01-02",
            "amount_minor": 100,
            "direction": "expense",
            "category": "Rent",
            "payment_mode": "Bank",
        },
        {
            "transaction_date": "2026-02-01",
            "amount_minor": 200,
            "direction": "expense",
            "category": "Rent",
            "payment_mode": "Bank",
        },
    ]
    service = _authorized_context(
        monkeypatch,
        _phase2_analysis(
            income=1000,
            expense=400,
            trends={"daily": [], "weekly": [], "monthly": []},
            transactions=transactions,
        ),
    )

    first = _health(service)
    second = _health(service)
    anomaly_types = {item["type"] for item in first["anomalies"]}

    assert "duplicate_pattern" not in anomaly_types
    assert "recurring_expense_growth" not in anomaly_types
    assert first == second


def test_phase2_member_access_is_rejected_before_analytics(monkeypatch):
    from services import business_health_service

    _authorized_context(monkeypatch)
    monkeypatch.setattr(
        business_health_service.queries,
        "get_business_membership",
        lambda business_id, user_id: {
            "business_status": "active",
            "membership_status": "active",
            "membership_role": "member",
        },
    )
    calls = []
    monkeypatch.setattr(
        business_health_service.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: calls.append(kwargs),
    )

    with pytest.raises(business_health_service.BusinessHealthError):
        _health(business_health_service)
    assert calls == []


def test_phase2_analytics_contract_exposes_sanitized_transaction_rows(monkeypatch):
    from services import analytics_service

    monkeypatch.setattr(analytics_service, "_require_authorized_session", lambda *args: None)
    monkeypatch.setattr(
        analytics_service,
        "_load_account",
        lambda account_id, business_id, currency: {
            "opening_balance_minor": 0,
            "currency": currency,
        },
    )
    monkeypatch.setattr(
        analytics_service,
        "_load_accepted_rows",
        lambda **kwargs: [
            {
                "transaction_date": "2026-08-01",
                "amount_minor": 100,
                "direction": "expense",
                "currency": "INR",
                "identity_id": "internal-identity",
                "category": "Food",
                "payment_mode": "UPI",
            }
        ],
    )

    result = analytics_service.get_financial_analytics(
        session_token="session-token",
        business_id=BUSINESS_ID,
        account_id=ACCOUNT_ID,
        start_date="2026-08-01",
        end_date="2026-08-31",
        currency="INR",
    )

    assert result["transactions"] == [
        {
            "transaction_date": "2026-08-01",
            "amount_minor": 100,
            "direction": "expense",
            "category": "Food",
            "payment_mode": "UPI",
        }
    ]
