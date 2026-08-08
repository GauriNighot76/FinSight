import hashlib
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from database.db import get_connection


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def generate_id(prefix: str) -> str:
    """Generate a unique ID."""
    return f"{prefix}_{uuid.uuid4().hex}"


def normalize_text(value: Any) -> str:
    """Normalize text for consistent hashing."""
    if value is None:
        return ""

    return " ".join(
        str(value).strip().lower().split()
    )


def normalize_amount(amount: Any) -> str:
    """Normalize an amount to two decimal places."""
    decimal_amount = Decimal(
        str(amount)
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return f"{decimal_amount:.2f}"


def decimal_to_float(amount: Decimal) -> float:
    """
    Convert Decimal to float before sending
    the value to SQLite.
    """
    return float(amount)


def create_transaction_hash(
    business_id: str,
    entity_id: Optional[str],
    transaction_date: str,
    amount: Any,
    transaction_type: str,
    category: Optional[str],
    payment_mode: Optional[str],
    description: Optional[str],
    user_id: str,
) -> str:
    """Create a SHA-256 hash for duplicate detection."""

    values = [
        normalize_text(business_id),
        normalize_text(entity_id),
        normalize_text(transaction_date),
        normalize_amount(amount),
        normalize_text(transaction_type),
        normalize_text(category),
        normalize_text(payment_mode),
        normalize_text(description),
        normalize_text(user_id),
    ]

    raw_value = "|".join(values)

    return hashlib.sha256(
        raw_value.encode("utf-8")
    ).hexdigest()


# ============================================================
# USER QUERIES
# ============================================================

def create_user(
    email: str,
    contact_number: str,
    password_hash: str,
    secret_question: str,
    secret_answer_hash: str,
) -> str:
    """Create a new user."""

    user_id = generate_id("usr")

    query = """
        INSERT INTO users (
            user_id,
            email,
            contact_number,
            password_hash,
            secret_question,
            secret_answer_hash
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """

    with get_connection() as connection:
        connection.execute(
            query,
            (
                user_id,
                email.strip().lower(),
                contact_number.strip(),
                password_hash,
                secret_question.strip(),
                secret_answer_hash,
            ),
        )

    return user_id


def get_user_by_email(
    email: str,
):
    """Get a user by email."""

    query = """
        SELECT *
        FROM users
        WHERE email = ?
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (email.strip().lower(),),
        ).fetchone()


def get_user_by_id(
    user_id: str,
):
    """Get a user by ID."""

    query = """
        SELECT *
        FROM users
        WHERE user_id = ?
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (user_id,),
        ).fetchone()


def update_password_hash(
    user_id: str,
    password_hash: str,
) -> bool:
    """Update a user's password hash."""

    query = """
        UPDATE users
        SET password_hash = ?
        WHERE user_id = ?
    """

    with get_connection() as connection:
        cursor = connection.execute(
            query,
            (
                password_hash,
                user_id,
            ),
        )

    return cursor.rowcount == 1


# ============================================================
# BUSINESS QUERIES
# ============================================================

def create_business(
    user_id: str,
    business_name: str,
    business_type: Optional[str] = None,
    address: Optional[str] = None,
) -> str:
    """Create a business owned by a user."""

    user = get_user_by_id(user_id)

    if user is None:
        raise ValueError("User does not exist.")

    business_id = generate_id("biz")

    query = """
        INSERT INTO business_registry (
            business_id,
            user_id,
            business_name,
            business_type,
            address
        )
        VALUES (?, ?, ?, ?, ?)
    """

    with get_connection() as connection:
        connection.execute(
            query,
            (
                business_id,
                user_id,
                business_name.strip(),
                business_type.strip()
                if business_type
                else None,
                address.strip()
                if address
                else None,
            ),
        )

    return business_id


