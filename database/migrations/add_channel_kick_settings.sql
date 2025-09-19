-- Migration: Add channel kick settings table
-- Date: 2025-01-18
-- Purpose: Allow admins to enable/disable kicking for each channel

CREATE TABLE IF NOT EXISTS channel_kick_settings (
    channel_id BIGINT PRIMARY KEY,
    channel_title TEXT,
    kick_enabled INTEGER DEFAULT 1,  -- 1 = enabled (default), 0 = disabled
    last_modified TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER  -- telegram_id of admin who made the change
);

-- Add index for quick lookup
CREATE INDEX IF NOT EXISTS idx_kick_enabled ON channel_kick_settings(kick_enabled);

-- Insert default settings for existing channels (all enabled by default)
-- These will be populated programmatically when the bot starts
