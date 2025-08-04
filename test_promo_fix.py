#!/usr/bin/env python3
"""
تست سریع برای بررسی وضعیت دکمه تبلیغاتی
"""

import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from database import Database
    from handlers.admin_promotional_category import PromotionalCategoryManager
    
    print("🔍 Testing promotional button system...")
    
    # تست دریافت وضعیت
    status = PromotionalCategoryManager.get_promotional_category_status()
    print(f"✅ Current status: {status}")
    
    # تست تنظیم محصول
    success = PromotionalCategoryManager.set_promotional_item(
        item_id=11,
        button_text="🌟 محصول ویژه - تست!",
        item_name="محصول تست",
        item_type="product",
        enabled=True
    )
    
    print(f"✅ Set product result: {success}")
    
    # بررسی وضعیت جدید
    new_status = PromotionalCategoryManager.get_promotional_category_status()
    print(f"✅ New status: {new_status}")
    
    print("🎉 Test completed successfully!")
    
except Exception as e:
    print(f"❌ Test failed: {e}")
    import traceback
    traceback.print_exc()
