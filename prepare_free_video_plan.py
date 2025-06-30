from datetime import datetime, timedelta
from database.models import Database  # Import the central Database class
import config

# --- Configuration ---
PLAN_NAME = 'ویدئو آموزشی رایگان'
PLAN_DESCRIPTION = 'دریافت پکیج ویدئویی آموزش رایگان تحلیل تکنیکال.'
PLAN_PRICE = 0
PLAN_DURATION = 0  # No duration for one-time content
PLAN_TYPE = 'one_time_content'
CAPACITY = 100  # Set to None for unlimited capacity
# Set expiration date to 30 days from now. Set to None for no expiration.
EXPIRATION_DATE = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
IS_ACTIVE = 1
DISPLAY_ORDER = 99  # Show it at the end of the list

def prepare_plan():
    """Connects to the database using the central Database class and inserts or updates the free video plan."""
    db = None
    try:
        # Instantiate the Database class, which handles the connection logic
        db = Database()
        if not db.connect():
            print("Failed to connect to the database. Aborting.")
            return

        # Check if the plan already exists
        db.execute("SELECT id FROM plans WHERE name = ?", (PLAN_NAME,))
        result = db.fetchone()

        if result:
            # Update existing plan
            plan_id = result['id']
            print(f"Plan '{PLAN_NAME}' already exists with ID {plan_id}. Updating it...")
            update_query = """
                UPDATE plans 
                SET description = ?, price = ?, days = ?, plan_type = ?, capacity = ?, expiration_date = ?, is_active = ?, display_order = ?
                WHERE id = ?
            """
            params = (PLAN_DESCRIPTION, PLAN_PRICE, PLAN_DURATION, PLAN_TYPE, CAPACITY, EXPIRATION_DATE, IS_ACTIVE, DISPLAY_ORDER, plan_id)
            if db.execute(update_query, params):
                db.commit()
                print("Plan updated successfully.")
            else:
                print("Failed to update plan.")
        else:
            # Insert new plan
            print(f"Inserting new plan: '{PLAN_NAME}'")
            insert_query = """
                INSERT INTO plans (name, description, price, days, plan_type, capacity, expiration_date, is_active, display_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (PLAN_NAME, PLAN_DESCRIPTION, PLAN_PRICE, PLAN_DURATION, PLAN_TYPE, CAPACITY, EXPIRATION_DATE, IS_ACTIVE, DISPLAY_ORDER)
            if db.execute(insert_query, params):
                db.commit()
                print("Plan inserted successfully.")
            else:
                print("Failed to insert plan.")

    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        if db:
            db.close()
            print("Database connection closed.")

if __name__ == '__main__':
    print("Preparing the free video educational plan...")
    prepare_plan()
