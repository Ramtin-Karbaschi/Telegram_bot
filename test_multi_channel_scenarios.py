#!/usr/bin/env python3
"""
تست سناریوهای مختلف دسترسی کاربران به کانال‌ها
این تست اطمینان می‌دهد که:
1. کاربران قدیمی با اشتراک فعال حذف نمی‌شوند
2. کاربران فقط به کانال‌های محصول خریداری شده دسترسی دارند
3. محصولات بدون کانال، با یک کانال، و با چند کانال به درستی کار می‌کنند
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from database.queries import DatabaseQueries

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def cleanup_test_data():
    """پاک کردن داده‌های تست قبلی"""
    conn = sqlite3.connect('database/data/daraei_academy.db')
    cursor = conn.cursor()
    
    # پاک کردن داده‌های تست قبلی
    cursor.execute("DELETE FROM subscriptions WHERE user_id >= 5000")
    cursor.execute("DELETE FROM users WHERE user_id >= 5000")
    cursor.execute("DELETE FROM plans WHERE id >= 5000")
    
    conn.commit()
    conn.close()

def setup_test_data():
    """ایجاد داده‌های تست"""
    conn = sqlite3.connect('database/data/daraei_academy.db')
    cursor = conn.cursor()
    
    cleanup_test_data()
    
    logger.info("🔧 ایجاد داده‌های تست...")
    
    # ایجاد محصولات تست
    test_products = [
        # محصول بدون کانال
        (5001, "محصول بدون کانال", None, 30, 100, 1),
        
        # محصول با یک کانال (کانال قدیمی که کاربران قبلی دارند)
        (5002, "محصول کانال قدیمی", json.dumps([{"id": -1001234567890, "name": "کانال قدیمی"}]), 30, 200, 1),
        
        # محصول با یک کانال جدید
        (5003, "محصول کانال جدید", json.dumps([{"id": -1009999999999, "name": "کانال جدید"}]), 30, 300, 1),
        
        # محصول با چند کانال (هم قدیمی هم جدید)
        (5004, "محصول چند کاناله", json.dumps([
            {"id": -1001234567890, "name": "کانال قدیمی"},
            {"id": -1009999999999, "name": "کانال جدید"}
        ]), 60, 500, 1),
    ]
    
    for product_data in test_products:
        cursor.execute("""
            INSERT INTO plans (id, name, channels_json, days, price, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, product_data)
        logger.info(f"  ✅ محصول '{product_data[1]}' ایجاد شد")
    
    # ایجاد کاربران تست
    test_users = [
        (5001, "کاربر قدیمی با محصول قدیمی"),
        (5002, "کاربر جدید با محصول جدید"),
        (5003, "کاربر با محصول چند کاناله"),
        (5004, "کاربر با محصول بدون کانال"),
        (5005, "کاربر با چند محصول"),
    ]
    
    for user_id, full_name in test_users:
        cursor.execute("""
            INSERT INTO users (user_id, full_name)
            VALUES (?, ?)
        """, (user_id, full_name))
        logger.info(f"  ✅ کاربر '{full_name}' ایجاد شد")
    
    # ایجاد اشتراک‌ها
    future_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    
    test_subscriptions = [
        # کاربر قدیمی با محصول قدیمی (باید به کانال قدیمی دسترسی داشته باشد)
        (5001, 5002, 'active', future_date),
        
        # کاربر جدید با محصول جدید (فقط به کانال جدید دسترسی دارد)
        (5002, 5003, 'active', future_date),
        
        # کاربر با محصول چند کاناله (به هر دو کانال دسترسی دارد)
        (5003, 5004, 'active', future_date),
        
        # کاربر با محصول بدون کانال (به هیچ کانالی دسترسی ندارد)
        (5004, 5001, 'active', future_date),
        
        # کاربر با چند محصول
        (5005, 5002, 'active', future_date),  # کانال قدیمی
        (5005, 5003, 'active', future_date),  # کانال جدید
    ]
    
    for sub_data in test_subscriptions:
        cursor.execute("""
            INSERT INTO subscriptions (user_id, plan_id, status, end_date)
            VALUES (?, ?, ?, ?)
        """, sub_data)
    
    conn.commit()
    conn.close()
    logger.info("✅ داده‌های تست آماده شدند\n")

