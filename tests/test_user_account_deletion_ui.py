from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from database import db
from finsight_app import scheme_assistant_ui
from services import auth_service
from tests.test_business_service import account, create

APP = Path(__file__).parents[1] / "finsight_app" / "app.py"


@pytest.fixture
def workspace(monkeypatch):
    monkeypatch.setattr(db, "initialize_database", lambda: None)
    monkeypatch.setattr(scheme_assistant_ui, "render_help_assistant", lambda *args: None)
    _, token = account("User", "user@example.com", "9000000001")
    def launch(authenticated=True):
        app = AppTest.from_file(str(APP), default_timeout=15)
        if authenticated:
            app.session_state["auth_token"] = token
        return app.run()
    return token, launch


def button(app, label):
    return next(b for b in app.button if b.label == label)


def input_field(app, label):
    return next(t for t in app.text_input if t.label == label)


def open_confirmation(app):
    button(app, "Account Settings").click().run()
    button(app, "Delete Account").click().run()
    assert not app.exception


def test_unauthenticated_users_cannot_see_settings(workspace):
    _, launch = workspace
    app = launch(False)
    assert not app.exception
    assert not any(b.label in {"Account Settings", "Delete Account"} for b in app.button)


def test_open_wrong_confirmation_missing_password_cancel_do_not_delete(workspace, monkeypatch):
    _, launch = workspace
    delete = Mock()
    monkeypatch.setattr(auth_service, "delete_account", delete)
    app = launch()
    open_confirmation(app)
    delete.assert_not_called()
    input_field(app, "Type DELETE MY ACCOUNT to continue:").set_value("DELETE")
    button(app, "Delete Account").click().run()
    assert any("exactly" in e.value for e in app.error)
    input_field(app, "Type DELETE MY ACCOUNT to continue:").set_value("DELETE MY ACCOUNT")
    button(app, "Delete Account").click().run()
    assert any("password" in e.value for e in app.error)
    button(app, "Cancel").click().run()
    assert not app.exception
    delete.assert_not_called()


def test_owner_blocked_in_real_settings_flow(workspace):
    token, launch = workspace
    create(token, "Owned Shop")
    app = launch()
    open_confirmation(app)
    input_field(app, "Type DELETE MY ACCOUNT to continue:").set_value("DELETE MY ACCOUNT")
    input_field(app, "Current Password").set_value("StrongPass1")
    button(app, "Delete Account").click().run()
    assert not app.exception
    assert any("active business" in e.value for e in app.error)
    assert any("Owned Shop" in t.value for t in app.text)
    assert auth_service.validate_session(token)["success"]


def test_eligible_user_signed_out_state_cleared_and_login_denied(workspace):
    token, launch = workspace
    second = auth_service.login("user@example.com", "StrongPass1")["session"]["token"]
    app = launch()
    app.session_state["upload_old_preview"] = ["private"]
    app.session_state["report_pdf_old"] = b"private"
    open_confirmation(app)
    input_field(app, "Type DELETE MY ACCOUNT to continue:").set_value("DELETE MY ACCOUNT")
    input_field(app, "Current Password").set_value("StrongPass1")
    button(app, "Delete Account").click().run()
    assert not app.exception
    state = app.session_state.filtered_state
    assert "auth_token" not in state
    assert "upload_old_preview" not in state and "report_pdf_old" not in state
    assert not state.get("account_delete_pending")
    assert any(s.value == "Welcome back" for s in app.subheader)
    assert any("account has been deleted" in s.value for s in app.success)
    assert not auth_service.validate_session(token)["success"]
    assert not auth_service.validate_session(second)["success"]
    input_field(app, "Email").set_value("user@example.com")
    input_field(app, "Password").set_value("StrongPass1")
    button(app, "Sign In").click().run()
    assert not app.exception
    assert app.error
    assert "auth_token" not in app.session_state.filtered_state
