#!/usr/bin/env python3
"""
Migration script to add discount_id column to crypto_payments table.
This enables tracking of discount codes used in crypto payments.
"""

import sqlite3
import os
from pathlib import Path

# Get the database path
DB_PATH = Path(__file__).parent / "database" / "data" / "daraei_academy.db"

def migrate_crypto_payments_table():
    """Add discount_id column to crypto_payments table if it doesn't exist."""
    
    if not DB_PATH.exists():
        print(f"Database not found at: {DB_PATH}")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if discount_id column already exists
        cursor.execute("PRAGMA table_info(crypto_payments)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'discount_id' in columns:
            print("✅ discount_id column already exists in crypto_payments table")
            return True
            
        # Add the discount_id column
        cursor.execute("""
            ALTER TABLE crypto_payments 
            ADD COLUMN discount_id INTEGER
        """)
        
        conn.commit()
        print("✅ Successfully added discount_id column to crypto_payments table")
        
        # Verify the column was added
        cursor.execute("PRAGMA table_info(crypto_payments)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'discount_id' in columns:
            print("✅ Migration verified: discount_id column is now present")
            return True
        else:
            print("❌ Migration failed: discount_id column not found after addition")
            return False
            
    except Exception as e:
        print(f"❌ Migration failed with error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("🔄 Starting migration: Adding discount_id to crypto_payments table...")
    success = migrate_crypto_payments_table()
    
    if success:
        print("🎉 Migration completed successfully!")
    else:
        print("💥 Migration failed!")
        exit(1)
