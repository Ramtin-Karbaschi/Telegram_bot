-- Migration: Add auto verification logs table
-- This table tracks all automatic payment verifications

CREATE TABLE IF NOT EXISTS auto_verification_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id TEXT NOT NULL,
    tx_hash TEXT NOT NULL,
    amount REAL NOT NULL,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'failed', 'subscription_error')),
    verification_method TEXT DEFAULT 'automatic',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    -- Indexes for better performance
    FOREIGN KEY (payment_id) REFERENCES crypto_payments(payment_id)
);

CREATE INDEX IF NOT EXISTS idx_auto_verification_logs_payment_id ON auto_verification_logs(payment_id);
CREATE INDEX IF NOT EXISTS idx_auto_verification_logs_user_id ON auto_verification_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_auto_verification_logs_created_at ON auto_verification_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_auto_verification_logs_status ON auto_verification_logs(status);

-- Add new status to crypto_payments table for manual review
-- Note: This assumes the crypto_payments table already exists
-- If the status column needs updating to include 'manual_review', uncomment below:

-- ALTER TABLE crypto_payments ADD COLUMN temp_status TEXT DEFAULT 'pending';
-- UPDATE crypto_payments SET temp_status = status;
-- ALTER TABLE crypto_payments DROP COLUMN status;
-- ALTER TABLE crypto_payments RENAME COLUMN temp_status TO status;

-- Add settings for auto verification system
INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_crypto_verify', '1');
INSERT OR IGNORE INTO settings (key, value) VALUES ('crypto_tolerance_percent', '5.0');
INSERT OR IGNORE INTO settings (key, value) VALUES ('max_auto_verify_usdt', '1000.0');
INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_approve_after_hours', '24');
INSERT OR IGNORE INTO settings (key, value) VALUES ('max_tx_age_hours', '24');
INSERT OR IGNORE INTO settings (key, value) VALUES ('tron_min_confirmations', '1');