def test_channel_access():
    """تست دسترسی کاربران به کانال‌ها"""
    
    logger.info("=" * 60)
    logger.info("🧪 تست سناریوهای مختلف دسترسی به کانال")
    logger.info("=" * 60)
    
    # کانال‌های تست
    old_channel = -1001234567890  # کانال قدیمی
    new_channel = -1009999999999  # کانال جدید
    
    test_cases = [
        {
            "user_id": 5001,
            "name": "کاربر قدیمی با محصول قدیمی",
            "tests": [
                (old_channel, True, "باید به کانال قدیمی دسترسی داشته باشد"),
                (new_channel, False, "نباید به کانال جدید دسترسی داشته باشد"),
            ]
        },
        {
            "user_id": 5002,
            "name": "کاربر جدید با محصول جدید",
            "tests": [
                (old_channel, False, "نباید به کانال قدیمی دسترسی داشته باشد"),
                (new_channel, True, "باید به کانال جدید دسترسی داشته باشد"),
            ]
        },
        {
            "user_id": 5003,
            "name": "کاربر با محصول چند کاناله",
            "tests": [
                (old_channel, True, "باید به کانال قدیمی دسترسی داشته باشد"),
                (new_channel, True, "باید به کانال جدید دسترسی داشته باشد"),
            ]
        },
        {
            "user_id": 5004,
            "name": "کاربر با محصول بدون کانال",
            "tests": [
                (old_channel, False, "نباید به هیچ کانالی دسترسی داشته باشد"),
                (new_channel, False, "نباید به هیچ کانالی دسترسی داشته باشد"),
            ]
        },
        {
            "user_id": 5005,
            "name": "کاربر با چند محصول",
            "tests": [
                (old_channel, True, "باید به کانال قدیمی دسترسی داشته باشد (از محصول اول)"),
                (new_channel, True, "باید به کانال جدید دسترسی داشته باشد (از محصول دوم)"),
            ]
        },
    ]
    
    passed = 0
    failed = 0
    
    for test_case in test_cases:
        logger.info(f"\n📋 تست {test_case['name']} (ID: {test_case['user_id']}):")
        
        # نمایش محصولات کاربر
        products = DatabaseQueries.get_user_purchased_products(test_case['user_id'])
        logger.info(f"  محصولات خریداری شده: {products}")
        
        for channel_id, should_have_access, description in test_case['tests']:
            has_access = DatabaseQueries.user_has_access_to_channel(test_case['user_id'], channel_id)
            
            if has_access == should_have_access:
                logger.info(f"  ✅ PASS: {description}")
                passed += 1
            else:
                logger.error(f"  ❌ FAIL: {description}")
                logger.error(f"     Expected: {should_have_access}, Got: {has_access}")
                failed += 1
    
    # تست لیست کاربران مجاز برای هر کانال
    logger.info("\n📋 تست لیست کاربران مجاز برای هر کانال:")
    
    old_channel_users = DatabaseQueries.get_users_with_channel_access(old_channel)
    logger.info(f"  کانال قدیمی: {sorted(old_channel_users)}")
    expected_old = [5001, 5003, 5005]
    if sorted(old_channel_users) == expected_old:
        logger.info(f"  ✅ PASS: کاربران مجاز کانال قدیمی صحیح است")
        passed += 1
    else:
        logger.error(f"  ❌ FAIL: انتظار {expected_old}, دریافت {sorted(old_channel_users)}")
        failed += 1
    
    new_channel_users = DatabaseQueries.get_users_with_channel_access(new_channel)
    logger.info(f"  کانال جدید: {sorted(new_channel_users)}")
    expected_new = [5002, 5003, 5005]
    if sorted(new_channel_users) == expected_new:
        logger.info(f"  ✅ PASS: کاربران مجاز کانال جدید صحیح است")
        passed += 1
    else:
        logger.error(f"  ❌ FAIL: انتظار {expected_new}, دریافت {sorted(new_channel_users)}")
        failed += 1
    
    # نتیجه نهایی
    logger.info("\n" + "=" * 60)
    logger.info("📊 نتیجه تست‌ها")
    logger.info("=" * 60)
    logger.info(f"تعداد کل: {passed + failed}")
    logger.info(f"موفق: {passed}")
    logger.info(f"ناموفق: {failed}")
    
    if failed == 0:
        logger.info("\n✅ همه تست‌ها با موفقیت انجام شد!")
        logger.info("💡 سیستم به درستی کار می‌کند:")
        logger.info("  - کاربران قدیمی حذف نمی‌شوند")
        logger.info("  - هر کاربر فقط به کانال‌های محصول خود دسترسی دارد")
        logger.info("  - محصولات بدون کانال کار می‌کنند")
        logger.info("  - محصولات چند کاناله کار می‌کنند")
    else:
        logger.error(f"\n❌ {failed} تست ناموفق بود!")
    
    return failed == 0

if __name__ == "__main__":
    try:
        setup_test_data()
        success = test_channel_access()
        
        # پاک کردن داده‌های تست
        logger.info("\n🧹 پاک کردن داده‌های تست...")
        cleanup_test_data()
        logger.info("✅ داده‌های تست پاک شدند")
        
        exit(0 if success else 1)
    except Exception as e:
        logger.error(f"خطا در اجرای تست: {e}")
        cleanup_test_data()
        exit(1)
