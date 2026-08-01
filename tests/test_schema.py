import sqlite3
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "database" / "schema.sql"

REQUIRED_TABLES = {
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

EXPECTED_PRIMARY_KEYS = {
    "users": ["user_id"],
    "business_registry": ["business_id"],
    "counterparty_entities": ["entity_id"],
    "transaction_general_ledger": ["transaction_id"],
    "structural_budget_allocations": ["budget_id"],
    "pipeline_upload_ingestion_logs": ["upload_id"],
    "authentication_logs": ["authentication_log_id"],
    "otp_verifications": ["otp_id"],
    "documents": ["document_id"],
    "document_chunks": ["chunk_id"],
}

BCRYPT_HASH = "$2b$12$" + "a" * 53
SECOND_BCRYPT_HASH = "$2b$12$" + "b" * 53
TRANSACTION_HASH = "c" * 64
SECOND_TRANSACTION_HASH = "d" * 64
OTP_HASH = "e" * 64


@pytest.fixture
def connection(tmp_path):
    database_path = tmp_path / "schema_test.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    yield connection
    connection.close()


def insert_user(connection, user_id="user-1", email="owner@example.com"):
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
            SECOND_BCRYPT_HASH,
        ),
    )


def insert_business(connection, business_id="business-1", user_id="user-1", name="FinSight Traders"):
    connection.execute(
        """
        INSERT INTO business_registry (
            business_id, user_id, business_name, business_type, industry
        )
        VALUES (?, ?, ?, ?, ?);
        """,
        (business_id, user_id, name, "MSME", "Retail"),
    )


def insert_counterparty(
    connection,
    entity_id="entity-1",
    business_id="business-1",
    entity_name="Acme Supplies",
    entity_type="SUPPLIER",
):
    connection.execute(
        """
        INSERT INTO counterparty_entities (
            entity_id, business_id, entity_name, entity_type
        )
        VALUES (?, ?, ?, ?);
        """,
        (entity_id, business_id, entity_name, entity_type),
    )


def insert_transaction(
    connection,
    transaction_id="transaction-1",
    user_id="user-1",
    business_id="business-1",
    entity_id=None,
    amount=100.0,
    transaction_hash=TRANSACTION_HASH,
):
    connection.execute(
        """
        INSERT INTO transaction_general_ledger (
            transaction_id, user_id, business_id, entity_id,
            transaction_date, amount, transaction_type, category,
            payment_mode, description, transaction_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            transaction_id,
            user_id,
            business_id,
            entity_id,
            "2026-08-01",
            amount,
            "DEBIT",
            "Inventory",
            "UPI",
            "Stock purchase",
            transaction_hash,
        ),
    )


def table_columns(connection, table_name):
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table_name});")}


def primary_key_columns(connection, table_name):
    rows = connection.execute(f"PRAGMA table_info({table_name});").fetchall()
    return [row["name"] for row in sorted(rows, key=lambda item: item["pk"]) if row["pk"] > 0]


def foreign_key_edges(connection, table_name):
    rows = connection.execute(f"PRAGMA foreign_key_list({table_name});").fetchall()
    return {
        (row["from"], row["table"], row["to"], row["on_delete"])
        for row in rows
    }


def test_all_required_tables_exist_and_removed_tables_do_not_exist(connection):
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table';"
    ).fetchall()
    table_names = {row["name"] for row in rows}

    assert REQUIRED_TABLES.issubset(table_names)
    assert "transaction_summaries" not in table_names
    assert "financial_summaries" not in table_names


def test_each_table_has_expected_primary_key(connection):
    for table_name, expected_columns in EXPECTED_PRIMARY_KEYS.items():
        assert primary_key_columns(connection, table_name) == expected_columns


def test_foreign_key_relationships_are_defined(connection):
    assert ("user_id", "users", "user_id", "CASCADE") in foreign_key_edges(
        connection, "business_registry"
    )
    assert ("business_id", "business_registry", "business_id", "CASCADE") in foreign_key_edges(
        connection, "counterparty_entities"
    )
    assert ("user_id", "users", "user_id", "CASCADE") in foreign_key_edges(
        connection, "transaction_general_ledger"
    )
    assert ("business_id", "business_registry", "business_id", "CASCADE") in foreign_key_edges(
        connection, "transaction_general_ledger"
    )
    assert ("entity_id", "counterparty_entities", "entity_id", "SET NULL") in foreign_key_edges(
        connection, "transaction_general_ledger"
    )
    assert ("business_id", "business_registry", "business_id", "CASCADE") in foreign_key_edges(
        connection, "structural_budget_allocations"
    )
    assert ("user_id", "users", "user_id", "SET NULL") in foreign_key_edges(
        connection, "pipeline_upload_ingestion_logs"
    )
    assert ("business_id", "business_registry", "business_id", "SET NULL") in foreign_key_edges(
        connection, "pipeline_upload_ingestion_logs"
    )
    assert ("user_id", "users", "user_id", "SET NULL") in foreign_key_edges(
        connection, "authentication_logs"
    )
    assert ("user_id", "users", "user_id", "CASCADE") in foreign_key_edges(
        connection, "otp_verifications"
    )
    assert ("user_id", "users", "user_id", "CASCADE") in foreign_key_edges(
        connection, "documents"
    )
    assert ("document_id", "documents", "document_id", "CASCADE") in foreign_key_edges(
        connection, "document_chunks"
    )
    assert ("user_id", "users", "user_id", "CASCADE") in foreign_key_edges(
        connection, "document_chunks"
    )


def test_foreign_key_enforcement_rejects_invalid_parent_records(connection):
    with pytest.raises(sqlite3.IntegrityError):
        insert_business(connection, business_id="invalid-business", user_id="missing-user")

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO otp_verifications (
                otp_id, user_id, otp_hash, expires_at
            )
            VALUES (?, ?, ?, ?);
            """,
            ("otp-invalid", "missing-user", OTP_HASH, "2026-08-01T12:00:00Z"),
        )


