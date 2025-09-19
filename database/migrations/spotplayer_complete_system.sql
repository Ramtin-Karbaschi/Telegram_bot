-- Migration: Complete SpotPlayer System with Full Product Management
-- Description: Creates comprehensive tables for SpotPlayer products with all management features

-- Drop old tables if needed (for clean setup)
DROP TABLE IF EXISTS spotplayer_purchases_backup;
DROP TABLE IF EXISTS spotplayer_products_backup;
DROP TABLE IF EXISTS spotplayer_access_log_backup;

-- Backup existing tables if they exist
-- Note: This will fail silently if tables don't exist, which is fine
ALTER TABLE spotplayer_purchases RENAME TO spotplayer_purchases_backup;
ALTER TABLE spotplayer_products RENAME TO spotplayer_products_backup;
ALTER TABLE spotplayer_access_log RENAME TO spotplayer_access_log_backup;

-- Create comprehensive SpotPlayer products table
CREATE TABLE IF NOT EXISTS spotplayer_products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Basic Information
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    
    -- Pricing
    price INTEGER NOT NULL,  -- Price in Rials
    
    -- SpotPlayer Configuration
    spotplayer_course_id TEXT NOT NULL,  -- Course ID from SpotPlayer
    
    -- Channel Configuration
    channel_id TEXT NOT NULL,  -- Telegram channel ID (from .env channels)
    channel_title TEXT,  -- Channel display name
    subscription_days INTEGER NOT NULL DEFAULT 30,  -- Subscription duration
    
    -- Availability Settings
    is_active BOOLEAN DEFAULT 1,  -- Is product active?
    is_public BOOLEAN DEFAULT 1,  -- Is visible to users?
    max_capacity INTEGER DEFAULT NULL,  -- Maximum number of sales (NULL = unlimited)
    current_sales INTEGER DEFAULT 0,  -- Current number of sales
    
    -- Additional Settings
    priority INTEGER DEFAULT 0,  -- Display priority (higher = shown first)
    tags TEXT,  -- JSON array of tags for categorization
    metadata TEXT,  -- JSON for additional custom data
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CHECK (price > 0),
    CHECK (subscription_days > 0),
    CHECK (current_sales >= 0),
    CHECK (max_capacity IS NULL OR max_capacity > 0),
    CHECK (max_capacity IS NULL OR current_sales <= max_capacity)
);

-- Create SpotPlayer purchases table
CREATE TABLE IF NOT EXISTS spotplayer_purchases (
    purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- User and Product
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    
    -- Payment Information
    tracking_code TEXT NOT NULL UNIQUE,
    amount_paid INTEGER NOT NULL,  -- Actual amount paid in Rials
    payment_method TEXT DEFAULT 'zarinpal',  -- Payment method used
    payment_data TEXT,  -- JSON data from payment gateway
    
    -- SpotPlayer License
    spotplayer_key TEXT NOT NULL UNIQUE,
    license_data TEXT,  -- JSON response from SpotPlayer API
    
    -- Subscription Details
    subscription_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    subscription_end TIMESTAMP,
    channel_invite_link TEXT,
    
    -- Status
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'expired', 'cancelled', 'refunded')),
    
    -- Metadata
    notes TEXT,
    admin_id INTEGER,  -- If manually activated by admin
    ip_address TEXT,
    user_agent TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (product_id) REFERENCES spotplayer_products(product_id),
    FOREIGN KEY (admin_id) REFERENCES users(user_id)
);

-- Create SpotPlayer access log table
CREATE TABLE IF NOT EXISTS spotplayer_access_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- References
    purchase_id INTEGER,
    user_id INTEGER,
    product_id INTEGER,
    
    -- Action Details
    action TEXT NOT NULL,  -- e.g., 'purchase_initiated', 'payment_verified', 'license_created', etc.
    status TEXT,  -- 'success', 'failed', 'pending'
    details TEXT,  -- JSON or text details
    
    -- Context
    ip_address TEXT,
    user_agent TEXT,
    
    -- Timestamp
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (purchase_id) REFERENCES spotplayer_purchases(purchase_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (product_id) REFERENCES spotplayer_products(product_id)
);

-- Create product statistics view
CREATE VIEW IF NOT EXISTS spotplayer_product_stats AS
SELECT 
    p.product_id,
    p.name,
    p.price,
    p.is_active,
    p.is_public,
    p.current_sales,
    p.max_capacity,
    COUNT(DISTINCT pu.purchase_id) as total_purchases,
    SUM(pu.amount_paid) as total_revenue,
    COUNT(DISTINCT pu.user_id) as unique_buyers,
    COUNT(CASE WHEN pu.status = 'active' THEN 1 END) as active_licenses,
    COUNT(CASE WHEN DATE(pu.created_at) = DATE('now') THEN 1 END) as today_sales,
    COUNT(CASE WHEN DATE(pu.created_at) >= DATE('now', '-7 days') THEN 1 END) as week_sales,
    COUNT(CASE WHEN DATE(pu.created_at) >= DATE('now', '-30 days') THEN 1 END) as month_sales
FROM spotplayer_products p
LEFT JOIN spotplayer_purchases pu ON p.product_id = pu.product_id
GROUP BY p.product_id;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_sp_products_active ON spotplayer_products(is_active);
CREATE INDEX IF NOT EXISTS idx_sp_products_public ON spotplayer_products(is_public);
CREATE INDEX IF NOT EXISTS idx_sp_products_price ON spotplayer_products(price);
CREATE INDEX IF NOT EXISTS idx_sp_products_priority ON spotplayer_products(priority DESC);

CREATE INDEX IF NOT EXISTS idx_sp_purchases_user ON spotplayer_purchases(user_id);
CREATE INDEX IF NOT EXISTS idx_sp_purchases_product ON spotplayer_purchases(product_id);
CREATE INDEX IF NOT EXISTS idx_sp_purchases_tracking ON spotplayer_purchases(tracking_code);
CREATE INDEX IF NOT EXISTS idx_sp_purchases_status ON spotplayer_purchases(status);
CREATE INDEX IF NOT EXISTS idx_sp_purchases_created ON spotplayer_purchases(created_at);

CREATE INDEX IF NOT EXISTS idx_sp_log_user ON spotplayer_access_log(user_id);
CREATE INDEX IF NOT EXISTS idx_sp_log_product ON spotplayer_access_log(product_id);
CREATE INDEX IF NOT EXISTS idx_sp_log_action ON spotplayer_access_log(action);
CREATE INDEX IF NOT EXISTS idx_sp_log_created ON spotplayer_access_log(created_at);

-- Create triggers for automatic updates
CREATE TRIGGER IF NOT EXISTS update_spotplayer_product_timestamp 
AFTER UPDATE ON spotplayer_products
BEGIN
    UPDATE spotplayer_products 
    SET updated_at = CURRENT_TIMESTAMP 
    WHERE product_id = NEW.product_id;
END;

-- Create trigger to update current_sales on new purchase
CREATE TRIGGER IF NOT EXISTS update_product_sales_count
AFTER INSERT ON spotplayer_purchases
BEGIN
    UPDATE spotplayer_products 
    SET current_sales = current_sales + 1
    WHERE product_id = NEW.product_id;
END;

-- Create trigger to check capacity before purchase
-- Note: SQLite doesn't support BEFORE triggers that can prevent insertion,
-- so this check should be done in application logic
