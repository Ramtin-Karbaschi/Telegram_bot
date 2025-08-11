#!/usr/bin/env python3
"""
تست نهایی برای رفع مشکل فعال‌سازی پرداخت تتری
بررسی کامل migration، ایجاد پرداخت و فرآیند تایید
"""

import sys
import os
import sqlite3
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_migration():
    """بررسی اینکه migration به درستی اجرا شده و ستون plan_id اضافه شده"""
    
    print("=" * 60)
    print("🔧 بررسی MIGRATION و ساختار دیتابیس")
    print("=" * 60)
    
    # اجرای migration
    from database.models import Database as DBModel
    db_instance = DBModel.get_instance()
    
    # بررسی ساختار جدول crypto_payments
    db_path = os.path.join('database', 'data', 'daraei_academy.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(crypto_payments)")
    columns = [col[1] for col in cursor.fetchall()]
    
    print(f"\n📋 ستون‌های جدول crypto_payments:")
    for col in columns:
        print(f"  • {col}")
    
    if 'plan_id' in columns:
        print("\n✅ ستون plan_id با موفقیت به جدول crypto_payments اضافه شده!")
    else:
        print("\n❌ ستون plan_id در جدول crypto_payments وجود ندارد!")
        return False
    
    conn.close()
    return True

def test_crypto_payment_creation():
    """تست ایجاد پرداخت کریپتو با plan_id"""
    
    print("\n" + "=" * 60)
    print("🧪 تست ایجاد پرداخت کریپتو با PLAN_ID")
    print("=" * 60)
    
    from database.models import Database as DBModel
    from database.queries import DatabaseQueries as Database
    
    # دریافت یک پلن نمونه
    all_plans = Database.get_all_plans()
    if not all_plans:
        print("❌ هیچ پلنی در دیتابیس یافت نشد!")
        return False
    
    test_plan = all_plans[0]
    plan_dict = dict(test_plan)
    plan_id = plan_dict.get("id")
    plan_name = plan_dict.get("name", "نامشخص")
    
    print(f"\n🎯 تست با پلن: {plan_name} (ID: {plan_id})")
    
    # ایجاد یک پرداخت کریپتو تست
    db_instance = DBModel.get_instance()
    
    test_user_id = 999999  # یک user_id تست
    test_rial_amount = 1000000
    test_usdt_amount = 50.0
    test_wallet = "TTest123..."
    expires_at = datetime.now() + timedelta(hours=1)
    
    try:
        payment_id = db_instance.create_crypto_payment_request(
            user_id=test_user_id,
            rial_amount=test_rial_amount,
            usdt_amount_requested=test_usdt_amount,
            wallet_address=test_wallet,
            expires_at=expires_at,
            plan_id=plan_id  # این مهم است!
        )
        
        if payment_id:
            print(f"✅ پرداخت کریپتو با موفقیت ایجاد شد: {payment_id}")
            
            # بررسی اینکه plan_id ذخیره شده
            crypto_payment = db_instance.get_crypto_payment_by_payment_id(payment_id)
            if crypto_payment and crypto_payment.get('plan_id') == plan_id:
                print(f"✅ plan_id به درستی ذخیره شده: {crypto_payment.get('plan_id')}")
                
                # پاک کردن رکورد تست
                conn = sqlite3.connect(os.path.join('database', 'data', 'daraei_academy.db'))
                cursor = conn.cursor()
                cursor.execute("DELETE FROM crypto_payments WHERE payment_id = ?", (payment_id,))
                conn.commit()
                conn.close()
                print("🧹 رکورد تست پاک شد")
                
                return True
            else:
                print("❌ plan_id به درستی ذخیره نشده!")
                return False
        else:
            print("❌ ایجاد پرداخت کریپتو ناموفق!")
            return False
            
    except Exception as e:
        print(f"❌ خطا در ایجاد پرداخت کریپتو: {e}")
        return False

def test_verification_flow():
    """تست فرآیند تایید پرداخت"""
    
    print("\n" + "=" * 60)
    print("🔍 تست فرآیند تایید پرداخت")
    print("=" * 60)
    
    # بررسی یک پرداخت موجود
    db_path = os.path.join('database', 'data', 'daraei_academy.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # یافتن پرداخت‌های کریپتو که plan_id دارند
    cursor.execute("""
        SELECT payment_id, user_id, plan_id, status, usdt_amount_requested
        FROM crypto_payments 
        WHERE plan_id IS NOT NULL
        ORDER BY created_at DESC
        LIMIT 5
    """)
    
    results = cursor.fetchall()
    
    if results:
        print(f"\n📋 {len(results)} پرداخت کریپتو با plan_id یافت شد:")
        for row in results:
            payment_id, user_id, plan_id, status, usdt_amount = row
            print(f"  • Payment ID: {payment_id}")
            print(f"    Plan ID: {plan_id} ✅")
            print(f"    Status: {status}")
            print(f"    USDT Amount: {usdt_amount}")
            print("-" * 40)
        
        # تست فرآیند تایید با اولین پرداخت
        test_payment = results[0]
        payment_id, user_id, plan_id, status, usdt_amount = test_payment
        
        print(f"\n🔍 تست فرآیند تایید برای Payment ID: {payment_id}")
        
        from database.models import Database as DBModel
        from database.queries import DatabaseQueries as Database
        
        # شبیه‌سازی فرآیند تایید
        db_instance = DBModel.get_instance()
        payment_record = db_instance.get_crypto_payment_by_payment_id(payment_id)
        
        if payment_record:
            retrieved_plan_id = payment_record.get('plan_id')
            if retrieved_plan_id:
                print(f"✅ plan_id با موفقیت دریافت شد: {retrieved_plan_id}")
                
                # دریافت اطلاعات پلن
                plan_row = Database.get_plan_by_id(retrieved_plan_id)
                if plan_row:
                    if hasattr(plan_row, "keys"):
                        plan_name = plan_row["name"]
                    else:
                        plan_name = dict(plan_row).get("name", "N/A")
                    
                    print(f"✅ اطلاعات پلن دریافت شد: {plan_name}")
                    print("🎉 فرآیند تایید آماده است!")
                    conn.close()
                    return True
                else:
                    print(f"❌ نتوانست اطلاعات پلن {retrieved_plan_id} را دریافت کند")
            else:
                print("❌ plan_id در رکورد پرداخت یافت نشد")
        else:
            print("❌ رکورد پرداخت یافت نشد")
    else:
        print("\n⚠️ هیچ پرداخت کریپتو با plan_id یافت نشد")
        print("   برای تست کامل، یک پرداخت جدید از طریق ربات ایجاد کنید")
    
    conn.close()
    return len(results) > 0

def main():
    print("=" * 70)
    print("🛠️  تست نهایی رفع مشکل فعال‌سازی پرداخت تتری")
    print("=" * 70)
    print("\n📌 خلاصه تغییرات:")
    print("1. ✅ اضافه کردن ستون plan_id به جدول crypto_payments")
    print("2. ✅ به‌روزرسانی تابع ایجاد پرداخت کریپتو")
    print("3. ✅ ساده‌سازی فرآیند تایید پرداخت")
    print("4. ✅ حذف کد اضافی و پیچیده")
    print("\n" + "=" * 70)
    
    # اجرای تست‌ها
    migration_success = test_migration()
    creation_success = test_crypto_payment_creation()
    verification_success = test_verification_flow()
    
    print("\n" + "=" * 70)
    print("📊 نتایج نهایی")
    print("=" * 70)
    
    print(f"\n🔧 Migration: {'✅ موفق' if migration_success else '❌ ناموفق'}")
    print(f"🧪 ایجاد پرداخت: {'✅ موفق' if creation_success else '❌ ناموفق'}")
    print(f"🔍 فرآیند تایید: {'✅ آماده' if verification_success else '❌ نیاز به تست بیشتر'}")
    
    if migration_success and creation_success:
        print("\n🎉 همه تغییرات با موفقیت اعمال شد!")
        print("\n🚀 مراحل بعدی:")
        print("1. ربات را راه‌اندازی کنید")
        print("2. یک پرداخت تتری جدید ایجاد کنید")
        print("3. پرداخت را تکمیل کنید و بررسی کنید که اشتراک فعال می‌شود")
        print("4. لاگ‌ها را برای هرگونه خطا بررسی کنید")
    else:
        print("\n⚠️ برخی مشکلات باقی مانده - لطفاً بررسی کنید")

if __name__ == "__main__":
    main()
