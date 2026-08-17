import sqlite3
from pathlib import Path

import pytest

from database import queries

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "database" / "schema.sql"


@pytest.fixture(autouse=True)
def isolated_test_database(tmp_path, monkeypatch):
    database_path = tmp_path / "test_finsight.db"

    def connection_factory():
        connection = sqlite3.connect(str(database_path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    with connection_factory() as connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    monkeypatch.setattr(queries, "get_connection", connection_factory)
    yield connection_factory
