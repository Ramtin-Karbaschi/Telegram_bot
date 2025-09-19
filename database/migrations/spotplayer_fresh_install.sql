-- Fresh SpotPlayer Installation
-- Safe migration that handles existing tables

-- First, drop any existing backup tables
DROP TABLE IF EXISTS spotplayer_purchases_old;
DROP TABLE IF EXISTS spotplayer_products_old;
DROP TABLE IF EXISTS spotplayer_access_log_old;

-- Drop views if they exist
DROP VIEW IF EXISTS spotplayer_product_stats;

-- Drop existing tables if needed (for clean install)
DROP TABLE IF EXISTS spotplayer_purchases;
DROP TABLE IF EXISTS spotplayer_products;
DROP TABLE IF EXISTS spotplayer_access_log;

-- Create SpotPlayer products table
CREATE TABLE spotplayer_products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- Basic Information
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    
    -- Pricing
    price INTEGER NOT NULL,
    
    -- SpotPlayer Configuration
    spotplayer_course_id TEXT NOT NULL,
    
    -- Channel Configuration
    channel_id TEXT NOT NULL,
    channel_title TEXT,
    subscription_days INTEGER NOT NULL DEFAULT 30,
    
    -- Availability Settings
    is_active BOOLEAN DEFAULT 1,
    is_public BOOLEAN DEFAULT 1,
    max_capacity INTEGER DEFAULT NULL,
    current_sales INTEGER DEFAULT 0,
    
    -- Additional Settings
    priority INTEGER DEFAULT 0,
    tags TEXT,
    metadata TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CHECK (price > 0),
    CHECK (subscription_days > 0),
    CHECK (current_sales >= 0)
);

-- Create SpotPlayer purchases table
CREATE TABLE spotplayer_purchases (
    purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- User and Product
    user_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    
    -- Payment Information
    tracking_code TEXT NOT NULL UNIQUE,
    amount_paid INTEGER NOT NULL,
    payment_method TEXT DEFAULT 'zarinpal',
    payment_data TEXT,
    
    -- SpotPlayer License
    spotplayer_key TEXT NOT NULL UNIQUE,
    license_data TEXT,
    
    -- Subscription Details
    subscription_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    subscription_end TIMESTAMP,
    channel_invite_link TEXT,
    
    -- Status
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'expired', 'cancelled', 'refunded')),
    
    -- Metadata
    notes TEXT,
    admin_id INTEGER,
    ip_address TEXT,
    user_agent TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (product_id) REFERENCES spotplayer_products(product_id)
);

-- Create SpotPlayer access log table
CREATE TABLE spotplayer_access_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- References
    purchase_id INTEGER,
    user_id INTEGER,
    product_id INTEGER,
    
    -- Action Details
    action TEXT NOT NULL,
    status TEXT,
    details TEXT,
    
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
CREATE VIEW spotplayer_product_stats AS
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

-- Create indexes
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
