import sqlite3

import pytest

from database import db


def test_schema_tables_exist(isolated_test_database):
    with isolated_test_database() as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert {"users", "business_registry", "authentication_logs",
                "auth_sessions", "provider_identities", "businesses",
                "business_memberships", "financial_accounts"} <= tables


def test_foreign_keys_enabled(isolated_test_database):
    with isolated_test_database() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_existing_module0_users_table_is_migrated(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.db"
    with sqlite3.connect(legacy_path) as connection:
        connection.execute(
            """CREATE TABLE users (
               user_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE,
               contact_number TEXT NOT NULL, password_hash TEXT NOT NULL,
               secret_question TEXT NOT NULL, secret_answer_hash TEXT NOT NULL,
               created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"""
        )
    monkeypatch.setattr(db, "DATABASE_PATH", legacy_path)
    db.initialize_database()
    with sqlite3.connect(legacy_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    assert {"username", "role", "account_status", "updated_at"} <= columns


def test_module2_migration_preserves_existing_module1_data(tmp_path, monkeypatch):
    existing_path = tmp_path / "module1.db"
    monkeypatch.setattr(db, "DATABASE_PATH", existing_path)
    db.initialize_database()
    with sqlite3.connect(existing_path) as connection:
        connection.execute(
            """INSERT INTO users
               (user_id,username,email,contact_number,password_hash,role,account_status)
               VALUES ('usr_existing','Existing','existing@example.com','9999999999',
                       'hash','standard_business','active')"""
        )
        connection.execute(
            """INSERT INTO auth_sessions
               (session_id,user_id,token_hash,expires_at)
               VALUES ('ses_existing','usr_existing','token-hash','2999-01-01T00:00:00+00:00')"""
        )
        connection.execute(
            """INSERT INTO business_registry
               (business_id,user_id,business_name) VALUES
               ('legacy_biz','usr_existing','Legacy Business')"""
        )
        connection.execute(
            """INSERT INTO transaction_general_ledger
               (transaction_id,business_id,user_id,transaction_date,amount,
                transaction_type,transaction_hash)
               VALUES ('legacy_tx','legacy_biz','usr_existing','2026-01-01',100,
                       'income','legacy-hash')"""
        )
    db.initialize_database()
    with sqlite3.connect(existing_path) as connection:
        assert connection.execute(
            "SELECT email FROM users WHERE user_id='usr_existing'"
        ).fetchone()[0] == "existing@example.com"
        assert connection.execute(
            "SELECT session_id FROM auth_sessions WHERE user_id='usr_existing'"
        ).fetchone()[0] == "ses_existing"
        assert connection.execute(
            "SELECT amount FROM transaction_general_ledger WHERE transaction_id='legacy_tx'"
        ).fetchone()[0] == 100
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert {"businesses", "business_memberships"} <= tables


def test_membership_foreign_keys_and_unique_pair(isolated_test_database):
    with isolated_test_database() as connection:
        connection.execute(
            """INSERT INTO users
               (user_id,username,email,contact_number,password_hash)
               VALUES ('usr_1','One','one@example.com','9999999999','hash')"""
        )
        connection.execute(
            "INSERT INTO businesses (business_id,business_name) VALUES ('biz_1','One Business')"
        )
        connection.execute(
            """INSERT INTO business_memberships
               (membership_id,business_id,user_id,membership_role)
               VALUES ('mem_1','biz_1','usr_1','owner')"""
        )
        try:
            connection.execute(
                """INSERT INTO business_memberships
                   (membership_id,business_id,user_id,membership_role)
                   VALUES ('mem_2','biz_1','usr_1','viewer')"""
            )
            duplicate_rejected = False
        except sqlite3.IntegrityError:
            duplicate_rejected = True
        try:
            connection.execute(
                """INSERT INTO business_memberships
                   (membership_id,business_id,user_id,membership_role)
                   VALUES ('mem_3','missing','usr_1','viewer')"""
            )
            orphan_rejected = False
        except sqlite3.IntegrityError:
            orphan_rejected = True
    assert duplicate_rejected and orphan_rejected


def test_module3_account_schema_constraints_and_foreign_key(isolated_test_database):
    with isolated_test_database() as connection:
        connection.execute(
            "INSERT INTO businesses (business_id,business_name) VALUES ('biz_1','Business')"
        )
        connection.execute(
            """INSERT INTO financial_accounts
               (account_id,business_id,account_name,account_type,currency,opening_balance_minor)
               VALUES ('acc_1','biz_1','Cash Drawer','cash','INR',1050075)"""
        )
        assert connection.execute(
            "SELECT opening_balance_minor FROM financial_accounts WHERE account_id='acc_1'"
        ).fetchone()[0] == 1050075
        for sql in (
            """INSERT INTO financial_accounts
               (account_id,business_id,account_name,account_type,currency)
               VALUES ('bad_type','biz_1','Bad','crypto','INR')""",
            """INSERT INTO financial_accounts
               (account_id,business_id,account_name,account_type,currency)
               VALUES ('bad_currency','biz_1','Bad','cash','inr')""",
            """INSERT INTO financial_accounts
               (account_id,business_id,account_name,account_type,currency)
               VALUES ('orphan','missing','Bad','cash','INR')""",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(sql)


def test_module3_migration_preserves_existing_data(tmp_path, monkeypatch):
    path = tmp_path / "module2.db"
    monkeypatch.setattr(db, "DATABASE_PATH", path)
    db.initialize_database()
    with sqlite3.connect(path) as connection:
        connection.execute(
            """INSERT INTO users
               (user_id,username,email,contact_number,password_hash)
               VALUES ('usr_keep','Keep','keep@example.com','9999999999','hash')"""
        )
        connection.execute(
            "INSERT INTO businesses (business_id,business_name) VALUES ('biz_keep','Keep Business')"
        )
        connection.execute(
            """INSERT INTO business_memberships
               (membership_id,business_id,user_id,membership_role)
               VALUES ('mem_keep','biz_keep','usr_keep','owner')"""
        )
    db.initialize_database()
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT business_name FROM businesses WHERE business_id='biz_keep'"
        ).fetchone()[0] == "Keep Business"
        assert connection.execute(
            "SELECT membership_role FROM business_memberships WHERE membership_id='mem_keep'"
        ).fetchone()[0] == "owner"
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='financial_accounts'"
        ).fetchone()[0] == "financial_accounts"
