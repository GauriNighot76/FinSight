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
