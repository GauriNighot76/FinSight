from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest


class FakeStreamlit:
    def __init__(self, *, selected=None, dates=None, buttons=None):
        self.selected = selected or {}
        self.dates = dates or {}
        self.buttons = buttons or {}
        self.events = []

    def _event(self, name, *values):
        self.events.append((name, *values))

    def header(self, value):
        self._event("header", value)

    def subheader(self, value):
        self._event("subheader", value)

    def caption(self, value):
        self._event("caption", value)

    def info(self, value):
        self._event("info", value)

    def warning(self, value):
        self._event("warning", value)

    def error(self, value):
        self._event("error", value)

    def success(self, value):
        self._event("success", value)

    def metric(self, label, value):
        self._event("metric", label, value)

    def selectbox(self, label, options, **_kwargs):
        self._event("selectbox", label, tuple(options))
        return self.selected.get(label, options[0] if options else None)

    def date_input(self, label, value, **_kwargs):
        self._event("date_input", label, value)
        return self.dates.get(label, value)

    def button(self, label, **_kwargs):
        self._event("button", label)
        return self.buttons.get(label, False)

    def line_chart(self, data, **_kwargs):
        self._event("line_chart", data)

    def dataframe(self, data, **_kwargs):
        self._event("dataframe", data)


def _authorized_context(monkeypatch, role="owner"):
    from finsight_app import analytics_ui

    monkeypatch.setattr(
        analytics_ui.auth_service,
        "validate_session",
        lambda token: {
            "success": True,
            "user": {"user_id": "owner-user", "username": "Owner"},
        },
    )
    monkeypatch.setattr(
        analytics_ui.business_service,
        "list_user_businesses",
        lambda token: {
            "success": True,
            "businesses": [
                {
                    "business_id": "business-1",
                    "business_name": "Controlled Demo",
                    "business_status": "active",
                    "membership": {
                        "membership_role": role,
                        "membership_status": "active",
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        analytics_ui.account_service,
        "list_business_accounts",
        lambda token, business_id: {
            "success": True,
            "accounts": [
                {
                    "account_id": "account-1",
                    "account_name": "Demo Account",
                    "currency": "INR",
                    "account_status": "active",
                }
            ],
        },
    )
    return analytics_ui


def _analytics_result(*, empty=False):
    if empty:
        return {
            "kpis": {
                "total_income_minor": 0,
                "total_expense_minor": 0,
                "net_cash_flow_minor": 0,
                "transaction_count": 0,
                "average_transaction_minor": Decimal("0"),
                "largest_income_minor": None,
                "largest_expense_minor": None,
                "opening_balance_minor": 0,
                "closing_balance_minor": 0,
                "savings_rate": None,
                "income_expense_ratio": None,
            },
            "trends": {"daily": [], "weekly": [], "monthly": []},
            "categories": [],
            "payment_modes": [],
            "accounts": [],
        }
    return {
        "kpis": {
            "total_income_minor": 1000,
            "total_expense_minor": 250,
            "net_cash_flow_minor": 750,
            "transaction_count": 2,
            "average_transaction_minor": Decimal("625"),
            "largest_income_minor": 1000,
            "largest_expense_minor": 250,
            "opening_balance_minor": 5000,
            "closing_balance_minor": 5750,
            "savings_rate": Decimal("75.00"),
            "income_expense_ratio": Decimal("4.00"),
        },
        "trends": {
            "daily": [{"period": "2026-08-01", "income_minor": 1000}],
            "weekly": [{"period": "2026-W31", "income_minor": 1000}],
            "monthly": [{"period": "2026-08", "income_minor": 1000}],
        },
        "categories": [{"category": "Sales", "amount_minor": 1000}],
        "payment_modes": [{"payment_mode": "UPI", "amount_minor": 1000}],
        "accounts": [{"transaction_count": 2, "net_cash_flow_minor": 750}],
    }


def _events_text(ui):
    return repr(ui.events)


def test_analytics_page_loads_for_authenticated_owner(monkeypatch):
    analytics_ui = _authorized_context(monkeypatch)
    calls = []
    monkeypatch.setattr(
        analytics_ui.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: calls.append(kwargs) or _analytics_result(),
    )
    ui = FakeStreamlit()

    assert analytics_ui.render_analytics_page(ui, "session-token") is True
    assert calls[0]["business_id"] == "business-1"
    assert calls[0]["account_id"] == "account-1"
    assert "session-token" not in _events_text(ui)
    assert "business-1" not in _events_text(ui)
    assert "account-1" not in _events_text(ui)


def test_authentication_is_required(monkeypatch):
    from finsight_app import analytics_ui

    monkeypatch.setattr(
        analytics_ui.auth_service,
        "validate_session",
        lambda token: {"success": False, "error": "SESSION_INVALID"},
    )
    ui = FakeStreamlit()

    assert analytics_ui.render_analytics_page(ui, "invalid-session") is False
    assert "invalid-session" not in _events_text(ui)
    assert not any(event[0] == "selectbox" for event in ui.events)


@pytest.mark.parametrize("role", ["member", "viewer"])
def test_only_owner_and_manager_businesses_are_available(monkeypatch, role):
    analytics_ui = _authorized_context(monkeypatch, role)
    ui = FakeStreamlit()

    assert analytics_ui.render_analytics_page(ui, "session-token") is False
    assert not any(event[0] == "selectbox" for event in ui.events)


def test_manager_can_load_analytics(monkeypatch):
    analytics_ui = _authorized_context(monkeypatch, "manager")
    monkeypatch.setattr(
        analytics_ui.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: _analytics_result(),
    )
    ui = FakeStreamlit()

    assert analytics_ui.render_analytics_page(ui, "manager-session") is True


def test_business_and_account_selectors_are_used(monkeypatch):
    analytics_ui = _authorized_context(monkeypatch)
    selected = {"Business": "Controlled Demo", "Account": "Demo Account (INR)"}
    calls = []
    monkeypatch.setattr(
        analytics_ui.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: calls.append(kwargs) or _analytics_result(),
    )
    ui = FakeStreamlit(selected=selected)

    assert analytics_ui.render_analytics_page(ui, "session-token") is True
    assert calls[0]["business_id"] == "business-1"
    assert calls[0]["account_id"] == "account-1"
    assert any(event[:2] == ("selectbox", "Business") for event in ui.events)
    assert any(event[:2] == ("selectbox", "Account") for event in ui.events)


def test_date_filter_is_passed_to_backend_without_ui_calculation(monkeypatch):
    analytics_ui = _authorized_context(monkeypatch)
    calls = []
    monkeypatch.setattr(
        analytics_ui.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: calls.append(kwargs) or _analytics_result(),
    )
    ui = FakeStreamlit(
        dates={"Start date": date(2026, 8, 1), "End date": date(2026, 8, 31)}
    )

    assert analytics_ui.render_analytics_page(ui, "session-token") is True
    assert calls[0]["start_date"] == "2026-08-01"
    assert calls[0]["end_date"] == "2026-08-31"


def test_kpis_are_rendered_from_backend_result(monkeypatch):
    analytics_ui = _authorized_context(monkeypatch)
    monkeypatch.setattr(
        analytics_ui.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: _analytics_result(),
    )
    ui = FakeStreamlit()

    analytics_ui.render_analytics_page(ui, "session-token")
    labels = [event[1] for event in ui.events if event[0] == "metric"]
    assert labels == [
        "Total Income",
        "Total Expense",
        "Net Cash Flow",
        "Transaction Count",
        "Average Transaction",
        "Largest Income",
        "Largest Expense",
        "Opening Balance",
        "Closing Balance",
        "Savings Rate",
        "Income/Expense Ratio",
    ]


def test_trends_and_summary_sections_render_backend_rows(monkeypatch):
    analytics_ui = _authorized_context(monkeypatch)
    result = _analytics_result()
    monkeypatch.setattr(
        analytics_ui.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: result,
    )
    ui = FakeStreamlit()

    analytics_ui.render_analytics_page(ui, "session-token")
    charts = [event[1] for event in ui.events if event[0] == "line_chart"]
    tables = [event[1] for event in ui.events if event[0] == "dataframe"]
    assert charts == [
        result["trends"]["daily"],
        result["trends"]["weekly"],
        result["trends"]["monthly"],
    ]
    assert tables == [result["categories"], result["payment_modes"], result["accounts"]]


def test_empty_analytics_shows_safe_empty_state(monkeypatch):
    analytics_ui = _authorized_context(monkeypatch)
    monkeypatch.setattr(
        analytics_ui.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: _analytics_result(empty=True),
    )
    ui = FakeStreamlit()

    assert analytics_ui.render_analytics_page(ui, "session-token") is True
    rendered = _events_text(ui)
    assert "No transactions" in rendered
    assert "Traceback" not in rendered
    assert sum(event[0] == "dataframe" for event in ui.events) == 3


@pytest.mark.parametrize(
    "error,expected",
    [
        ("The analytics date range is invalid.", "valid date range"),
        ("The selected financial account is unavailable.", "financial account"),
        ("The selected analytics currency is invalid.", "currency"),
    ],
)
def test_backend_errors_are_sanitized(monkeypatch, error, expected):
    analytics_ui = _authorized_context(monkeypatch)
    monkeypatch.setattr(
        analytics_ui.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: (_ for _ in ()).throw(
            analytics_ui.analytics_service.AnalyticsError(error)
        ),
    )
    ui = FakeStreamlit()

    assert analytics_ui.render_analytics_page(ui, "session-token") is False
    rendered = _events_text(ui)
    assert expected in rendered
    assert "SELECT" not in rendered
    assert "session-token" not in rendered


def test_unexpected_errors_are_safe_and_service_is_called_once(monkeypatch):
    analytics_ui = _authorized_context(monkeypatch)
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("SQL secret path raw payload")

    monkeypatch.setattr(analytics_ui.analytics_service, "get_financial_analytics", fail)
    ui = FakeStreamlit()

    assert analytics_ui.render_analytics_page(ui, "session-token") is False
    rendered = _events_text(ui)
    assert len(calls) == 1
    assert "could not be loaded" in rendered
    assert "SQL" not in rendered
    assert "secret path" not in rendered
    assert "raw payload" not in rendered


def test_business_lookup_errors_are_safe(monkeypatch):
    analytics_ui = _authorized_context(monkeypatch)
    monkeypatch.setattr(
        analytics_ui.business_service,
        "list_user_businesses",
        lambda token: (_ for _ in ()).throw(RuntimeError("SQL business secret")),
    )
    ui = FakeStreamlit()

    assert analytics_ui.render_analytics_page(ui, "session-token") is False
    rendered = _events_text(ui)
    assert "could not be loaded" in rendered
    assert "SQL business secret" not in rendered


def test_account_lookup_errors_are_safe(monkeypatch):
    analytics_ui = _authorized_context(monkeypatch)
    monkeypatch.setattr(
        analytics_ui.account_service,
        "list_business_accounts",
        lambda token, business_id: (_ for _ in ()).throw(
            RuntimeError("account SQL secret")
        ),
    )
    ui = FakeStreamlit()

    assert analytics_ui.render_analytics_page(ui, "session-token") is False
    rendered = _events_text(ui)
    assert "could not be loaded" in rendered
    assert "account SQL secret" not in rendered


def test_ui_has_no_direct_database_access(monkeypatch):
    analytics_ui = _authorized_context(monkeypatch)
    monkeypatch.setattr(
        analytics_ui.analytics_service,
        "get_financial_analytics",
        lambda **kwargs: _analytics_result(),
    )
    ui = FakeStreamlit()

    assert analytics_ui.render_analytics_page(ui, "session-token") is True
    assert not hasattr(analytics_ui, "queries")


def test_app_entrypoint_wires_the_analytics_page():
    app_source = (Path(__file__).parents[1] / "finsight_app" / "app.py").read_text()
    assert "from finsight_app.analytics_ui import render_analytics_page" in app_source
    assert "render_analytics_page(st, auth_token)" in app_source
