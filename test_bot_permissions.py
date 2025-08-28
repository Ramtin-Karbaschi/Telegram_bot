#!/usr/bin/env python3
"""Test script to check bot permissions in sales channel"""

import asyncio
import config
from telegram import Bot

async def check_bot_permissions():
    bot = Bot(config.MAIN_BOT_TOKEN)
    await bot.initialize()
    
    try:
        # Get bot info
        me = await bot.get_me()
        print(f"Bot ID: {me.id}")
        print(f"Bot username: @{me.username}")
        
        # Check if bot is in the sales channel
        channel_id = config.SALE_CHANNEL_ID
        print(f"Checking permissions in channel: {channel_id}")
        
        try:
            member = await bot.get_chat_member(channel_id, me.id)
            print(f"Bot status in sales channel: {member.status}")
            
            if member.status == 'administrator':
                print("✅ Bot is admin - can send messages")
            elif member.status == 'member':
                print("⚠️ Bot is member - may not be able to send messages")
            else:
                print(f"❌ Bot status '{member.status}' - cannot send messages")
                
        except Exception as e:
            print(f"❌ Error checking bot in channel: {e}")
            print("This usually means the bot is not added to the channel")
            
        # Send a test message only if explicitly enabled via env var
        if os.getenv("ENABLE_SALES_CHANNEL_TEST_MESSAGE", "0") == "1":
            try:
                test_msg = await bot.send_message(
                    chat_id=channel_id,
                    text=f"🔧 تست دسترسی ربات - {datetime.now().strftime('%H:%M:%S')}\n\nاین پیام برای تست عملکرد سیستم گزارش فروش ارسال شده است."
                )
                print(f"✅ Test message sent successfully: {test_msg.message_id}")
            except Exception as e:
                print(f"❌ Failed to send test message: {e}")
        else:
            print("ℹ️ Skipping test message send (ENABLE_SALES_CHANNEL_TEST_MESSAGE != 1)")
            
    finally:
        await bot.shutdown()

if __name__ == "__main__":
    asyncio.run(check_bot_permissions())
