#!/usr/bin/env python3
"""Script to check recent bot logs for sales notification attempts"""

import os
import re
from datetime import datetime, timedelta

def check_recent_logs():
    """Check for recent log files and sales notification attempts"""
    
    # Common log file locations
    log_locations = [
        "bot.log",
        "telegram_bot.log", 
        "main_bot.log",
        "logs/bot.log",
        "logs/telegram_bot.log",
        "nohup.out"
    ]
    
    print("🔍 Searching for log files...")
    
    found_logs = []
    for log_file in log_locations:
        if os.path.exists(log_file):
            found_logs.append(log_file)
            print(f"✅ Found: {log_file}")
    
    if not found_logs:
        print("❌ No log files found in common locations")
        print("Log files might be in a different location or logging might not be configured")
        return
    
    # Search for sales notification related logs in the last 24 hours
    yesterday = datetime.now() - timedelta(days=1)
    
    for log_file in found_logs:
        print(f"\n📄 Checking {log_file}...")
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # Look for sales notification related logs
            sales_logs = []
            for line in lines:
                if any(keyword in line.lower() for keyword in [
                    'sales report', 'sale_channel_id', 'گزارش فروش', 
                    'send sales', 'sales message', 'purchase report'
                ]):
                    sales_logs.append(line.strip())
            
            if sales_logs:
                print(f"🎯 Found {len(sales_logs)} sales-related log entries:")
                for log in sales_logs[-10:]:  # Show last 10 entries
                    print(f"  {log}")
            else:
                print("❌ No sales notification logs found")
                
        except Exception as e:
            print(f"❌ Error reading {log_file}: {e}")

if __name__ == "__main__":
    check_recent_logs()
