from finsight_app import workspace_ui


class _Container:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeStreamlit:
    def __init__(self):
        self.events = []

    def subheader(self, value):
        self.events.append(("subheader", value))

    def info(self, value):
        self.events.append(("info", value))

    def success(self, value):
        self.events.append(("success", value))

    def container(self, **_kwargs):
        return _Container()

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
                "explanation": "One expense is unusually large.",
                "affected_period": "2026-08-03",
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
        lambda st, token, business: ({}, health),
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
    assert sum("Unexpected Payment Mode" in event[1] for event in first_titles) == 1
    assert any(
        event[:2] == ("write", "Payment mode:")
        and event[2] == "Cash"
        for event in first.events
    )
