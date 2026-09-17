"""Local administrator-role management for a self-hosted FinSight instance."""

import argparse
import os
import secrets

from database import db


def set_administrator(email: str, bootstrap_secret: str) -> bool:
    expected = os.getenv("FINSIGHT_ADMIN_BOOTSTRAP_SECRET", "")
    if len(expected) < 24 or not secrets.compare_digest(expected, bootstrap_secret):
        raise PermissionError("Administrator bootstrap authorization failed.")
    db.initialize_database()
    with db.get_connection() as connection:
        existing = connection.execute(
            """SELECT 1 FROM users
               WHERE role='administrator' AND account_status='active' LIMIT 1"""
        ).fetchone()
        if existing is not None:
            raise PermissionError(
                "An active administrator already exists. Bootstrap can run only once."
            )
        cursor = connection.execute(
            """UPDATE users SET role='administrator',updated_at=CURRENT_TIMESTAMP
               WHERE email=? COLLATE NOCASE AND account_status='active'""",
            (email.strip(),),
        )
    return cursor.rowcount == 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote an existing FinSight user.")
    parser.add_argument("email", help="Email of an existing active user")
    parser.add_argument(
        "--secret",
        default=os.getenv("FINSIGHT_ADMIN_BOOTSTRAP_SECRET_INPUT", ""),
        help="One-time bootstrap secret (prefer the input environment variable)",
    )
    args = parser.parse_args()
    try:
        if set_administrator(args.email, args.secret):
            print("Administrator access granted. Remove both bootstrap environment variables now.")
            return 0
    except PermissionError as error:
        print(str(error))
        return 2
    print("No active FinSight user was found with that email.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
