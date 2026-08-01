import sqlite3

import pytest

from database import db


EXPECTED_TABLES = {
    "users",
    "business_registry",
    "counterparty_entities",
    "transaction_general_ledger",
    "structural_budget_allocations",
    "pipeline_upload_ingestion_logs",
    "authentication_logs",
    "otp_verifications",
    "documents",
    "document_chunks",
}

BCRYPT_HASH = "$2b$12$" + "a" * 53
SECRET_HASH = "$2b$12$" + "b" * 53


def insert_test_user(connection, user_id="user-1", email="owner@example.com"):
    connection.execute(
        """
        INSERT INTO users (
            user_id, name, email, contact_number, password_hash,
            secret_question, secret_answer_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (
            user_id,
            "Owner",
            email,
            "9999999999",
            BCRYPT_HASH,
            "What is your recovery phrase?",
            SECRET_HASH,
        ),
    )


def test_connection_creation_returns_sqlite_connection(tmp_path):
    database_path = tmp_path / "connection.sqlite3"

    connection = db.get_db_connection(database_path)
    try:
        assert isinstance(connection, sqlite3.Connection)
        row = connection.execute("SELECT 1 AS ok;").fetchone()
        assert row["ok"] == 1
    finally:
        connection.close()


def test_configured_database_path_is_used(tmp_path):
    database_path = tmp_path / "nested" / "configured.sqlite3"

    with db.get_connection(database_path) as connection:
        connection.execute("CREATE TABLE path_check (id INTEGER PRIMARY KEY);")
        connection.execute("INSERT INTO path_check (id) VALUES (?);", (1,))

    assert database_path.exists()

    with sqlite3.connect(database_path) as verification_connection:
        row = verification_connection.execute("SELECT COUNT(*) FROM path_check;").fetchone()
        assert row[0] == 1


def test_foreign_keys_are_enabled_for_connections(tmp_path):
    database_path = tmp_path / "foreign_keys.sqlite3"

    with db.get_connection(database_path) as connection:
        row = connection.execute("PRAGMA foreign_keys;").fetchone()
        assert row[0] == 1


def test_schema_initialization_creates_expected_tables(tmp_path):
    database_path = tmp_path / "schema.sqlite3"

    initialized_path = db.init_database(database_path)

    assert initialized_path == database_path.resolve()

    with db.get_connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table';
            """
        ).fetchall()

    table_names = {row["name"] for row in rows}
    assert EXPECTED_TABLES.issubset(table_names)


def test_successful_context_transaction_commits(tmp_path):
    database_path = tmp_path / "commit.sqlite3"
    db.init_database(database_path)

    with db.get_connection(database_path) as connection:
        insert_test_user(connection)

    with db.get_connection(database_path) as connection:
        row = connection.execute(
            "SELECT email FROM users WHERE user_id = ?;",
            ("user-1",),
        ).fetchone()

    assert row["email"] == "owner@example.com"


def test_context_transaction_rolls_back_on_exception(tmp_path):
    database_path = tmp_path / "rollback.sqlite3"
    db.init_database(database_path)

    with pytest.raises(RuntimeError):
        with db.get_connection(database_path) as connection:
            insert_test_user(connection)
            raise RuntimeError("force rollback")

    with db.get_connection(database_path) as connection:
        row = connection.execute("SELECT COUNT(*) AS user_count FROM users;").fetchone()

    assert row["user_count"] == 0


def test_context_managed_connection_is_closed_after_exit(tmp_path):
    database_path = tmp_path / "cleanup.sqlite3"

    with db.get_connection(database_path) as connection:
        connection.execute("CREATE TABLE cleanup_check (id INTEGER PRIMARY KEY);")

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1;")
