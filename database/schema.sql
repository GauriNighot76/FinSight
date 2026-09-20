PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    contact_number TEXT NOT NULL,
    password_hash TEXT,
    secret_question TEXT NOT NULL DEFAULT '',
    secret_answer_hash TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'standard_business'
        CHECK (role IN ('administrator','standard_business','accountant','auditor')),
    account_status TEXT NOT NULL DEFAULT 'active'
        CHECK (account_status IN ('active','disabled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS business_registry (
    business_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, business_name TEXT NOT NULL,
    business_type TEXT, address TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE (user_id, business_name)
);
CREATE TABLE IF NOT EXISTS counterparty_entities (
    entity_id TEXT PRIMARY KEY, business_id TEXT NOT NULL, entity_name TEXT NOT NULL,
    entity_type TEXT NOT NULL, contact_number TEXT, email TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES business_registry(business_id) ON DELETE CASCADE,
    UNIQUE (business_id, entity_name, entity_type)
);
CREATE TABLE IF NOT EXISTS transaction_general_ledger (
    transaction_id TEXT PRIMARY KEY, business_id TEXT NOT NULL, entity_id TEXT,
    user_id TEXT NOT NULL, transaction_date TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0), transaction_type TEXT NOT NULL,
    category TEXT, payment_mode TEXT, description TEXT, transaction_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES business_registry(business_id) ON DELETE CASCADE,
    FOREIGN KEY (entity_id) REFERENCES counterparty_entities(entity_id) ON DELETE SET NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS structural_budget_allocations (
    budget_id TEXT PRIMARY KEY, business_id TEXT NOT NULL, category TEXT NOT NULL,
    allocated_amount REAL NOT NULL CHECK (allocated_amount >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES business_registry(business_id) ON DELETE CASCADE,
    UNIQUE (business_id, category)
);
CREATE TABLE IF NOT EXISTS pipeline_upload_ingestion_logs (
    upload_id TEXT PRIMARY KEY, user_id TEXT, business_id TEXT NOT NULL,
    file_name TEXT NOT NULL, file_type TEXT, total_records INTEGER NOT NULL DEFAULT 0,
    successful_records INTEGER NOT NULL DEFAULT 0, failed_records INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL, error_message TEXT, uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY (business_id) REFERENCES business_registry(business_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS authentication_logs (
    authentication_log_id TEXT PRIMARY KEY, user_id TEXT, event_type TEXT NOT NULL,
    ip_address TEXT, user_agent TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS otp_verifications (
    otp_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, otp_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL, is_used INTEGER NOT NULL DEFAULT 0 CHECK (is_used IN (0,1)),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, file_name TEXT NOT NULL,
    file_type TEXT, file_path TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, user_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL, chunk_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE (document_id, chunk_index)
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL, revoked_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS provider_identities (
    identity_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, provider TEXT NOT NULL,
    provider_subject TEXT NOT NULL, provider_email TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE (provider, provider_subject)
);

-- Module 2 business boundary. The legacy business_registry table remains
-- unchanged because Module 0 financial queries still depend on it.
CREATE TABLE IF NOT EXISTS businesses (
    business_id TEXT PRIMARY KEY,
    business_name TEXT NOT NULL,
    legal_identifier TEXT,
    contact_email TEXT,
    contact_phone TEXT,
    business_status TEXT NOT NULL DEFAULT 'active'
        CHECK (business_status IN ('active','disabled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS business_memberships (
    membership_id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    membership_role TEXT NOT NULL
        CHECK (membership_role IN ('owner','manager','member','viewer')),
    membership_status TEXT NOT NULL DEFAULT 'active'
        CHECK (membership_status IN ('active','disabled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES businesses(business_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE (business_id, user_id)
);

-- Module 3 accounts belong to Module 2 businesses so access is always
-- authorized through business_memberships. Balances use integer minor units.
CREATE TABLE IF NOT EXISTS financial_accounts (
    account_id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    account_name TEXT NOT NULL CHECK (length(trim(account_name)) BETWEEN 2 AND 120),
    account_type TEXT NOT NULL
        CHECK (account_type IN ('bank','cash','credit_card','loan','other')),
    institution_name TEXT,
    account_identifier TEXT,
    currency TEXT NOT NULL DEFAULT 'INR'
        CHECK (length(currency) = 3 AND currency = upper(currency)),
    opening_balance_minor INTEGER NOT NULL DEFAULT 0,
    account_status TEXT NOT NULL DEFAULT 'active'
        CHECK (account_status IN ('active','disabled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES businesses(business_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_business_user ON business_registry(user_id);
CREATE INDEX IF NOT EXISTS idx_counterparty_business ON counterparty_entities(business_id);
CREATE INDEX IF NOT EXISTS idx_transaction_business ON transaction_general_ledger(business_id);
CREATE INDEX IF NOT EXISTS idx_transaction_user ON transaction_general_ledger(user_id);
CREATE INDEX IF NOT EXISTS idx_transaction_entity ON transaction_general_ledger(entity_id);
CREATE INDEX IF NOT EXISTS idx_transaction_date ON transaction_general_ledger(transaction_date);
CREATE INDEX IF NOT EXISTS idx_transaction_hash ON transaction_general_ledger(transaction_hash);
CREATE INDEX IF NOT EXISTS idx_budget_business ON structural_budget_allocations(business_id);
CREATE INDEX IF NOT EXISTS idx_upload_user ON pipeline_upload_ingestion_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_upload_business ON pipeline_upload_ingestion_logs(business_id);
CREATE INDEX IF NOT EXISTS idx_auth_user ON authentication_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_otp_user ON otp_verifications(user_id);
CREATE INDEX IF NOT EXISTS idx_document_user ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_chunk_document ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunk_user ON document_chunks(user_id);
CREATE INDEX IF NOT EXISTS idx_session_user ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_session_expiry ON auth_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_identity_user ON provider_identities(user_id);
CREATE INDEX IF NOT EXISTS idx_business_status ON businesses(business_status);
CREATE INDEX IF NOT EXISTS idx_membership_user_status
ON business_memberships(user_id, membership_status);
CREATE INDEX IF NOT EXISTS idx_membership_business_status
ON business_memberships(business_id, membership_status);
CREATE INDEX IF NOT EXISTS idx_financial_account_business_status
ON financial_accounts(business_id, account_status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_financial_account_identifier
ON financial_accounts(business_id, account_identifier)
WHERE account_identifier IS NOT NULL AND account_identifier <> '';

-- Module 4 ingestion boundary.
-- These structures are additive. Legacy business_registry and
-- transaction_general_ledger ownership semantics remain unchanged.

CREATE TABLE IF NOT EXISTS business_registry_bridges (
    bridge_id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    registry_business_id TEXT NOT NULL,
    proposed_by_user_id TEXT NOT NULL,
    verified_by_user_id TEXT,
    bridge_status TEXT NOT NULL
        CHECK (bridge_status IN ('pending','active','rejected','disabled')),
    proposed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (business_id) REFERENCES businesses(business_id) ON DELETE RESTRICT,
    FOREIGN KEY (registry_business_id) REFERENCES business_registry(business_id) ON DELETE RESTRICT,
    FOREIGN KEY (proposed_by_user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY (verified_by_user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    CHECK (
        bridge_status <> 'active'
        OR (verified_by_user_id IS NOT NULL AND verified_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_bridge_one_active_business
ON business_registry_bridges(business_id)
WHERE bridge_status = 'active';

CREATE UNIQUE INDEX IF NOT EXISTS idx_bridge_one_active_registry
ON business_registry_bridges(registry_business_id)
WHERE bridge_status = 'active';

CREATE INDEX IF NOT EXISTS idx_bridge_business_status
ON business_registry_bridges(business_id, bridge_status);

CREATE INDEX IF NOT EXISTS idx_bridge_registry_status
ON business_registry_bridges(registry_business_id, bridge_status);

CREATE TABLE IF NOT EXISTS ingestion_attempts (
    attempt_id TEXT PRIMARY KEY,
    parent_attempt_id TEXT,
    business_id TEXT NOT NULL,
    registry_business_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    uploader_user_id TEXT NOT NULL,
    source_system TEXT NOT NULL
        CHECK (source_system IN ('finsight_demo_bank_statement_v1')),
    contract_version TEXT NOT NULL,
    currency TEXT NOT NULL
        CHECK (length(currency) = 3 AND currency = upper(currency)),
    record_count INTEGER NOT NULL DEFAULT 0 CHECK (record_count >= 0),
    inserted_count INTEGER NOT NULL DEFAULT 0 CHECK (inserted_count >= 0),
    duplicate_count INTEGER NOT NULL DEFAULT 0 CHECK (duplicate_count >= 0),
    rejected_count INTEGER NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
    attempt_status TEXT NOT NULL
        CHECK (attempt_status IN ('processing','completed','failed')),
    public_error_code TEXT,
    public_error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    FOREIGN KEY (parent_attempt_id) REFERENCES ingestion_attempts(attempt_id) ON DELETE RESTRICT,
    FOREIGN KEY (business_id) REFERENCES businesses(business_id) ON DELETE RESTRICT,
    FOREIGN KEY (registry_business_id) REFERENCES business_registry(business_id) ON DELETE RESTRICT,
    FOREIGN KEY (account_id) REFERENCES financial_accounts(account_id) ON DELETE RESTRICT,
    FOREIGN KEY (uploader_user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    CHECK (attempt_status <> 'completed' OR completed_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_ingestion_attempt_business_created
ON ingestion_attempts(business_id, created_at);

CREATE INDEX IF NOT EXISTS idx_ingestion_attempt_account_created
ON ingestion_attempts(account_id, created_at);

CREATE INDEX IF NOT EXISTS idx_ingestion_attempt_uploader_created
ON ingestion_attempts(uploader_user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_ingestion_attempt_status_created
ON ingestion_attempts(attempt_status, created_at);

CREATE INDEX IF NOT EXISTS idx_ingestion_attempt_parent
ON ingestion_attempts(parent_attempt_id);

CREATE TABLE IF NOT EXISTS ingested_transaction_identities (
    identity_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL UNIQUE,
    attempt_id TEXT NOT NULL,
    business_id TEXT NOT NULL,
    registry_business_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    source_system TEXT NOT NULL
        CHECK (source_system IN ('finsight_demo_bank_statement_v1')),
    source_transaction_id TEXT CHECK (source_transaction_id IS NULL OR length(trim(source_transaction_id)) > 0),
    transaction_date TEXT NOT NULL,
    amount_minor INTEGER NOT NULL
        CHECK (typeof(amount_minor) = 'integer' AND amount_minor >= 0),
    direction TEXT NOT NULL CHECK (direction IN ('income','expense')),
    currency TEXT NOT NULL
        CHECK (length(currency) = 3 AND currency = upper(currency)),
    canonical_identity_hash TEXT NOT NULL UNIQUE
        CHECK (length(trim(canonical_identity_hash)) > 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transaction_general_ledger(transaction_id) ON DELETE RESTRICT,
    FOREIGN KEY (attempt_id) REFERENCES ingestion_attempts(attempt_id) ON DELETE RESTRICT,
    FOREIGN KEY (business_id) REFERENCES businesses(business_id) ON DELETE RESTRICT,
    FOREIGN KEY (registry_business_id) REFERENCES business_registry(business_id) ON DELETE RESTRICT,
    FOREIGN KEY (account_id) REFERENCES financial_accounts(account_id) ON DELETE RESTRICT
);


CREATE UNIQUE INDEX IF NOT EXISTS idx_ingested_source_identity
ON ingested_transaction_identities(account_id, source_system, source_transaction_id)
WHERE source_transaction_id IS NOT NULL AND trim(source_transaction_id) <> '';

CREATE INDEX IF NOT EXISTS idx_ingested_identity_account_created
ON ingested_transaction_identities(account_id, created_at);

CREATE INDEX IF NOT EXISTS idx_ingested_identity_attempt
ON ingested_transaction_identities(attempt_id);

CREATE INDEX IF NOT EXISTS idx_ingested_identity_registry_date
ON ingested_transaction_identities(registry_business_id, transaction_date);

CREATE INDEX IF NOT EXISTS idx_ingested_identity_business_account_date
ON ingested_transaction_identities(business_id, account_id, transaction_date);
