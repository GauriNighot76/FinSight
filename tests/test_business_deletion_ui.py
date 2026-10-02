from pathlib import Path
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from database import db, queries
from finsight_app import scheme_assistant_ui
from finsight_app.business_ui import _clear_deleted_business_state
from services import business_service
from tests.test_business_service import account, create

APP = Path(__file__).parents[1] / "finsight_app" / "app.py"


@pytest.fixture
def workspace(monkeypatch):
    monkeypatch.setattr(db, "initialize_database", lambda: None)
    monkeypatch.setattr(scheme_assistant_ui, "render_help_assistant", lambda *a: None)
    _, token = account("Owner", "owner@example.com", "9000000001")
    business = create(token)["business"]
    def launch(session_token=token):
        app = AppTest.from_file(str(APP), default_timeout=15)
        app.session_state["auth_token"] = session_token
        app.session_state["app_page"] = "Manage Businesses"
        return app.run()
    return token, business, launch


@pytest.mark.parametrize("role", ["manager", "member", "viewer"])
def test_nonowners_do_not_see_delete(workspace, role):
    token, business, launch = workspace
    _, member_token = account("Member", "member@example.com", "9000000002")
    business_service.add_member(token, business["business_id"], "member@example.com", role)
    app = launch(member_token)
    assert not app.exception
    assert "Delete Business" not in [b.label for b in app.button]


def test_open_cancel_and_wrong_confirmation_never_call_service(workspace, monkeypatch):
    _, business, launch = workspace
    delete = Mock()
    monkeypatch.setattr(business_service, "delete_business", delete)
    app = launch()
    prefix = f"delete_business_{business['business_id']}_"
    app.button(key=prefix + "open").click().run()
    assert not app.exception
    delete.assert_not_called()
    app.text_input(key=prefix + "name").set_value("Acme").run()
    app.button(key=prefix + "confirm").click().run()
    assert not app.exception
    assert any("exactly" in e.value for e in app.error)
    delete.assert_not_called()
    app.button(key=prefix + "cancel").click().run()
    assert not app.exception
    delete.assert_not_called()
    assert not app.session_state.filtered_state.get(prefix + "pending")


@pytest.mark.parametrize("another_business", [False, True])
def test_confirm_refreshes_real_app_and_preserves_other_state(workspace, another_business):
    token, business, launch = workspace
    bid = business["business_id"]
    other = create(token, "Other Business")["business"] if another_business else None
    app = launch()
    app.session_state[f"upload_{bid}_preview"] = ["old preview"]
    app.session_state[f"report_pdf_{bid}"] = b"old pdf"
    if other:
        app.session_state[f"report_pdf_{other['business_id']}"] = b"keep"
    prefix = f"delete_business_{bid}_"
    app.button(key=prefix + "open").click().run()
    app.text_input(key=prefix + "name").set_value("  Acme MSME  ").run()
    app.button(key=prefix + "confirm").click().run()
    assert not app.exception
    assert queries.get_module2_business(bid)["business_status"] == "disabled"
    state = app.session_state.filtered_state
    assert f"upload_{bid}_preview" not in state
    assert f"report_pdf_{bid}" not in state
    assert state.get("selected_business_id") != bid
    assert state.get("business_selector") != bid
    assert state["auth_token"] == token
    if other:
        assert state["selected_business_id"] == other["business_id"]
        assert state[f"report_pdf_{other['business_id']}"] == b"keep"
        assert app.selectbox(key="business_selector").options == ["Other Business"]
        assert state["app_page"] == "Overview"
    else:
        assert any(s.value == "Set up your business" for s in app.subheader)


def test_targeted_cleanup_leaves_unrelated_business_and_login():
    class State:
        session_state = {
            "selected_business_id": "A", "business_selector": "A", "auth_token": "token",
            "upload_A_mapping": {}, "A_file_map_description": "Item", "A_transaction_editor": {},
            "report_section_A_summary": True, "scheme_answer_A": "answer",
            "report_pdf_B": b"keep", "upload_B_mapping": {"keep": True},
        }
    st = State()
    _clear_deleted_business_state(st, "A")
    assert st.session_state == {"auth_token": "token", "report_pdf_B": b"keep",
                                "upload_B_mapping": {"keep": True}}
