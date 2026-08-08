import sqlite3
import pytest

from pathlib import Path

from database import queries


BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"


@pytest.fixture(autouse=True)
def isolated_test_database(tmp_path, monkeypatch):
    """
    Give every test its own fresh SQLite database.

    The real data/finsight.db is never used by tests.
    """

    test_database_path = tmp_path / "test_finsight.db"

    def get_test_connection():
        connection = sqlite3.connect(
            str(test_database_path),
            timeout=30,
        )

        connection.row_factory = sqlite3.Row

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        return connection

    # Create the complete schema in the temporary database.
    schema_sql = SCHEMA_PATH.read_text(
        encoding="utf-8"
    )

    with get_test_connection() as connection:
        connection.executescript(schema_sql)

    # Replace the database connection used by queries.py
    # only while the test is running.
    monkeypatch.setattr(
        queries,
        "get_connection",
        get_test_connection,
    )

    yield