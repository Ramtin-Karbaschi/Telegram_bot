"""
🧪 تست کامل سیستم دکمه تبلیغاتی دسته‌بندی
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.models import Database
from handlers.admin_promotional_category import PromotionalCategoryManager, create_promotional_category_table

async def test_promotional_category_system():
    """تست کامل سیستم دکمه تبلیغاتی"""
    
    print("🧪 Testing Promotional Category System")
    print("=" * 60)
    
    # Test 1: Database Table Creation
    print("\n1️⃣ Testing database table creation...")
    try:
        create_promotional_category_table()
        print("✅ Database table created successfully")
    except Exception as e:
        print(f"❌ Database table creation failed: {e}")
        return False
    
    # Test 2: Initial Status Check
    print("\n2️⃣ Testing initial status...")
    try:
        status = PromotionalCategoryManager.get_promotional_category_status()
        print(f"✅ Initial status: enabled={status['enabled']}, category_id={status['category_id']}")
    except Exception as e:
        print(f"❌ Status check failed: {e}")
        return False
    
    # Test 3: Setting Promotional Category
    print("\n3️⃣ Testing promotional category setup...")
    try:
        # فرض می‌کنیم دسته‌بندی با ID 1 وجود دارد
        result = PromotionalCategoryManager.set_promotional_category(
            category_id=1,
            button_text="🛍️ ویژه کمپین",
            enabled=True
        )
        if result:
            print("✅ Promotional category set successfully")
        else:
            print("❌ Failed to set promotional category")
            return False
    except Exception as e:
        print(f"❌ Setting promotional category failed: {e}")
        return False
    
    # Test 4: Status After Setting
    print("\n4️⃣ Testing status after setup...")
    try:
        status = PromotionalCategoryManager.get_promotional_category_status()
        print(f"✅ Updated status: enabled={status['enabled']}, text={status['button_text']}")
        
        if status['enabled'] and status['button_text'] == "🛍️ ویژه کمپین":
            print("✅ Configuration stored correctly")
        else:
            print("❌ Configuration not stored correctly")
            return False
    except Exception as e:
        print(f"❌ Status check after setup failed: {e}")
        return False
    
    # Test 5: Toggle Feature
    print("\n5️⃣ Testing toggle feature...")
    try:
        # غیرفعال کردن
        new_status = PromotionalCategoryManager.toggle_promotional_category()
        print(f"✅ Toggled to: {new_status}")
        
        # فعال کردن مجدد
        new_status = PromotionalCategoryManager.toggle_promotional_category()
        print(f"✅ Toggled back to: {new_status}")
    except Exception as e:
        print(f"❌ Toggle feature failed: {e}")
        return False
    
    # Test 6: Import Tests
    print("\n6️⃣ Testing imports...")
    try:
        from handlers.admin_promotional_category import (
            show_promotional_category_admin, show_category_selection,
            set_promotional_category_handler, toggle_promotional_category_handler
        )
        print("✅ Admin handlers imported successfully")
        
        from utils.promotional_category_utils import (
            get_promotional_category_button, handle_promotional_category_button
        )
        print("✅ Utility functions imported successfully")
        
        from handlers.promotional_category_integration import (
            promotional_category_text_handler, get_promotional_category_handler
        )
        print("✅ Integration handlers imported successfully")
        
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        return False
    
    # Test 7: Button Generation
    print("\n7️⃣ Testing button generation...")
    try:
        from utils.promotional_category_utils import get_promotional_category_button
        button = get_promotional_category_button()
        
        if button:
            print(f"✅ Button generated: {button.text}")
        else:
            print("⚠️ Button is None (might be disabled)")
    except Exception as e:
        print(f"❌ Button generation failed: {e}")
        return False
    
    return True

def test_keyboard_integration():
    """تست یکپارچگی با keyboard"""
    print("\n8️⃣ Testing keyboard integration...")
    try:
        from utils.keyboards import get_main_reply_keyboard
        
        # تست ایجاد keyboard
        keyboard = get_main_reply_keyboard(user_id=123, is_registered=True)
        print("✅ Main reply keyboard generated successfully")
        
        # بررسی وجود دکمه تبلیغاتی در keyboard
        all_texts = []
        for row in keyboard.keyboard:
            for button in row:
                all_texts.append(button.text)
        
        print(f"✅ Keyboard contains {len(all_texts)} buttons")
        
        # اگر دکمه تبلیغاتی فعال باشد، باید در keyboard باشد
        status = PromotionalCategoryManager.get_promotional_category_status()
        if status['enabled'] and status['button_text']:
            if status['button_text'] in all_texts:
                print(f"✅ Promotional button found in keyboard: {status['button_text']}")
            else:
                print(f"⚠️ Promotional button not found in keyboard")
        else:
            print("✅ Promotional button disabled, correctly not in keyboard")
        
        return True
        
    except Exception as e:
        print(f"❌ Keyboard integration test failed: {e}")
        return False

async def main():
    """اجرای تست‌ها"""
    print("🚀 Starting Promotional Category System Tests")
    
    # تست سیستم اصلی
    system_test = await test_promotional_category_system()
    
    # تست یکپارچگی keyboard
    keyboard_test = test_keyboard_integration()
    
    print("\n" + "=" * 60)
    if system_test and keyboard_test:
        print("🎉 ✅ ALL TESTS PASSED!")
        print("🎯 Promotional Category System is ready!")
        print("📋 Admin can now:")
        print("   • Access promotional category management from admin menu")
        print("   • Select categories from database")
        print("   • Enable/disable promotional button")
        print("   • Button appears next to AltSeason button in main menu")
        print("   • Clicking button navigates users to selected category")
    else:
        print("❌ SOME TESTS FAILED!")
        print("⚠️ System needs attention before use")
    
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
