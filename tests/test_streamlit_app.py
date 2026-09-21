from pathlib import Path

from streamlit.testing.v1 import AppTest

from database import db


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_app_loads_from_unrelated_working_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "state" / "finsight.db")
    monkeypatch.chdir(tmp_path)

    app = AppTest.from_file(str(PROJECT_ROOT / "finsight_app" / "app.py"))
    app.run(timeout=20)

    assert not app.exception
    assert app.title[0].value == "FinSight — MSME Financial Analytics"
    assert any("Sign in to access" in item.value for item in app.info)


def test_new_user_setup_report_switch_and_logout(tmp_path, monkeypatch):
    from datetime import date
    from database import queries
    from services import account_service, business_service, csv_normalizer, ingestion_service, auth_service

    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "ui.db")
    monkeypatch.setattr(queries, "get_connection", db.get_connection)
    app = AppTest.from_file(str(PROJECT_ROOT / "finsight_app" / "app.py")).run(timeout=20)
    app.text_input(key="register_name").set_value("Exam Owner")
    app.text_input(key="register_email").set_value("exam@example.test")
    app.text_input(key="register_contact").set_value("9999999991")
    app.text_input(key="register_password").set_value("ValidPass123!")
    app.button(key="register_submit").click().run()
    assert not app.exception
    assert any("Account created" in item.value for item in app.success)
    app.text_input(key="login_email").set_value("exam@example.test")
    app.text_input(key="login_password").set_value("ValidPass123!")
    app.button(key="login_submit").click().run()
    app.text_input(key="setup_business_name").set_value("ABC Traders")
    app.button(key="setup_create_business").click().run()
    assert not app.exception
    assert not any("approval" in item.value.lower() for item in [*app.info, *app.warning])
    app.text_input(key="setup_account_name").set_value("Current Account")
    app.button(key="setup_create_account").click().run()
    assert not app.exception
    token = app.session_state["auth_token"]
    first = business_service.list_user_businesses(token)["businesses"][0]
    account = account_service.list_business_accounts(token, first["business_id"])["accounts"][0]
    # AppTest does not expose file-upload interaction; real CSV/service integration
    # is exercised here and upload rendering is covered by adapter tests.
    payload = csv_normalizer.normalize_csv((PROJECT_ROOT / "sample_data/valid_transactions.csv").read_bytes())
    ingestion_service.ingest(session_token=token, business_id=first["business_id"], account_id=account["account_id"], payload=payload)
    app.date_input(key="analytics_start_date").set_value(date(2026, 3, 1))
    app.date_input(key="analytics_end_date").set_value(date(2026, 9, 20))
    app.button(key="analytics_insights").click().run(timeout=20)
    assert not app.exception
    assert next(m.value for m in app.metric if m.label == "Total Income") == "INR 371,000.00"
    assert any(m.label == "Health score" for m in app.metric)
    assert any(b.label == "Download selected-business PDF" for b in app.get("download_button"))
    second = business_service.create_business(token, {"business_name": "Second Business"})["business"]
    account_service.create_account(token, second["business_id"], {"account_name": "Current Account", "account_type": "bank"})
    app.run()
    app.selectbox(key="analytics_business").select("Second Business").run()
    assert not app.exception
    assert next(m.value for m in app.metric if m.label == "Total Income") == "INR 0.00"
    assert not any(m.label == "Health score" for m in app.metric)
    assert not any(b.label == "Download selected-business PDF" for b in app.get("download_button"))
    next(b for b in app.button if b.label == "Sign out").click().run()
    assert not app.exception
    assert not auth_service.validate_session(token)["success"]
    assert app.text_input(key="login_password").value == ""
    assert not any(m.label == "Total Income" for m in app.metric)
