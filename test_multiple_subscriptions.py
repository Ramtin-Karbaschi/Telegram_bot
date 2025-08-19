#!/usr/bin/env python3
"""
تست سناریو کاربر با چند اشتراک همزمان با کانال‌های مختلف
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from database.queries import DatabaseQueries

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def cleanup_test_data():
    """پاک کردن داده‌های تست"""
    conn = sqlite3.connect('database/data/daraei_academy.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subscriptions WHERE user_id = 9999")
    cursor.execute("DELETE FROM users WHERE user_id = 9999")
    cursor.execute("DELETE FROM plans WHERE id IN (9001, 9002)")
    conn.commit()
    conn.close()

def test_multiple_subscriptions():
    """تست کاربر با دو اشتراک همزمان"""
    
    logger.info("=" * 70)
    logger.info("🧪 تست سناریو: کاربر با دو اشتراک همزمان با کانال‌های مختلف")
    logger.info("=" * 70)
    
    conn = sqlite3.connect('database/data/daraei_academy.db')
    cursor = conn.cursor()
    
    # پاک کردن داده‌های قبلی
    cleanup_test_data()
    
    # ایجاد محصولات
    channel_a = -1001111111111
    channel_b = -1002222222222
    
    cursor.execute("""
        INSERT INTO plans (id, name, channels_json, days, price, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (9001, "محصول A با کانال A", json.dumps([{"id": channel_a, "name": "کانال A"}]), 30, 100, 1))
    
    cursor.execute("""
        INSERT INTO plans (id, name, channels_json, days, price, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (9002, "محصول B با کانال B", json.dumps([{"id": channel_b, "name": "کانال B"}]), 30, 200, 1))
    
    # ایجاد کاربر
    cursor.execute("""
        INSERT INTO users (user_id, full_name)
        VALUES (?, ?)
    """, (9999, "کاربر تست با دو اشتراک"))
    
    # خرید اول: محصول A (30 روز از امروز)
    end_date_a = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        INSERT INTO subscriptions (user_id, plan_id, status, end_date, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (9999, 9001, 'active', end_date_a, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    
    logger.info("\n📅 سناریو:")
    logger.info(f"  1️⃣ کاربر امروز محصول A خرید (30 روز، کانال A) - انقضا: {end_date_a}")
    
    # خرید دوم: محصول B در همان روز
    end_date_b = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        INSERT INTO subscriptions (user_id, plan_id, status, end_date, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (9999, 9002, 'active', end_date_b, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    
    logger.info(f"  2️⃣ کاربر امروز محصول B خرید (30 روز، کانال B) - انقضا: {end_date_b}")
    
    conn.commit()
    
    # بررسی دسترسی‌ها
    logger.info("\n🔍 بررسی دسترسی‌ها:")
    
    # محصولات خریداری شده
    products = DatabaseQueries.get_user_purchased_products(9999)
    logger.info(f"  محصولات خریداری شده: {products}")
    
    # دسترسی به کانال A
    has_access_a = DatabaseQueries.user_has_access_to_channel(9999, channel_a)
    logger.info(f"  دسترسی به کانال A: {'✅ بله' if has_access_a else '❌ خیر'}")
    
    # دسترسی به کانال B
    has_access_b = DatabaseQueries.user_has_access_to_channel(9999, channel_b)
    logger.info(f"  دسترسی به کانال B: {'✅ بله' if has_access_b else '❌ خیر'}")
    
    # شبیه‌سازی انقضای یک اشتراک
    logger.info("\n⏰ شبیه‌سازی انقضای اشتراک A:")
    past_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        UPDATE subscriptions 
        SET status = 'expired', end_date = ?
        WHERE user_id = 9999 AND plan_id = 9001
    """, (past_date,))
    conn.commit()
    
    # بررسی مجدد دسترسی‌ها
    has_access_a_after = DatabaseQueries.user_has_access_to_channel(9999, channel_a)
    has_access_b_after = DatabaseQueries.user_has_access_to_channel(9999, channel_b)
    
    logger.info(f"  دسترسی به کانال A: {'✅ بله' if has_access_a_after else '❌ خیر'}")
    logger.info(f"  دسترسی به کانال B: {'✅ بله' if has_access_b_after else '❌ خیر'}")
    
    # نتیجه‌گیری
    logger.info("\n" + "=" * 70)
    logger.info("📊 نتیجه:")
    logger.info("=" * 70)
    
    success = (
        len(products) == 2 and
        has_access_a and
        has_access_b and
        not has_access_a_after and
        has_access_b_after
    )
    
    if success:
        logger.info("✅ سیستم به درستی کار می‌کند!")
        logger.info("  • کاربر به هر دو کانال دسترسی داشت")
        logger.info("  • بعد از انقضای اشتراک A، فقط دسترسی به کانال A قطع شد")
        logger.info("  • دسترسی به کانال B همچنان برقرار است")
    else:
        logger.error("❌ مشکل در سیستم!")
    
    # تست حالت پیشرفته: محصول با کانال‌های مشترک
    logger.info("\n" + "=" * 70)
    logger.info("🔬 تست پیشرفته: محصولات با کانال‌های مشترک")
    logger.info("=" * 70)
    
    # ایجاد محصول C که هم کانال A و هم کانال C دارد
    channel_c = -1003333333333
    cursor.execute("""
        INSERT INTO plans (id, name, channels_json, days, price, is_active)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (9003, "محصول C با کانال‌های A و C", json.dumps([
        {"id": channel_a, "name": "کانال A"},
        {"id": channel_c, "name": "کانال C"}
    ]), 60, 300, 1))
    
    # کاربر جدید
    cursor.execute("DELETE FROM subscriptions WHERE user_id = 9998")
    cursor.execute("DELETE FROM users WHERE user_id = 9998")
    cursor.execute("""
        INSERT INTO users (user_id, full_name)
        VALUES (?, ?)
    """, (9998, "کاربر با محصولات مشترک"))
    
    # خرید محصول B (کانال B) و محصول C (کانال‌های A و C)
    cursor.execute("""
        INSERT INTO subscriptions (user_id, plan_id, status, end_date)
        VALUES (?, ?, ?, ?)
    """, (9998, 9002, 'active', (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')))
    
    cursor.execute("""
        INSERT INTO subscriptions (user_id, plan_id, status, end_date)
        VALUES (?, ?, ?, ?)
    """, (9998, 9003, 'active', (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d %H:%M:%S')))
    
    conn.commit()
    
    logger.info("سناریو: کاربر دو محصول خرید:")
    logger.info("  • محصول B: کانال B")
    logger.info("  • محصول C: کانال‌های A و C")
    logger.info("\nانتظار: دسترسی به کانال‌های A، B و C")
    
    access_a = DatabaseQueries.user_has_access_to_channel(9998, channel_a)
    access_b = DatabaseQueries.user_has_access_to_channel(9998, channel_b)
    access_c = DatabaseQueries.user_has_access_to_channel(9998, channel_c)
    
    logger.info(f"\nنتیجه:")
    logger.info(f"  کانال A: {'✅' if access_a else '❌'}")
    logger.info(f"  کانال B: {'✅' if access_b else '❌'}")
    logger.info(f"  کانال C: {'✅' if access_c else '❌'}")
    
    if access_a and access_b and access_c:
        logger.info("\n✅ عالی! سیستم محصولات با کانال‌های مشترک را نیز پشتیبانی می‌کند")
    
    # پاک کردن داده‌های تست
    cleanup_test_data()
    cursor.execute("DELETE FROM users WHERE user_id = 9998")
    cursor.execute("DELETE FROM subscriptions WHERE user_id = 9998")
    cursor.execute("DELETE FROM plans WHERE id = 9003")
    conn.commit()
    conn.close()
    
    return success

if __name__ == "__main__":
    try:
        success = test_multiple_subscriptions()
        exit(0 if success else 1)
    except Exception as e:
        logger.error(f"خطا: {e}")
        cleanup_test_data()
        exit(1)
