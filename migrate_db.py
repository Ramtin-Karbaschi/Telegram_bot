# migrate_db.py
import sqlite3
import config # برای دسترسی به نام پایگاه داده

DB_NAME = config.DATABASE_NAME

def migrate_subscriptions_table():
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # بررسی اینکه آیا ستون از قبل وجود دارد یا خیر
        cursor.execute("PRAGMA table_info(subscriptions)")
        columns = [column[1] for column in cursor.fetchall()]

        # Define columns to check and add {column_name: column_type}
        columns_to_ensure = {
            'amount_paid': 'REAL',
            'payment_method': 'TEXT',
            'created_at': 'TEXT',
            'updated_at': 'TEXT'
        }

        for col_name, col_type in columns_to_ensure.items():
            if col_name not in columns:
                print(f"Adding '{col_name}' column ({col_type}) to 'subscriptions' table...")
                cursor.execute(f"ALTER TABLE subscriptions ADD COLUMN {col_name} {col_type}")
                conn.commit()
                print(f"'{col_name}' column added successfully.")
            else:
                print(f"'{col_name}' column already exists in 'subscriptions' table.")

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    finally:
        if conn:
            conn.close()

def migrate_plans_table():
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(plans)")
        columns = [column[1] for column in cursor.fetchall()]

        # Define columns to check and add {column_name: column_type}
        columns_to_ensure = {
            'currency': 'TEXT NOT NULL DEFAULT \'IRT\'',
            'days': 'INTEGER NOT NULL DEFAULT 0', # Default 0 to avoid issues if not set immediately
            'description': 'TEXT',
            'is_active': 'BOOLEAN DEFAULT TRUE',
            'created_at': 'TEXT',
            'updated_at': 'TEXT'
        }

        for col_name, col_definition in columns_to_ensure.items():
            if col_name not in columns:
                print(f"Adding '{col_name}' column ({col_definition}) to 'plans' table...")
                # Note: Default values for NOT NULL columns are important if table already has rows
                # For 'days INTEGER NOT NULL', if there are existing rows, they need a value.
                # SQLite adds NULL by default if no DEFAULT clause, which violates NOT NULL for existing rows.
                # Adding 'DEFAULT 0' for 'days' as a safe measure. Adjust if a different default is better.
                # For 'currency TEXT NOT NULL DEFAULT \'IRT\'', the default is already in definition.
                cursor.execute(f"ALTER TABLE plans ADD COLUMN {col_name} {col_definition}")
                conn.commit()
                print(f"'{col_name}' column added successfully.")
            else:
                print(f"'{col_name}' column already exists in 'plans' table.")

    except sqlite3.Error as e:
        print(f"SQLite error in migrate_plans_table: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print(f"Attempting to migrate database: {DB_NAME}")
    migrate_subscriptions_table()
    migrate_plans_table()
    print("Migration attempt finished.")
