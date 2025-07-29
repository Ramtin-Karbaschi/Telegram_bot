#!/usr/bin/env python3
"""
تست تناقص آمار ادمین پنل
تست می‌کند که آیا آمار دو بخش "📊 آمار کلی" و "📈 آمار اشتراک‌ها" یکسان است
"""

from database.queries import DatabaseQueries

def test_admin_stats_consistency():
    print("🔍 تست تناقص آمار ادمین پنل...\n")
    
    # گرفتن آمار از دو منبع مختلف
    stats1 = DatabaseQueries.get_subscription_stats()
    stats2 = DatabaseQueries.get_sales_stats_per_plan()
    
    # محاسبه مجموع از آمار پلن‌ها
    total_active = sum(s.get('active_subscriptions', 0) for s in stats2)
    total_subs = sum(s.get('total_subscriptions', 0) for s in stats2)
    total_usdt = sum(s.get('total_revenue_usdt', 0) for s in stats2)
    total_irr = sum(s.get('total_revenue_rial', 0) for s in stats2)
    
    print("📊 آمار کلی (get_subscription_stats):")
    print(f"  - کل کاربران: {stats1.get('total_users', 0)}")
    print(f"  - کاربران فعال: {stats1.get('active_subscribers', 0)}")
    print(f"  - کاربران منقضی: {stats1.get('expired_subscribers', 0)}")
    print(f"  - درآمد USDT: {stats1.get('total_revenue_usdt', 0)}")
    print(f"  - درآمد IRR: {stats1.get('total_revenue_irr', 0)}")
    
    print("\n📈 آمار اشتراک‌ها (get_sales_stats_per_plan):")
    print(f"  - کل اشتراک فعال: {total_active}")
    print(f"  - کل اشتراک ثبت‌شده: {total_subs}")  
    print(f"  - درآمد USDT: {total_usdt}")
    print(f"  - درآمد IRR: {total_irr}")
    print(f"  - تعداد پلن‌ها: {len(stats2)}")
    
    print("\n🔍 بررسی تناقض‌ها:")
    
    # بررسی کاربران فعال
    active_match = stats1.get('active_subscribers', 0) == total_active
    print(f"  ✅ کاربران فعال یکسان: {active_match} ({stats1.get('active_subscribers', 0)} vs {total_active})")
    
    # بررسی درآمد USDT
    usdt_match = abs(stats1.get('total_revenue_usdt', 0) - total_usdt) < 0.01  # tolerance برای float
    print(f"  ✅ درآمد USDT یکسان: {usdt_match} ({stats1.get('total_revenue_usdt', 0)} vs {total_usdt})")
    
    # بررسی درآمد IRR
    irr_match = abs(stats1.get('total_revenue_irr', 0) - total_irr) < 1  # tolerance برای IRR
    print(f"  ✅ درآمد IRR یکسان: {irr_match} ({stats1.get('total_revenue_irr', 0)} vs {total_irr})")
    
    print("\n📋 نتیجه:")
    all_consistent = active_match and usdt_match and irr_match
    if all_consistent:
        print("  ✅ همه آمارها منسجم و یکسان هستند!")
    else:
        print("  ❌ هنوز تناقض‌هایی وجود دارد!")
        print("  🔧 نیاز به بررسی بیشتر...")
    
    return all_consistent

if __name__ == "__main__":
    test_admin_stats_consistency()
