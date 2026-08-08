PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    contact_number TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    secret_question TEXT NOT NULL,
    secret_answer_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS business_registry (
    business_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    business_name TEXT NOT NULL,
    business_type TEXT,
    address TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    UNIQUE (user_id, business_name)
);

CREATE TABLE IF NOT EXISTS counterparty_entities (
    entity_id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    contact_number TEXT,
    email TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (business_id)
        REFERENCES business_registry(business_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS transaction_general_ledger (
    transaction_id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    entity_id TEXT,
    user_id TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    transaction_type TEXT NOT NULL,
    category TEXT,
    payment_mode TEXT,
    description TEXT,
    transaction_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

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

CREATE TABLE IF NOT EXISTS structural_budget_allocations (
    budget_id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    category TEXT NOT NULL,
    allocated_amount REAL NOT NULL CHECK (allocated_amount >= 0),
    period_start TEXT,
    period_end TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (business_id)
        REFERENCES business_registry(business_id)
        ON DELETE CASCADE,

    UNIQUE (business_id, category)
);

CREATE TABLE IF NOT EXISTS pipeline_upload_ingestion_logs (
    upload_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    business_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT,
    records_received INTEGER NOT NULL DEFAULT 0,
    records_inserted INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    FOREIGN KEY (business_id)
        REFERENCES business_registry(business_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS authentication_logs (
    authentication_log_id TEXT PRIMARY KEY,
    user_id TEXT,
    event_type TEXT NOT NULL,
    email TEXT,
    ip_address TEXT,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS otp_verifications (
    otp_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    otp_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    is_used INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT,
    file_path TEXT,
    processing_status TEXT DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (document_id)
        REFERENCES documents(document_id)
        ON DELETE CASCADE,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    UNIQUE (document_id, chunk_index)
);