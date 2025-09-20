#!/usr/bin/env python3
"""
🚨 EMERGENCY RESTART - Skip all pending updates
ریستارت اضطراری با حذف صف پیام‌های قدیمی
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram import Bot
from telegram.ext import Application
from telegram.request import HTTPXRequest
import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def clear_updates():
    """Clear all pending updates from Telegram servers"""
    print("\n" + "="*60)
    print("🚨 EMERGENCY UPDATE CLEAR")
    print("="*60)
    
    # Create bot instance with optimized settings
    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=15.0,
        write_timeout=15.0,
        pool_timeout=10.0,
        connection_pool_size=32,
    )
    
    app = Application.builder().token(config.MAIN_BOT_TOKEN).request(request).build()
    
    try:
        # Initialize the application
        await app.initialize()
        
        # Get and clear all pending updates
        print("📥 Getting pending updates...")
        updates = await app.bot.get_updates(timeout=1)
        
        if updates:
            print(f"⚠️ Found {len(updates)} pending updates")
            
            # Get the last update ID
            last_update_id = updates[-1].update_id
            
            # Clear all updates by getting with offset
            print(f"🗑️ Clearing updates up to ID {last_update_id}...")
            await app.bot.get_updates(offset=last_update_id + 1, timeout=1)
            
            print("✅ All pending updates cleared!")
        else:
            print("✅ No pending updates found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await app.shutdown()

async def main():
    """Main emergency restart function"""
    print("""
╔════════════════════════════════════════════════════════════════╗
║              🚨 EMERGENCY BOT RESTART UTILITY                  ║
║                  ریستارت اضطراری و پاک‌سازی صف                ║
╚════════════════════════════════════════════════════════════════╝
    """)
    
    # Step 1: Remove persistence file
    persistence_files = [
        "database/data/bot_persistence.pkl",
        "bot_persistence.pkl"
    ]
    
    print("\n📁 Removing persistence files...")
    for file in persistence_files:
        if os.path.exists(file):
            try:
                os.remove(file)
                print(f"   ✅ Removed: {file}")
            except Exception as e:
                print(f"   ⚠️ Could not remove {file}: {e}")
    
    # Step 2: Clear Telegram update queue
    await clear_updates()
    
    # Step 3: Clear large log files
    print("\n📝 Clearing log files...")
    log_files = ["bot.log", "bot_activity.log", "debug_purchases.log"]
    for log_file in log_files:
        if os.path.exists(log_file):
            try:
                # Keep only last 100 lines
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.writelines(lines[-100:] if len(lines) > 100 else lines)
                print(f"   ✅ Truncated: {log_file}")
            except Exception as e:
                # If error, just clear the file
                try:
                    open(log_file, 'w').close()
                    print(f"   ✅ Cleared: {log_file}")
                except:
                    print(f"   ⚠️ Could not clear {log_file}")
    
    print("""
╔════════════════════════════════════════════════════════════════╗
║                    ✅ EMERGENCY CLEANUP COMPLETE               ║
╠════════════════════════════════════════════════════════════════╣
║                                                                ║
║  📌 اقدامات انجام شده:                                        ║
║     1. فایل‌های persistence حذف شدند                          ║
║     2. صف پیام‌های Telegram پاک شد                            ║
║     3. لاگ فایل‌ها پاک‌سازی شدند                              ║
║                                                                ║
║  🚀 حالا بات را با دستور زیر شروع کنید:                      ║
║     python run.py                                             ║
║                                                                ║
║  ⚡ بات از پیام‌های جدید شروع خواهد کرد!                     ║
║                                                                ║
╚════════════════════════════════════════════════════════════════╝
    """)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Critical error: {e}")
        sys.exit(1)
