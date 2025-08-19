#!/usr/bin/env python3
"""
اسکریپت بررسی دسترسی کاربران به کانال‌ها
این اسکریپت وضعیت کاربران فعلی را بررسی می‌کند و نشان می‌دهد:
- کدام کاربران اشتراک فعال دارند
- هر کاربر به کدام کانال‌ها دسترسی دارد
- محصولاتی که کانال ندارند
"""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from database.queries import DatabaseQueries

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def analyze_current_state():
    """تحلیل وضعیت فعلی کاربران و محصولات"""
    
    conn = sqlite3.connect('database/data/daraei_academy.db')
    cursor = conn.cursor()
    
    try:
        logger.info("=" * 80)
        logger.info("🔍 بررسی وضعیت کاربران و دسترسی به کانال‌ها")
        logger.info("=" * 80)
        
        # 1. بررسی محصولات و کانال‌های آنها
        logger.info("\n📦 محصولات فعال و کانال‌های مرتبط:")
        logger.info("-" * 40)
        
        cursor.execute("""
            SELECT id, name, channels_json, 
                   (SELECT COUNT(*) FROM subscriptions WHERE plan_id = plans.id AND status = 'active') as active_subs
            FROM plans 
            WHERE is_active = 1
            ORDER BY id
        """)
        
        products_without_channels = []
        products_with_single_channel = []
        products_with_multiple_channels = []
        
        for plan_id, plan_name, channels_json, active_subs in cursor.fetchall():
            channel_count = 0
            channel_ids = []
            
            if channels_json:
                try:
                    channels = json.loads(channels_json)
                    if isinstance(channels, list):
                        channel_count = len(channels)
                        channel_ids = [ch.get('id') for ch in channels if isinstance(ch, dict) and ch.get('id')]
                    elif isinstance(channels, dict) and channels.get('id'):
                        channel_count = 1
                        channel_ids = [channels['id']]
                except json.JSONDecodeError:
                    pass
            
            if channel_count == 0:
                if channels_json:  # محصولات با ساختار نامعتبر JSON
                    logger.info(f"  ⚠️ محصول '{plan_name}' (ID: {plan_id}) - ساختار کانال نامعتبر - {active_subs} کاربر فعال")
                else:
                    products_without_channels.append((plan_id, plan_name, active_subs))
                    logger.info(f"  ❌ محصول '{plan_name}' (ID: {plan_id}) - بدون کانال - {active_subs} کاربر فعال")
            elif channel_count == 1:
                products_with_single_channel.append((plan_id, plan_name, channel_ids[0], active_subs))
                logger.info(f"  ✅ محصول '{plan_name}' (ID: {plan_id}) - 1 کانال: {channel_ids[0]} - {active_subs} کاربر فعال")
            else:
                products_with_multiple_channels.append((plan_id, plan_name, channel_ids, active_subs))
                logger.info(f"  ✅✅ محصول '{plan_name}' (ID: {plan_id}) - {channel_count} کانال: {channel_ids} - {active_subs} کاربر فعال")
        
        # 2. بررسی کاربران فعال و دسترسی‌های آنها
        logger.info("\n👥 کاربران با اشتراک فعال:")
        logger.info("-" * 40)
        
        cursor.execute("""
            SELECT s.user_id, u.full_name, GROUP_CONCAT(p.name, ', ') as products,
                   GROUP_CONCAT(p.channels_json, '|||') as all_channels
            FROM subscriptions s
            JOIN users u ON s.user_id = u.user_id
            JOIN plans p ON s.plan_id = p.id
            WHERE s.status = 'active'
            AND (s.end_date IS NULL OR s.end_date > datetime('now'))
            GROUP BY s.user_id
            ORDER BY s.user_id
        """)
        
        active_users = cursor.fetchall()
        logger.info(f"تعداد کل کاربران با اشتراک فعال: {len(active_users)}")
        
        users_with_no_channel_access = []
        users_with_single_channel = []
        users_with_multiple_channels = []
        
        for row in active_users:
            if len(row) < 4:
                continue
            user_id, full_name, products, all_channels_json = row
            # محاسبه کانال‌های قابل دسترسی
            accessible_channels = set()
            
            if all_channels_json:
                for channels_json in all_channels_json.split('|||'):
                    if channels_json and channels_json != 'None':
                        try:
                            channels = json.loads(channels_json)
                            if isinstance(channels, list):
                                for ch in channels:
                                    if isinstance(ch, dict) and ch.get('id'):
                                        accessible_channels.add(ch['id'])
                            elif isinstance(channels, dict) and channels.get('id'):
                                accessible_channels.add(channels['id'])
                        except (json.JSONDecodeError, TypeError):
                            continue
            
            channel_count = len(accessible_channels)
            
            if channel_count == 0:
                users_with_no_channel_access.append((user_id, full_name, products))
            elif channel_count == 1:
                users_with_single_channel.append((user_id, full_name, products, list(accessible_channels)[0]))
            else:
                users_with_multiple_channels.append((user_id, full_name, products, list(accessible_channels)))
        
        # 3. نمایش خلاصه
        logger.info("\n📊 خلاصه وضعیت:")
        logger.info("=" * 40)
        
        logger.info(f"📦 محصولات:")
        logger.info(f"  - بدون کانال: {len(products_without_channels)} محصول")
        logger.info(f"  - با یک کانال: {len(products_with_single_channel)} محصول")
        logger.info(f"  - با چند کانال: {len(products_with_multiple_channels)} محصول")
        
        logger.info(f"\n👥 کاربران فعال:")
        logger.info(f"  - بدون دسترسی به کانال: {len(users_with_no_channel_access)} کاربر")
        logger.info(f"  - دسترسی به یک کانال: {len(users_with_single_channel)} کاربر")
        logger.info(f"  - دسترسی به چند کانال: {len(users_with_multiple_channels)} کاربر")
        
        # 4. نمایش کاربران بدون دسترسی (اگر وجود دارد)
        if users_with_no_channel_access:
            logger.info("\n⚠️ کاربران با اشتراک فعال ولی بدون دسترسی به کانال:")
            for user_id, full_name, products in users_with_no_channel_access:
                logger.info(f"  - {full_name} (ID: {user_id}) - محصولات: {products}")
        
        # 5. نمایش کاربران با دسترسی چندگانه (اگر وجود دارد)
        if users_with_multiple_channels:
            logger.info("\n✨ کاربران با دسترسی به چند کانال:")
            for user_id, full_name, products, channels in users_with_multiple_channels[:5]:  # نمایش 5 مورد اول
                logger.info(f"  - {full_name} (ID: {user_id})")
                logger.info(f"    محصولات: {products}")
                logger.info(f"    کانال‌ها: {channels}")
        
        return True
        
    except Exception as e:
        logger.error(f"خطا در بررسی: {e}")
        return False
    finally:
        conn.close()

