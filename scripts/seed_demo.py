"""Create the isolated synthetic examination demo using FinSight services."""

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import db, queries
from services import (
    account_service,
    auth_service,
    bridge_service,
    business_service,
    csv_normalizer,
    ingestion_service,
)


OWNER_EMAIL = "owner@demo.finsight.local"
ADMIN_EMAIL = "admin@demo.finsight.local"
DEMO_PASSWORD = "FinSightDemo2026!"
BUSINESS_NAME = "FinSight Synthetic Store"
ACCOUNT_NAME = "Synthetic Current Account"
ALLOWED_EMAILS = {OWNER_EMAIL, ADMIN_EMAIL}


def _select(items, key, value):
    return next((item for item in items if item.get(key) == value), None)


def _assert_disposable_database() -> None:
    with db.get_connection() as connection:
        emails = {
            row["email"]
            for row in connection.execute("SELECT email FROM users").fetchall()
        }
    if emails - ALLOWED_EMAILS:
        raise RuntimeError(
            "Refusing to seed a database containing non-demo users. "
            "Use a new database or back up the existing one."
        )


def seed(database_path: Path) -> dict[str, int]:
    database_path = database_path.resolve()
    db.DATA_DIR = database_path.parent
    db.DATABASE_PATH = database_path
    db.initialize_database()
    _assert_disposable_database()

    owner = queries.get_user_by_email(OWNER_EMAIL)
    if owner is None:
        result = auth_service.signup(
            "Demo Owner", OWNER_EMAIL, "9999999991", DEMO_PASSWORD
        )
        if not result.get("success"):
            raise RuntimeError("Demo owner could not be created.")

    os.environ["FINSIGHT_ALLOW_DEMO_SEED"] = "1"
    try:
        result = auth_service.provision_demo_administrator(
            "Demo Administrator", ADMIN_EMAIL, "9999999992", DEMO_PASSWORD
        )
    finally:
        os.environ.pop("FINSIGHT_ALLOW_DEMO_SEED", None)
    if not result.get("success"):
        raise RuntimeError("Demo administrator could not be created.")

    owner_login = auth_service.login(OWNER_EMAIL, DEMO_PASSWORD)
    admin_login = auth_service.login(ADMIN_EMAIL, DEMO_PASSWORD)
    if not owner_login.get("success") or not admin_login.get("success"):
        raise RuntimeError("Demo sign-in could not be completed.")
    owner_token = owner_login["session"]["token"]
    admin_token = admin_login["session"]["token"]

    businesses = business_service.list_user_businesses(owner_token).get("businesses", [])
    business = _select(businesses, "business_name", BUSINESS_NAME)
    if business is None:
        result = business_service.create_business(
            owner_token, {"business_name": BUSINESS_NAME}
        )
        if not result.get("success"):
            raise RuntimeError("Demo business could not be created.")
        business = result["business"]

    accounts = account_service.list_business_accounts(
        owner_token, business["business_id"]
    ).get("accounts", [])
    account = _select(accounts, "account_name", ACCOUNT_NAME)
    if account is None:
        result = account_service.create_account(
            owner_token,
            business["business_id"],
            {
                "account_name": ACCOUNT_NAME,
                "account_type": "bank",
                "currency": "INR",
                "opening_balance": "10000.00",
            },
        )
        if not result.get("success"):
            raise RuntimeError("Demo financial account could not be created.")
        account = result["account"]

    bridge = bridge_service.get_bridge_status(
        owner_token, business["business_id"]
    ).get("bridge")
    if bridge is None:
        result = bridge_service.propose_bridge(owner_token, business["business_id"])
        if not result.get("success"):
            raise RuntimeError("Demo registry verification could not be requested.")
        bridge = result["bridge"]
    if bridge["bridge_status"] == "pending":
        result = bridge_service.approve_bridge(admin_token, bridge["bridge_id"])
        if not result.get("success"):
            raise RuntimeError("Demo registry verification could not be approved.")

    payload = csv_normalizer.normalize_csv(
        (PROJECT_ROOT / "sample_data" / "valid_transactions.csv").read_bytes()
    )
    ingestion = ingestion_service.ingest(
        session_token=owner_token,
        business_id=business["business_id"],
        account_id=account["account_id"],
        payload=payload,
        record_failure=True,
    )
    auth_service.logout(admin_token)
    auth_service.logout(owner_token)
    return {
        "records": ingestion.record_count,
        "inserted": ingestion.inserted_count,
        "duplicates": ingestion.duplicate_count,
        "rejected": ingestion.rejected_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "data" / "finsight.db",
        help="Disposable demo database path (default: data/finsight.db)",
    )
    args = parser.parse_args()
    try:
        counts = seed(args.database)
    except RuntimeError as error:
        print(f"Demo seed stopped: {error}")
        return 1
    print(
        "Demo seed complete: "
        f"records={counts['records']}, inserted={counts['inserted']}, "
        f"duplicates={counts['duplicates']}, rejected={counts['rejected']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
