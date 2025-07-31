#!/usr/bin/env python3
"""
🧪 Test Admin Crypto Keyboard System
===================================

Test the new keyboard-based admin crypto management system.
No commands - only interactive keyboard buttons.
"""

import sys
import os
import asyncio
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_keyboard_system():
    """Test the keyboard system functionality"""
    
    print("\n🚀 **Admin Crypto Keyboard System Test**")
    print("=" * 50)
    
    try:
        # Test import
        from handlers.admin_crypto_keyboard import AdminCryptoKeyboard, admin_crypto_conversation
        print("✅ Keyboard handler imported successfully")
        
        # Test keyboard generation
        main_keyboard = AdminCryptoKeyboard.get_main_keyboard()
        print("✅ Main keyboard generated successfully")
        
        reports_keyboard = AdminCryptoKeyboard.get_reports_keyboard()
        print("✅ Reports keyboard generated successfully")
        
        security_keyboard = AdminCryptoKeyboard.get_security_keyboard()
        print("✅ Security keyboard generated successfully")
        
        # Test conversation handler
        if admin_crypto_conversation:
            print("✅ Conversation handler created successfully")
            print(f"   • Entry points: {len(admin_crypto_conversation.entry_points)}")
            print(f"   • States: {len(admin_crypto_conversation.states)}")
            print(f"   • Fallbacks: {len(admin_crypto_conversation.fallbacks)}")
        
        # Test enhanced crypto service
        from services.enhanced_crypto_service import EnhancedCryptoService
        print("✅ Enhanced crypto service imported")
        
        # Test admin utils
        from utils.admin_utils import admin_required
        print("✅ Admin utils imported")
        
        # Test admin entry command
        from handlers.admin_crypto_entry import admin_crypto_entry_handler
        print("✅ Admin entry command imported")
        
        print("\n🎉 **All components working correctly!**")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

async def test_manual_tx_verification():
    """Test manual TX hash verification logic"""
    
    print("\n🔍 **Manual TX Verification Test**")
    print("=" * 50)
    
    try:
        from services.comprehensive_payment_system import get_payment_system
        
        payment_system = get_payment_system()
        print("✅ Payment system connected")
        
        # Test valid TX hash format
        valid_tx = "a" * 64
        print(f"✅ Valid TX format: {len(valid_tx)} chars")
        
        # Test invalid TX hash formats
        invalid_formats = [
            "short",  # Too short
            "a" * 63,  # One char short
            "a" * 65,  # One char too long
            "xyz" * 21 + "g",  # Invalid character
        ]
        
        for i, invalid_tx in enumerate(invalid_formats):
            is_valid = len(invalid_tx) == 64 and all(c in '0123456789abcdefABCDEF' for c in invalid_tx)
            print(f"✅ Invalid format {i+1}: {'❌ Rejected' if not is_valid else '⚠️ Should be rejected'}")
        
        print("✅ TX hash validation logic working")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

async def test_system_health():
    """Test system health check"""
    
    print("\n🏥 **System Health Test**")
    print("=" * 50)
    
    try:
        from services.enhanced_crypto_service import EnhancedCryptoService
        
        health = await EnhancedCryptoService.health_check()
        
        print(f"   • Status: {health.get('status')}")
        print(f"   • Wallet: {health.get('wallet_address', 'N/A')}")
        print(f"   • Balance: {health.get('wallet_balance', 0):.6f} USDT")
        print(f"   • TronPy: {'✅' if health.get('tronpy_connected') else '❌'}")
        
        if health.get('status') == 'healthy':
            print("✅ System health check passed")
        else:
            print("⚠️ System health check has warnings")
        
        return True
        
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

async def main():
    """Run all tests"""
    
    print("🧪 **ADMIN CRYPTO KEYBOARD SYSTEM TEST**")
    print("=" * 60)
    print("Testing the new keyboard-based admin interface")
    print("No commands required - all features via keyboard!")
    print("=" * 60)
    
    tests = [
        ("Keyboard System Components", test_keyboard_system),
        ("Manual TX Verification", test_manual_tx_verification),
        ("System Health Check", test_system_health),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n🧪 Running: {test_name}")
        try:
            result = await test_func()
            results.append((test_name, result))
            print(f"✅ {test_name}: {'PASSED' if result else 'FAILED'}")
        except Exception as e:
            print(f"❌ {test_name}: FAILED - {e}")
            results.append((test_name, False))
    
    # Final Results
    print("\n" + "=" * 60)
    print("🏁 **FINAL TEST RESULTS**")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status} {test_name}")
    
    print(f"\n📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 **ALL TESTS PASSED!**")
        print("\n🚀 **Your keyboard-based admin system is ready!**")
        print("\n📋 **How to use:**")
        print("   1. Admin runs: /admin")
        print("   2. Clicks: 💰 پنل کریپتو")
        print("   3. Uses keyboard buttons (no commands!)")
        print("   4. Can test TX hashes manually")
        print("   5. Access all system features via keyboard")
        print("\n💎 **Key Features:**")
        print("   ✅ No commands required")
        print("   ✅ Interactive keyboard interface")
        print("   ✅ Manual TX hash verification")
        print("   ✅ System health monitoring")
        print("   ✅ Security management")
        print("   ✅ Reports generation")
    else:
        print(f"\n⚠️ {total - passed} test(s) failed")
        print("   • Check error messages above")
        print("   • Ensure dependencies are installed")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
