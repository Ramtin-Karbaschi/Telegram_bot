#!/usr/bin/env python3
"""
Test to verify backward compatibility when channels_json column doesn't exist
This simulates the server environment where the column wasn't created
"""

import sqlite3
import tempfile
import os
import sys
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.queries import DatabaseQueries

def create_test_db_without_channels():
    """Create a test database WITHOUT channels_json column (like your server)"""
    temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    conn = sqlite3.connect(temp_db.name)
    cursor = conn.cursor()
    
    # Create tables WITHOUT channels_json
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
    
    # Add test data
    cursor.execute("INSERT INTO users VALUES (1001, 'user1', 'کاربر اول')")
    cursor.execute("INSERT INTO users VALUES (1002, 'user2', 'کاربر دوم')")
    cursor.execute("INSERT INTO users VALUES (1003, 'user3', 'کاربر سوم')")
    
    cursor.execute("INSERT INTO plans VALUES (1, 'پلن ماهانه', 100000, 30)")
    cursor.execute("INSERT INTO plans VALUES (2, 'پلن سالانه', 1000000, 365)")
    
    # Active subscriptions
    end_date = (datetime.now() + timedelta(days=15)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO subscriptions VALUES (1, 1001, 1, '2024-01-01', ?, 'active')", (end_date,))
    cursor.execute("INSERT INTO subscriptions VALUES (2, 1002, 2, '2024-01-01', ?, 'active')", (end_date,))
    
    # Expired subscription
    expired_date = (datetime.now() - timedelta(days=5)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT INTO subscriptions VALUES (3, 1003, 1, '2024-01-01', ?, 'active')", (expired_date,))
    
    conn.commit()
    conn.close()
    
    return temp_db.name

def test_backward_compatibility():
    """Test that users with active subscriptions are NOT kicked when channels_json doesn't exist"""
    
    print("=" * 70)
    print("🧪 تست سازگاری با دیتابیس بدون ستون channels_json")
    print("=" * 70)
    
    # Create test database WITHOUT channels_json
    test_db = create_test_db_without_channels()
    
    # Use environment variable to override database path
    import os
    original_env = os.environ.get('DARAEI_DB_PATH')
    os.environ['DARAEI_DB_PATH'] = test_db
    
    # Patch the Database class
    from database import Database
    original_connect = Database.connect
    
    def mock_connect(self):
        self.conn = sqlite3.connect(test_db)
        return True
    
    Database.connect = mock_connect
    
    try:
        # Test channel ID (your old channel)
        channel_id = -1001234567890
        
        print("\n📊 بررسی دسترسی کاربران به کانال قدیمی:")
        print("-" * 50)
        
        # Test user 1001 (active subscription)
        has_access = DatabaseQueries.user_has_access_to_channel(1001, channel_id)
        print(f"کاربر 1001 (اشتراک فعال): {'✅ دسترسی دارد' if has_access else '❌ دسترسی ندارد'}")
        assert has_access, "کاربر با اشتراک فعال باید دسترسی داشته باشد!"
        
        # Test user 1002 (active subscription)
        has_access = DatabaseQueries.user_has_access_to_channel(1002, channel_id)
        print(f"کاربر 1002 (اشتراک فعال): {'✅ دسترسی دارد' if has_access else '❌ دسترسی ندارد'}")
        assert has_access, "کاربر با اشتراک فعال باید دسترسی داشته باشد!"
        
        # Test user 1003 (expired subscription)
        has_access = DatabaseQueries.user_has_access_to_channel(1003, channel_id)
        print(f"کاربر 1003 (اشتراک منقضی): {'✅ دسترسی دارد' if has_access else '❌ دسترسی ندارد'}")
        assert not has_access, "کاربر با اشتراک منقضی نباید دسترسی داشته باشد"
        
        # Test non-existent user
        has_access = DatabaseQueries.user_has_access_to_channel(9999, channel_id)
        print(f"کاربر 9999 (وجود ندارد): {'✅ دسترسی دارد' if has_access else '❌ دسترسی ندارد'}")
        assert not has_access, "کاربر غیرموجود نباید دسترسی داشته باشد"
        
        print("\n📋 لیست کاربران با دسترسی به کانال:")
        print("-" * 50)
        authorized_users = DatabaseQueries.get_users_with_channel_access(channel_id)
        print(f"کاربران مجاز: {authorized_users}")
        assert 1001 in authorized_users, "کاربر 1001 باید در لیست باشد"
        assert 1002 in authorized_users, "کاربر 1002 باید در لیست باشد"
        assert 1003 not in authorized_users, "کاربر 1003 نباید در لیست باشد"
        
        print("\n" + "=" * 70)
        print("✅ تمام تست‌ها با موفقیت انجام شد!")
        print("=" * 70)
        print("\n🎯 نتیجه:")
        print("• کاربران با اشتراک فعال کیک نمی‌شوند")
        print("• کاربران با اشتراک منقضی دسترسی ندارند")
        print("• سیستم با دیتابیس قدیمی (بدون channels_json) سازگار است")
        print("=" * 70)
        
        return True
        
    except AssertionError as e:
        print(f"\n❌ خطا در تست: {e}")
        return False
    except Exception as e:
        print(f"\n❌ خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Restore original path
        database.DB_PATH = original_db_path
        # Clean up temp file
        try:
            os.unlink(test_db)
        except:
            pass

if __name__ == "__main__":
    success = test_backward_compatibility()
    sys.exit(0 if success else 1)
