#!/usr/bin/env python3
"""
تست محاسبه درآمد با داده‌های شبیه‌سازی شده
"""

from database.models import Database
from database.queries import DatabaseQueries

def test_revenue_calculation():
    print("🧪 تست محاسبه درآمد...\n")
    
    db = Database()
    if not db.connect():
        print("❌ خطا در اتصال به دیتابیس")
        return
        
    try:
        cursor = db.conn.cursor()
        
        # 1. ایجاد یک پرداخت موفق آزمایشی IRR
        print("📝 ایجاد پرداخت آزمایشی IRR...")
        cursor.execute("""
            INSERT INTO payments (user_id, plan_id, amount, status, payment_method, created_at)
            VALUES (1, 4, 500000, 'paid', 'rial', datetime('now'))
        """)
        
        # 2. ایجاد یک پرداخت موفق آزمایشی USDT  
        print("📝 ایجاد پرداخت آزمایشی USDT...")
        cursor.execute("""
            INSERT INTO payments (user_id, plan_id, amount, usdt_amount_requested, status, payment_method, created_at)
            VALUES (2, 4, 8800000, 10.5, 'paid', 'crypto', datetime('now'))
        """)
        
        db.conn.commit()
        print("✅ پرداخت‌های آزمایشی ایجاد شدند\n")
        
        # تست آمار بهبود یافته
        print("📊 تست آمار بهبود یافته:")
        stats = DatabaseQueries.get_subscription_stats()
        print(f"  - درآمد IRR: {stats['total_revenue_irr']:,.0f} ریال")
        print(f"  - درآمد USDT: {stats['total_revenue_usdt']:,.2f} USDT")
        
        # تست آمار پلن‌ها
        print("\n📈 تست آمار پلن‌ها:")
        plan_stats = DatabaseQueries.get_sales_stats_per_plan()
        total_irr = sum(s.get('total_revenue_rial', 0) for s in plan_stats)
        total_usdt = sum(s.get('total_revenue_usdt', 0) for s in plan_stats)
        print(f"  - مجموع درآمد IRR: {total_irr:,.0f} ریال")
        print(f"  - مجموع درآمد USDT: {total_usdt:,.2f} USDT")
        
        # بررسی consistency
        print(f"\n🔍 بررسی consistency:")
        irr_match = abs(stats['total_revenue_irr'] - total_irr) < 1
        usdt_match = abs(stats['total_revenue_usdt'] - total_usdt) < 0.01
        print(f"  - IRR consistent: {irr_match} ({stats['total_revenue_irr']:,.0f} vs {total_irr:,.0f})")
        print(f"  - USDT consistent: {usdt_match} ({stats['total_revenue_usdt']:,.2f} vs {total_usdt:,.2f})")
        
        if irr_match and usdt_match:
            print("  ✅ محاسبه درآمد صحیح و consistent است!")
        else:
            print("  ❌ هنوز مشکلی در محاسبه درآمد وجود دارد")
            
        # پاک کردن داده‌های آزمایشی
        print("\n🧹 پاک کردن داده‌های آزمایشی...")
        cursor.execute("DELETE FROM payments WHERE status = 'paid' AND created_at >= datetime('now', '-1 minute')")
        db.conn.commit()
        print("✅ داده‌های آزمایشی پاک شدند")
        
    except Exception as e:
        print(f"❌ خطا: {e}")
        db.conn.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_revenue_calculation()
