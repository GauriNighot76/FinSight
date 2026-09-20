"""Benchmark legacy and SQL-backed FinSight analytics on synthetic data."""

import argparse
import gc
import hashlib
import sqlite3
import sys
import tempfile
import time
import tracemalloc
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import db, queries  # noqa: E402
from services import analytics_service  # noqa: E402


BUSINESS_ID = "benchmark-business"
REGISTRY_BUSINESS_ID = "benchmark-registry"
ACCOUNT_ID = "benchmark-account"
USER_ID = "benchmark-user"
ATTEMPT_ID = "benchmark-attempt"
SOURCE_SYSTEM = "finsight_demo_bank_statement_v1"
TOKEN = "benchmark-session-token"
START_DATE = "2026-01-01"
END_DATE = "2026-12-31"
CURRENCY = "INR"


def _create_database(database_path: Path) -> None:
    schema = (ROOT / "database" / "schema.sql").read_text(encoding="utf-8")
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(schema)
        connection.execute(
            """INSERT INTO users
               (user_id,username,email,contact_number,password_hash,role,account_status)
               VALUES (?, 'Benchmark User', 'benchmark@example.test', '9999999999',
                       'hash', 'standard_business', 'active')""",
            (USER_ID,),
        )
        connection.execute(
            """INSERT INTO auth_sessions
               (session_id,user_id,token_hash,expires_at)
               VALUES ('benchmark-session', ?, ?, ?)""",
            (
                USER_ID,
                hashlib.sha256(TOKEN.encode("utf-8")).hexdigest(),
                datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat(),
            ),
        )
        connection.execute(
            """INSERT INTO businesses
               (business_id,business_name,business_status)
               VALUES (?, 'Benchmark Business', 'active')""",
            (BUSINESS_ID,),
        )
        connection.execute(
            """INSERT INTO business_memberships
               (membership_id,business_id,user_id,membership_role,membership_status)
               VALUES ('benchmark-membership', ?, ?, 'owner', 'active')""",
            (BUSINESS_ID, USER_ID),
        )
        connection.execute(
            """INSERT INTO business_registry
               (business_id,user_id,business_name)
               VALUES (?, ?, 'Benchmark Registry')""",
            (REGISTRY_BUSINESS_ID, USER_ID),
        )
        connection.execute(
            """INSERT INTO financial_accounts
               (account_id,business_id,account_name,account_type,currency,
                opening_balance_minor,account_status)
               VALUES (?, ?, 'Benchmark Account', 'bank', ?, 1000000, 'active')""",
            (ACCOUNT_ID, BUSINESS_ID, CURRENCY),
        )
        connection.execute(
            """INSERT INTO ingestion_attempts
               (attempt_id,business_id,registry_business_id,account_id,
                uploader_user_id,source_system,contract_version,currency,
                record_count,inserted_count,attempt_status,completed_at)
               VALUES (?, ?, ?, ?, ?, ?, 'finsight_ingestion_v1', ?, 0, 0,
                       'completed', CURRENT_TIMESTAMP)""",
            (
                ATTEMPT_ID,
                BUSINESS_ID,
                REGISTRY_BUSINESS_ID,
                ACCOUNT_ID,
                USER_ID,
                SOURCE_SYSTEM,
                CURRENCY,
            ),
        )


def _seed_rows(database_path: Path, row_count: int, batch_size: int = 10000) -> None:
    start = date.fromisoformat(START_DATE)
    categories = ("Sales", "Rent", "Inventory", "Utilities", None)
    payment_modes = ("Cash", "UPI", "Card", "Bank", "Cheque")
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for batch_start in range(0, row_count, batch_size):
            batch_end = min(batch_start + batch_size, row_count)
            ledger_rows = []
            identity_rows = []
            for index in range(batch_start, batch_end):
                transaction_id = f"benchmark-transaction-{index:07d}"
                transaction_date = (start + timedelta(days=index % 365)).isoformat()
                amount_minor = (index % 100000) + 1
                direction = "income" if index % 3 == 0 else "expense"
                category = categories[index % len(categories)]
                payment_mode = payment_modes[index % len(payment_modes)]
                ledger_rows.append(
                    (
                        transaction_id,
                        REGISTRY_BUSINESS_ID,
                        USER_ID,
                        transaction_date,
                        amount_minor / 100,
                        direction,
                        category,
                        payment_mode,
                        "benchmark row",
                        f"benchmark-ledger-hash-{index}",
                    )
                )
                identity_rows.append(
                    (
                        f"benchmark-identity-{index:07d}",
                        transaction_id,
                        ATTEMPT_ID,
                        BUSINESS_ID,
                        REGISTRY_BUSINESS_ID,
                        ACCOUNT_ID,
                        SOURCE_SYSTEM,
                        f"BENCH-{index}",
                        transaction_date,
                        amount_minor,
                        direction,
                        CURRENCY,
                        f"benchmark-canonical-hash-{index}",
                    )
                )
            connection.executemany(
                """INSERT INTO transaction_general_ledger
                   (transaction_id,business_id,user_id,transaction_date,amount,
                    transaction_type,category,payment_mode,description,transaction_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ledger_rows,
            )
            connection.executemany(
                """INSERT INTO ingested_transaction_identities
                   (identity_id,transaction_id,attempt_id,business_id,
                    registry_business_id,account_id,source_system,
                    source_transaction_id,transaction_date,amount_minor,
                    direction,currency,canonical_identity_hash)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                identity_rows,
            )
        connection.execute(
            """UPDATE ingestion_attempts
               SET record_count=?, inserted_count=?
               WHERE attempt_id=?""",
            (row_count, row_count, ATTEMPT_ID),
        )
        connection.execute("ANALYZE")


