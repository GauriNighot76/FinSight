PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    contact_number TEXT,
    password_hash TEXT NOT NULL,
    secret_question TEXT NOT NULL,
    secret_answer_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (length(trim(user_id)) > 0),
    CHECK (length(trim(email)) > 3 AND instr(email, '@') > 1),
    CHECK (contact_number IS NULL OR length(trim(contact_number)) > 0),
    CHECK (password_hash GLOB '$2[abxy]$*' AND length(password_hash) >= 59),
    CHECK (length(trim(secret_question)) > 0),
    CHECK (secret_answer_hash GLOB '$2[abxy]$*' AND length(secret_answer_hash) >= 59)
);

CREATE TABLE IF NOT EXISTS business_registry (
    business_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    business_name TEXT NOT NULL,
    business_type TEXT,
    industry TEXT,
    contact_number TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (length(trim(business_id)) > 0),
    CHECK (length(trim(business_name)) > 0),
    CHECK (business_type IS NULL OR length(trim(business_type)) > 0),
    CHECK (industry IS NULL OR length(trim(industry)) > 0),
    CHECK (contact_number IS NULL OR length(trim(contact_number)) > 0),
    UNIQUE (user_id, business_name),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS counterparty_entities (
    entity_id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    contact_number TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (length(trim(entity_id)) > 0),
    CHECK (length(trim(entity_name)) > 0),
    CHECK (entity_type IN ('CUSTOMER', 'SUPPLIER', 'VENDOR', 'LENDER', 'OTHER')),
    CHECK (contact_number IS NULL OR length(trim(contact_number)) > 0),
    UNIQUE (business_id, entity_name, entity_type),
    FOREIGN KEY (business_id) REFERENCES business_registry(business_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS transaction_general_ledger (
    transaction_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    business_id TEXT NOT NULL,
    entity_id TEXT,
    transaction_date TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    transaction_type TEXT NOT NULL,
    category TEXT NOT NULL,
    payment_mode TEXT NOT NULL DEFAULT 'OTHER',
    description TEXT,
    transaction_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (length(trim(transaction_id)) > 0),
    CHECK (length(trim(transaction_date)) > 0),
    CHECK (amount > 0),
    CHECK (transaction_type IN ('CREDIT', 'DEBIT')),
    CHECK (length(trim(category)) > 0),
    CHECK (payment_mode IN ('CASH', 'BANK_TRANSFER', 'UPI', 'CARD', 'CHEQUE', 'OTHER')),
    CHECK (description IS NULL OR length(trim(description)) > 0),
    CHECK (length(transaction_hash) = 64 AND transaction_hash NOT GLOB '*[^0-9a-f]*'),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (business_id) REFERENCES business_registry(business_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES counterparty_entities(entity_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS structural_budget_allocations (
    budget_id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    category TEXT NOT NULL,
    budget_amount NUMERIC NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (length(trim(budget_id)) > 0),
    CHECK (length(trim(category)) > 0),
    CHECK (budget_amount >= 0),
    UNIQUE (business_id, category),
    FOREIGN KEY (business_id) REFERENCES business_registry(business_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pipeline_upload_ingestion_logs (
    upload_id TEXT PRIMARY KEY,
    user_id TEXT,
    business_id TEXT,
    file_name TEXT NOT NULL,
    file_type TEXT,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    rows_processed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING',
    error_message TEXT,
    CHECK (length(trim(upload_id)) > 0),
    CHECK (length(trim(file_name)) > 0),
    CHECK (file_type IS NULL OR length(trim(file_type)) > 0),
    CHECK (rows_processed >= 0),
    CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
    CHECK (error_message IS NULL OR length(trim(error_message)) > 0),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY (business_id) REFERENCES business_registry(business_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS authentication_logs (
    authentication_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    event_type TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    ip_address TEXT,
    user_agent TEXT,
    CHECK (
        event_type IN (
            'LOGIN_SUCCESS',
            'LOGIN_FAILED',
            'OTP_SENT',
            'OTP_VERIFIED',
            'OTP_FAILED',
            'PASSWORD_RESET',
            'SECRET_ANSWER_VERIFIED',
            'SECRET_ANSWER_FAILED'
        )
    ),
    CHECK (ip_address IS NULL OR length(trim(ip_address)) > 0),
    CHECK (user_agent IS NULL OR length(trim(user_agent)) > 0),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS otp_verifications (
    otp_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    otp_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    is_used INTEGER NOT NULL DEFAULT 0,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (length(trim(otp_id)) > 0),
    CHECK (length(otp_hash) >= 64),
    CHECK (length(trim(expires_at)) > 0),
    CHECK (is_used IN (0, 1)),
    CHECK (attempt_count >= 0),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    processing_status TEXT NOT NULL DEFAULT 'UPLOADED',
    CHECK (length(trim(document_id)) > 0),
    CHECK (length(trim(file_name)) > 0),
    CHECK (processing_status IN ('UPLOADED', 'PROCESSING', 'COMPLETED', 'FAILED')),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (length(trim(chunk_id)) > 0),
    CHECK (chunk_index >= 0),
    CHECK (length(trim(chunk_text)) > 0),
    UNIQUE (document_id, chunk_index),
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_business_registry_user_id
    ON business_registry(user_id);

CREATE INDEX IF NOT EXISTS idx_counterparty_entities_business_id
    ON counterparty_entities(business_id);

CREATE INDEX IF NOT EXISTS idx_transaction_general_ledger_business_id
    ON transaction_general_ledger(business_id);

CREATE INDEX IF NOT EXISTS idx_transaction_general_ledger_user_id
    ON transaction_general_ledger(user_id);

CREATE INDEX IF NOT EXISTS idx_transaction_general_ledger_entity_id
    ON transaction_general_ledger(entity_id);

CREATE INDEX IF NOT EXISTS idx_transaction_general_ledger_transaction_hash
    ON transaction_general_ledger(transaction_hash);

CREATE INDEX IF NOT EXISTS idx_transaction_general_ledger_transaction_date
    ON transaction_general_ledger(transaction_date);

CREATE INDEX IF NOT EXISTS idx_structural_budget_allocations_business_id
    ON structural_budget_allocations(business_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_upload_ingestion_logs_user_id
    ON pipeline_upload_ingestion_logs(user_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_upload_ingestion_logs_business_id
    ON pipeline_upload_ingestion_logs(business_id);

CREATE INDEX IF NOT EXISTS idx_authentication_logs_user_id
    ON authentication_logs(user_id);

CREATE INDEX IF NOT EXISTS idx_otp_verifications_user_id
    ON otp_verifications(user_id);

CREATE INDEX IF NOT EXISTS idx_documents_user_id
    ON documents(user_id);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
    ON document_chunks(document_id);

CREATE INDEX IF NOT EXISTS idx_document_chunks_user_id
    ON document_chunks(user_id);
