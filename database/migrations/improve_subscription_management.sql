-- Migration: Improve subscription management with category-based aggregation
-- Date: 2025-01-18
-- Purpose: Allow separate tracking per product/category with time aggregation for same category

-- Add category_id to subscriptions table if not exists
-- This links each subscription directly to a category for easier aggregation
ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES categories(id);

-- Create index for faster category-based queries
CREATE INDEX IF NOT EXISTS idx_subscriptions_category ON subscriptions(user_id, category_id, status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_plan ON subscriptions(user_id, plan_id, status);

-- Create a view for aggregated subscription times by category
-- This view calculates total remaining time per category for each user
CREATE VIEW IF NOT EXISTS user_category_subscriptions AS
SELECT 
    s.user_id,
    COALESCE(p.category_id, 0) as category_id,
    c.name as category_name,
    COUNT(DISTINCT s.id) as subscription_count,
    MIN(s.start_date) as first_subscription_date,
    MAX(
        CASE 
            WHEN s.status = 'active' AND (s.end_date IS NULL OR s.end_date > datetime('now'))
            THEN s.end_date 
            ELSE NULL 
        END
    ) as latest_active_end_date,
    SUM(
        CASE 
            WHEN s.status = 'active' AND (s.end_date IS NULL OR s.end_date > datetime('now'))
            THEN CAST((julianday(s.end_date) - julianday(datetime('now'))) AS INTEGER)
            ELSE 0
        END
    ) as total_remaining_days
FROM subscriptions s
JOIN plans p ON s.plan_id = p.id
LEFT JOIN categories c ON p.category_id = c.id
WHERE s.status = 'active'
GROUP BY s.user_id, p.category_id, c.name;

-- Create subscription history table for better tracking
CREATE TABLE IF NOT EXISTS subscription_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscription_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    plan_id INTEGER NOT NULL,
    category_id INTEGER,
    action TEXT NOT NULL, -- 'created', 'extended', 'expired', 'cancelled'
    old_end_date TEXT,
    new_end_date TEXT,
    days_added INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER, -- admin who made the change if applicable
    notes TEXT,
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (plan_id) REFERENCES plans(id),
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

-- Create index for history queries
CREATE INDEX IF NOT EXISTS idx_subscription_history_user ON subscription_history(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_subscription_history_subscription ON subscription_history(subscription_id, created_at DESC);
