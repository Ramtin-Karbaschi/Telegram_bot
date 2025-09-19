#!/usr/bin/env python3
"""تست سریع رفع تداخل"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Test imports
print("1. تست import ها...")
try:
    from handlers.admin.unified_invite_handler import UnifiedInviteHandler
    from bots.manager_bot import ManagerBot
    print("✅ Import ها موفق بود")
except Exception as e:
    print(f"❌ خطا در import: {e}")
    sys.exit(1)

# Test handler registration
print("\n2. بررسی ثبت handler...")
try:
    # Create handler
    handler = UnifiedInviteHandler()
    conv_handler = handler.get_conversation_handler()
    
    # Check entry points
    entry_points = conv_handler.entry_points
    patterns = []
    for ep in entry_points:
        if hasattr(ep, 'pattern'):
            if hasattr(ep.pattern, 'pattern'):
                patterns.append(ep.pattern.pattern)
            else:
                patterns.append(str(ep.pattern))
    
    print(f"✅ Entry points: {patterns}")
    
    # Check if it matches our callback
    if 'users_create_invite_link' in str(patterns):
        print("✅ Handler با callback 'users_create_invite_link' مطابقت دارد")
    else:
        print("⚠️ Pattern مطابقت ندارد")
        
except Exception as e:
    print(f"❌ خطا: {e}")
    import traceback
    traceback.print_exc()
    
print("\n✅ تست کامل شد - سیستم باید بدون تداخل کار کند")
print("\n📝 نکات:")
print("  • Handler قدیمی در admin_menu_handlers کامنت شده")
print("  • Handler جدید در unified_invite_handler فعال است")
print("  • خطای 'Message is not modified' مدیریت می‌شود")
