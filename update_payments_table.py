import sqlite3
import os
import logging
from config import DATABASE_NAME # Import DATABASE_NAME from config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def rename_id_column_in_payments(db_path):
    """
    Renames the 'id' column to 'payment_id' in the 'payments' table.
    """
    conn = None
    try:
        logger.info(f"Attempting to connect to database at: {db_path}")
        if not os.path.exists(os.path.dirname(db_path)) and os.path.dirname(db_path):
            logger.info(f"Database directory {os.path.dirname(db_path)} does not exist. Creating it.")
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        logger.info(f"Successfully connected to the database: {db_path}")

        # Check if the 'id' column exists and 'payment_id' does not
        cursor.execute("PRAGMA table_info(payments)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'id' in columns and 'payment_id' not in columns:
            logger.info("Found 'id' column and 'payment_id' column does not exist. Attempting to rename 'id' to 'payment_id'.")
            # In SQLite, renaming a column directly is tricky, especially if it's part of constraints like PRIMARY KEY.
            # The common workaround is to rename the table, create a new table with the correct schema,
            # copy data, and then drop the old table.
            # However, for a simple rename of a column that is a PK, `ALTER TABLE RENAME COLUMN` is available in newer SQLite versions (3.25.0+).
            # We'll try the direct rename first. If it fails, a more complex migration would be needed.
            # For this script, we assume a newer SQLite version or that the operation is permissible.
            # IMPORTANT: Backup your database before running this script if your SQLite version is older.
            cursor.execute("ALTER TABLE payments RENAME COLUMN id TO payment_id")
            conn.commit()
            logger.info("Successfully renamed column 'id' to 'payment_id' in 'payments' table.")
        elif 'payment_id' in columns:
            logger.info("Column 'payment_id' already exists in 'payments' table. No action needed for renaming.")
        elif 'id' not in columns:
            logger.warning("Column 'id' does not exist in 'payments' table. Cannot rename.")
        else:
            logger.info("Condition for renaming 'id' to 'payment_id' not met. Columns: %s", columns)

    except sqlite3.Error as e:
        logger.error(f"SQLite error occurred: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed.")

if __name__ == "__main__":
    if not DATABASE_NAME:
        logger.error("DATABASE_NAME is not defined in config.py or .env. Cannot proceed.")
    else:
        # Construct the absolute path to the database file
        # Assuming config.py is in the root of the project or DATABASE_NAME is an absolute path
        # If DATABASE_NAME is relative, it's relative to where the script is run from,
        # or how it's constructed in config.py
        
        # Get the directory of the current script
        current_script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # If DATABASE_NAME is already an absolute path, use it directly
        if os.path.isabs(DATABASE_NAME):
            db_full_path = DATABASE_NAME
        else:
            # If DATABASE_NAME is relative, assume it's relative to the project root
            # where config.py is located.
            # This logic mirrors how DATABASE_NAME is constructed in config.py
            # For simplicity, if DATABASE_NAME is like "database/data/file.db",
            # we assume the script is run from the project root.
            db_full_path = os.path.join(current_script_dir, DATABASE_NAME)
            
        # Normalize the path to resolve any ".." or "." components
        db_full_path = os.path.normpath(db_full_path)

        logger.info(f"Database path to be used: {db_full_path}")
        if not os.path.isfile(db_full_path) and not DATABASE_NAME.endswith(":memory:"):
             logger.warning(f"Database file {db_full_path} does not exist. The script might not be effective unless the DB is created by the main app first.")
        
        rename_id_column_in_payments(db_full_path)
