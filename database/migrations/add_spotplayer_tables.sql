-- Migration: Add SpotPlayer tables
-- Description: Creates tables for SpotPlayer product management

-- Create SpotPlayer purchases table
CREATE TABLE IF NOT EXISTS spotplayer_purchases (
    purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    tracking_code TEXT NOT NULL UNIQUE,
    amount INTEGER NOT NULL,
    spotplayer_key TEXT NOT NULL UNIQUE,
    payment_data TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_spotplayer_user ON spotplayer_purchases(user_id);
CREATE INDEX IF NOT EXISTS idx_spotplayer_tracking ON spotplayer_purchases(tracking_code);
CREATE INDEX IF NOT EXISTS idx_spotplayer_key ON spotplayer_purchases(spotplayer_key);
CREATE INDEX IF NOT EXISTS idx_spotplayer_created ON spotplayer_purchases(created_at);

-- Create SpotPlayer configuration table
CREATE TABLE IF NOT EXISTS spotplayer_config (
    config_id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key TEXT NOT NULL UNIQUE,
    config_value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default configuration
INSERT OR IGNORE INTO spotplayer_config (config_key, config_value, description) VALUES
    ('product_name', 'دوره آموزشی SpotPlayer', 'Product display name'),
    ('price', '1500000', 'Price in Rials'),
    ('subscription_days', '120', 'VIP subscription duration in days'),
    ('channel_id', '-1001234567890', 'VIP channel ID for SpotPlayer users'),
    ('channel_username', '@YourVIPChannel', 'VIP channel username'),
    ('zarinpal_merchant', 'YOUR_MERCHANT_ID', 'Zarinpal merchant ID'),
    ('min_amount', '1400000', 'Minimum acceptable amount for verification'),
    ('max_amount', '1600000', 'Maximum acceptable amount for verification'),
    ('enabled', '1', 'Whether SpotPlayer feature is enabled');

-- Create SpotPlayer access log table
CREATE TABLE IF NOT EXISTS spotplayer_access_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER,
    user_id INTEGER,
    action TEXT NOT NULL,
    details TEXT,
    ip_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (purchase_id) REFERENCES spotplayer_purchases(purchase_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Create index for access log
CREATE INDEX IF NOT EXISTS idx_spotplayer_log_user ON spotplayer_access_log(user_id);
CREATE INDEX IF NOT EXISTS idx_spotplayer_log_purchase ON spotplayer_access_log(purchase_id);
CREATE INDEX IF NOT EXISTS idx_spotplayer_log_created ON spotplayer_access_log(created_at);