def get_business_by_id(
    business_id: str,
    user_id: Optional[str] = None,
):
    """Get a business, optionally checking ownership."""

    if user_id is not None:
        query = """
            SELECT *
            FROM business_registry
            WHERE business_id = ?
              AND user_id = ?
        """

        parameters = (
            business_id,
            user_id,
        )

    else:
        query = """
            SELECT *
            FROM business_registry
            WHERE business_id = ?
        """

        parameters = (
            business_id,
        )

    with get_connection() as connection:
        return connection.execute(
            query,
            parameters,
        ).fetchone()


def get_user_businesses(
    user_id: str,
):
    """Get all businesses owned by a user."""

    query = """
        SELECT *
        FROM business_registry
        WHERE user_id = ?
        ORDER BY business_name
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (user_id,),
        ).fetchall()


def update_business(
    business_id: str,
    user_id: str,
    business_name: str,
    business_type: Optional[str] = None,
    address: Optional[str] = None,
) -> bool:
    """Update a business owned by the user."""

    query = """
        UPDATE business_registry
        SET business_name = ?,
            business_type = ?,
            address = ?
        WHERE business_id = ?
          AND user_id = ?
    """

    with get_connection() as connection:
        cursor = connection.execute(
            query,
            (
                business_name.strip(),
                business_type.strip()
                if business_type
                else None,
                address.strip()
                if address
                else None,
                business_id,
                user_id,
            ),
        )

    return cursor.rowcount == 1


def delete_business(
    business_id: str,
    user_id: str,
) -> bool:
    """Delete a business owned by the user."""

    query = """
        DELETE FROM business_registry
        WHERE business_id = ?
          AND user_id = ?
    """

    with get_connection() as connection:
        cursor = connection.execute(
            query,
            (
                business_id,
                user_id,
            ),
        )

    return cursor.rowcount == 1


# ============================================================
# COUNTERPARTY QUERIES
# ============================================================

def create_counterparty(
    business_id: str,
    entity_name: str,
    entity_type: str,
    contact_number: Optional[str] = None,
    email: Optional[str] = None,
) -> str:
    """Create a customer, supplier, or vendor."""

    business = get_business_by_id(business_id)

    if business is None:
        raise ValueError("Business does not exist.")

    entity_id = generate_id("ent")

    query = """
        INSERT INTO counterparty_entities (
            entity_id,
            business_id,
            entity_name,
            entity_type,
            contact_number,
            email
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """

    with get_connection() as connection:
        connection.execute(
            query,
            (
                entity_id,
                business_id,
                entity_name.strip(),
                entity_type.strip(),
                contact_number.strip()
                if contact_number
                else None,
                email.strip().lower()
                if email
                else None,
            ),
        )

    return entity_id


def get_business_counterparties(
    business_id: str,
    user_id: str,
):
    """Get counterparties for a user's business."""

    business = get_business_by_id(
        business_id,
        user_id,
    )

    if business is None:
        raise PermissionError(
            "Business does not belong to this user."
        )

    query = """
        SELECT *
        FROM counterparty_entities
        WHERE business_id = ?
        ORDER BY entity_name
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (business_id,),
        ).fetchall()


def get_counterparty_by_id(
    entity_id: str,
    user_id: str,
):
    """Get a counterparty only if it belongs to the user's business."""

    query = """
        SELECT ce.*
        FROM counterparty_entities AS ce
        INNER JOIN business_registry AS br
            ON ce.business_id = br.business_id
        WHERE ce.entity_id = ?
          AND br.user_id = ?
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (
                entity_id,
                user_id,
            ),
        ).fetchone()


def update_counterparty(
    entity_id: str,
    user_id: str,
    entity_name: str,
    entity_type: str,
    contact_number: Optional[str] = None,
    email: Optional[str] = None,
) -> bool:
    """Update a counterparty owned by the user's business."""

    query = """
        UPDATE counterparty_entities
        SET entity_name = ?,
            entity_type = ?,
            contact_number = ?,
            email = ?
        WHERE entity_id = ?
          AND business_id IN (
              SELECT business_id
              FROM business_registry
              WHERE user_id = ?
          )
    """

    with get_connection() as connection:
        cursor = connection.execute(
            query,
            (
                entity_name.strip(),
                entity_type.strip(),
                contact_number.strip()
                if contact_number
                else None,
                email.strip().lower()
                if email
                else None,
                entity_id,
                user_id,
            ),
        )

    return cursor.rowcount == 1


def delete_counterparty(
    entity_id: str,
    user_id: str,
) -> bool:
    """Delete a counterparty owned by the user's business."""

    query = """
        DELETE FROM counterparty_entities
        WHERE entity_id = ?
          AND business_id IN (
              SELECT business_id
              FROM business_registry
              WHERE user_id = ?
          )
    """

    with get_connection() as connection:
        cursor = connection.execute(
            query,
            (
                entity_id,
                user_id,
            ),
        )

    return cursor.rowcount == 1


# ============================================================
# TRANSACTION QUERIES
# ============================================================

def find_transaction_by_hash(
    transaction_hash: str,
    business_id: str,
    user_id: str,
):
    """Find an existing transaction with the same hash."""

    query = """
        SELECT *
        FROM transaction_general_ledger
        WHERE transaction_hash = ?
          AND business_id = ?
          AND user_id = ?
        LIMIT 1
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (
                transaction_hash,
                business_id,
                user_id,
            ),
        ).fetchone()


def create_transaction(
    business_id: str,
    entity_id: Optional[str],
    user_id: str,
    transaction_date: str,
    amount: Any,
    transaction_type: str,
    category: Optional[str] = None,
    payment_mode: Optional[str] = None,
    description: Optional[str] = None,
):
    """
    Create a transaction.

    Duplicate transactions are allowed,
    but duplicate=True is returned if a matching
    transaction already exists.
    """

    business = get_business_by_id(
        business_id,
        user_id,
    )

    if business is None:
        raise PermissionError(
            "Business does not belong to this user."
        )

    if entity_id is not None:

        query = """
            SELECT entity_id
            FROM counterparty_entities
            WHERE entity_id = ?
              AND business_id = ?
        """

        with get_connection() as connection:
            entity = connection.execute(
                query,
                (
                    entity_id,
                    business_id,
                ),
            ).fetchone()

        if entity is None:
            raise ValueError(
                "Counterparty does not belong to this business."
            )

    normalized_amount = Decimal(
        str(amount)
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    if normalized_amount <= 0:
        raise ValueError(
            "Transaction amount must be greater than zero."
        )

    transaction_hash = create_transaction_hash(
        business_id=business_id,
        entity_id=entity_id,
        transaction_date=transaction_date,
        amount=normalized_amount,
        transaction_type=transaction_type,
        category=category,
        payment_mode=payment_mode,
        description=description,
        user_id=user_id,
    )

    existing_transaction = find_transaction_by_hash(
        transaction_hash=transaction_hash,
        business_id=business_id,
        user_id=user_id,
    )

    duplicate = existing_transaction is not None

    transaction_id = generate_id("txn")

    query = """
        INSERT INTO transaction_general_ledger (
            transaction_id,
            business_id,
            entity_id,
            user_id,
            transaction_date,
            amount,
            transaction_type,
            category,
            payment_mode,
            description,
            transaction_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    with get_connection() as connection:
        connection.execute(
            query,
            (
                transaction_id,
                business_id,
                entity_id,
                user_id,
                transaction_date,
                decimal_to_float(normalized_amount),
                transaction_type.strip().lower(),
                category.strip()
                if category
                else None,
                payment_mode.strip()
                if payment_mode
                else None,
                description.strip()
                if description
                else None,
                transaction_hash,
            ),
        )

    return {
        "transaction_id": transaction_id,
        "transaction_hash": transaction_hash,
        "duplicate": duplicate,
    }


def get_business_transactions(
    business_id: str,
    user_id: str,
):
    """Get all transactions for a user's business."""

    business = get_business_by_id(
        business_id,
        user_id,
    )

    if business is None:
        raise PermissionError(
            "Business does not belong to this user."
        )

    query = """
        SELECT *
        FROM transaction_general_ledger
        WHERE business_id = ?
          AND user_id = ?
        ORDER BY transaction_date DESC, created_at DESC
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (
                business_id,
                user_id,
            ),
        ).fetchall()


def get_transaction_by_id(
    transaction_id: str,
    user_id: str,
):
    """Get one transaction belonging to the user."""

    query = """
        SELECT *
        FROM transaction_general_ledger
        WHERE transaction_id = ?
          AND user_id = ?
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (
                transaction_id,
                user_id,
            ),
        ).fetchone()


# ============================================================
# BUDGET QUERIES
# ============================================================

def create_budget(
    business_id: str,
    category: str,
    allocated_amount: Any,
    user_id: str,
) -> str:
    """Create a budget for a user's business."""

    business = get_business_by_id(
        business_id,
        user_id,
    )

    if business is None:
        raise PermissionError(
            "Business does not belong to this user."
        )

    amount = Decimal(
        str(allocated_amount)
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    if amount < 0:
        raise ValueError(
            "Budget amount cannot be negative."
        )

    budget_id = generate_id("bud")

    query = """
        INSERT INTO structural_budget_allocations (
            budget_id,
            business_id,
            category,
            allocated_amount
        )
        VALUES (?, ?, ?, ?)
    """

    with get_connection() as connection:
        connection.execute(
            query,
            (
                budget_id,
                business_id,
                category.strip(),
                decimal_to_float(amount),
            ),
        )

    return budget_id


def get_business_budgets(
    business_id: str,
    user_id: str,
):
    """Get all budgets for a user's business."""

    business = get_business_by_id(
        business_id,
        user_id,
    )

    if business is None:
        raise PermissionError(
            "Business does not belong to this user."
        )

    query = """
        SELECT *
        FROM structural_budget_allocations
        WHERE business_id = ?
        ORDER BY category
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (business_id,),
        ).fetchall()


def get_budget_variance(
    business_id: str,
    user_id: str,
):
    """Compare budget allocation with actual expenses."""

    business = get_business_by_id(
        business_id,
        user_id,
    )

    if business is None:
        raise PermissionError(
            "Business does not belong to this user."
        )

    query = """
        SELECT
            b.budget_id,
            b.category,
            b.allocated_amount,
            COALESCE(
                SUM(
                    CASE
                        WHEN LOWER(t.transaction_type) = 'expense'
                        THEN t.amount
                        ELSE 0
                    END
                ),
                0
            ) AS actual_spending,
            b.allocated_amount -
            COALESCE(
                SUM(
                    CASE
                        WHEN LOWER(t.transaction_type) = 'expense'
                        THEN t.amount
                        ELSE 0
                    END
                ),
                0
            ) AS variance
        FROM structural_budget_allocations AS b
        LEFT JOIN transaction_general_ledger AS t
            ON t.business_id = b.business_id
           AND LOWER(COALESCE(t.category, '')) =
               LOWER(b.category)
           AND t.user_id = ?
        WHERE b.business_id = ?
        GROUP BY
            b.budget_id,
            b.category,
            b.allocated_amount
        ORDER BY b.category
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (
                user_id,
                business_id,
            ),
        ).fetchall()


# ============================================================
# FINANCIAL SUMMARY QUERIES
# ============================================================

def get_financial_summary(
    business_id: str,
    user_id: str,
):
    """Calculate the financial summary dynamically."""

    business = get_business_by_id(
        business_id,
        user_id,
    )

    if business is None:
        raise PermissionError(
            "Business does not belong to this user."
        )

    query = """
        SELECT
            COUNT(*) AS total_transactions,

            COALESCE(
                SUM(
                    CASE
                        WHEN LOWER(transaction_type) = 'income'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ) AS total_income,

            COALESCE(
                SUM(
                    CASE
                        WHEN LOWER(transaction_type) = 'expense'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ) AS total_expense

        FROM transaction_general_ledger

        WHERE business_id = ?
          AND user_id = ?
    """

    with get_connection() as connection:
        row = connection.execute(
            query,
            (
                business_id,
                user_id,
            ),
        ).fetchone()

    total_income = float(
        row["total_income"] or 0
    )

    total_expense = float(
        row["total_expense"] or 0
    )

    return {
        "total_transactions": row["total_transactions"],
        "total_income": total_income,
        "total_expense": total_expense,
        "net_cash_flow": (
            total_income - total_expense
        ),
    }


# ============================================================
# UPLOAD INGESTION LOGS
# ============================================================

def create_upload_log(
    user_id: str,
    business_id: str,
    file_name: str,
    file_type: Optional[str],
    total_records: int,
    successful_records: int,
    failed_records: int,
    status: str,
    error_message: Optional[str] = None,
) -> str:
    """Store an upload ingestion event."""

    business = get_business_by_id(
        business_id,
        user_id,
    )

    if business is None:
        raise PermissionError(
            "Business does not belong to this user."
        )

    upload_id = generate_id("upl")

    query = """
        INSERT INTO pipeline_upload_ingestion_logs (
            upload_id,
            user_id,
            business_id,
            file_name,
            file_type,
            records_received,
            records_inserted,
            records_rejected,
            status,
            error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    with get_connection() as connection:
        connection.execute(
            query,
            (
                upload_id,
                user_id,
                business_id,
                file_name,
                file_type,
                total_records,
                successful_records,
                failed_records,
                status,
                error_message,
            ),
        )

    return upload_id


def get_upload_logs(
    business_id: str,
    user_id: str,
):
    """Get upload logs for a user's business."""

    business = get_business_by_id(
        business_id,
        user_id,
    )

    if business is None:
        raise PermissionError(
            "Business does not belong to this user."
        )

    query = """
        SELECT *
        FROM pipeline_upload_ingestion_logs
        WHERE business_id = ?
          AND user_id = ?
        ORDER BY created_at DESC
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (
                business_id,
                user_id,
            ),
        ).fetchall()


# ============================================================
# AUTHENTICATION LOGS
# ============================================================

def create_authentication_log(
    user_id: Optional[str],
    event_type: str,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> str:
    """Record an authentication event."""

    log_id = generate_id("auth")

    details = user_agent

    query = """
        INSERT INTO authentication_logs (
            authentication_log_id,
            user_id,
            event_type,
            ip_address,
            details
        )
        VALUES (?, ?, ?, ?, ?)
    """

    with get_connection() as connection:
        connection.execute(
            query,
            (
                log_id,
                user_id,
                event_type.strip(),
                ip_address,
                details,
            ),
        )

    return log_id


# ============================================================
# OTP QUERIES
# ============================================================

def create_otp_record(
    user_id: str,
    otp_hash: str,
    expires_at: str,
) -> str:
    """Store a hashed OTP."""

    user = get_user_by_id(user_id)

    if user is None:
        raise ValueError("User does not exist.")

    otp_id = generate_id("otp")

    query = """
        INSERT INTO otp_verifications (
            otp_id,
            user_id,
            otp_hash,
            expires_at
        )
        VALUES (?, ?, ?, ?)
    """

    with get_connection() as connection:
        connection.execute(
            query,
            (
                otp_id,
                user_id,
                otp_hash,
                expires_at,
            ),
        )

    return otp_id


def get_latest_unused_otp(
    user_id: str,
):
    """Get the latest unused and unexpired OTP."""

    query = """
        SELECT *
        FROM otp_verifications
        WHERE user_id = ?
          AND is_used = 0
          AND expires_at > CURRENT_TIMESTAMP
        ORDER BY created_at DESC
        LIMIT 1
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (user_id,),
        ).fetchone()


