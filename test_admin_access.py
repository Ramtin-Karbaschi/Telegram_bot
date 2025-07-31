#!/usr/bin/env python3
"""
🧪 Test Admin Access
===================

Test if admin can access the crypto panel and if all handlers work.
"""

import sys
import os
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_admin_config():
    """Test admin configuration"""
    
    print("🔍 Testing Admin Configuration...")
    
    try:
        import config
        
        print(f"✅ ADMIN_USER_IDS: {getattr(config, 'ADMIN_USER_IDS', 'NOT FOUND')}")
        print(f"✅ ALL_ADMINS_LIST: {getattr(config, 'ALL_ADMINS_LIST', 'NOT FOUND')}")
        
        if hasattr(config, 'ADMIN_USER_IDS') and config.ADMIN_USER_IDS:
            print(f"📊 Number of admins: {len(config.ADMIN_USER_IDS)}")
            for admin_id in config.ADMIN_USER_IDS:
                print(f"   • Admin ID: {admin_id}")
        else:
            print("❌ No admin IDs found! This is the problem!")
            print("\n🔧 Solution: Add admin IDs to your .env file:")
            print('ALL_ADMINS_CONFIG=[{"chat_id": YOUR_TELEGRAM_ID, "alias": "Admin Name", "roles": ["main_bot_error_contact", "manager_bot_admin"]}]')
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing admin config: {e}")
        return False

async def test_handlers():
    """Test if handlers are properly imported"""
    
    print("\n🔍 Testing Handler Imports...")
    
    try:
        from handlers.admin_crypto_keyboard import AdminCryptoKeyboard, admin_crypto_conversation
        print("✅ AdminCryptoKeyboard imported")
        
        from handlers.admin_crypto_entry import admin_crypto_entry_handler
        print("✅ Admin crypto entry handler imported")
        
        from utils.admin_utils import admin_required
        print("✅ Admin utils imported")
        
        return True
        
    except Exception as e:
        print(f"❌ Handler import error: {e}")
        return False

async def test_keyboard_generation():
    """Test keyboard generation"""
    
    print("\n🔍 Testing Keyboard Generation...")
    
    try:
        from handlers.admin_crypto_keyboard import AdminCryptoKeyboard
        
        keyboard = AdminCryptoKeyboard.get_main_keyboard()
        print("✅ Main keyboard generated")
        
        reports_keyboard = AdminCryptoKeyboard.get_reports_keyboard()
        print("✅ Reports keyboard generated")
        
        security_keyboard = AdminCryptoKeyboard.get_security_keyboard()
        print("✅ Security keyboard generated")
        
        return True
        
    except Exception as e:
        print(f"❌ Keyboard generation error: {e}")
        return False

async def main():
    """Run all tests"""
    
    print("🚀 **ADMIN ACCESS DIAGNOSTIC TEST**")
    print("=" * 50)
    
    tests = [
        ("Admin Configuration", test_admin_config),
        ("Handler Imports", test_handlers),
        ("Keyboard Generation", test_keyboard_generation),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}: FAILED - {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 **DIAGNOSTIC SUMMARY**")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status} {test_name}")
    
    print(f"\n📈 Results: {passed}/{total} tests passed")
    
    if passed != total:
        print("\n🔧 **TROUBLESHOOTING STEPS:**")
        print("1. Check if your Telegram ID is in ALL_ADMINS_CONFIG in .env")
        print("2. Restart the bot after making changes")
        print("3. Try /admin command in Telegram")
        print("4. Look for 💰 پنل کریپتو button in admin menu")
        
    print("\n" + "=" * 50)

if __name__ == "__main__":
    asyncio.run(main())
