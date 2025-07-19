import sqlite3
import os

# --- Configuration ---
# Please ensure this path points to your actual database file.
DB_FOLDER = os.path.join('database', 'data')
DB_NAME = 'daraei_academy.db'
DB_PATH = os.path.join(DB_FOLDER, DB_NAME)
# -------------------

def migrate():
    """
    Checks the 'plans' table for a 'capacity' column and adds it if it doesn't exist.
    """
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file not found at '{DB_PATH}'. Please check the path in this script.")
        return

    print(f"Connecting to database at '{DB_PATH}'...")
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Get the list of columns in the 'plans' table
        cursor.execute("PRAGMA table_info(plans);")
        columns = [info[1] for info in cursor.fetchall()]

        # Check if 'capacity' column already exists
        if 'capacity' in columns:
            print("'capacity' column already exists in the 'plans' table. No changes needed.")
        else:
            print("Applying migration: Adding 'capacity' column to 'plans' table...")
            # Add the 'capacity' column
            cursor.execute("ALTER TABLE plans ADD COLUMN capacity INTEGER DEFAULT NULL;")
            conn.commit()
            print("Migration successful! The 'capacity' column has been added.")

        # Migration for renaming birth_year to birth_date in users table
        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'birth_year' in columns and 'birth_date' not in columns:
            print("Applying migration: Renaming 'birth_year' to 'birth_date'...")
            try:
                cursor.execute('ALTER TABLE users RENAME COLUMN birth_year TO birth_date')
                conn.commit()
                print("Successfully renamed 'birth_year' to 'birth_date'.")
            except sqlite3.Error as e:
                print(f"Could not rename column 'birth_year': {e}")
                print("This may be due to an older SQLite version. Manual migration may be required.")

    except sqlite3.Error as e:
        print(f"An error occurred: {e}")
    finally:
        if conn:
            try:
                # Migration for users table: add subscription summary columns
                cursor.execute("PRAGMA table_info(users)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'total_subscription_days' not in columns:
                    cursor.execute('ALTER TABLE users ADD COLUMN total_subscription_days INTEGER DEFAULT 0')
                    print("Added 'total_subscription_days' to 'users' table.")
                if 'subscription_expiration_date' not in columns:
                    cursor.execute('ALTER TABLE users ADD COLUMN subscription_expiration_date TEXT')
                    print("Added 'subscription_expiration_date' to 'users' table.")
            except sqlite3.Error as e:
                print(f"Error migrating 'users' table: {e}")

            # Add more migration logic here in the future
            print("Database migration check complete.")
            conn.close()
            print("Database connection closed.")

if __name__ == '__main__':
    migrate()
