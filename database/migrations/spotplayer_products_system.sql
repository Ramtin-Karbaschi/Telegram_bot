-- Migration: SpotPlayer Products System
-- Description: Creates tables for multiple SpotPlayer products with different prices

-- Drop old tables if exists (for clean migration)
DROP TABLE IF EXISTS spotplayer_purchases_old;
DROP TABLE IF EXISTS spotplayer_config_old;
DROP TABLE IF EXISTS spotplayer_access_log_old;

-- Rename existing tables if they exist (backup)
ALTER TABLE spotplayer_purchases RENAME TO spotplayer_purchases_old;
ALTER TABLE spotplayer_config RENAME TO spotplayer_config_old;
ALTER TABLE spotplayer_access_log RENAME TO spotplayer_access_log_old;

-- Create SpotPlayer products table
CREATE TABLE IF NOT EXISTS spotplayer_products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    price INTEGER NOT NULL,  -- Price in Rials
    spotplayer_course_id TEXT NOT NULL,  -- SpotPlayer course identifier
    subscription_days INTEGER NOT NULL,  -- Subscription duration
    channel_id TEXT NOT NULL,  -- Telegram channel ID
    channel_username TEXT,  -- Channel username for display
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create SpotPlayer purchases table
CREATE TABLE IF NOT EXISTS spotplayer_purchases (
    purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    tracking_code TEXT NOT NULL UNIQUE,
    amount INTEGER NOT NULL,  -- Actual amount paid
    spotplayer_key TEXT NOT NULL UNIQUE,
    payment_data TEXT,  -- JSON data from Zarinpal
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (product_id) REFERENCES spotplayer_products(product_id)
);

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

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_spotplayer_purchases_user ON spotplayer_purchases(user_id);
CREATE INDEX IF NOT EXISTS idx_spotplayer_purchases_tracking ON spotplayer_purchases(tracking_code);
CREATE INDEX IF NOT EXISTS idx_spotplayer_purchases_product ON spotplayer_purchases(product_id);
CREATE INDEX IF NOT EXISTS idx_spotplayer_products_price ON spotplayer_products(price);
CREATE INDEX IF NOT EXISTS idx_spotplayer_products_active ON spotplayer_products(is_active);
CREATE INDEX IF NOT EXISTS idx_spotplayer_log_user ON spotplayer_access_log(user_id);
CREATE INDEX IF NOT EXISTS idx_spotplayer_log_created ON spotplayer_access_log(created_at);

-- Insert example products (replace with your actual products)
INSERT OR IGNORE INTO spotplayer_products 
(name, description, price, spotplayer_course_id, subscription_days, channel_id, channel_username) 
VALUES
('هایپربول', 'دوره آموزشی هایپربول', 50000, 'hyperbole_course', 120, '-1001234567890', '@vip_channel'),
('فارکس', 'دوره آموزشی فارکس', 1000, 'forex_course', 90, '-1009876543210', '@forex_channel');

-- Note: Update the channel_id values with your actual channel IDs from .env file
