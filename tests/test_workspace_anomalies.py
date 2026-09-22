from finsight_app import workspace_ui


class _Container:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _MetricColumn:
    def __init__(self, events):
        self.events = events

    def metric(self, label, value):
        self.events.append(("metric", label, value))


class FakeStreamlit:
    def __init__(self):
        self.events = []

    def subheader(self, value):
        self.events.append(("subheader", value))

    def info(self, value):
        self.events.append(("info", value))

    def success(self, value):
        self.events.append(("success", value))

    def error(self, value):
        self.events.append(("error", value))

    def container(self, **_kwargs):
        return _Container()

    def expander(self, label, **kwargs):
        self.events.append(("expander", label, kwargs))
        return _Container()

    def columns(self, count):
        return [_MetricColumn(self.events) for _ in range(count)]

    def markdown(self, value):
        self.events.append(("markdown", value))

    def caption(self, value):
        self.events.append(("caption", value))

    def write(self, *values):
        self.events.append(("write", *values))


def _health():
    return {
        "metrics": {"transaction_count": 3},
        "anomalies": [
            {
                "anomaly_id": "a1",
                "type": "unusually_large_expense",
                "severity": "HIGH",
                "explanation": "One expense exceeds the robust outer fence.",
                "affected_period": "2026-08-03",
                "affected_transaction": {
                    "date": "2026-08-03",
                    "description": "Bulk medicine purchase",
                    "amount_minor": 4200000,
                    "category": "Inventory Purchase",
                    "payment_mode": "Bank",
                },
                "detection_context": {},
            },
            {
                "anomaly_id": "a2",
                "type": "unexpected_payment_mode",
                "severity": "MEDIUM",
                "explanation": "Payment mode Cash appears only once.",
                "detection_context": {"payment_mode": "Cash"},
            },
        ],
    }


def test_repeated_anomaly_render_does_not_multiply_findings(monkeypatch):
    health = _health()
    monkeypatch.setattr(
        workspace_ui,
        "_health_context",
        lambda st, token, business: ({"currency": "INR"}, health),
    )
    business = {"business_id": "business-1", "business_name": "Retail A"}

    first = FakeStreamlit()
    second = FakeStreamlit()

    assert workspace_ui.render_anomalies(first, "token", business) is True
    assert workspace_ui.render_anomalies(second, "token", business) is True

    first_titles = [
        event for event in first.events
        if event[0] == "markdown" and event[1].startswith("**")
    ]
    second_titles = [
        event for event in second.events
        if event[0] == "markdown" and event[1].startswith("**")
    ]
    assert len(first_titles) == len(health["anomalies"])
    assert second_titles == first_titles
    assert sum("Unusually Large Expense" in event[1] for event in first_titles) == 1
    assert sum("Unusual Payment Mode" in event[1] for event in first_titles) == 1

    metrics = [event for event in first.events if event[0] == "metric"]
    assert ("metric", "Total Findings", 2) in metrics
    assert ("metric", "High / Critical", 1) in metrics
    assert ("metric", "Medium", 1) in metrics
    assert ("metric", "Low", 0) in metrics

    expanders = [event[1] for event in first.events if event[0] == "expander"]
    assert "Unusually Large Transactions (1)" in expanders
    assert "Repeated / Payment Patterns (1)" in expanders

    assert any(
        event[:2] == ("write", "Amount:")
        and event[2] == "₹42,000.00"
        for event in first.events
    )
    assert any(
        event[:2] == ("write", "Description:")
        and event[2] == "Bulk medicine purchase"
        for event in first.events
    )
    assert any(
        event[:2] == ("write", "Category:")
        and event[2] == "Inventory Purchase"
        for event in first.events
    )
    assert any(
        event[:2] == ("write", "Payment mode:")
        and event[2] == "Cash"
        for event in first.events
    )


