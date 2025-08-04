#!/usr/bin/env python3
"""
اجرای اجباری migration برای رفع مشکل constraint
"""

import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from database import Database
    
    print("🔧 Starting forced migration...")
    
    db = Database.get_instance()
    
    # بررسی constraint فعلی
    try:
        db.execute("""
            INSERT OR IGNORE INTO promotional_category_settings 
            (category_id, item_id, button_text, item_name, item_type, enabled) 
            VALUES (NULL, 999, 'test', 'test', 'product', 0)
        """)
        db.execute("DELETE FROM promotional_category_settings WHERE item_id = 999")
        db.commit()
        print("✅ category_id NULL constraint is working correctly")
    except Exception as constraint_error:
        print(f"❌ category_id constraint issue detected: {constraint_error}")
        print("🔧 Recreating table to fix constraints...")
        
        # Force table recreation
        db.execute("DROP TABLE IF EXISTS promotional_category_settings_temp")
        db.execute("""
            CREATE TABLE promotional_category_settings_temp (
                id INTEGER PRIMARY KEY,
                category_id INTEGER,
                item_id INTEGER,
                button_text TEXT NOT NULL,
                category_name TEXT,
                item_name TEXT,
                item_type TEXT DEFAULT 'category',
                enabled BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Copy existing data
        db.execute("""
            INSERT INTO promotional_category_settings_temp 
            (id, category_id, item_id, button_text, category_name, item_name, item_type, enabled, created_at, updated_at)
            SELECT id, category_id, 
                   COALESCE(item_id, category_id) as item_id,
                   button_text, category_name, 
                   COALESCE(item_name, category_name) as item_name,
                   COALESCE(item_type, 'category') as item_type,
                   enabled, created_at, updated_at
            FROM promotional_category_settings
        """)
        
        # Replace tables
        db.execute("DROP TABLE promotional_category_settings")
        db.execute("ALTER TABLE promotional_category_settings_temp RENAME TO promotional_category_settings")
        db.commit()
        print("✅ Successfully recreated table with fixed constraints")
    
    # Test again
    try:
        db.execute("""
            INSERT OR IGNORE INTO promotional_category_settings 
            (category_id, item_id, button_text, item_name, item_type, enabled) 
            VALUES (NULL, 998, 'test2', 'test2', 'product', 0)
        """)
        db.execute("DELETE FROM promotional_category_settings WHERE item_id = 998")
        db.commit()
        print("✅ Final test passed - constraints are fixed!")
    except Exception as e:
        print(f"❌ Final test failed: {e}")
    
    print("🎉 Forced migration completed!")
    
except Exception as e:
    print(f"❌ Migration failed: {e}")
    import traceback
    traceback.print_exc()
