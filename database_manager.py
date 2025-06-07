# database_manager.py
import os
import sys

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from telegram_bot.database.queries import DatabaseQueries # Adjusted import path
from telegram_bot.config import DATABASE_NAME # Import from config

# --- Optional: Function to add initial plans ---
def add_initial_plans():
    """Adds some predefined plans to the database if they don't exist."""
    plans_data = [
        {"name": "اشتراک ۱ ماهه", "description": "دسترسی کامل به محتوا برای ۱ ماه", "price": 50000, "price_tether": 5, "days": 30, "features": "[]", "is_active": 1, "display_order": 1},
        {"name": "اشتراک ۳ ماهه", "description": "دسترسی کامل به محتوا برای ۳ ماه", "price": 120000, "price_tether": 12, "days": 90, "features": "[]", "is_active": 1, "display_order": 2},
        {"name": "اشتراک ۶ ماهه", "description": "دسترسی کامل به محتوا برای ۶ ماه", "price": 200000, "price_tether": 20, "days": 180, "features": "[]", "is_active": 1, "display_order": 3},
    ]
    
    print("در حال بررسی و افزودن طرح‌های اولیه...")
    existing_plans = DatabaseQueries.get_active_plans()
    existing_plan_names = [p['name'] for p in existing_plans]

    for plan in plans_data:
        if plan['name'] not in existing_plan_names:
            try:
                # This is a simplified add_plan. If you have a proper DatabaseQueries.add_plan, use that.
                db = DatabaseQueries.get_db_connection() # Assuming you have a way to get a raw connection
                if db:
                    cursor = db.cursor()
                    cursor.execute(
                        """INSERT INTO plans (name, description, price, price_tether, days, features, is_active, display_order)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (plan['name'], plan['description'], plan['price'], plan['price_tether'], plan['days'], plan['features'], plan['is_active'], plan['display_order'])
                    )
                    db.commit()
                    print(f"طرح '{plan['name']}' با موفقیت اضافه شد.")
                    db.close()
                else:
                    print(f"خطا: عدم امکان اتصال به پایگاه داده برای افزودن طرح '{plan['name']}'.")
            except Exception as e:
                print(f"خطا در افزودن طرح '{plan['name']}': {e}")
        else:
            print(f"طرح '{plan['name']}' از قبل موجود است.")
# --------------------------------------------------

def main():
    # Correct the path to the database file based on typical project structure
    # Assuming DATABASE_NAME is just the filename, e.g., "daraei_academy.db"
    # And it's located in the root of the project or a specific 'instance' folder.
    # For this example, let's assume it's in the same directory as this script for simplicity if not found elsewhere.
    
    # Path adjustment: If your DATABASE_NAME in models.py is just a filename,
    # you might need to construct the full path to where it's supposed to be.
    # If it's already an absolute path, this adjustment might not be needed.
    # DATABASE_NAME from config.py is already a full path or relative path from project root
    # If DATABASE_NAME is like "database/data/daraei_academy.db"
    db_file_path = os.path.join(project_root, DATABASE_NAME) 
    # Ensure the path is absolute and normalized
    db_file_path = os.path.abspath(db_file_path)

    print(f"مسیر فایل پایگاه داده هدف: {db_file_path}")
    
    # Create the directory for the database if it doesn't exist
    db_dir = os.path.dirname(db_file_path)
    if not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir)
            print(f"پوشه پایگاه داده '{db_dir}' ایجاد شد.")
        except OSError as e:
            print(f"خطا در ایجاد پوشه پایگاه داده '{db_dir}': {e}")
            return

    if os.path.exists(db_file_path):
        print(f"پایگاه داده '{db_file_path}' از قبل موجود است. در حال حذف و ایجاد مجدد...")
        try:
            os.remove(db_file_path)
            print(f"پایگاه داده '{db_file_path}' حذف شد.")
        except OSError as e:
            print(f"خطا در حذف پایگاه داده: {e}")
            # Continue to initialization, as init_database should handle table creation if db exists but is empty
            # or if tables are missing. If os.remove fails due to permissions, init might also fail.
    else:
        print(f"پایگاه داده '{db_file_path}' یافت نشد. در حال ایجاد...")

    print("در حال مقداردهی اولیه پایگاه داده...")
    # Ensure DatabaseQueries is correctly imported and init_database is callable
    if DatabaseQueries.init_database(): # This should create tables if they don't exist
        print("پایگاه داده با موفقیت مقداردهی اولیه شد (جداول ایجاد یا تأیید شدند).")
        
        # --- Optional: Add initial plans after ensuring tables are created ---
        # add_initial_plans() # Uncomment if you have this function and want to use it
        # ---------------------------------------------------------------------
    else:
        print("خطا در مقداردهی اولیه پایگاه داده.")

if __name__ == "__main__":
    # Ensure the script context is correct for imports
    # This is a common pattern if your script is inside a package
    # and needs to import sibling modules or from the parent package.
    # The sys.path modification at the top should handle this for 'telegram_bot.database.queries'
    main()
