from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
SCHEMA_PATH = BASE_DIR / "schema.sql"
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "finsight.db"
DATABASE_ENV_VAR = "FINSIGHT_DB_PATH"


def get_database_path(database_path: str | os.PathLike[str] | None = None) -> Path:
    configured_path = database_path or os.environ.get(DATABASE_ENV_VAR) or DEFAULT_DATABASE_PATH
    resolved_path = Path(configured_path).expanduser()
    if not resolved_path.is_absolute():
        resolved_path = PROJECT_ROOT / resolved_path
    return resolved_path.resolve()


def get_db_connection(
    database_path: str | os.PathLike[str] | None = None,
    *,
    row_factory: bool = True,
) -> sqlite3.Connection:
    resolved_path = get_database_path(database_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(resolved_path)
    if row_factory:
        connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


@contextmanager
def get_connection(
    database_path: str | os.PathLike[str] | None = None,
    *,
    row_factory: bool = True,
) -> Iterator[sqlite3.Connection]:
    connection = get_db_connection(database_path, row_factory=row_factory)
    try:
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


def init_database(
    database_path: str | os.PathLike[str] | None = None,
    schema_path: str | os.PathLike[str] = SCHEMA_PATH,
) -> Path:
    resolved_schema_path = Path(schema_path).expanduser()
    if not resolved_schema_path.is_absolute():
        resolved_schema_path = PROJECT_ROOT / resolved_schema_path
    resolved_schema_path = resolved_schema_path.resolve()

    if not resolved_schema_path.exists():
        raise FileNotFoundError(f"schema.sql was not found at {resolved_schema_path}")

    schema_sql = resolved_schema_path.read_text(encoding="utf-8")
    resolved_database_path = get_database_path(database_path)

    with get_connection(resolved_database_path) as connection:
        cursor = connection.cursor()
        cursor.executescript(schema_sql)

    return resolved_database_path


if __name__ == "__main__":
    initialized_path = init_database()
    print(f"FinSight database initialized successfully at {initialized_path}")