def test_unique_constraints_are_enforced(connection):
    insert_user(connection, user_id="user-1", email="owner@example.com")

    with pytest.raises(sqlite3.IntegrityError):
        insert_user(connection, user_id="user-2", email="OWNER@example.com")

    insert_user(connection, user_id="user-3", email="second@example.com")
    insert_business(connection, business_id="business-1", user_id="user-1", name="FinSight Traders")

    with pytest.raises(sqlite3.IntegrityError):
        insert_business(connection, business_id="business-2", user_id="user-1", name="FinSight Traders")

    insert_business(connection, business_id="business-3", user_id="user-3", name="FinSight Traders")
    insert_counterparty(connection, entity_id="entity-1", entity_name="Acme Supplies", entity_type="SUPPLIER")

    with pytest.raises(sqlite3.IntegrityError):
        insert_counterparty(connection, entity_id="entity-2", entity_name="Acme Supplies", entity_type="SUPPLIER")

    insert_counterparty(connection, entity_id="entity-3", entity_name="Acme Supplies", entity_type="VENDOR")
    connection.execute(
        """
        INSERT INTO structural_budget_allocations (
            budget_id, business_id, category, budget_amount
        )
        VALUES (?, ?, ?, ?);
        """,
        ("budget-1", "business-1", "Inventory", 5000),
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO structural_budget_allocations (
                budget_id, business_id, category, budget_amount
            )
            VALUES (?, ?, ?, ?);
            """,
            ("budget-2", "business-1", "Inventory", 7000),
        )


def test_transaction_amount_check_and_nullable_counterparty(connection):
    insert_user(connection)
    insert_business(connection)

    insert_transaction(connection, transaction_id="transaction-positive", entity_id=None, amount=250.75)

    row = connection.execute(
        """
        SELECT entity_id
        FROM transaction_general_ledger
        WHERE transaction_id = ?;
        """,
        ("transaction-positive",),
    ).fetchone()
    assert row["entity_id"] is None

    with pytest.raises(sqlite3.IntegrityError):
        insert_transaction(connection, transaction_id="transaction-zero", amount=0)

    with pytest.raises(sqlite3.IntegrityError):
        insert_transaction(connection, transaction_id="transaction-negative", amount=-1)


def test_negative_budget_amount_is_rejected(connection):
    insert_user(connection)
    insert_business(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO structural_budget_allocations (
                budget_id, business_id, category, budget_amount
            )
            VALUES (?, ?, ?, ?);
            """,
            ("budget-negative", "business-1", "Marketing", -100),
        )


def test_duplicate_transaction_hash_is_allowed(connection):
    insert_user(connection)
    insert_business(connection)

    insert_transaction(connection, transaction_id="transaction-1", transaction_hash=SECOND_TRANSACTION_HASH)
    insert_transaction(connection, transaction_id="transaction-2", transaction_hash=SECOND_TRANSACTION_HASH)

    row = connection.execute(
        """
        SELECT COUNT(*) AS transaction_count
        FROM transaction_general_ledger
        WHERE transaction_hash = ?;
        """,
        (SECOND_TRANSACTION_HASH,),
    ).fetchone()
    assert row["transaction_count"] == 2


def test_otp_security_structure(connection):
    user_columns = table_columns(connection, "users")
    otp_columns = table_columns(connection, "otp_verifications")

    assert "otp_hash" in otp_columns
    assert "otp_token" not in user_columns
    assert "otp_expires_at" not in user_columns

    insert_user(connection)
    connection.execute(
        """
        INSERT INTO otp_verifications (
            otp_id, user_id, otp_hash, expires_at, is_used, attempt_count
        )
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        ("otp-1", "user-1", OTP_HASH, "2026-08-01T12:00:00Z", 0, 0),
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO otp_verifications (
                otp_id, user_id, otp_hash, expires_at
            )
            VALUES (?, ?, ?, ?);
            """,
            ("otp-2", "missing-user", OTP_HASH, "2026-08-01T12:00:00Z"),
        )


def test_document_ownership_structure(connection):
    assert ("user_id", "users", "user_id", "CASCADE") in foreign_key_edges(
        connection, "documents"
    )
    assert ("document_id", "documents", "document_id", "CASCADE") in foreign_key_edges(
        connection, "document_chunks"
    )
    assert ("user_id", "users", "user_id", "CASCADE") in foreign_key_edges(
        connection, "document_chunks"
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO documents (document_id, user_id, file_name)
            VALUES (?, ?, ?);
            """,
            ("document-invalid", "missing-user", "gst.pdf"),
        )

    insert_user(connection)
    connection.execute(
        """
        INSERT INTO documents (document_id, user_id, file_name)
        VALUES (?, ?, ?);
        """,
        ("document-1", "user-1", "gst.pdf"),
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO document_chunks (
                chunk_id, document_id, user_id, chunk_index, chunk_text
            )
            VALUES (?, ?, ?, ?, ?);
            """,
            ("chunk-invalid-document", "missing-document", "user-1", 0, "Chunk text"),
        )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO document_chunks (
                chunk_id, document_id, user_id, chunk_index, chunk_text
            )
            VALUES (?, ?, ?, ?, ?);
            """,
            ("chunk-invalid-user", "document-1", "missing-user", 0, "Chunk text"),
        )

    connection.execute(
        """
        INSERT INTO document_chunks (
            chunk_id, document_id, user_id, chunk_index, chunk_text
        )
        VALUES (?, ?, ?, ?, ?);
        """,
        ("chunk-1", "document-1", "user-1", 0, "Chunk text"),
    )
