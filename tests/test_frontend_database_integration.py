from contextlib import nullcontext
from datetime import date
from io import BytesIO

from finsight_app import dashboard_ui, eligibility_engine, kpi_engine


class FakeStreamlit:
    def __init__(self, *, buttons=None):
        self.buttons = buttons or {}
        self.events = []

    def _event(self, name, *values):
        self.events.append((name, *values))

    def title(self, value):
        self._event("title", value)

    def subheader(self, value):
        self._event("subheader", value)

    def caption(self, value):
        self._event("caption", value)

    def metric(self, label, value):
        self._event("metric", label, value)

    def info(self, value):
        self._event("info", value)

    def warning(self, value):
        self._event("warning", value)

    def error(self, value):
        self._event("error", value)

    def write(self, value):
        self._event("write", value)

    def selectbox(self, label, options, **_kwargs):
        self._event("selectbox", label, tuple(options))
        return options[0]

    def number_input(self, label, **kwargs):
        self._event("number_input", label)
        return kwargs["value"]

    def expander(self, label, **_kwargs):
        self._event("expander", label)
        return nullcontext()

    def container(self, **_kwargs):
        return nullcontext()

    def text_input(self, label, **_kwargs):
        self._event("text_input", label)
        return ""

    def button(self, label, **_kwargs):
        self._event("button", label)
        return self.buttons.get(label, False)

    def download_button(self, label, **kwargs):
        self._event("download_button", label, kwargs)
        return True


def _scope():
    return {
        "business": {"business_name": "Clinic Demo"},
        "account": {"account_name": "Current Account"},
        "business_id": "business-1",
        "account_id": "account-1",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "currency": "INR",
        "analytics": {
            "kpis": {
                "total_income_minor": 10000,
                "total_expense_minor": 2500,
                "net_cash_flow_minor": 7500,
                "transaction_count": 2,
            }
        },
    }


def test_database_dashboard_renders_backend_values_without_static_kpis():
    ui = FakeStreamlit()

    assert dashboard_ui.render_database_dashboard(ui, "session-token", _scope()) is True

    metrics = [event for event in ui.events if event[0] == "metric"]
    assert metrics == [
        ("metric", "Revenue", "INR 100.00"),
        ("metric", "Expenses", "INR 25.00"),
        ("metric", "Net cash flow", "INR 75.00"),
        ("metric", "Transactions", "2"),
    ]
    assert any("SQLite" in event[1] for event in ui.events if event[0] == "caption")


def test_database_dashboard_builds_pdf_from_selected_backend_scope(monkeypatch):
    ui = FakeStreamlit(buttons={"Generate PDF report": True})
    captured = {}

    def build_report(**kwargs):
        captured.update(kwargs)
        return {
            "business": {"name": "Clinic Demo"},
            "date_range": {"start_date": "2026-01-01", "end_date": "2026-01-31"},
            "currency": "INR",
            "sections": {
                "financial_summary": {
                    "total_income_minor": 10000,
                    "total_expense_minor": 2500,
                    "net_cash_flow_minor": 7500,
                    "transaction_count": 2,
                }
            },
        }

    monkeypatch.setattr(dashboard_ui.report_service, "build_report", build_report)
    monkeypatch.setattr(dashboard_ui, "generate_report", lambda report, schemes: BytesIO(b"%PDF"))

    assert dashboard_ui.render_database_dashboard(ui, "session-token", _scope()) is True
    assert captured == {
        "session_token": "session-token",
        "business_id": "business-1",
        "account_id": "account-1",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        "currency": "INR",
        "generated_at": captured["generated_at"],
    }
    download = next(event for event in ui.events if event[0] == "download_button")
    assert download[2]["data"] == b"%PDF"


def test_legacy_helpers_resolve_paths_from_their_module_location():
    # These functions remain available for legacy/demo callers, but no longer
    # depend on the process current working directory when using their defaults.
    assert kpi_engine.compute_kpis()["revenue_total"] > 0
    assert eligibility_engine.check_eligibility(
        {
            "turnover": 100000,
            "sector": "Service",
            "state": "Maharashtra",
            "business_category": "Micro",
            "owner_age": 30,
        }
    )