def test_same_date_outliers_render_distinguishing_transaction_context(monkeypatch):
    health = {
        "metrics": {"transaction_count": 10},
        "anomalies": [
            {
                "anomaly_id": "outlier-a",
                "type": "unusually_large_expense",
                "severity": "HIGH",
                "explanation": "Outer-fence outlier.",
                "affected_transaction": {
                    "date": "2026-03-19",
                    "description": "Bulk antibiotic purchase",
                    "amount_minor": 4200000,
                    "category": "Inventory",
                    "payment_mode": "Bank",
                },
                "detection_context": {},
            },
            {
                "anomaly_id": "outlier-b",
                "type": "unusually_large_expense",
                "severity": "HIGH",
                "explanation": "Outer-fence outlier.",
                "affected_transaction": {
                    "date": "2026-03-19",
                    "description": "Cold storage repair",
                    "amount_minor": 5500000,
                    "category": "Repairs",
                    "payment_mode": "UPI",
                },
                "detection_context": {},
            },
        ],
    }
    monkeypatch.setattr(
        workspace_ui,
        "_health_context",
        lambda st, token, business: ({"currency": "INR"}, health),
    )
    ui = FakeStreamlit()

    assert workspace_ui.render_anomalies(
        ui,
        "token",
        {"business_id": "business-1", "business_name": "Medical"},
    ) is True

    rendered = repr(ui.events)
    assert "Bulk antibiotic purchase" in rendered
    assert "Cold storage repair" in rendered
    assert "₹42,000.00" in rendered
    assert "₹55,000.00" in rendered
    assert rendered.count("2026-03-19") == 2


def test_category_and_negative_daily_titles_expose_context(monkeypatch):
    health = {
        "metrics": {"transaction_count": 8},
        "anomalies": [
            {
                "anomaly_id": "category-a",
                "type": "category_spike",
                "severity": "MEDIUM",
                "explanation": "Inventory expense increased.",
                "affected_period": "2026-07",
                "detection_context": {"category": "Inventory"},
            },
            {
                "anomaly_id": "daily-a",
                "type": "negative_cash_flow_period",
                "severity": "LOW",
                "explanation": "Recorded expenses exceeded income on this day.",
                "affected_period": "2026-07-14",
                "detection_context": {"period_kind": "daily"},
            },
        ],
    }
    monkeypatch.setattr(
        workspace_ui,
        "_health_context",
        lambda st, token, business: ({"currency": "INR"}, health),
    )
    ui = FakeStreamlit()

    workspace_ui.render_anomalies(
        ui,
        "token",
        {"business_id": "business-1", "business_name": "Medical"},
    )

    rendered = repr(ui.events)
    assert "Category Spike" in rendered
    assert "Inventory" in rendered
    assert "Negative Daily Cash Flow" in rendered
    assert "Affected day:" in rendered


def test_health_context_rejects_stale_legacy_anomaly_engine(monkeypatch):
    ui = FakeStreamlit()
    monkeypatch.setattr(
        workspace_ui,
        "_business_account",
        lambda st, token, business_id: {
            "account_id": "account-1",
            "currency": "INR",
        },
    )
    monkeypatch.setattr(
        workspace_ui.business_health_service,
        "get_business_health",
        lambda **kwargs: {
            "metrics": {"transaction_count": 10},
            "anomalies": [
                {
                    "type": "unusually_large_income",
                    "severity": "HIGH",
                    "reason": "The income is more than twice the average income amount.",
                }
            ],
        },
    )

    args, health = workspace_ui._health_context(
        ui,
        "token",
        {"business_id": "business-1"},
    )

    assert args["business_id"] == "business-1"
    assert health is None
    assert any(
        event[0] == "error" and "runtime is out of date" in event[1].lower()
        for event in ui.events
    )


def test_health_context_accepts_only_current_anomaly_engine(monkeypatch):
    ui = FakeStreamlit()
    payload = {
        "metrics": {"transaction_count": 10},
        "anomalies": [],
        "anomaly_engine_version": "finsight_tukey_outer_v1",
    }
    monkeypatch.setattr(
        workspace_ui,
        "_business_account",
        lambda st, token, business_id: {
            "account_id": "account-1",
            "currency": "INR",
        },
    )
    monkeypatch.setattr(
        workspace_ui.business_health_service,
        "get_business_health",
        lambda **kwargs: payload,
    )

    _args, health = workspace_ui._health_context(
        ui,
        "token",
        {"business_id": "business-1"},
    )

    assert health is payload
    assert not any(event[0] == "error" for event in ui.events)
