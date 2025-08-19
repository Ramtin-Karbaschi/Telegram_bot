#!/usr/bin/env python3
"""
Migration script for product-based channel access control.
This script ensures the database schema supports proper product-channel mapping.
Run this on the server to prepare the database for the new access control system.
"""

import sqlite3
import logging
import json
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def migrate_database(db_path='database/data/daraei_academy.db'):
    """Apply migrations for product-based channel access control."""
    
    if not Path(db_path).exists():
        logger.error(f"Database not found at {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        logger.info("Starting product-channel access migration...")
        
        # Check if channels_json column exists in plans table
        cursor.execute("PRAGMA table_info(plans)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'channels_json' not in columns:
            logger.info("Adding channels_json column to plans table...")
            cursor.execute("""
                ALTER TABLE plans 
                ADD COLUMN channels_json TEXT
            """)
            logger.info("channels_json column added successfully")
        else:
            logger.info("channels_json column already exists")
        
        # Verify subscriptions table has necessary columns
        cursor.execute("PRAGMA table_info(subscriptions)")
        sub_columns = [col[1] for col in cursor.fetchall()]
        
        required_columns = ['user_id', 'plan_id', 'status', 'start_date', 'end_date']
        missing_columns = [col for col in required_columns if col not in sub_columns]
        
        if missing_columns:
            logger.warning(f"Missing columns in subscriptions table: {missing_columns}")
            # Here you would add the missing columns if needed
        else:
            logger.info("Subscriptions table has all required columns")
        
        # Create an index for faster queries if not exists
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_subscriptions_user_plan 
            ON subscriptions(user_id, plan_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_subscriptions_status 
            ON subscriptions(status)
        """)
        logger.info("Database indexes created/verified")
        
        # Check for products without channel assignments
        cursor.execute("""
            SELECT id, name, channels_json 
            FROM plans 
            WHERE is_active = 1
        """)
        plans = cursor.fetchall()
        
        plans_without_channels = []
        for plan_id, plan_name, channels_json in plans:
            if not channels_json or channels_json == 'null':
                plans_without_channels.append((plan_id, plan_name))
        
        if plans_without_channels:
            logger.warning("The following active plans don't have channel assignments:")
            for plan_id, plan_name in plans_without_channels:
                logger.warning(f"  - Plan ID {plan_id}: {plan_name}")
            logger.warning("Please update these plans with their corresponding channel IDs")
        
        # Log current configuration
        cursor.execute("""
            SELECT COUNT(*) FROM plans WHERE is_active = 1
        """)
        active_plans_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM subscriptions WHERE status = 'active'
        """)
        active_subs_count = cursor.fetchone()[0]
        
        logger.info(f"Migration completed successfully!")
        logger.info(f"Active plans: {active_plans_count}")
        logger.info(f"Active subscriptions: {active_subs_count}")
        
        # Add migration record
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            INSERT OR IGNORE INTO migrations (name, applied_at) 
            VALUES (?, ?)
        """, ('product_channel_access_control', datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Migration 'product_channel_access_control' applied successfully")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

def verify_product_channel_mapping(db_path='database/data/daraei_academy.db'):
    """Verify that all products have proper channel mappings."""
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        logger.info("\n=== Verifying Product-Channel Mappings ===")
        
        cursor.execute("""
            SELECT id, name, channels_json 
            FROM plans 
            WHERE is_active = 1
            ORDER BY id
        """)
        
        all_valid = True
        for plan_id, plan_name, channels_json in cursor.fetchall():
            if channels_json:
                try:
                    channels = json.loads(channels_json)
                    if isinstance(channels, list) and len(channels) > 0:
                        channel_ids = [ch.get('id') for ch in channels if isinstance(ch, dict)]
                        logger.info(f"✓ Plan '{plan_name}' (ID: {plan_id}) -> Channels: {channel_ids}")
                    elif isinstance(channels, dict) and 'id' in channels:
                        logger.info(f"✓ Plan '{plan_name}' (ID: {plan_id}) -> Channel: {channels['id']}")
                    else:
                        logger.warning(f"✗ Plan '{plan_name}' (ID: {plan_id}) has invalid channel structure")
                        all_valid = False
                except json.JSONDecodeError:
                    logger.error(f"✗ Plan '{plan_name}' (ID: {plan_id}) has invalid JSON in channels_json")
                    all_valid = False
            else:
                logger.warning(f"✗ Plan '{plan_name}' (ID: {plan_id}) has no channel assignment")
                all_valid = False
        
        conn.close()
        
        if all_valid:
            logger.info("\n✅ All active products have valid channel mappings!")
        else:
            logger.warning("\n⚠️ Some products need channel configuration. Update them in admin panel.")
        
        return all_valid
        
    except Exception as e:
        logger.error(f"Verification failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Product-Based Channel Access Control Migration")
    logger.info("=" * 60)
    
    # Run migration
    if migrate_database():
        # Verify configuration
        verify_product_channel_mapping()
        
        logger.info("\n" + "=" * 60)
        logger.info("IMPORTANT: Next Steps")
        logger.info("=" * 60)
        logger.info("1. Ensure all products have correct channel IDs in channels_json")
        logger.info("2. Restart the bot to apply code changes")
        logger.info("3. Test with a test user to verify access control")
        logger.info("4. Monitor logs for any issues")
    else:
        logger.error("\nMigration failed! Please check the logs and fix any issues.")
