-- Migration: Add single-use discount support
-- Date: 2025-01-15

-- Add single_use_per_user field to discounts table
ALTER TABLE discounts ADD COLUMN single_use_per_user BOOLEAN DEFAULT 0;

-- Create discount usage history table
CREATE TABLE IF NOT EXISTS discount_usage_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    discount_id INTEGER NOT NULL,
    plan_id INTEGER,
    payment_id INTEGER,
    used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    amount_discounted REAL,
    payment_method TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (discount_id) REFERENCES discounts(id),
    FOREIGN KEY (plan_id) REFERENCES plans(id),
    FOREIGN KEY (payment_id) REFERENCES payments(payment_id),
    UNIQUE(user_id, discount_id) -- این محدودیت فقط برای کدهای single_use_per_user اعمال می‌شود
);

-- Create index for faster lookups
CREATE INDEX idx_discount_usage_user_discount ON discount_usage_history(user_id, discount_id);
CREATE INDEX idx_discount_usage_used_at ON discount_usage_history(used_at);
