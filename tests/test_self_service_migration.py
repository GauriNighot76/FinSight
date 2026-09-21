"""Compatibility upgrades must preserve identity, restrictions, and financial rows."""
import sqlite3

import pytest

from database import db, queries
from services import auth_service, business_service, bridge_service


@pytest.fixture
def existing_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DATABASE_PATH", tmp_path / "copy.db")
    monkeypatch.setattr(queries, "get_connection", db.get_connection)
    db.initialize_database()
    # Synthetic copy-shaped database only; no user database is opened.
    with db.get_connection() as c:
        c.execute("INSERT INTO users(user_id,username,email,contact_number) VALUES ('owner','Owner','o@example.test','9999999999')")
        for name in ('pending', 'missing', 'active', 'rejected', 'disabled', 'wrong_owner', 'ambiguous'):
            c.execute("INSERT INTO businesses(business_id,business_name) VALUES (?,?)", (name, 'Same Name'))
            c.execute("INSERT INTO business_memberships(membership_id,business_id,user_id,membership_role) VALUES (?,?,'owner','owner')", (name, name))
            if name == 'missing':
                continue
            c.execute("INSERT INTO business_registry(business_id,user_id,business_name) VALUES (?,'owner',?)", (name, name))
            status = name if name in ('pending', 'active', 'rejected', 'disabled') else 'pending'
            c.execute("""INSERT INTO business_registry_bridges(bridge_id,business_id,registry_business_id,
                         proposed_by_user_id,verified_by_user_id,bridge_status,verified_at)
                         VALUES (?,?,?,'owner','owner',?,'2026-01-01')""", (name, name, name, status))
        c.execute("INSERT INTO users(user_id,username,email,contact_number) VALUES ('other','Other','b@example.test','9999999998')")
        c.execute("UPDATE business_registry SET user_id='other' WHERE business_id='wrong_owner'")
        c.execute("INSERT INTO business_memberships(membership_id,business_id,user_id,membership_role) VALUES ('other','ambiguous','other','owner')")
        c.execute("""INSERT INTO transaction_general_ledger(transaction_id,business_id,user_id,transaction_date,amount,transaction_type,transaction_hash)
                     VALUES ('existing','pending','owner','2026-01-01',123.45,'income','existing-hash')""")
    return db.get_connection


def snapshot(connection_factory):
    with connection_factory() as c:
        return {table: [tuple(row) for row in c.execute(f'SELECT * FROM {table} ORDER BY 1')]
                for table in ('businesses', 'business_memberships', 'business_registry', 'business_registry_bridges', 'transaction_general_ledger')}


def test_backfill_preserves_rows_restrictions_and_is_idempotent(existing_db):
    before = snapshot(existing_db)
    db.initialize_database()
    after = snapshot(existing_db)
    assert before['transaction_general_ledger'] == after['transaction_general_ledger']
    assert before['business_memberships'] == after['business_memberships']
    assert len(after['business_registry']) == len(before['business_registry']) + 1
    with existing_db() as c:
        statuses = dict(c.execute('SELECT business_id,bridge_status FROM business_registry_bridges'))
    assert statuses == {'pending': 'active', 'missing': 'active', 'active': 'active',
                        'rejected': 'rejected', 'disabled': 'disabled', 'wrong_owner': 'pending', 'ambiguous': 'pending'}
    assert queries.get_active_bridge('pending')['registry_business_id'] == 'pending'
    db.initialize_database()
    assert snapshot(existing_db) == after


def test_backfill_rolls_back_all_mapping_changes(existing_db):
    with existing_db() as c:
        c.execute("""CREATE TRIGGER reject_mapping BEFORE INSERT ON business_registry_bridges
                     BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
    before = snapshot(existing_db)
    with pytest.raises(sqlite3.IntegrityError):
        db.initialize_database()
    assert snapshot(existing_db) == before


@pytest.mark.parametrize('table', ['business_registry', 'business_registry_bridges'])
def test_new_business_rolls_back_when_mapping_creation_fails(isolated_test_database, table):
    with isolated_test_database() as c:
        c.execute("INSERT INTO users(user_id,username,email,contact_number) VALUES ('owner','Owner','o@example.test','9999999999')")
        c.execute(f"CREATE TRIGGER reject_write BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT, 'injected'); END")
    with pytest.raises(sqlite3.IntegrityError):
        queries.create_business_with_owner('owner', 'ABC Traders')
    with isolated_test_database() as c:
        for name in ('businesses', 'business_memberships', 'business_registry', 'business_registry_bridges'):
            assert c.execute(f'SELECT COUNT(*) FROM {name}').fetchone()[0] == 0


def test_same_business_name_does_not_reuse_registry_or_invent_type(isolated_test_database):
    with isolated_test_database() as c:
        c.execute("INSERT INTO users(user_id,username,email,contact_number) VALUES ('owner','Owner','o@example.test','9999999999')")
    first, _ = queries.create_business_with_owner('owner', 'ABC Traders')
    second, _ = queries.create_business_with_owner('owner', 'ABC Traders')
    assert queries.get_active_bridge(first)['registry_business_id'] != queries.get_active_bridge(second)['registry_business_id']
    with isolated_test_database() as c:
        assert all(row[0] is None for row in c.execute('SELECT business_type FROM business_registry'))


@pytest.mark.parametrize('status', ['rejected', 'disabled'])
def test_owner_cannot_bypass_restricted_history(existing_db, status):
    token = auth_service.create_session('owner')['token']
    result = bridge_service.propose_bridge(token, status)
    assert result['error'] == 'BRIDGE_ALREADY_EXISTS'
    assert queries.get_business_bridge(status)['bridge_status'] == status
