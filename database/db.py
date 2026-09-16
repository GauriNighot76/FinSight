import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "finsight.db"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"


def _migrate_identity_uniqueness(connection: sqlite3.Connection) -> None:
    """Allow distinct source IDs to share the same economic values.

    Earlier databases made the coarse canonical hash globally unique, causing
    legitimate same-value transactions to be discarded.  The source-ID index
    remains unique and is the authoritative idempotency key when supplied.
    """
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='ingested_transaction_identities'"
    ).fetchone()
    table_sql = row["sql"] if row and row["sql"] else ""
    if "canonical_identity_hash TEXT NOT NULL UNIQUE" not in table_sql:
        return
    connection.executescript(
        """
        PRAGMA foreign_keys=OFF;
        BEGIN;
        ALTER TABLE ingested_transaction_identities RENAME TO ingested_transaction_identities_old;
        CREATE TABLE ingested_transaction_identities (
            identity_id TEXT PRIMARY KEY,
            transaction_id TEXT NOT NULL UNIQUE,
            attempt_id TEXT NOT NULL,
            business_id TEXT NOT NULL,
            registry_business_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            source_system TEXT NOT NULL CHECK (source_system IN ('finsight_demo_bank_statement_v1')),
            source_transaction_id TEXT CHECK (source_transaction_id IS NULL OR length(trim(source_transaction_id)) > 0),
            transaction_date TEXT NOT NULL,
            amount_minor INTEGER NOT NULL CHECK (typeof(amount_minor) = 'integer' AND amount_minor >= 0),
            direction TEXT NOT NULL CHECK (direction IN ('income','expense')),
            currency TEXT NOT NULL CHECK (length(currency) = 3 AND currency = upper(currency)),
            canonical_identity_hash TEXT NOT NULL CHECK (length(trim(canonical_identity_hash)) > 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transaction_id) REFERENCES transaction_general_ledger(transaction_id) ON DELETE RESTRICT,
            FOREIGN KEY (attempt_id) REFERENCES ingestion_attempts(attempt_id) ON DELETE RESTRICT,
            FOREIGN KEY (business_id) REFERENCES businesses(business_id) ON DELETE RESTRICT,
            FOREIGN KEY (registry_business_id) REFERENCES business_registry(business_id) ON DELETE RESTRICT,
            FOREIGN KEY (account_id) REFERENCES financial_accounts(account_id) ON DELETE RESTRICT
        );
        INSERT INTO ingested_transaction_identities
        SELECT * FROM ingested_transaction_identities_old;
        DROP TABLE ingested_transaction_identities_old;
        COMMIT;
        PRAGMA foreign_keys=ON;
        """
    )


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DATABASE_PATH), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")
    with get_connection() as connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrate_identity_uniqueness(connection)
        # Recreate indexes after a table-rebuild migration.
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        existing = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        migrations = {
            "username": "ALTER TABLE users ADD COLUMN username TEXT NOT NULL DEFAULT 'User'",
            "role": "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'standard_business'",
            "account_status": "ALTER TABLE users ADD COLUMN account_status TEXT NOT NULL DEFAULT 'active'",
            "updated_at": "ALTER TABLE users ADD COLUMN updated_at TEXT",
        }
        for column, statement in migrations.items():
            if column not in existing:
                connection.execute(statement)
        connection.execute("UPDATE users SET updated_at=COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)")


if __name__ == "__main__":
    initialize_database()
