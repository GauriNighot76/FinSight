"""Back up the database, then remove imported transaction history.

Run without --confirm for a read-only count. The explicit confirmation phrase
prevents accidental deletion while giving local/demo installations a clean
way to recover from earlier broken imports.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from database.db import DATABASE_PATH

CONFIRMATION = "RESET-IMPORTED-TRANSACTIONS"


def _counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        "transactions": connection.execute(
            "SELECT COUNT(*) FROM transaction_general_ledger"
        ).fetchone()[0],
        "identities": connection.execute(
            "SELECT COUNT(*) FROM ingested_transaction_identities"
        ).fetchone()[0],
        "attempts": connection.execute(
            "SELECT COUNT(*) FROM ingestion_attempts"
        ).fetchone()[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Back up FinSight and clear imported transactions while preserving users and businesses."
    )
    parser.add_argument("--confirm", help=f"Required phrase: {CONFIRMATION}")
    args = parser.parse_args()

    if not DATABASE_PATH.exists():
        print(f"No database found at {DATABASE_PATH}")
        return 0

    with sqlite3.connect(DATABASE_PATH) as connection:
        counts = _counts(connection)
    print(
        f"Current data: {counts['transactions']} transactions, "
        f"{counts['identities']} import identities, {counts['attempts']} import attempts."
    )
    if args.confirm != CONFIRMATION:
        print(f"Read-only check. To clear these records, rerun with --confirm {CONFIRMATION}")
        return 0

    backup_dir = DATABASE_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"finsight-before-reset-{stamp}.db"
    shutil.copy2(DATABASE_PATH, backup_path)

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "CREATE TEMP TABLE imported_ids AS "
            "SELECT transaction_id FROM ingested_transaction_identities"
        )
        connection.execute("DELETE FROM ingested_transaction_identities")
        connection.execute(
            "DELETE FROM transaction_general_ledger "
            "WHERE transaction_id IN (SELECT transaction_id FROM imported_ids)"
        )
        connection.execute("DELETE FROM ingestion_attempts")
        connection.execute("DROP TABLE imported_ids")

    print(f"Imported transaction history cleared. Backup: {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
