import hashlib
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterator, Optional

from database.db import get_connection


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def normalize_text(value: Any) -> str:
    return "" if value is None else " ".join(str(value).strip().lower().split())


def normalize_amount(amount: Any) -> str:
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{value:.2f}"


def create_transaction_hash(business_id, entity_id, transaction_date, amount,
                            transaction_type, category, payment_mode, description, user_id):
    values = [business_id, entity_id, transaction_date, normalize_amount(amount),
              transaction_type, category, payment_mode, description, user_id]
    return hashlib.sha256("|".join(normalize_text(v) for v in values).encode()).hexdigest()


def create_user(email: str, contact_number: str, password_hash: Optional[str],
                secret_question: str = "", secret_answer_hash: str = "",
                username: Optional[str] = None, role: str = "standard_business") -> str:
    user_id = generate_id("usr")
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO users
               (user_id, username, email, contact_number, password_hash,
                secret_question, secret_answer_hash, role)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, (username or email.split("@", 1)[0]).strip(), email.strip().lower(),
             contact_number.strip(), password_hash, secret_question.strip(),
             secret_answer_hash, role),
        )
    return user_id


def get_user_by_email(email: str):
    with get_connection() as connection:
        return connection.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()


def get_user_by_id(user_id: str):
    with get_connection() as connection:
        return connection.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


def update_password_hash(user_id: str, password_hash: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (password_hash, user_id),
        )
    return cursor.rowcount == 1


def create_business(user_id: str, business_name: str, business_type=None, address=None) -> str:
    if get_user_by_id(user_id) is None:
        raise ValueError("User does not exist.")
    business_id = generate_id("biz")
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO business_registry
               (business_id,user_id,business_name,business_type,address) VALUES (?,?,?,?,?)""",
            (business_id, user_id, business_name.strip(),
             business_type.strip() if business_type else None, address.strip() if address else None),
        )
    return business_id


def get_business_by_id(business_id: str, user_id: Optional[str] = None):
    sql = "SELECT * FROM business_registry WHERE business_id = ?"
    params = (business_id,)
    if user_id is not None:
        sql += " AND user_id = ?"
        params += (user_id,)
    with get_connection() as connection:
        return connection.execute(sql, params).fetchone()


def get_user_businesses(user_id: str):
    with get_connection() as connection:
        return connection.execute("SELECT * FROM business_registry WHERE user_id=? ORDER BY business_name", (user_id,)).fetchall()


def create_counterparty(business_id: str, entity_name: str, entity_type: str,
                        contact_number=None, email=None) -> str:
    if get_business_by_id(business_id) is None:
        raise ValueError("Business does not exist.")
    entity_id = generate_id("ent")
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO counterparty_entities
               (entity_id,business_id,entity_name,entity_type,contact_number,email) VALUES (?,?,?,?,?,?)""",
            (entity_id, business_id, entity_name.strip(), entity_type.strip(), contact_number,
             email.strip().lower() if email else None),
        )
    return entity_id


