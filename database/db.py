import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "finsight.db"
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"


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
        business_columns = {row[1] for row in connection.execute("PRAGMA table_info(businesses)")}
        if "business_type" not in business_columns:
            connection.execute("ALTER TABLE businesses ADD COLUMN business_type TEXT")
        if "ledger_registry_business_id" not in business_columns:
            connection.execute("ALTER TABLE businesses ADD COLUMN ledger_registry_business_id TEXT")


if __name__ == "__main__":
    initialize_database()
