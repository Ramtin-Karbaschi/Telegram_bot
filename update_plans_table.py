import sqlite3

# مسیر فایل دیتابیس خود را در اینجا تنظیم کنید
DATABASE_FILE = r"E:\Learning\AI\Daraie Academy\telegram_bot\database\data\daraei_academy.db"

def add_price_columns_to_plans():
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # دریافت اطلاعات ستون‌های موجود
        cursor.execute("PRAGMA table_info(plans)")
        columns_info = cursor.fetchall()
        columns = [column_info[1] for column_info in columns_info]

        # بررسی و افزودن ستون original_price_irr
        if 'original_price_irr' not in columns:
            print("Adding column 'original_price_irr' to 'plans' table...")
            cursor.execute("ALTER TABLE plans ADD COLUMN original_price_irr REAL")
            print("'original_price_irr' added.")
        else:
            print("'original_price_irr' already exists in 'plans' table.")

        # بررسی و افزودن ستون price_tether
        if 'price_tether' not in columns:
            print("Adding column 'price_tether' to 'plans' table...")
            cursor.execute("ALTER TABLE plans ADD COLUMN price_tether REAL")
            print("'price_tether' added.")
        else:
            print("'price_tether' already exists in 'plans' table.")

        # بررسی و افزودن ستون original_price_usdt
        if 'original_price_usdt' not in columns:
            print("Adding column 'original_price_usdt' to 'plans' table...")
            cursor.execute("ALTER TABLE plans ADD COLUMN original_price_usdt REAL")
            print("'original_price_usdt' added.")
        else:
            print("'original_price_usdt' already exists in 'plans' table.")

        # بررسی و افزودن ستون display_order (چون در کوئری استفاده شده)
        if 'display_order' not in columns:
            print("Adding column 'display_order' to 'plans' table with default 0...")
            cursor.execute("ALTER TABLE plans ADD COLUMN display_order INTEGER DEFAULT 0")
            print("'display_order' added.")
        else:
            print("'display_order' already exists in 'plans' table.")

        conn.commit()
        print("Database schema check/update for 'plans' table completed successfully.")

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
        if conn:
            conn.rollback() # در صورت بروز خطا، تغییرات را بازگردانی کن
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print(f"Attempting to update schema for database: {DATABASE_FILE}")
    add_price_columns_to_plans()
