#!/usr/bin/env python3
"""
🧪 تست سیستم چندین دکمه تبلیغاتی
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handlers.admin_promotional_category import PromotionalCategoryManager

def test_multiple_promotional_buttons():
    """تست اضافه کردن و مدیریت چندین دکمه تبلیغاتی"""
    
    print("🧪 شروع تست سیستم چندین دکمه تبلیغاتی...")
    
    # 1. اضافه کردن دکمه اول
    print("\n1️⃣ اضافه کردن دکمه اول...")
    success1 = PromotionalCategoryManager.add_promotional_button(
        item_id=1,
        button_text="🌟 دوره کوچینگ فیوچرز / ۲۸ میلیون - ویژه!",
        item_name="دوره کوچینگ فیوچرز / ۲۸ میلیون",
        item_type="product"
    )
    print(f"✅ دکمه اول: {'موفق' if success1 else 'ناموفق'}")
    
    # 2. اضافه کردن دکمه دوم
    print("\n2️⃣ اضافه کردن دکمه دوم...")
    success2 = PromotionalCategoryManager.add_promotional_button(
        item_id=2,
        button_text="🚀 پکیج ویژه تریدینگ - محدود!",
        item_name="پکیج ویژه تریدینگ",
        item_type="category"
    )
    print(f"✅ دکمه دوم: {'موفق' if success2 else 'ناموفق'}")
    
    # 3. اضافه کردن دکمه سوم
    print("\n3️⃣ اضافه کردن دکمه سوم...")
    success3 = PromotionalCategoryManager.add_promotional_button(
        item_id=3,
        button_text="💎 دوره VIP - فقط امروز!",
        item_name="دوره VIP",
        item_type="product"
    )
    print(f"✅ دکمه سوم: {'موفق' if success3 else 'ناموفق'}")
    
    # 4. نمایش تمام دکمه‌ها
    print("\n4️⃣ لیست تمام دکمه‌های تبلیغاتی:")
    buttons = PromotionalCategoryManager.get_all_promotional_buttons()
    
    if buttons:
        for i, button in enumerate(buttons, 1):
            status = "✅ فعال" if button['enabled'] else "❌ غیرفعال"
            print(f"   {i}. {status} - {button['item_name']}")
            print(f"      📝 متن: {button['button_text']}")
            print(f"      🏷️ نوع: {button['item_type']}")
            print(f"      🔢 ترتیب: {button['display_order']}")
            print()
    else:
        print("   ❌ هیچ دکمه‌ای یافت نشد!")
    
    # 5. تست غیرفعال کردن یک دکمه
    if buttons and len(buttons) >= 2:
        print(f"5️⃣ غیرفعال کردن دکمه دوم (ID: {buttons[1]['id']})...")
        toggle_success = PromotionalCategoryManager.toggle_promotional_button(buttons[1]['id'])
        print(f"✅ تغییر وضعیت: {'موفق' if toggle_success else 'ناموفق'}")
        
        # نمایش وضعیت جدید
        updated_buttons = PromotionalCategoryManager.get_all_promotional_buttons()
        print(f"   📊 تعداد دکمه‌های فعال: {len(updated_buttons)}")
    
    # 6. تست حذف یک دکمه
    if buttons and len(buttons) >= 3:
        print(f"\n6️⃣ حذف دکمه سوم (ID: {buttons[2]['id']})...")
        delete_success = PromotionalCategoryManager.remove_promotional_button(buttons[2]['id'])
        print(f"✅ حذف دکمه: {'موفق' if delete_success else 'ناموفق'}")
        
        # نمایش وضعیت نهایی
        final_buttons = PromotionalCategoryManager.get_all_promotional_buttons()
        print(f"   📊 تعداد دکمه‌های باقی‌مانده: {len(final_buttons)}")
    
    print("\n🎉 تست کامل شد!")
    print("\n📋 خلاصه نتایج:")
    print(f"   ✅ دکمه‌های اضافه شده: {sum([success1, success2, success3])}")
    print(f"   📊 دکمه‌های فعال نهایی: {len(PromotionalCategoryManager.get_all_promotional_buttons())}")

if __name__ == "__main__":
    test_multiple_promotional_buttons()
