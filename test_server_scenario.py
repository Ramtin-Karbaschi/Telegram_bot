#!/usr/bin/env python3
"""
Test simulating exact server scenario where channels_json doesn't exist
"""

import sqlite3
import tempfile
import os
import sys
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_with_patched_database():
    """Test the actual queries with a database without channels_json"""
    
    print("=" * 70)
    print("🧪 تست شبیه‌سازی دقیق محیط سرور")
    print("=" * 70)
    
    # Create test database WITHOUT channels_json
    temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    conn = sqlite3.connect(temp_db.name)
    cursor = conn.cursor()
    
    # Create tables exactly like server (WITHOUT channels_json)
    cursor.execute('''
        CREATE TABLE users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE plans (
            id INTEGER PRIMARY KEY,
            name TEXT,
            price REAL,
            duration_days INTEGER
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE subscriptions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            plan_id INTEGER,
            start_date TEXT,
            end_date TEXT,
            status TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (plan_id) REFERENCES plans(id)
        )
    ''')
    
    # Add real users with active subscriptions
    cursor.execute("INSERT INTO users VALUES (1001, 'ali_user', 'علی')")
    cursor.execute("INSERT INTO users VALUES (1002, 'sara_user', 'سارا')")
    cursor.execute("INSERT INTO users VALUES (1003, 'reza_user', 'رضا')")
    
    cursor.execute("INSERT INTO plans VALUES (1, 'اشتراک ماهانه', 500000, 30)")
    cursor.execute("INSERT INTO plans VALUES (2, 'اشتراک سالانه', 5000000, 365)")
    
    # Active subscriptions (should NOT be kicked)
    future_date = (datetime.now() + timedelta(days=20)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO subscriptions VALUES (1, 1001, 1, '2024-08-01', ?, 'active')", (future_date,))
    cursor.execute("INSERT INTO subscriptions VALUES (2, 1002, 2, '2024-08-01', ?, 'active')", (future_date,))
    
    # Expired subscription (should be kicked)
    past_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO subscriptions VALUES (3, 1003, 1, '2024-07-01', ?, 'active')", (past_date,))
    
    conn.commit()
    conn.close()
    
    # Now test directly with the database queries
    from database import Database
    from database.queries import DatabaseQueries
    
    # Patch to use our test database
    original_connect = Database.connect
    def mock_connect(self):
        self.conn = sqlite3.connect(temp_db.name)
        return True
    Database.connect = mock_connect
    
    try:
        # Simulate checking access for your actual channel
        channel_id = -1001234567890  # Your channel ID
        
        print("\n📊 وضعیت کاربران:")
        print("-" * 50)
        
        # Check each user
        results = []
        for user_id, name in [(1001, 'علی'), (1002, 'سارا'), (1003, 'رضا')]:
            has_access = DatabaseQueries.user_has_access_to_channel(user_id, channel_id)
            status = "✅ دسترسی دارد (کیک نمی‌شود)" if has_access else "❌ دسترسی ندارد (کیک می‌شود)"
            results.append((name, has_access))
            print(f"{name} (ID: {user_id}): {status}")
        
        # Get all authorized users
        print("\n📋 لیست کل کاربران مجاز:")
        print("-" * 50)
        authorized = DatabaseQueries.get_users_with_channel_access(channel_id)
        print(f"IDs: {authorized}")
        
        # Verify results
        assert results[0][1] == True, "علی با اشتراک فعال باید دسترسی داشته باشد!"
        assert results[1][1] == True, "سارا با اشتراک فعال باید دسترسی داشته باشد!"
        assert results[2][1] == False, "رضا با اشتراک منقضی نباید دسترسی داشته باشد!"
        
        print("\n" + "=" * 70)
        print("✅ تست موفقیت‌آمیز!")
        print("=" * 70)
        print("\n✨ نتیجه نهایی:")
        print("• کاربران با اشتراک فعال کیک نمی‌شوند ✅")
        print("• فقط کاربران با اشتراک منقضی کیک می‌شوند ✅")
        print("• سیستم بدون نیاز به ستون channels_json کار می‌کند ✅")
        
        return True
        
    except Exception as e:
        print(f"\n❌ خطا: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        Database.connect = original_connect
        try:
            os.unlink(temp_db.name)
        except:
            pass

if __name__ == "__main__":
    success = test_with_patched_database()
    sys.exit(0 if success else 1)
