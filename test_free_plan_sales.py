#!/usr/bin/env python3
"""Test script to simulate a free plan activation and check sales notification"""

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

async def test_free_plan_sales_notification():
    """Test the sales notification system for free plan activation"""
    
    # Initialize bot
    bot = Bot(config.MAIN_BOT_TOKEN)
    await bot.initialize()
    
    try:
        print(f"Testing free plan sales notification...")
        print(f"SALE_CHANNEL_ID: {config.SALE_CHANNEL_ID}")
        
        # Create mock context
        mock_context = MockContext(bot)
        
        # Test the activate_or_extend_subscription function with free plan parameters
        print("Calling activate_or_extend_subscription with free plan parameters...")
        
        success, message = await activate_or_extend_subscription(
            user_id=123456789,  # Mock user ID
            telegram_id=123456789,  # Mock telegram ID
            plan_id=1,  # Mock plan ID
            plan_name="تست پلن رایگان",
            payment_amount=0.0,  # Free plan
            payment_method="free",
            transaction_id="FREE_TEST",
            context=mock_context,
            payment_table_id=0  # This was the issue - 0 blocked sales notifications
        )
        
        print(f"Result: success={success}, message={message}")
        
        if success:
            print("✅ Free plan activation completed - check sales channel for notification")
        else:
            print(f"❌ Free plan activation failed: {message}")
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await bot.shutdown()

if __name__ == "__main__":
    asyncio.run(test_free_plan_sales_notification())