def create_transaction(business_id: str, entity_id: Optional[str], user_id: str,
                       transaction_date: str, amount: Any, transaction_type: str,
                       category=None, payment_mode=None, description=None):
    if get_business_by_id(business_id, user_id) is None:
        raise PermissionError("Business does not belong to this user.")
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if value <= 0:
        raise ValueError("Transaction amount must be greater than zero.")
    if entity_id:
        with get_connection() as connection:
            entity = connection.execute(
                "SELECT 1 FROM counterparty_entities WHERE entity_id=? AND business_id=?",
                (entity_id, business_id),
            ).fetchone()
        if entity is None:
            raise ValueError("Counterparty does not belong to this business.")
    tx_hash = create_transaction_hash(business_id, entity_id, transaction_date, value,
                                      transaction_type, category, payment_mode, description, user_id)
    with get_connection() as connection:
        duplicate = connection.execute(
            "SELECT 1 FROM transaction_general_ledger WHERE transaction_hash=? AND business_id=? AND user_id=?",
            (tx_hash, business_id, user_id),
        ).fetchone() is not None
        transaction_id = generate_id("txn")
        connection.execute(
            """INSERT INTO transaction_general_ledger
               (transaction_id,business_id,entity_id,user_id,transaction_date,amount,
                transaction_type,category,payment_mode,description,transaction_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (transaction_id, business_id, entity_id, user_id, transaction_date, float(value),
             transaction_type.strip().lower(), category, payment_mode, description, tx_hash),
        )
    return {"transaction_id": transaction_id, "transaction_hash": tx_hash, "duplicate": duplicate}


def get_business_transactions(business_id: str, user_id: str):
    if get_business_by_id(business_id, user_id) is None:
        raise PermissionError("Business does not belong to this user.")
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM transaction_general_ledger WHERE business_id=? AND user_id=? ORDER BY transaction_date DESC, created_at DESC",
            (business_id, user_id),
        ).fetchall()


def get_financial_summary(business_id: str, user_id: str):
    if get_business_by_id(business_id, user_id) is None:
        raise PermissionError("Business does not belong to this user.")
    with get_connection() as connection:
        row = connection.execute(
            """SELECT COUNT(*) total_transactions,
               COALESCE(SUM(CASE WHEN LOWER(transaction_type)='income' THEN amount ELSE 0 END),0) total_income,
               COALESCE(SUM(CASE WHEN LOWER(transaction_type)='expense' THEN amount ELSE 0 END),0) total_expense
               FROM transaction_general_ledger WHERE business_id=? AND user_id=?""",
            (business_id, user_id),
        ).fetchone()
    income, expense = float(row["total_income"]), float(row["total_expense"])
    return {"total_transactions": row["total_transactions"], "total_income": income,
            "total_expense": expense, "net_cash_flow": income - expense}


def create_budget(business_id: str, category: str, allocated_amount: Any, user_id: str) -> str:
    if get_business_by_id(business_id, user_id) is None:
        raise PermissionError("Business does not belong to this user.")
    amount = Decimal(str(allocated_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount < 0:
        raise ValueError("Budget amount cannot be negative.")
    budget_id = generate_id("bud")
    with get_connection() as connection:
        connection.execute("INSERT INTO structural_budget_allocations VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
                           (budget_id, business_id, category.strip(), float(amount)))
    return budget_id


def get_business_budgets(business_id: str, user_id: str):
    if get_business_by_id(business_id, user_id) is None:
        raise PermissionError("Business does not belong to this user.")
    with get_connection() as connection:
        return connection.execute("SELECT * FROM structural_budget_allocations WHERE business_id=? ORDER BY category", (business_id,)).fetchall()


def get_budget_variance(business_id: str, user_id: str):
    if get_business_by_id(business_id, user_id) is None:
        raise PermissionError("Business does not belong to this user.")
    with get_connection() as connection:
        return connection.execute(
            """SELECT b.budget_id,b.category,b.allocated_amount,
               COALESCE(SUM(CASE WHEN LOWER(t.transaction_type)='expense' THEN t.amount ELSE 0 END),0) actual_spending,
               b.allocated_amount-COALESCE(SUM(CASE WHEN LOWER(t.transaction_type)='expense' THEN t.amount ELSE 0 END),0) variance
               FROM structural_budget_allocations b LEFT JOIN transaction_general_ledger t
               ON t.business_id=b.business_id AND LOWER(COALESCE(t.category,''))=LOWER(b.category) AND t.user_id=?
               WHERE b.business_id=? GROUP BY b.budget_id,b.category,b.allocated_amount ORDER BY b.category""",
            (user_id, business_id),
        ).fetchall()


def create_authentication_log(user_id: Optional[str], event_type: str,
                              ip_address=None, user_agent=None) -> str:
    log_id = generate_id("auth")
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO authentication_logs (authentication_log_id,user_id,event_type,ip_address,user_agent) VALUES (?,?,?,?,?)",
            (log_id, user_id, event_type.strip(), ip_address, user_agent),
        )
    return log_id


def create_session(user_id: str, token_hash: str, expires_at: str) -> str:
    session_id = generate_id("ses")
    with get_connection() as connection:
        connection.execute("INSERT INTO auth_sessions (session_id,user_id,token_hash,expires_at) VALUES (?,?,?,?)",
                           (session_id, user_id, token_hash, expires_at))
    return session_id


def get_active_session(token_hash: str):
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        return connection.execute(
            """SELECT s.*,u.username,u.email,u.role,u.account_status FROM auth_sessions s
               JOIN users u ON u.user_id=s.user_id
               WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>?""",
            (token_hash, now),
        ).fetchone()


def revoke_session(token_hash: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE auth_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
            (datetime.now(timezone.utc).isoformat(), token_hash),
        )
    return cursor.rowcount == 1


def get_provider_identity(provider: str, provider_subject: str):
    with get_connection() as connection:
        return connection.execute(
            """SELECT p.*,u.username,u.email,u.role,u.account_status FROM provider_identities p
               JOIN users u ON u.user_id=p.user_id WHERE p.provider=? AND p.provider_subject=?""",
            (provider, provider_subject),
        ).fetchone()


def create_provider_identity(user_id: str, provider: str, provider_subject: str,
                             provider_email: str) -> str:
    identity_id = generate_id("pid")
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO provider_identities (identity_id,user_id,provider,provider_subject,provider_email) VALUES (?,?,?,?,?)",
            (identity_id, user_id, provider, provider_subject, provider_email.lower()),
        )
    return identity_id


def create_document(user_id: str, file_name: str, file_type=None, file_path=None) -> str:
    if get_user_by_id(user_id) is None:
        raise ValueError("User does not exist.")
    document_id = generate_id("doc")
    with get_connection() as connection:
        connection.execute("INSERT INTO documents (document_id,user_id,file_name,file_type,file_path) VALUES (?,?,?,?,?)",
                           (document_id, user_id, file_name, file_type, file_path))
    return document_id


def get_user_documents(user_id: str):
    with get_connection() as connection:
        return connection.execute("SELECT * FROM documents WHERE user_id=? ORDER BY created_at DESC", (user_id,)).fetchall()


def get_document_by_id(document_id: str, user_id: str):
    with get_connection() as connection:
        return connection.execute("SELECT * FROM documents WHERE document_id=? AND user_id=?", (document_id, user_id)).fetchone()


def create_document_chunk(document_id: str, user_id: str, chunk_index: int, chunk_text: str) -> str:
    if get_document_by_id(document_id, user_id) is None:
        raise PermissionError("Document does not belong to this user.")
    chunk_id = generate_id("chk")
    with get_connection() as connection:
        connection.execute("INSERT INTO document_chunks (chunk_id,document_id,user_id,chunk_index,chunk_text) VALUES (?,?,?,?,?)",
                           (chunk_id, document_id, user_id, chunk_index, chunk_text))
    return chunk_id


def get_document_chunks(document_id: str, user_id: str):
    if get_document_by_id(document_id, user_id) is None:
        raise PermissionError("Document does not belong to this user.")
    with get_connection() as connection:
        return connection.execute("SELECT * FROM document_chunks WHERE document_id=? AND user_id=? ORDER BY chunk_index",
                                  (document_id, user_id)).fetchall()


# Module 2: business and membership queries

def create_business_with_owner(user_id: str, business_name: str,
                               legal_identifier: Optional[str] = None,
                               contact_email: Optional[str] = None,
                               contact_phone: Optional[str] = None) -> tuple[str, str]:
    """Atomically create a Module 2 business and its owner membership."""
    business_id = generate_id("biz")
    membership_id = generate_id("mem")
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO businesses
               (business_id,business_name,legal_identifier,contact_email,contact_phone)
               VALUES (?,?,?,?,?)""",
            (business_id, business_name, legal_identifier, contact_email, contact_phone),
        )
        connection.execute(
            """INSERT INTO business_memberships
               (membership_id,business_id,user_id,membership_role)
               VALUES (?,?,?,'owner')""",
            (membership_id, business_id, user_id),
        )
    return business_id, membership_id


