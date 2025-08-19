#!/usr/bin/env python3
"""
Migration script to add channels_json column to plans table
This script safely adds the column if it doesn't exist
"""

import sqlite3
import sys
import os
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def add_channels_json_column(db_path='database/data/daraei_academy.db'):
    """Add channels_json column to plans table if it doesn't exist"""
    
    if not os.path.exists(db_path):
        logging.error(f"Database not found at {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if column already exists
        cursor.execute("PRAGMA table_info(plans)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'channels_json' in columns:
            logging.info("✅ channels_json column already exists in plans table")
            return True
        
        # Add the column
        logging.info("Adding channels_json column to plans table...")
        cursor.execute("ALTER TABLE plans ADD COLUMN channels_json TEXT")
        conn.commit()
        
        logging.info("✅ Successfully added channels_json column")
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(plans)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'channels_json' in columns:
            logging.info("✅ Verified: channels_json column now exists")
            
            # Count active subscriptions that won't be affected
            cursor.execute("""
                SELECT COUNT(DISTINCT s.user_id) 
                FROM subscriptions s 
                WHERE s.status = 'active' 
                AND (s.end_date IS NULL OR s.end_date > datetime('now'))
            """)
            active_users = cursor.fetchone()[0]
            logging.info(f"📊 Found {active_users} users with active subscriptions")
            logging.info("These users will maintain their access (backward compatibility)")
            
            return True
        else:
            logging.error("❌ Failed to verify column addition")
            return False
            
    except Exception as e:
        logging.error(f"❌ Error adding column: {e}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    # Allow custom database path as argument
    db_path = sys.argv[1] if len(sys.argv) > 1 else 'database/data/daraei_academy.db'
    
    logging.info("=" * 60)
    logging.info("Starting migration to add channels_json column")
    logging.info("=" * 60)
    
    success = add_channels_json_column(db_path)
    
    if success:
        logging.info("=" * 60)
        logging.info("✅ Migration completed successfully!")
        logging.info("Your users with active subscriptions will NOT be kicked")
        logging.info("The system now supports both legacy and new channel management")
        logging.info("=" * 60)
    else:
        logging.error("=" * 60)
        logging.error("❌ Migration failed - please check the error messages above")
        logging.error("=" * 60)
        sys.exit(1)