def _legacy_path() -> dict[str, Any]:
    analytics_service._require_authorized_session(TOKEN, BUSINESS_ID)
    start_date, end_date = analytics_service._validate_date_range(
        START_DATE, END_DATE
    )
    account = analytics_service._load_account(ACCOUNT_ID, BUSINESS_ID, CURRENCY)
    rows = analytics_service._load_accepted_rows(
        business_id=BUSINESS_ID,
        account_id=ACCOUNT_ID,
        start_date=start_date,
        end_date=end_date,
    )
    if any(row["currency"] != CURRENCY for row in rows):
        raise analytics_service.AnalyticsError(
            "The selected analytics currency is inconsistent."
        )

    incomes = [row["amount_minor"] for row in rows if row["direction"] == "income"]
    expenses = [row["amount_minor"] for row in rows if row["direction"] == "expense"]
    total_income = sum(incomes)
    total_expense = sum(expenses)
    transaction_count = len(rows)
    opening_balance = account["opening_balance_minor"]
    return {
        "kpis": {
            "total_income_minor": total_income,
            "total_expense_minor": total_expense,
            "net_cash_flow_minor": total_income - total_expense,
            "transaction_count": transaction_count,
            "average_transaction_minor": (
                Decimal(total_income + total_expense) / Decimal(transaction_count)
                if transaction_count
                else Decimal("0")
            ),
            "largest_income_minor": max(incomes) if incomes else None,
            "smallest_income_minor": min(incomes) if incomes else None,
            "largest_expense_minor": max(expenses) if expenses else None,
            "smallest_expense_minor": min(expenses) if expenses else None,
            "opening_balance_minor": opening_balance,
            "closing_balance_minor": (
                opening_balance + total_income - total_expense
                if opening_balance is not None
                else None
            ),
            "income_expense_ratio": (
                Decimal(total_income) / Decimal(total_expense)
                if total_expense
                else None
            ),
            "savings_rate": analytics_service._percentage(
                total_income - total_expense, total_income
            ),
        },
        "trends": analytics_service._build_trends(rows),
        "categories": analytics_service._build_category_summary(rows),
        "payment_modes": analytics_service._build_payment_mode_summary(rows),
        "accounts": analytics_service._build_account_summary(
            ACCOUNT_ID, account, rows
        ),
        "transactions": analytics_service._build_transaction_rows(rows),
    }


def _new_path(include_transactions: bool) -> dict[str, Any]:
    return analytics_service.get_financial_analytics(
        session_token=TOKEN,
        business_id=BUSINESS_ID,
        account_id=ACCOUNT_ID,
        start_date=START_DATE,
        end_date=END_DATE,
        currency=CURRENCY,
        include_transactions=include_transactions,
    )


def _measure(function: Callable[[], Any]) -> tuple[float, float]:
    gc.collect()
    tracemalloc.start()
    started = time.perf_counter()
    result = function()
    elapsed_ms = (time.perf_counter() - started) * 1000
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del result
    return elapsed_ms, peak_bytes / (1024 * 1024)


def _query_plan() -> list[str]:
    connection = queries.get_connection()
    try:
        return [
            str(row[3])
            for row in connection.execute(
                "EXPLAIN QUERY PLAN " + analytics_service._KPI_SQL,
                (CURRENCY, BUSINESS_ID, ACCOUNT_ID, START_DATE, END_DATE),
            ).fetchall()
        ]
    finally:
        connection.close()


def _run_size(row_count: int) -> tuple[dict[str, Any], list[str]]:
    with tempfile.TemporaryDirectory(prefix="finsight-analytics-") as temp_directory:
        database_path = Path(temp_directory) / "benchmark.db"
        db.DATABASE_PATH = database_path
        _create_database(database_path)
        _seed_rows(database_path, row_count)

        _legacy_path()
        _new_path(False)
        _new_path(True)

        legacy_ms, legacy_peak = _measure(_legacy_path)
        sql_without_ms, sql_without_peak = _measure(lambda: _new_path(False))
        sql_with_ms, sql_with_peak = _measure(lambda: _new_path(True))
        result = {
            "rows": row_count,
            "legacy_ms": legacy_ms,
            "legacy_peak": legacy_peak,
            "sql_without_ms": sql_without_ms,
            "sql_without_peak": sql_without_peak,
            "sql_with_ms": sql_with_ms,
            "sql_with_peak": sql_with_peak,
            "database_mib": database_path.stat().st_size / (1024 * 1024),
        }
        return result, _query_plan()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--large",
        action="store_true",
        help="Also run the optional 1,000,000-row benchmark.",
    )
    args = parser.parse_args()
    sizes = [1000, 10000, 100000]
    if args.large:
        sizes.append(1000000)

    results = []
    plans = []
    for row_count in sizes:
        result, plan = _run_size(row_count)
        results.append(result)
        plans.append((row_count, plan))

    print(
        "| Rows | Legacy ms | Legacy peak MiB | SQL no transactions ms | "
        "SQL no transactions peak MiB | SQL with transactions ms | "
        "SQL with transactions peak MiB | DB MiB |"
    )
    print("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for result in results:
        print(
            f"| {result['rows']:,} | {result['legacy_ms']:.2f} | "
            f"{result['legacy_peak']:.2f} | {result['sql_without_ms']:.2f} | "
            f"{result['sql_without_peak']:.2f} | {result['sql_with_ms']:.2f} | "
            f"{result['sql_with_peak']:.2f} | {result['database_mib']:.2f} |"
        )

    print("\n## EXPLAIN QUERY PLAN")
    for row_count, plan in plans:
        print(f"\n### {row_count:,} rows")
        for line in plan:
            print(f"- `{line}`")


if __name__ == "__main__":
    main()