def get_module2_business(business_id: str):
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM businesses WHERE business_id=?", (business_id,)
        ).fetchone()


def get_business_membership(business_id: str, user_id: str):
    with get_connection() as connection:
        return connection.execute(
            """SELECT m.*,b.business_name,b.business_status
               FROM business_memberships m JOIN businesses b ON b.business_id=m.business_id
               WHERE m.business_id=? AND m.user_id=?""",
            (business_id, user_id),
        ).fetchone()


def list_active_user_businesses(user_id: str):
    with get_connection() as connection:
        return connection.execute(
            """SELECT b.business_id,b.business_name,b.legal_identifier,b.contact_email,
                      b.contact_phone,b.business_status,b.created_at,b.updated_at,
                      m.membership_id,m.user_id,m.membership_role,m.membership_status,
                      m.created_at AS membership_created_at,
                      m.updated_at AS membership_updated_at
               FROM businesses b JOIN business_memberships m ON m.business_id=b.business_id
               WHERE m.user_id=? AND m.membership_status='active'
                 AND b.business_status='active' ORDER BY b.business_name""",
            (user_id,),
        ).fetchall()


def add_business_membership(business_id: str, user_id: str, membership_role: str) -> str:
    membership_id = generate_id("mem")
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO business_memberships
               (membership_id,business_id,user_id,membership_role)
               VALUES (?,?,?,?)""",
            (membership_id, business_id, user_id, membership_role),
        )
    return membership_id


def list_business_memberships(business_id: str):
    with get_connection() as connection:
        return connection.execute(
            """SELECT m.membership_id,m.business_id,m.user_id,m.membership_role,
                      m.membership_status,m.created_at,m.updated_at,u.username,u.email
               FROM business_memberships m JOIN users u ON u.user_id=m.user_id
               WHERE m.business_id=? ORDER BY u.username,u.email""",
            (business_id,),
        ).fetchall()


def disable_business_membership(membership_id: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """UPDATE business_memberships
               SET membership_status='disabled',updated_at=CURRENT_TIMESTAMP
               WHERE membership_id=? AND membership_status='active'""",
            (membership_id,),
        )
    return cursor.rowcount == 1


def set_module2_business_status(business_id: str, status: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE businesses SET business_status=?,updated_at=CURRENT_TIMESTAMP WHERE business_id=?",
            (status, business_id),
        )
    return cursor.rowcount == 1


def set_membership_status(membership_id: str, status: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """UPDATE business_memberships
               SET membership_status=?,updated_at=CURRENT_TIMESTAMP WHERE membership_id=?""",
            (status, membership_id),
        )
    return cursor.rowcount == 1


# Module 3: financial account queries

def create_financial_account(business_id: str, account_name: str, account_type: str,
                             institution_name: Optional[str], account_identifier: Optional[str],
                             currency: str, opening_balance_minor: int) -> str:
    account_id = generate_id("acc")
    with get_connection() as connection:
        connection.execute(
            """INSERT INTO financial_accounts
               (account_id,business_id,account_name,account_type,institution_name,
                account_identifier,currency,opening_balance_minor)
               VALUES (?,?,?,?,?,?,?,?)""",
            (account_id, business_id, account_name, account_type, institution_name,
             account_identifier, currency, opening_balance_minor),
        )
    return account_id


def get_financial_account(account_id: str):
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM financial_accounts WHERE account_id=?", (account_id,)
        ).fetchone()


def list_active_financial_accounts(business_id: str):
    with get_connection() as connection:
        return connection.execute(
            """SELECT * FROM financial_accounts
               WHERE business_id=? AND account_status='active'
               ORDER BY account_name,account_id""",
            (business_id,),
        ).fetchall()


def update_financial_account(account_id: str, account_name: str, account_type: str,
                             institution_name: Optional[str], account_identifier: Optional[str],
                             currency: str, opening_balance_minor: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """UPDATE financial_accounts
               SET account_name=?,account_type=?,institution_name=?,account_identifier=?,
                   currency=?,opening_balance_minor=?,updated_at=CURRENT_TIMESTAMP
               WHERE account_id=? AND account_status='active'""",
            (account_name, account_type, institution_name, account_identifier,
             currency, opening_balance_minor, account_id),
        )
    return cursor.rowcount == 1


def disable_financial_account(account_id: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute(
            """UPDATE financial_accounts
               SET account_status='disabled',updated_at=CURRENT_TIMESTAMP
               WHERE account_id=? AND account_status='active'""",
            (account_id,),
        )
    return cursor.rowcount == 1


# Module 4: ingestion repository queries

@contextmanager
def _module4_connection(connection: Optional[Any] = None) -> Iterator[Any]:
    """Yield a caller-owned connection or manage a repository connection.

    Callers coordinating multiple Module 4 writes must provide their own
    connection so that this layer never commits an individual operation out
    from under the caller's transaction.
    """
    if connection is not None:
        yield connection
        return

    owned_connection = get_connection()
    try:
        yield owned_connection
        owned_connection.commit()
    except Exception:
        owned_connection.rollback()
        raise
    finally:
        owned_connection.close()


@contextmanager
def module4_transaction() -> Iterator[Any]:
    """Open one caller-owned SQLite transaction for Module 4 operations."""
    connection = get_connection()
    try:
        connection.execute("BEGIN")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_active_business(business_id: str, connection: Optional[Any] = None):
    with _module4_connection(connection) as active_connection:
        return active_connection.execute(
            """SELECT * FROM businesses
               WHERE business_id=? AND business_status='active'""",
            (business_id,),
        ).fetchone()


def get_active_business_membership(
    business_id: str, user_id: str, connection: Optional[Any] = None
):
    with _module4_connection(connection) as active_connection:
        return active_connection.execute(
            """SELECT m.*,b.business_name,b.business_status
               FROM business_memberships m
               JOIN businesses b ON b.business_id=m.business_id
               WHERE m.business_id=? AND m.user_id=?
                 AND b.business_status='active'
                 AND m.membership_status='active'""",
            (business_id, user_id),
        ).fetchone()


def get_active_financial_account(
    account_id: str, business_id: str, connection: Optional[Any] = None
):
    with _module4_connection(connection) as active_connection:
        return active_connection.execute(
            """SELECT * FROM financial_accounts
               WHERE account_id=? AND business_id=?
                 AND account_status='active'""",
            (account_id, business_id),
        ).fetchone()


def get_active_bridge(business_id: str, connection: Optional[Any] = None):
    with _module4_connection(connection) as active_connection:
        return active_connection.execute(
            """SELECT * FROM business_registry_bridges
               WHERE business_id=? AND bridge_status='active'
                 AND verified_by_user_id IS NOT NULL
                 AND verified_at IS NOT NULL""",
            (business_id,),
        ).fetchone()


def get_business_bridge(business_id: str, connection: Optional[Any] = None):
    """Return the newest bridge proposal for a Module 2 business."""
    with _module4_connection(connection) as active_connection:
        return active_connection.execute(
            """SELECT bridge_id,business_id,registry_business_id,
                      proposed_by_user_id,verified_by_user_id,bridge_status,
                      proposed_at,verified_at,updated_at
               FROM business_registry_bridges
               WHERE business_id=?
               ORDER BY proposed_at DESC, bridge_id DESC LIMIT 1""",
            (business_id,),
        ).fetchone()


def get_bridge_by_id(bridge_id: str, connection: Optional[Any] = None):
    with _module4_connection(connection) as active_connection:
        return active_connection.execute(
            """SELECT bridge_id,business_id,registry_business_id,
                      proposed_by_user_id,verified_by_user_id,bridge_status,
                      proposed_at,verified_at,updated_at
               FROM business_registry_bridges WHERE bridge_id=?""",
            (bridge_id,),
        ).fetchone()


def create_registry_bridge_proposal(
    *,
    business_id: str,
    owner_user_id: str,
    business_name: str,
    connection: Optional[Any] = None,
) -> str:
    """Create a legacy registry record and pending bridge in one transaction."""
    bridge_id = generate_id("brg")
    registry_business_id = generate_id("rbiz")
    with _module4_connection(connection) as active_connection:
        active_connection.execute(
            """INSERT INTO business_registry
               (business_id,user_id,business_name)
               VALUES (?,?,?)""",
            (registry_business_id, owner_user_id, business_name),
        )
        active_connection.execute(
            """INSERT INTO business_registry_bridges
               (bridge_id,business_id,registry_business_id,proposed_by_user_id,
                bridge_status)
               VALUES (?,?,?,?,'pending')""",
            (bridge_id, business_id, registry_business_id, owner_user_id),
        )
    return bridge_id


def list_pending_bridges(connection: Optional[Any] = None):
    with _module4_connection(connection) as active_connection:
        return active_connection.execute(
            """SELECT br.bridge_id,br.business_id,br.registry_business_id,
                      br.proposed_by_user_id,br.verified_by_user_id,
                      br.bridge_status,br.proposed_at,br.verified_at,
                      br.updated_at,b.business_name
               FROM business_registry_bridges br
               JOIN businesses b ON b.business_id=br.business_id
               WHERE br.bridge_status='pending'
               ORDER BY br.proposed_at,br.bridge_id"""
        ).fetchall()


def activate_registry_bridge(
    bridge_id: str,
    verifier_user_id: str,
    connection: Optional[Any] = None,
) -> bool:
    """Activate a pending bridge only when verifier and proposer differ."""
    with _module4_connection(connection) as active_connection:
        cursor = active_connection.execute(
            """UPDATE business_registry_bridges
               SET verified_by_user_id=?,bridge_status='active',
                   verified_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
               WHERE bridge_id=? AND bridge_status='pending'
                 AND proposed_by_user_id<>?""",
            (verifier_user_id, bridge_id, verifier_user_id),
        )
    return cursor.rowcount == 1


def get_registry_business(registry_business_id: str, connection: Optional[Any] = None):
    with _module4_connection(connection) as active_connection:
        return active_connection.execute(
            "SELECT * FROM business_registry WHERE business_id=?",
            (registry_business_id,),
        ).fetchone()


def get_registry_owner(
    registry_business_id: str, connection: Optional[Any] = None
) -> Optional[str]:
    with _module4_connection(connection) as active_connection:
        row = active_connection.execute(
            "SELECT user_id FROM business_registry WHERE business_id=?",
            (registry_business_id,),
        ).fetchone()
    return None if row is None else row["user_id"]


def create_ingestion_attempt(
    *,
    business_id: str,
    registry_business_id: str,
    account_id: str,
    uploader_user_id: str,
    source_system: str,
    contract_version: str,
    currency: str,
    record_count: int,
    parent_attempt_id: Optional[str] = None,
    connection: Optional[Any] = None,
) -> str:
    attempt_id = generate_id("att")
    with _module4_connection(connection) as active_connection:
        active_connection.execute(
            """INSERT INTO ingestion_attempts
               (attempt_id,parent_attempt_id,business_id,registry_business_id,
                account_id,uploader_user_id,source_system,contract_version,
                currency,record_count,attempt_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,'processing')""",
            (
                attempt_id,
                parent_attempt_id,
                business_id,
                registry_business_id,
                account_id,
                uploader_user_id,
                source_system,
                contract_version,
                currency,
                record_count,
            ),
        )
    return attempt_id


def get_ingestion_attempt(attempt_id: str, connection: Optional[Any] = None):
    """Return one ingestion attempt without changing caller transaction state."""
    with _module4_connection(connection) as active_connection:
        return active_connection.execute(
            "SELECT * FROM ingestion_attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()


def complete_ingestion_attempt(
    attempt_id: str,
    *,
    inserted_count: int,
    duplicate_count: int,
    rejected_count: int,
    connection: Optional[Any] = None,
) -> bool:
    with _module4_connection(connection) as active_connection:
        cursor = active_connection.execute(
            """UPDATE ingestion_attempts
               SET inserted_count=?,duplicate_count=?,rejected_count=?,
                   attempt_status='completed',public_error_code=NULL,
                   public_error_message=NULL,completed_at=CURRENT_TIMESTAMP
               WHERE attempt_id=? AND attempt_status='processing'""",
            (
                inserted_count,
                duplicate_count,
                rejected_count,
                attempt_id,
            ),
        )
    return cursor.rowcount == 1


def fail_ingestion_attempt(
    attempt_id: str,
    *,
    inserted_count: int,
    duplicate_count: int,
    rejected_count: int,
    public_error_code: str,
    public_error_message: str,
    connection: Optional[Any] = None,
) -> bool:
    with _module4_connection(connection) as active_connection:
        cursor = active_connection.execute(
            """UPDATE ingestion_attempts
               SET inserted_count=?,duplicate_count=?,rejected_count=?,
                   attempt_status='failed',public_error_code=?,
                   public_error_message=?,completed_at=CURRENT_TIMESTAMP
               WHERE attempt_id=? AND attempt_status='processing'""",
            (
                inserted_count,
                duplicate_count,
                rejected_count,
                public_error_code,
                public_error_message,
                attempt_id,
            ),
        )
    return cursor.rowcount == 1


def find_identity_by_hash(
    *,
    business_id: str,
    registry_business_id: str,
    account_id: str,
    source_system: str,
    canonical_identity_hash: str,
    connection: Optional[Any] = None,
):
    with _module4_connection(connection) as active_connection:
        return active_connection.execute(
            """SELECT * FROM ingested_transaction_identities
               WHERE business_id=? AND registry_business_id=?
                 AND account_id=? AND source_system=?
                 AND canonical_identity_hash=?""",
            (
                business_id,
                registry_business_id,
                account_id,
                source_system,
                canonical_identity_hash,
            ),
        ).fetchone()


def find_identity_by_source(
    *,
    business_id: str,
    registry_business_id: str,
    account_id: str,
    source_system: str,
    source_transaction_id: Optional[str],
    connection: Optional[Any] = None,
):
    if source_transaction_id is None:
        return None
    with _module4_connection(connection) as active_connection:
        return active_connection.execute(
            """SELECT * FROM ingested_transaction_identities
               WHERE business_id=? AND registry_business_id=?
                 AND account_id=? AND source_system=?
                 AND source_transaction_id=?""",
            (
                business_id,
                registry_business_id,
                account_id,
                source_system,
                source_transaction_id,
            ),
        ).fetchone()


def insert_ledger_transaction(
    *,
    registry_business_id: str,
    legacy_owner_user_id: str,
    transaction_date: str,
    amount: Any,
    transaction_type: str,
    transaction_hash: str,
    entity_id: Optional[str] = None,
    category: Optional[str] = None,
    payment_mode: Optional[str] = None,
    description: Optional[str] = None,
    connection: Optional[Any] = None,
) -> str:
    transaction_id = generate_id("txn")
    with _module4_connection(connection) as active_connection:
        active_connection.execute(
            """INSERT INTO transaction_general_ledger
               (transaction_id,business_id,entity_id,user_id,transaction_date,
                amount,transaction_type,category,payment_mode,description,
                transaction_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                transaction_id,
                registry_business_id,
                entity_id,
                legacy_owner_user_id,
                transaction_date,
                amount,
                transaction_type,
                category,
                payment_mode,
                description,
                transaction_hash,
            ),
        )
    return transaction_id


def insert_transaction_identity(
    *,
    transaction_id: str,
    attempt_id: str,
    business_id: str,
    registry_business_id: str,
    account_id: str,
    source_system: str,
    source_transaction_id: Optional[str],
    transaction_date: str,
    amount_minor: int,
    direction: str,
    currency: str,
    canonical_identity_hash: str,
    connection: Optional[Any] = None,
) -> str:
    identity_id = generate_id("iti")
    with _module4_connection(connection) as active_connection:
        active_connection.execute(
            """INSERT INTO ingested_transaction_identities
               (identity_id,transaction_id,attempt_id,business_id,
                registry_business_id,account_id,source_system,
                source_transaction_id,transaction_date,amount_minor,
                direction,currency,canonical_identity_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                identity_id,
                transaction_id,
                attempt_id,
                business_id,
                registry_business_id,
                account_id,
                source_system,
                source_transaction_id,
                transaction_date,
                amount_minor,
                direction,
                currency,
                canonical_identity_hash,
            ),
        )
    return identity_id