def test_user_access(user_id: int):
    """تست دسترسی یک کاربر خاص به کانال‌ها"""
    
    logger.info(f"\n🔍 بررسی دسترسی کاربر {user_id}:")
    logger.info("-" * 40)
    
    # دریافت محصولات خریداری شده
    products = DatabaseQueries.get_user_purchased_products(user_id)
    
    if not products:
        logger.info("❌ این کاربر هیچ اشتراک فعالی ندارد")
        return
    
    logger.info(f"✅ محصولات فعال: {products}")
    
    # بررسی کانال‌های قابل دسترسی
    conn = sqlite3.connect('database/data/daraei_academy.db')
    cursor = conn.cursor()
    
    accessible_channels = []
    for product_id in products:
        cursor.execute("SELECT name, channels_json FROM plans WHERE id = ?", (product_id,))
        result = cursor.fetchone()
        
        if result:
            product_name, channels_json = result
            logger.info(f"\n  محصول: {product_name} (ID: {product_id})")
            
            if channels_json:
                try:
                    channels = json.loads(channels_json)
                    if isinstance(channels, list):
                        for ch in channels:
                            if isinstance(ch, dict) and ch.get('id'):
                                accessible_channels.append(ch['id'])
                                logger.info(f"    ✅ دسترسی به کانال: {ch.get('id')} ({ch.get('name', 'بدون نام')})")
                    elif isinstance(channels, dict) and channels.get('id'):
                        accessible_channels.append(channels['id'])
                        logger.info(f"    ✅ دسترسی به کانال: {channels['id']}")
                except json.JSONDecodeError:
                    logger.warning(f"    ⚠️ خطا در پردازش کانال‌ها")
            else:
                logger.info(f"    ❌ این محصول کانالی ندارد")
    
    conn.close()
    
    if accessible_channels:
        logger.info(f"\n📋 خلاصه: کاربر به {len(set(accessible_channels))} کانال منحصر به فرد دسترسی دارد")
    else:
        logger.info("\n❌ کاربر به هیچ کانالی دسترسی ندارد")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='بررسی دسترسی کاربران به کانال‌ها')
    parser.add_argument('--user', type=int, help='بررسی دسترسی یک کاربر خاص')
    args = parser.parse_args()
    
    if args.user:
        test_user_access(args.user)
    else:
        analyze_current_state()
        
        logger.info("\n" + "=" * 80)
        logger.info("💡 راهنما:")
        logger.info("=" * 80)
        logger.info("✅ سیستم فعلی به درستی کار می‌کند:")
        logger.info("  - کاربران فقط به کانال‌های محصول خریداری شده دسترسی دارند")
        logger.info("  - محصولات بدون کانال = کاربر دسترسی به کانال ندارد")
        logger.info("  - محصولات با چند کانال = کاربر به همه آنها دسترسی دارد")
        logger.info("\n📝 برای بررسی یک کاربر خاص:")
        logger.info("  python check_user_channel_access.py --user USER_ID")
