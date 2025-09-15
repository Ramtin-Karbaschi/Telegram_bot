"""
تست سیستم کد تخفیف تک‌مصرف برای هر کاربر
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.models import Database
from database.queries import DatabaseQueries
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_single_use_discount_system():
    """تست کامل سیستم کد تخفیف تک‌مصرف"""
    
    print("\n" + "="*60)
    print("شروع تست سیستم کد تخفیف تک‌مصرف")
    print("="*60)
    
    # 1. ایجاد یک کد تخفیف تست با قابلیت single_use_per_user
    print("\n1. ایجاد کد تخفیف تست...")
    test_code = f"TEST_SINGLE_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    discount_id = DatabaseQueries.create_discount(
        code=test_code,
        discount_type='percentage',
        value=50.0,  # 50% تخفیف
        start_date=None,
        end_date=(datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
        max_uses=100,
        is_active=True,
        single_use_per_user=True  # این کلید اصلی است
    )
    
    if discount_id:
        print(f"✅ کد تخفیف با ID {discount_id} ایجاد شد")
        print(f"   کد: {test_code}")
        print(f"   نوع: تک‌مصرف برای هر کاربر")
    else:
        print("❌ خطا در ایجاد کد تخفیف")
        return False
    
    # 2. بررسی اطلاعات کد تخفیف
    print("\n2. بررسی اطلاعات کد تخفیف...")
    discount = DatabaseQueries.get_discount_by_id(discount_id)
    if discount:
        discount_dict = dict(discount) if hasattr(discount, 'keys') else discount
        print(f"✅ کد تخفیف بازیابی شد:")
        print(f"   single_use_per_user: {discount_dict.get('single_use_per_user', 'N/A')}")
    else:
        print("❌ خطا در بازیابی کد تخفیف")
        return False
    
    # 3. شبیه‌سازی استفاده کاربر از کد تخفیف
    test_user_id = 12345678  # ID کاربر تست
    test_plan_id = 1  # ID پلن تست
    
    print(f"\n3. شبیه‌سازی استفاده کاربر {test_user_id} از کد تخفیف...")
    
    # بررسی آیا کاربر قبلاً استفاده کرده است
    has_used = DatabaseQueries.has_user_used_discount(test_user_id, discount_id)
    print(f"   کاربر قبلاً استفاده کرده؟ {has_used}")
    
    if not has_used:
        # ثبت استفاده از کد تخفیف
        success = DatabaseQueries.record_discount_usage(
            user_id=test_user_id,
            discount_id=discount_id,
            plan_id=test_plan_id,
            payment_id=None,
            amount_discounted=50000,  # مبلغ تخفیف
            payment_method='test'
        )
        
        if success:
            print("✅ استفاده از کد تخفیف ثبت شد")
            
            # افزایش شمارنده استفاده
            DatabaseQueries.increment_discount_usage(discount_id)
            print("✅ شمارنده استفاده افزایش یافت")
        else:
            print("❌ خطا در ثبت استفاده از کد تخفیف")
    
    # 4. تلاش برای استفاده مجدد توسط همان کاربر
    print(f"\n4. تلاش برای استفاده مجدد توسط همان کاربر...")
    has_used = DatabaseQueries.has_user_used_discount(test_user_id, discount_id)
    
    if has_used:
        print("✅ سیستم به درستی تشخیص داد که کاربر قبلاً استفاده کرده است")
        
        # تلاش برای ثبت مجدد (باید شکست بخورد)
        success = DatabaseQueries.record_discount_usage(
            user_id=test_user_id,
            discount_id=discount_id,
            plan_id=test_plan_id,
            payment_id=None,
            amount_discounted=50000,
            payment_method='test'
        )
        
        if not success:
            print("✅ سیستم به درستی از استفاده مجدد جلوگیری کرد")
        else:
            print("❌ خطا: سیستم اجازه استفاده مجدد داد!")
            return False
    else:
        print("❌ خطا: سیستم نتوانست استفاده قبلی را تشخیص دهد")
        return False
    
    # 5. تست با کاربر دیگر (باید موفق باشد)
    test_user_id_2 = 87654321
    print(f"\n5. تست با کاربر دیگر (ID: {test_user_id_2})...")
    
    has_used = DatabaseQueries.has_user_used_discount(test_user_id_2, discount_id)
    print(f"   کاربر جدید قبلاً استفاده کرده؟ {has_used}")
    
    if not has_used:
        success = DatabaseQueries.record_discount_usage(
            user_id=test_user_id_2,
            discount_id=discount_id,
            plan_id=test_plan_id,
            payment_id=None,
            amount_discounted=75000,
            payment_method='test'
        )
        
        if success:
            print("✅ کاربر جدید توانست از کد تخفیف استفاده کند")
        else:
            print("❌ خطا در ثبت استفاده برای کاربر جدید")
            return False
    
    # 6. بررسی تاریخچه استفاده
    print("\n6. بررسی تاریخچه استفاده از کد تخفیف...")
    history = DatabaseQueries.get_discount_usage_history(discount_id=discount_id)
    
    if history and len(history) >= 2:
        print(f"✅ تاریخچه استفاده: {len(history)} مورد")
        for idx, record in enumerate(history, 1):
            record_dict = dict(record) if hasattr(record, 'keys') else record
            print(f"   {idx}. کاربر {record_dict['user_id']}: {record_dict['amount_discounted']} تومان تخفیف")
    else:
        print(f"⚠️ تاریخچه استفاده: {len(history) if history else 0} مورد")
    
    # 7. پاکسازی داده‌های تست
    print("\n7. پاکسازی داده‌های تست...")
    try:
        db = Database()
        if db.connect():
            # حذف تاریخچه استفاده
            db.execute("DELETE FROM discount_usage_history WHERE discount_id = ?", (discount_id,))
            # حذف کد تخفیف
            db.execute("DELETE FROM discounts WHERE id = ?", (discount_id,))
            db.commit()
            print("✅ داده‌های تست پاک شد")
    except Exception as e:
        print(f"⚠️ خطا در پاکسازی: {e}")
    
    print("\n" + "="*60)
    print("✅ تست با موفقیت انجام شد!")
    print("سیستم کد تخفیف تک‌مصرف به درستی کار می‌کند.")
    print("="*60)
    
    return True

def check_database_structure():
    """بررسی ساختار دیتابیس"""
    print("\n📊 بررسی ساختار دیتابیس...")
    
    db = Database()
    if db.connect():
        cursor = db.conn.cursor()
        
        # بررسی جدول discounts
        cursor.execute("PRAGMA table_info(discounts)")
        discount_cols = [row[1] for row in cursor.fetchall()]
        
        if 'single_use_per_user' in discount_cols:
            print("✅ فیلد single_use_per_user در جدول discounts وجود دارد")
        else:
            print("❌ فیلد single_use_per_user در جدول discounts وجود ندارد")
        
        # بررسی جدول discount_usage_history
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='discount_usage_history'
        """)
        
        if cursor.fetchone():
            print("✅ جدول discount_usage_history وجود دارد")
            
            # بررسی ستون‌های جدول
            cursor.execute("PRAGMA table_info(discount_usage_history)")
            history_cols = [row[1] for row in cursor.fetchall()]
            print(f"   ستون‌ها: {', '.join(history_cols)}")
        else:
            print("❌ جدول discount_usage_history وجود ندارد")
        
        db.close()

if __name__ == "__main__":
    try:
        # ابتدا ساختار دیتابیس را بررسی می‌کنیم
        check_database_structure()
        
        # سپس تست اصلی را اجرا می‌کنیم
        test_single_use_discount_system()
        
    except Exception as e:
        logger.error(f"خطای غیرمنتظره: {e}")
        import traceback
        traceback.print_exc()
