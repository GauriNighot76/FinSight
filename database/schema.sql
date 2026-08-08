PRAGMA foreign_keys = ON;


-- ============================================================
-- 1. USERS
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,

    email TEXT NOT NULL UNIQUE,

    contact_number TEXT NOT NULL,

    password_hash TEXT NOT NULL,

    secret_question TEXT NOT NULL,

    secret_answer_hash TEXT NOT NULL,

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 2. BUSINESS REGISTRY
-- ============================================================

CREATE TABLE IF NOT EXISTS business_registry (
    business_id TEXT PRIMARY KEY,

    user_id TEXT NOT NULL,

    business_name TEXT NOT NULL,

    business_type TEXT,

    address TEXT,

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    UNIQUE (user_id, business_name)
);


-- ============================================================
-- 3. COUNTERPARTY ENTITIES
-- ============================================================

CREATE TABLE IF NOT EXISTS counterparty_entities (
    entity_id TEXT PRIMARY KEY,

    business_id TEXT NOT NULL,

    entity_name TEXT NOT NULL,

    entity_type TEXT NOT NULL,

    contact_number TEXT,

    email TEXT,

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (business_id)
        REFERENCES business_registry(business_id)
        ON DELETE CASCADE,

    UNIQUE (
        business_id,
        entity_name,
        entity_type
    )
);


-- ============================================================
-- 4. TRANSACTION GENERAL LEDGER
-- ============================================================

CREATE TABLE IF NOT EXISTS transaction_general_ledger (
    transaction_id TEXT PRIMARY KEY,

    business_id TEXT NOT NULL,

    entity_id TEXT,

    user_id TEXT NOT NULL,

    transaction_date TEXT NOT NULL,

    amount REAL NOT NULL
        CHECK (amount > 0),

    transaction_type TEXT NOT NULL,

    category TEXT,

    payment_mode TEXT,

    description TEXT,

    transaction_hash TEXT NOT NULL,

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (business_id)
        REFERENCES business_registry(business_id)
        ON DELETE CASCADE,

    FOREIGN KEY (entity_id)
        REFERENCES counterparty_entities(entity_id)
        ON DELETE SET NULL,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);


-- ============================================================
-- 5. STRUCTURAL BUDGET ALLOCATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS structural_budget_allocations (
    budget_id TEXT PRIMARY KEY,

    business_id TEXT NOT NULL,

    category TEXT NOT NULL,

    allocated_amount REAL NOT NULL
        CHECK (allocated_amount >= 0),

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (business_id)
        REFERENCES business_registry(business_id)
        ON DELETE CASCADE,

    UNIQUE (
        business_id,
        category
    )
);


-- ============================================================
-- 6. PIPELINE UPLOAD INGESTION LOGS
-- ============================================================

CREATE TABLE IF NOT EXISTS pipeline_upload_ingestion_logs (
    upload_id TEXT PRIMARY KEY,

    user_id TEXT,

    business_id TEXT NOT NULL,

    file_name TEXT NOT NULL,

    file_type TEXT,

    total_records INTEGER NOT NULL
        DEFAULT 0,

    successful_records INTEGER NOT NULL
        DEFAULT 0,

    failed_records INTEGER NOT NULL
        DEFAULT 0,

    status TEXT NOT NULL,

    error_message TEXT,

    uploaded_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE SET NULL,

    FOREIGN KEY (business_id)
        REFERENCES business_registry(business_id)
        ON DELETE CASCADE
);


-- ============================================================
-- 7. AUTHENTICATION LOGS
-- ============================================================

CREATE TABLE IF NOT EXISTS authentication_logs (
    authentication_log_id TEXT PRIMARY KEY,

    user_id TEXT,

    event_type TEXT NOT NULL,

    ip_address TEXT,

    user_agent TEXT,

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE SET NULL
);


-- ============================================================
-- 8. OTP VERIFICATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS otp_verifications (
    otp_id TEXT PRIMARY KEY,

    user_id TEXT NOT NULL,

    otp_hash TEXT NOT NULL,

    expires_at TEXT NOT NULL,

    is_used INTEGER NOT NULL
        DEFAULT 0
        CHECK (is_used IN (0, 1)),

    attempt_count INTEGER NOT NULL
        DEFAULT 0
        CHECK (attempt_count >= 0),

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);


-- ============================================================
-- 9. DOCUMENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,

    user_id TEXT NOT NULL,

    file_name TEXT NOT NULL,

    file_type TEXT,

    file_path TEXT,

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);


-- ============================================================
-- 10. DOCUMENT CHUNKS
-- ============================================================

CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id TEXT PRIMARY KEY,

    document_id TEXT NOT NULL,

    user_id TEXT NOT NULL,

    chunk_index INTEGER NOT NULL,

    chunk_text TEXT NOT NULL,

    created_at TEXT NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (document_id)
        REFERENCES documents(document_id)
        ON DELETE CASCADE,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    UNIQUE (
        document_id,
        chunk_index
    )
);


-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_business_user
ON business_registry(user_id);


CREATE INDEX IF NOT EXISTS idx_counterparty_business
ON counterparty_entities(business_id);


CREATE INDEX IF NOT EXISTS idx_transaction_business
ON transaction_general_ledger(business_id);


CREATE INDEX IF NOT EXISTS idx_transaction_user
ON transaction_general_ledger(user_id);


CREATE INDEX IF NOT EXISTS idx_transaction_entity
ON transaction_general_ledger(entity_id);


CREATE INDEX IF NOT EXISTS idx_transaction_date
ON transaction_general_ledger(transaction_date);


CREATE INDEX IF NOT EXISTS idx_transaction_hash
ON transaction_general_ledger(transaction_hash);


CREATE INDEX IF NOT EXISTS idx_budget_business
ON structural_budget_allocations(business_id);


CREATE INDEX IF NOT EXISTS idx_upload_user
ON pipeline_upload_ingestion_logs(user_id);


CREATE INDEX IF NOT EXISTS idx_upload_business
ON pipeline_upload_ingestion_logs(business_id);


CREATE INDEX IF NOT EXISTS idx_auth_user
ON authentication_logs(user_id);


CREATE INDEX IF NOT EXISTS idx_otp_user
ON otp_verifications(user_id);


CREATE INDEX IF NOT EXISTS idx_document_user
ON documents(user_id);


CREATE INDEX IF NOT EXISTS idx_chunk_document
ON document_chunks(document_id);


CREATE INDEX IF NOT EXISTS idx_chunk_user
ON document_chunks(user_id);