def mark_otp_used(
    otp_id: str,
) -> bool:
    """Mark an OTP as used."""

    query = """
        UPDATE otp_verifications
        SET is_used = 1
        WHERE otp_id = ?
          AND is_used = 0
    """

    with get_connection() as connection:
        cursor = connection.execute(
            query,
            (otp_id,),
        )

    return cursor.rowcount == 1


def increment_otp_attempt(
    otp_id: str,
) -> bool:
    """Increase the OTP attempt count."""

    query = """
        UPDATE otp_verifications
        SET attempt_count = attempt_count + 1
        WHERE otp_id = ?
          AND is_used = 0
    """

    with get_connection() as connection:
        cursor = connection.execute(
            query,
            (otp_id,),
        )

    return cursor.rowcount == 1


# ============================================================
# DOCUMENT QUERIES
# ============================================================

def create_document(
    user_id: str,
    file_name: str,
    file_type: Optional[str] = None,
    file_path: Optional[str] = None,
) -> str:
    """Create a document owned by a user."""

    user = get_user_by_id(user_id)

    if user is None:
        raise ValueError("User does not exist.")

    document_id = generate_id("doc")

    query = """
        INSERT INTO documents (
            document_id,
            user_id,
            file_name,
            file_type,
            file_path
        )
        VALUES (?, ?, ?, ?, ?)
    """

    with get_connection() as connection:
        connection.execute(
            query,
            (
                document_id,
                user_id,
                file_name,
                file_type,
                file_path,
            ),
        )

    return document_id


