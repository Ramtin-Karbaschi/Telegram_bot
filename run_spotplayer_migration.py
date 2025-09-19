#!/usr/bin/env python3
"""
Run SpotPlayer migration safely
"""

import sqlite3
import os

def run_migration():
    """Run the SpotPlayer migration"""
    
    # Connect to database
    db_path = 'database/data/daraei_academy.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("🔧 Running SpotPlayer Migration...")
    
    try:
        # Check if old tables exist and rename them if needed
        tables_to_backup = ['spotplayer_purchases', 'spotplayer_products', 'spotplayer_access_log']
        
        for table in tables_to_backup:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            if cursor.fetchone():
                print(f"   Backing up {table}...")
                try:
                    cursor.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
                except:
                    pass
        
        # Now run the migration
        with open('database/migrations/spotplayer_complete_system.sql', 'r', encoding='utf-8') as f:
            migration_sql = f.read()
            
        # Remove the problematic ALTER TABLE statements
        lines = migration_sql.split('\n')
        filtered_lines = []
        skip = False
        
        for line in lines:
            if 'ALTER TABLE' in line and 'RENAME TO' in line and '_backup' in line:
                skip = True
                continue
            if skip and ';' in line:
                skip = False
                continue
            if not skip:
                filtered_lines.append(line)
        
        clean_sql = '\n'.join(filtered_lines)
        
        # Execute migration
        cursor.executescript(clean_sql)
        conn.commit()
        
        print("✅ Migration completed successfully!")
        
        # Check what was created
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'spotplayer%'"
        )
        tables = cursor.fetchall()
        
        print(f"\n📋 Created tables:")
        for table in tables:
            print(f"   • {table[0]}")
        
        # Check views
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='view' AND name LIKE 'spotplayer%'"
        )
        views = cursor.fetchall()
        
        if views:
            print(f"\n📊 Created views:")
            for view in views:
                print(f"   • {view[0]}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
        return False
        
    finally:
        conn.close()

if __name__ == "__main__":
    success = run_migration()
    
    if success:
        print("\n✅ SpotPlayer database is ready!")
    else:
        print("\n❌ Migration failed. Check the error above.")
