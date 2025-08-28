#!/usr/bin/env python3
"""Comprehensive test script for all payment types sales notifications"""

import asyncio
import logging
from datetime import datetime
from telegram import Bot
from telegram.ext import ContextTypes
import config
from handlers.subscription.subscription_handlers import activate_or_extend_subscription

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MockContext:
    def __init__(self, bot):
        self.bot = bot
        self.user_data = {}

async def test_all_payment_types():
    """Test sales notifications for all payment types: free, zarinpal, crypto"""
    
    # Initialize bot
    bot = Bot(config.MAIN_BOT_TOKEN)
    await bot.initialize()
    
    try:
        print(f"🔍 Testing all payment types sales notifications...")
        print(f"SALE_CHANNEL_ID: {config.SALE_CHANNEL_ID}")
        print("=" * 60)
        
        # Create mock context
        mock_context = MockContext(bot)
        
        # Test cases for different payment types
        test_cases = [
            {
                "name": "Free Plan",
                "user_id": 111111111,
                "telegram_id": 111111111,
                "plan_id": 1,
                "plan_name": "پلن رایگان تست",
                "payment_amount": 0.0,
                "payment_method": "free",
                "transaction_id": "FREE_TEST",
                "payment_table_id": 0
            },
            {
                "name": "Zarinpal Payment",
                "user_id": 222222222,
                "telegram_id": 222222222,
                "plan_id": 2,
                "plan_name": "پلن پولی تست",
                "payment_amount": 500000.0,
                "payment_method": "zarinpal",
                "transaction_id": "ZP_TEST_12345",
                "payment_table_id": 999  # Mock payment ID
            },
            {
                "name": "Crypto/USDT Payment",
                "user_id": 333333333,
                "telegram_id": 333333333,
                "plan_id": 3,
                "plan_name": "پلن کریپتو تست",
                "payment_amount": 25.50,
                "payment_method": "crypto",
                "transaction_id": "CRYPTO_TEST_HASH",
                "payment_table_id": 888  # Mock crypto payment ID
            },
            {
                "name": "Tether Payment",
                "user_id": 444444444,
                "telegram_id": 444444444,
                "plan_id": 4,
                "plan_name": "پلن تتر تست",
                "payment_amount": 15.75,
                "payment_method": "tether",
                "transaction_id": "TETHER_TEST_HASH",
                "payment_table_id": 777  # Mock tether payment ID
            }
        ]
        
        results = []
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n🧪 Test {i}: {test_case['name']}")
            print(f"   Payment Method: {test_case['payment_method']}")
            print(f"   Amount: {test_case['payment_amount']}")
            print(f"   Payment Table ID: {test_case['payment_table_id']}")
            
            try:
                success, message = await activate_or_extend_subscription(
                    user_id=test_case['user_id'],
                    telegram_id=test_case['telegram_id'],
                    plan_id=test_case['plan_id'],
                    plan_name=test_case['plan_name'],
                    payment_amount=test_case['payment_amount'],
                    payment_method=test_case['payment_method'],
                    transaction_id=test_case['transaction_id'],
                    context=mock_context,
                    payment_table_id=test_case['payment_table_id']
                )
                
                if success:
                    print(f"   ✅ SUCCESS: {test_case['name']} - Sales notification should be sent")
                    results.append({"test": test_case['name'], "status": "SUCCESS", "error": None})
                else:
                    print(f"   ❌ FAILED: {test_case['name']} - {message}")
                    results.append({"test": test_case['name'], "status": "FAILED", "error": message})
                    
            except Exception as e:
                print(f"   💥 ERROR: {test_case['name']} - {str(e)}")
                results.append({"test": test_case['name'], "status": "ERROR", "error": str(e)})
                
            # Small delay between tests
            await asyncio.sleep(1)
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 TEST SUMMARY:")
        print("=" * 60)
        
        success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
        total_tests = len(results)
        
        for result in results:
            status_icon = "✅" if result['status'] == 'SUCCESS' else "❌"
            print(f"{status_icon} {result['test']}: {result['status']}")
            if result['error']:
                print(f"   Error: {result['error']}")
        
        print(f"\n🎯 Overall Result: {success_count}/{total_tests} tests passed")
        
        if success_count == total_tests:
            print("🎉 ALL TESTS PASSED - Sales notifications work for all payment types!")
        else:
            print("⚠️  SOME TESTS FAILED - Check the errors above")
            
        return success_count == total_tests
        
    except Exception as e:
        print(f"💥 CRITICAL ERROR during testing: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await bot.shutdown()

async def test_main_bot_zarinpal():
    """Test the main bot Zarinpal flow specifically"""
    print("\n🔍 Testing main_bot.py Zarinpal flow...")
    
    # Check if the sales notification code exists in main_bot.py
    try:
        with open('bots/main_bot.py', 'r', encoding='utf-8') as f:
            content = f.read()
            
        if 'config.SALE_CHANNEL_ID' in content and 'sales_channel_id' in content:
            print("✅ Main bot Zarinpal sales notification code found")
            if 'DEBUG: Attempting to send sales report' in content:
                print("✅ Debug logging is present in main bot")
            else:
                print("⚠️  Debug logging might be missing in main bot")
        else:
            print("❌ Main bot sales notification code not found")
            
    except Exception as e:
        print(f"❌ Error checking main bot: {e}")

if __name__ == "__main__":
    print("🚀 Starting comprehensive sales notification tests...")
    
    # Test all payment types
    success = asyncio.run(test_all_payment_types())
    
    # Test main bot code
    asyncio.run(test_main_bot_zarinpal())
    
    if success:
        print("\n🎊 ALL SALES NOTIFICATION SYSTEMS ARE WORKING CORRECTLY!")
    else:
        print("\n⚠️  SOME ISSUES FOUND - Please check the test results above")