def get_user_documents(
    user_id: str,
):
    """Get all documents belonging to a user."""

    query = """
        SELECT *
        FROM documents
        WHERE user_id = ?
        ORDER BY created_at DESC
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (user_id,),
        ).fetchall()


def get_document_by_id(
    document_id: str,
    user_id: str,
):
    """Get a document owned by the user."""

    query = """
        SELECT *
        FROM documents
        WHERE document_id = ?
          AND user_id = ?
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (
                document_id,
                user_id,
            ),
        ).fetchone()


def delete_document(
    document_id: str,
    user_id: str,
) -> bool:
    """Delete a document owned by the user."""

    query = """
        DELETE FROM documents
        WHERE document_id = ?
          AND user_id = ?
    """

    with get_connection() as connection:
        cursor = connection.execute(
            query,
            (
                document_id,
                user_id,
            ),
        )

    return cursor.rowcount == 1


# ============================================================
# DOCUMENT CHUNK QUERIES
# ============================================================

def create_document_chunk(
    document_id: str,
    user_id: str,
    chunk_index: int,
    chunk_text: str,
) -> str:
    """Create a document chunk."""

    document = get_document_by_id(
        document_id,
        user_id,
    )

    if document is None:
        raise PermissionError(
            "Document does not belong to this user."
        )

    chunk_id = generate_id("chk")

    query = """
        INSERT INTO document_chunks (
            chunk_id,
            document_id,
            user_id,
            chunk_index,
            chunk_text
        )
        VALUES (?, ?, ?, ?, ?)
    """

    with get_connection() as connection:
        connection.execute(
            query,
            (
                chunk_id,
                document_id,
                user_id,
                chunk_index,
                chunk_text,
            ),
        )

    return chunk_id


def get_document_chunks(
    document_id: str,
    user_id: str,
):
    """Get chunks for a user's document."""

    document = get_document_by_id(
        document_id,
        user_id,
    )

    if document is None:
        raise PermissionError(
            "Document does not belong to this user."
        )

    query = """
        SELECT *
        FROM document_chunks
        WHERE document_id = ?
          AND user_id = ?
        ORDER BY chunk_index
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (
                document_id,
                user_id,
            ),
        ).fetchall()


def get_user_document_chunks(
    user_id: str,
):
    """Get all document chunks belonging to a user."""

    query = """
        SELECT *
        FROM document_chunks
        WHERE user_id = ?
        ORDER BY document_id, chunk_index
    """

    with get_connection() as connection:
        return connection.execute(
            query,
            (user_id,),
        ).fetchall()