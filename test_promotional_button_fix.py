#!/usr/bin/env python3
"""
تست عملکرد دکمه تبلیغاتی پس از اصلاحات
"""

import sys
import os

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Now import our modules
try:
    from database import Database, DatabaseQueries
    from handlers.admin_promotional_category import PromotionalCategoryManager
except ImportError as e:
    print(f"Import error: {e}")
    print("Current directory:", current_dir)
    print("Python path:", sys.path[:3])
    sys.exit(1)

def test_database_migration():
    """تست migration دیتابیس"""
    print("🔍 Testing database migration...")
    
    try:
        db = Database.get_instance()
        
        # بررسی وجود جدول
        db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='promotional_category_settings'")
        table_exists = db.fetchone() is not None
        print(f"✅ Table exists: {table_exists}")
        
        if table_exists:
            # بررسی ستون‌ها
            db.execute("PRAGMA table_info(promotional_category_settings)")
            columns = [row[1] for row in db.fetchall()]
            print(f"✅ Columns: {columns}")
            
            required_columns = ['item_id', 'item_name', 'item_type']
            missing_columns = [col for col in required_columns if col not in columns]
            
            if missing_columns:
                print(f"❌ Missing columns: {missing_columns}")
                return False
            else:
                print("✅ All required columns exist")
                
        return True
    except Exception as e:
        print(f"❌ Migration test failed: {e}")
        return False

def test_promotional_manager():
    """تست کلاس PromotionalCategoryManager"""
    print("\n🔍 Testing PromotionalCategoryManager...")
    
    try:
        # تست دریافت وضعیت
        status = PromotionalCategoryManager.get_promotional_category_status()
        print(f"✅ Status retrieved: {status}")
        
        # تست تنظیم آیتم تبلیغاتی
        success = PromotionalCategoryManager.set_promotional_item(
            item_id=1,
            button_text="تست دکمه تبلیغاتی",
            item_name="تست آیتم",
            item_type="category",
            enabled=True
        )
        print(f"✅ Set promotional item: {success}")
        
        # تست دوباره دریافت وضعیت
        new_status = PromotionalCategoryManager.get_promotional_category_status()
        print(f"✅ New status: {new_status}")
        
        return True
    except Exception as e:
        print(f"❌ PromotionalCategoryManager test failed: {e}")
        return False

def test_products_retrieval():
    """تست دریافت محصولات"""
    print("\n🔍 Testing products retrieval...")
    
    try:
        # تست دریافت محصولات
        products = DatabaseQueries.get_all_plans()
        print(f"✅ Products count: {len(products) if products else 0}")
        if products:
            first_product = dict(products[0]) if hasattr(products[0], 'keys') else products[0]
            print(f"   First product: {first_product}")
            
            # تست دریافت یک محصول مشخص
            product_id = first_product.get('id')
            if product_id:
                single_product = DatabaseQueries.get_plan_by_id(product_id)
                if single_product:
                    single_dict = dict(single_product) if hasattr(single_product, 'keys') else single_product
                    print(f"   Retrieved single product: {single_dict}")
        
        return True
    except Exception as e:
        print(f"❌ Products test failed: {e}")
        return False

def main():
    print("🚀 Starting promotional button fix tests...\n")
    
    tests = [
        test_database_migration,
        test_promotional_manager,
        test_products_retrieval
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
                print("✅ PASSED\n")
            else:
                failed += 1
                print("❌ FAILED\n")
        except Exception as e:
            failed += 1
            print(f"❌ FAILED with exception: {e}\n")
    
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! Promotional button system should work correctly.")
    else:
        print("⚠️ Some tests failed. Please check the issues above.")

if __name__ == "__main__":
    main()
