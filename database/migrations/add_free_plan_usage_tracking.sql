-- Migration: Add permanent tracking for free plan usage
-- Purpose: Track all free plan activations permanently to prevent reuse
-- Date: 2025-01-10

-- Create table to track free plan usage permanently
CREATE TABLE IF NOT EXISTS free_plan_usage_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    plan_id INTEGER NOT NULL,
    activation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    subscription_id INTEGER,
    payment_method TEXT,
    transaction_id TEXT,
    notes TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (plan_id) REFERENCES plans(id),
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
    UNIQUE(user_id, plan_id)  -- Each user can only activate each free plan once
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_free_plan_usage_user_plan ON free_plan_usage_tracking(user_id, plan_id);
CREATE INDEX IF NOT EXISTS idx_free_plan_usage_date ON free_plan_usage_tracking(activation_date);

-- Add column to subscriptions table for tracking subscription chain (if not exists)
-- This allows us to maintain subscription history instead of overwriting
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS previous_subscription_id INTEGER REFERENCES subscriptions(id);
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS is_extension BOOLEAN DEFAULT 0;

-- Add composite index for better query performance on active subscriptions
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_status_end ON subscriptions(user_id, status, end_date);

-- Migrate existing free plan subscriptions to the tracking table
-- This ensures historical data is preserved
INSERT OR IGNORE INTO free_plan_usage_tracking (user_id, plan_id, activation_date, subscription_id, payment_method)
SELECT 
    s.user_id,
    s.plan_id,
    s.created_at,
    s.id,
    s.payment_method
FROM subscriptions s
INNER JOIN plans p ON s.plan_id = p.id
WHERE (p.price = 0 OR p.price IS NULL) 
   AND (p.price_tether = 0 OR p.price_tether IS NULL)
   AND (p.base_price = 0 OR p.base_price IS NULL);

-- Add trigger to automatically track free plan activations
CREATE TRIGGER IF NOT EXISTS track_free_plan_activation
AFTER INSERT ON subscriptions
FOR EACH ROW
WHEN (
    SELECT 1 FROM plans p 
    WHERE p.id = NEW.plan_id 
    AND (p.price = 0 OR p.price IS NULL) 
    AND (p.price_tether = 0 OR p.price_tether IS NULL)
    AND (p.base_price = 0 OR p.base_price IS NULL)
) IS NOT NULL
BEGIN
    INSERT OR IGNORE INTO free_plan_usage_tracking (user_id, plan_id, subscription_id, payment_method)
    VALUES (NEW.user_id, NEW.plan_id, NEW.id, NEW.payment_method);
END;
