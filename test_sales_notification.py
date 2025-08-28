#!/usr/bin/env python3
"""Test script to simulate a successful purchase and check sales notification"""

import asyncio
import logging
from datetime import datetime
from telegram import Bot
from telegram.ext import ContextTypes
import config
from database.queries import DatabaseQueries

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MockUpdate:
    def __init__(self, user_id):
        self.effective_user = MockUser(user_id)
        
class MockUser:
    def __init__(self, user_id):
        self.id = user_id
        self.username = "test_user"

class MockContext:
    def __init__(self, bot):
        self.bot = bot
        self.user_data = {}

async def test_sales_notification():
    """Test the sales notification system by simulating a purchase"""
    
    # Initialize bot
    bot = Bot(config.MAIN_BOT_TOKEN)
    await bot.initialize()
    
    try:
        # Check if SALE_CHANNEL_ID is loaded correctly
        print(f"SALE_CHANNEL_ID from config: {config.SALE_CHANNEL_ID}")
        print(f"Type: {type(config.SALE_CHANNEL_ID)}")
        
        if not config.SALE_CHANNEL_ID:
            print("❌ SALE_CHANNEL_ID is not set!")
            return
            
        # Test direct message sending
        test_message = f"""#خرید_تست
━━━━━━━━━━━━━━━
📅 تاریخ: {datetime.now().strftime('%Y/%m/%d')}
👤 کاربر: @test_user
👤 نام کامل: کاربر تست
📦 محصول: محصول تست
💰 مبلغ: 100,000 تومان
━━━━━━━━━━━━━━━"""

        print(f"Attempting to send test sales message to channel {config.SALE_CHANNEL_ID}")
        
        message = await bot.send_message(
            chat_id=config.SALE_CHANNEL_ID,
            text=test_message
        )
        
        print(f"✅ Test sales message sent successfully! Message ID: {message.message_id}")
        
        # Now test the actual subscription handler function
        print("\n--- Testing subscription handler function ---")
        
        from handlers.subscription.subscription_handlers import SubscriptionHandler
        
        # Create mock objects
        mock_update = MockUpdate(123456789)
        mock_context = MockContext(bot)
        
        # Test the function (this will fail because we don't have real user/plan data, but we can see the logs)
        try:
            handler = SubscriptionHandler()
            # This will likely fail, but we want to see if it reaches the sales notification part
            await handler.add_subscription_and_notify(
                user_id=123456789,
                telegram_id=123456789,
                plan_id=1,
                plan_name="تست محصول",
                plan_duration_days=30,
                payment_amount=100000,
                payment_method="zarinpal",
                payment_table_id=None,
                context=mock_context
            )
        except Exception as e:
            print(f"Expected error in subscription handler (no real data): {e}")
            print("Check the logs above to see if sales notification was attempted")
        
    finally:
        await bot.shutdown()

if __name__ == "__main__":
    asyncio.run(test_sales_notification())
