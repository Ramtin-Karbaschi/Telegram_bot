"""
Database queries for the Daraei Academy Telegram bot
"""

import sqlite3
from datetime import datetime, timedelta
import config
import logging
from database.models import Database
from database.schema import ALL_TABLES
from utils.helpers import get_current_time  # ensure Tehran-tz aware now

class DatabaseQueries:
    """Class for handling database operations"""
    
    @staticmethod
    def init_database():
        """Initialize the database and create tables if they don't exist"""
        db = Database()
        if db.connect():
            result = db.create_tables(ALL_TABLES)
            db.commit()
            db.close()
            return result
        return False
    
    # -----------------------------------
    # Video file caching
    # -----------------------------------
    @staticmethod
    def _ensure_video_table(db):
        """Ensure the video_files table exists."""
        create_sql = """
            CREATE TABLE IF NOT EXISTS video_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT UNIQUE,
                telegram_file_id TEXT
            );
        """
        # Create table if it doesn't exist
        db.execute(create_sql)

        # ------------------------------------------------------------------
        # Lightweight schema-migration guard: make sure crucial columns exist
        # ------------------------------------------------------------------
        # Older versions of the bot may have created the table without the
        # telegram_file_id column or UNIQUE constraint. We inspect the table
        # schema at runtime and patch it if required so that inserts do not
        # fail silently.
        try:
            db.execute("PRAGMA table_info(video_files)")
            columns_info = db.fetchall()  # list[sqlite3.Row]
            existing_columns = {row[1] for row in columns_info}

            # Add telegram_file_id column if it's missing
            if "telegram_file_id" not in existing_columns:
                db.execute("ALTER TABLE video_files ADD COLUMN telegram_file_id TEXT")

            # Ensure file_name column is UNIQUE – if the column already exists
            # but is not UNIQUE we cannot alter easily; in that rare case we
            # leave it as-is because INSERT OR REPLACE will still work, but may
            # store duplicates. A full migration would require copying data to a
            # new table which is out of scope for a runtime patch.
        finally:
            # Persist any DDL changes before continuing
            db.commit()

    @staticmethod
    def get_video_file_id(file_name: str):
        """Return cached telegram_file_id for a local video filename, or None."""
        db = Database()
        if db.connect():
            try:
                DatabaseQueries._ensure_video_table(db)
                db.execute("SELECT telegram_file_id FROM video_files WHERE file_name = ?", (file_name,))
                row = db.fetchone()
                return row[0] if row else None
            finally:
                db.close()
        return None

    @staticmethod
    def save_video_file_id(file_name: str, file_id: str):
        """Upsert telegram_file_id for a given video filename."""
        db = Database()
        if db.connect():
            try:
                DatabaseQueries._ensure_video_table(db)
                # Use INSERT OR REPLACE for wider SQLite compatibility (<3.24 does not support ON CONFLICT ... DO UPDATE)
                db.execute(
                    "INSERT OR REPLACE INTO video_files (file_name, telegram_file_id) VALUES (?, ?)",
                    (file_name, file_id),
                )
                db.commit()
                return True
            except Exception as e:
                logging.error(f"Error saving video file_id for {file_name}: {e}")
            finally:
                db.close()
        return False

    # -----------------------------------
    # User-related queries
    @staticmethod
    def user_exists(user_id):
        """Check if a user exists in the database"""
        db = Database()
        if db.connect():
            db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            result = db.fetchone() is not None
            db.close()
            return result
        return False
    
    @staticmethod
    def add_user(user_id, username=None):
        """Add a new user to the database"""
        db = Database()
        if db.connect():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                "INSERT INTO users (user_id, username, registration_date, last_activity) VALUES (?, ?, ?, ?)",
                (user_id, username, now, now)
            )
            db.commit()
            db.close()
            return True
        return False
    
    @staticmethod
    def update_user_activity(user_id):
        """Update user's last activity timestamp"""
        db = Database()
        if db.connect():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                "UPDATE users SET last_activity = ? WHERE user_id = ?",
                (now, user_id)
            )
            db.commit()
            db.close()
            return True
        return False
    
    @staticmethod
    def get_user_details(user_id):
        """Get user details from database"""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = db.fetchone()
            db.close()
            return result
        return None
    
    @staticmethod
    def update_user_profile(user_id, full_name=None, phone=None, email=None, education=None, city=None, age=None, occupation=None, birth_year=None):
        """Update user profile information"""
        db = Database()
        if db.connect():
            updates = []
            params = []
            
            if full_name is not None:
                updates.append("full_name = ?")
                params.append(full_name)
            if phone is not None:
                updates.append("phone = ?")
                params.append(phone)
            if email is not None:
                updates.append("email = ?")
                params.append(email)
            if education is not None:
                updates.append("education = ?")
                params.append(education)
            if city is not None:
                updates.append("city = ?")
                params.append(city)
            if age is not None:
                updates.append("age = ?")
                params.append(age)
            if occupation is not None:
                updates.append("occupation = ?")
                params.append(occupation)
            if birth_year is not None:
                updates.append("birth_year = ?")
                params.append(birth_year)
            
            if updates:
                query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
                params.append(user_id)
                db.execute(query, tuple(params))
                db.commit()
                db.close()
                return True
        return False

    @staticmethod
    def update_user_single_field(user_id: int, field_name: str, value):
        """Update a single field for a user in the database."""
        db = Database()
        if db.connect():
            # Ensure field_name is a valid column name to prevent SQL injection
            # A whitelist of editable fields is a good practice
            allowed_fields = ['full_name', 'phone', 'email', 'education', 'city', 'age', 'occupation', 'birth_year']
            if field_name not in allowed_fields:
                db.close()
                # Optionally log this attempt or raise an error
                return False
            
            query = f"UPDATE users SET {field_name} = ? WHERE user_id = ?"
            try:
                db.execute(query, (value, user_id))
                db.commit()
                return True
            except sqlite3.Error as e:
                # Log the error e
                print(f"SQLite error when updating single field {field_name}: {e}")
                return False
            finally:
                db.close()
        return False
    
    # User Activity Log queries
    @staticmethod
    def add_user_activity_log(telegram_id: int, action_type: str, details: str = None, user_id: int = None):
        """Add a new user activity log to the database."""
        db = Database()
        if db.connect():
            now = datetime.now().isoformat()
            try:
                db.execute(
                    "INSERT INTO user_activity_logs (user_id, telegram_id, action_type, timestamp, details) VALUES (?, ?, ?, ?, ?)",
                    (user_id, telegram_id, action_type, now, details)
                )
                db.commit()
                return True
            except sqlite3.Error as e:
                print(f"SQLite error when adding user activity log: {e}") # Basic error logging
                # Consider more robust logging for production
                return False
            finally:
                db.close()
        return False

    # Registration-related queries
    @staticmethod
    def is_registered(user_id):
        """Check if a user has completed registration"""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT full_name, phone FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = db.fetchone() # result is a sqlite3.Row object or None
            db.close()
            
            if result: # Check if a row was returned
                # Check if 'full_name' and 'phone' fields are present and not None/empty
                # Assuming column names are 'full_name' and 'phone'
                try:
                    # Access by column name for sqlite3.Row
                    full_name_present = result['full_name'] is not None and str(result['full_name']).strip() != ""
                    phone_present = result['phone'] is not None and str(result['phone']).strip() != ""
                    return full_name_present and phone_present
                except (IndexError, KeyError):
                    # Handle cases where columns might not exist, though schema should ensure this
                    return False 
        return False

    @staticmethod
    def create_crypto_payment_request(user_id: int, rial_amount: float, usdt_amount_requested: float = None, wallet_address: str = None, expires_at: datetime = None):
        """
        Creates a preliminary crypto payment request in the database.
        'usdt_amount_requested' can be None initially and updated later.
        Assumes 'payments' table has: user_id, amount (for rial), usdt_amount_requested,
        payment_method, status, description, wallet_address, expires_at, created_at, updated_at.
        """
        db = Database()
        if db.connect():
            now_iso = datetime.now().isoformat()
            expires_at_iso = expires_at.isoformat() if expires_at else None
            
            description = f"Crypto payment for user ID {user_id}"

            try:
                db.execute(
                    """INSERT INTO payments (user_id, amount, usdt_amount_requested, payment_method, status, description, wallet_address, expires_at, created_at, updated_at)
                       VALUES (?, ?, ?, 'crypto', 'pending', ?, ?, ?, ?, ?)""",
                    (user_id, rial_amount, usdt_amount_requested, description, wallet_address, expires_at_iso, now_iso, now_iso)
                )
                payment_id = db.cursor.lastrowid # Corrected: Use cursor.lastrowid
                db.commit()
                return payment_id
            except sqlite3.Error as e:
                config.logger.error(f"SQLite error in create_crypto_payment_request: {e}") # Use logger
                return None
            finally:
                db.close()
        return None

    @staticmethod
    def update_crypto_payment_request_with_amount(payment_request_id: int, usdt_amount: float):
        """
        Updates an existing crypto payment request with the calculated USDT amount.
        Assumes 'payments' table has: usdt_amount_requested, updated_at, payment_id, payment_method.
        """
        db = Database()
        if db.connect():
            now_iso = datetime.now().isoformat()
            try:
                db.execute(
                    "UPDATE payments SET usdt_amount_requested = ?, updated_at = ? WHERE payment_id = ? AND payment_method = 'crypto' AND status = 'pending'",
                    (usdt_amount, now_iso, payment_request_id)
                )
                db.commit()
                # Check if any row was actually updated; rowcount might be 0 if no matching record or value is the same
                return db.cursor.rowcount > 0 
            except sqlite3.Error as e:
                config.logger.error(f"SQLite error in update_crypto_payment_request_with_amount: {e}") # Use logger
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def update_payment_transaction_id(payment_id: int, transaction_id: str, status: str = "pending_verification"):
        """
        Updates the transaction ID and status of a payment record.
        Typically used for Zarinpal payments after getting an authority.
        """
        db = Database()
        if db.connect():
            try:
                # now_iso = datetime.now().isoformat() # Temporarily removed for updated_at
                db.execute(
                    "UPDATE payments SET transaction_id = ?, status = ? WHERE payment_id = ?",
                    (transaction_id, status, payment_id) # Temporarily removed now_iso
                )
                db.commit()
                return db.cursor.rowcount > 0  # Corrected to use db.cursor.rowcount
            except sqlite3.Error as e:
                config.logger.error(f"SQLite error in update_payment_transaction_id for payment_id {payment_id}: {e}")
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def get_payment_by_authority(authority: str):
        """
        Retrieves payment details from the database using the Zarinpal authority code.
        Args:
            authority: The Authority code provided by Zarinpal.
        Returns:
            A dictionary containing payment details (payment_id, user_id, plan_id, amount, status)
            if found, otherwise None.
        """
        db = Database()
        if db.connect():
            try:
                # Assuming 'transaction_id' stores the Zarinpal Authority and 'plan_id' column exists.
                # Also assuming 'payments' table has 'payment_method' to distinguish zarinpal payments
                db.execute(
                    """SELECT p.payment_id, p.user_id, p.plan_id, p.amount, p.status
                       FROM payments p
                       WHERE p.transaction_id = ? AND p.payment_method = 'zarinpal'""",
                    (authority,)
                )
                result = db.fetchone()
                # Convert tuple to dict if result is not None
                if result:
                    columns = [desc[0] for desc in db.cursor.description]
                    return dict(zip(columns, result))
                return None
            except sqlite3.Error as e:
                config.logger.error(f"Database error in get_payment_by_authority for authority {authority}: {e}")
                return None
            finally:
                db.close()
        return None

    @staticmethod
    def update_payment_verification_status(payment_id: int, new_status: str, zarinpal_ref_id: str = None):
        """
        Updates the status of a payment after verification attempt and stores Zarinpal's RefID.
        Args:
            payment_id: The ID of the payment record.
            new_status: The new status (e.g., 'completed', 'failed', 'already_verified').
            zarinpal_ref_id: Zarinpal's final reference ID after successful verification.
                               Assumes a 'gateway_ref_id' column exists in the 'payments' table.
        """
        db = Database()
        if db.connect():
            try:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if zarinpal_ref_id:
                    db.execute(
                        """UPDATE payments
                           SET status = ?, gateway_ref_id = ?, updated_at = ?
                           WHERE payment_id = ?""",
                        (new_status, zarinpal_ref_id, now, payment_id)
                    )
                else:
                    db.execute(
                        """UPDATE payments
                           SET status = ?, updated_at = ?
                           WHERE payment_id = ?""",
                        (new_status, now, payment_id)
                    )
                db.commit()
                # Check if the update was successful
                return db.cursor.rowcount > 0
            except sqlite3.Error as e:
                config.logger.error(f"Database error in update_payment_verification_status for payment_id {payment_id}: {e}")
                return False
            finally:
                db.close()
        return False

    # Plan-related queries
    @staticmethod
    def get_active_plans():
        """Get all active subscription plans, ordered by display_order."""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT id, name, description, price, original_price_irr, price_tether, original_price_usdt, days, features, display_order FROM plans WHERE is_active = 1 ORDER BY display_order ASC, id ASC"
            )
            result = db.fetchall()
            db.close()
            return result
        return []

    @staticmethod
    def get_plan_by_id(plan_id):
        """Get plan details by its ID."""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT id, name, description, price, original_price_irr, price_tether, original_price_usdt, days, features, is_active, display_order FROM plans WHERE id = ?",
                (plan_id,)
            )
            result = db.fetchone()
            db.close()
            return result
        return None
    
    # Subscription-related queries
    @staticmethod
    def get_all_active_subscribers():
        """Get all users with an active subscription."""
        db = Database()
        if db.connect():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                "SELECT user_id FROM subscriptions WHERE status = 'active' AND end_date > ?",
                (now,)
            )
            result = db.fetchall()
            db.close()
            return result
        return []

    @staticmethod
    def has_active_subscription(user_id: int) -> bool:
        """Check if a user has an active, non-expired subscription."""
        db = Database()
        if db.connect():
            try:
                # Use current time that is timezone-aware
                current_time = get_current_time()
                query = """
                    SELECT 1 FROM subscriptions
                    WHERE user_id = ? AND end_date > ? AND status = 'active'
                    LIMIT 1
                """
                db.execute(query, (user_id, current_time))
                result = db.fetchone()
                return result is not None
            except sqlite3.Error as e:
                logging.error(f"Database error in has_active_subscription for user {user_id}: {e}")
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def get_users_with_non_active_subscription_records():
        """Get users with non-active (expired, cancelled, etc.) subscription records."""
        db = Database()
        if db.connect():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                "SELECT user_id, status FROM subscriptions WHERE status != 'active' OR end_date <= ?",
                (now,)
            )
    @staticmethod
    def _update_existing_subscription(subscription_id, plan_id, payment_id, new_end_date_str, amount_paid, payment_method, status='active'):
        """
        Helper function to update an existing subscription record.
        This is typically called when a user renews or extends an active subscription.
        """
        db = Database()
        if db.connect():
            try:
                db.execute(
                    """UPDATE subscriptions
                       SET plan_id = ?,
                           payment_id = ?,
                           end_date = ?,
                           amount_paid = ?,
                           payment_method = ?,
                           status = ?,
                           updated_at = ?
                       WHERE id = ?""",
                    (plan_id, payment_id, new_end_date_str, amount_paid, payment_method, status, 
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"), subscription_id)
                )
                db.commit()
                return True
            except sqlite3.Error as e:
                print(f"Error updating subscription {subscription_id}: {e}")
                return False
            except Exception as e:
                print(f"Unexpected error updating subscription {subscription_id}: {e}")
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def count_total_subs(plan_id: int) -> int:
        """Return total number of active subscription records for the specified plan."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT COUNT(*) FROM subscriptions WHERE plan_id = ? AND status = 'active'"
                if db.execute(query, (plan_id,)):
                    result = db.fetchone()
                    return result[0] if result else 0
            except sqlite3.Error as e:
                print(f"SQLite error in count_total_subs: {e}")
            finally:
                db.close()
        return 0

    @staticmethod
    def add_subscription(user_id: int, plan_id: int, payment_id: int, 
                     plan_duration_days: int, amount_paid: float, 
                     payment_method: str, status: str = 'active'):
        """
        Adds a new subscription or extends an existing active one for a user.
        If an active subscription exists, its end_date is extended.
        Otherwise, a new subscription record is created.

        Args:
            user_id: The ID of the user.
            plan_id: The ID of the subscription plan.
            payment_id: The ID of the payment record associated with this subscription/renewal.
            plan_duration_days: The duration of the plan in days.
            amount_paid: The amount paid for this specific transaction.
            payment_method: The method used for this payment (e.g., 'rial', 'tether').
            status: The status of the subscription, defaults to 'active'.

        Returns:
            The ID of the created or updated subscription record, or None on failure.
        """
        db = Database()
        if not db.connect():
            print(f"Failed to connect to database in add_subscription for user {user_id}")
            return None

        try:
            print(f"DEBUG: add_subscription called with user_id={user_id}, plan_id={plan_id}, payment_id={payment_id}")
            
            current_active_sub = DatabaseQueries.get_user_active_subscription(user_id) 
            print(f"DEBUG: Current active subscription: {current_active_sub}")
            
            now_dt = datetime.now()
            
            if current_active_sub:
                current_end_date_str = current_active_sub['end_date']
                try:
                    current_end_date_dt = datetime.strptime(current_end_date_str, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError) as e:
                    print(f"Error parsing current_end_date '{current_end_date_str}' for user {user_id}: {e}. Treating as no active sub.")
                    current_active_sub = None

                if current_active_sub and current_end_date_dt > now_dt:
                    start_point_for_new_duration = current_end_date_dt
                else:
                    start_point_for_new_duration = now_dt
                
                new_end_date_dt = start_point_for_new_duration + timedelta(days=plan_duration_days)
                new_end_date_str = new_end_date_dt.strftime("%Y-%m-%d %H:%M:%S")

                print(f"DEBUG: Updating existing subscription {current_active_sub['id']} with new end date {new_end_date_str}")
                
                if DatabaseQueries._update_existing_subscription(
                    subscription_id=current_active_sub['id'],
                    plan_id=plan_id,
                    payment_id=payment_id,
                    new_end_date_str=new_end_date_str,
                    amount_paid=amount_paid,
                    payment_method=payment_method,
                    status=status
                ):
                    print(f"DEBUG: Successfully updated subscription {current_active_sub['id']}")
                    return current_active_sub['id']
                else:
                    print(f"Failed to update existing subscription for user {user_id}.")
                    return None
            else:
                start_date_dt = now_dt
                end_date_dt = start_date_dt + timedelta(days=plan_duration_days)
                
                start_date_str = start_date_dt.strftime("%Y-%m-%d %H:%M:%S")
                end_date_str = end_date_dt.strftime("%Y-%m-%d %H:%M:%S")

                print(f"DEBUG: Creating new subscription - start: {start_date_str}, end: {end_date_str}")

                db.execute(
                    """INSERT INTO subscriptions 
                       (user_id, plan_id, payment_id, start_date, end_date, amount_paid, status, payment_method, created_at, updated_at) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, plan_id, payment_id, start_date_str, end_date_str, amount_paid, status, 
                     payment_method, now_dt.strftime("%Y-%m-%d %H:%M:%S"), now_dt.strftime("%Y-%m-%d %H:%M:%S"))
                )
                subscription_id = db.cursor.lastrowid
                print(f"DEBUG: Inserted new subscription with ID: {subscription_id}")
                
                db.commit()
                print(f"DEBUG: Committed transaction for subscription {subscription_id}")
                
                return subscription_id
        except sqlite3.Error as e:
            print(f"Database error in add_subscription for user {user_id}: {e}")
            if db.conn:
                db.conn.rollback()  # Use the connection object for rollback
            return None
        except Exception as e:
            print(f"Unexpected error in add_subscription for user {user_id}: {e}")
            if db.conn:
                db.conn.rollback()  # Use the connection object for rollback
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_subscription(subscription_id):
        """Get subscription details"""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT * FROM subscriptions WHERE id = ?",
                (subscription_id,)
            )
            result = db.fetchone()
            db.close()
            return result
        return None

    # ---- Free Plan Helper Methods ----
    @staticmethod
    def has_user_used_free_plan(user_id: int, plan_id: int) -> bool:
        """Return True if the user has already subscribed to the given plan (whether active or expired)."""
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "SELECT 1 FROM subscriptions WHERE user_id = ? AND plan_id = ? LIMIT 1",
                    (user_id, plan_id),
                )
                return db.fetchone() is not None
            except sqlite3.Error as e:
                logging.error(f"SQLite error in has_user_used_free_plan: {e}")
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def count_total_subscriptions_for_plan(plan_id: int) -> int:
        """Return total number of subscription records for the specified plan."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT COUNT(*) AS cnt FROM subscriptions WHERE plan_id = ?", (plan_id,))
                row = db.fetchone()
                return (row['cnt'] if isinstance(row, sqlite3.Row) else row[0]) if row else 0
            except sqlite3.Error as e:
                logging.error(f"SQLite error in count_total_subscriptions_for_plan: {e}")
                return 0
            finally:
                db.close()
        return 0

    @staticmethod
    def deactivate_plan(plan_id: int) -> bool:
        """Set is_active = 0 for the given plan. Returns True if a row was affected."""
        db = Database()
        if db.connect():
            try:
                db.execute("UPDATE plans SET is_active = 0 WHERE id = ?", (plan_id,))
                db.commit()
                return db.cursor.rowcount > 0
            except sqlite3.Error as e:
                logging.error(f"SQLite error in deactivate_plan: {e}")
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def get_plan_by_id(plan_id: int):
        """Fetch a plan row by its ID."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
                return db.fetchone()
            except sqlite3.Error as e:
                logging.error(f"SQLite error in get_plan_by_id: {e}")
                return None
            finally:
                db.close()
        return None

    # Backwards compatibility alias
    @staticmethod
    def get_plan(plan_id: int):
        return DatabaseQueries.get_plan_by_id(plan_id)

    @staticmethod
    # ---- User Subscription Summary Helpers ----
    @staticmethod
    def _ensure_user_summary_columns():
        """Ensures that `users` table has the summary columns. If not, add them with ALTER TABLE."""
        db = Database()
        if not db.connect():
            return False
        try:
            db.execute("PRAGMA table_info(users)")
            cols = [row['name'] for row in db.fetchall()]
            needed = []
            if 'total_subscription_days' not in cols:
                needed.append("ALTER TABLE users ADD COLUMN total_subscription_days INTEGER DEFAULT 0")
            if 'subscription_expiration_date' not in cols:
                needed.append("ALTER TABLE users ADD COLUMN subscription_expiration_date TEXT")
            for stmt in needed:
                db.execute(stmt)
            if needed:
                db.commit()
        except sqlite3.Error as e:
            logging.error(f"SQLite error ensuring user summary columns: {e}")
        finally:
            db.close()
        return True

    @staticmethod
    def get_user_subscription_summary(user_id: int):
        """Return total days and expiration date for a user from `users` table (may return None)."""
        DatabaseQueries._ensure_user_summary_columns()
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT total_subscription_days, subscription_expiration_date FROM users WHERE user_id = ?", (user_id,))
                return db.fetchone()
            except sqlite3.Error as e:
                logging.error(f"SQLite error in get_user_subscription_summary: {e}")
                return None
            finally:
                db.close()
        return None

    @staticmethod
    def update_user_subscription_summary(user_id: int, total_days: int, expiration_date: str) -> bool:
        """Update summary columns for user."""
        DatabaseQueries._ensure_user_summary_columns()
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "UPDATE users SET total_subscription_days = ?, subscription_expiration_date = ? WHERE user_id = ?",
                    (total_days, expiration_date, user_id),
                )
                db.commit()
                return db.cursor.rowcount > 0
            except sqlite3.Error as e:
                logging.error(f"SQLite error in update_user_subscription_summary: {e}")
                return False
            finally:
                db.close()
        return False

    def get_user_active_subscription(user_id):
        """Get user's active subscription.
           Returns the one with the latest end_date if multiple somehow exist.
        """
        db = Database()
        if db.connect():
            # Use Tehran timezone aware "now" to avoid offset issues
            now_str = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
            
            try:
                db.execute(
                    """SELECT s.id, s.user_id, s.plan_id, s.payment_id, 
                              s.start_date, s.end_date, s.amount_paid, s.payment_method, 
                              s.status, s.created_at, s.updated_at,
                              p.name as plan_name, p.days as plan_duration_config_days
                       FROM subscriptions s
                       JOIN plans p ON s.plan_id = p.id
                       WHERE s.user_id = ? AND s.status = 'active' AND s.end_date > ?
                       ORDER BY s.end_date DESC LIMIT 1""",
                    (user_id, now_str)
                )
                result = db.fetchone()
                return result
            except sqlite3.Error as e:
                print(f"Database error in get_user_active_subscription for user {user_id}: {e}")
                return None
            finally:
                db.close()
        return None

    @staticmethod
    def get_open_tickets():
        """Fetch all tickets with 'open' or 'pending_admin_reply' status."""
        db = Database()
        tickets = []
        if db.connect():
            try:
                # Query to fetch tickets and join with users table to get full_name
                # Adjust column names (t.message, u.full_name) as per your actual schema
                query = """
                    SELECT t.id as ticket_id, t.user_id, u.full_name as user_name, 
                           t.subject as subject, t.status, t.created_at
                    FROM tickets t
                    JOIN users u ON t.user_id = u.user_id
                    WHERE t.status IN ('open', 'pending_admin_reply')
                    ORDER BY t.created_at ASC;
                """
                db.execute(query)
                rows = db.fetchall()
                if rows:
                    column_names = [desc[0] for desc in db.cursor.description]
                    for row in rows:
                        tickets.append(dict(zip(column_names, row)))
            except sqlite3.Error as e:
                print(f"SQLite error in get_open_tickets: {e}")
                # Log error
            finally:
                db.close()
        return tickets

    @staticmethod
    def get_all_tickets():
        """Fetch all tickets regardless of status for admin view."""
        db = Database()
        tickets = []
        if db.connect():
            try:
                query = """
                    SELECT t.id as ticket_id, t.user_id, u.full_name as user_name,
                           t.subject as subject, t.status, t.created_at
                    FROM tickets t
                    JOIN users u ON t.user_id = u.user_id
                    ORDER BY t.created_at DESC;
                """
                db.execute(query)
                rows = db.fetchall()
                if rows:
                    column_names = [desc[0] for desc in db.cursor.description]
                    for row in rows:
                        tickets.append(dict(zip(column_names, row)))
            except sqlite3.Error as e:
                print(f"SQLite error in get_all_tickets: {e}")
            finally:
                db.close()
        return tickets

    @staticmethod
    def get_ticket_details(ticket_id):
        """Fetch details for a specific ticket, including its messages."""
        db = Database()
        ticket_data = None
        if db.connect():
            try:
                # Fetch ticket main info
                db.execute("""
                    SELECT t.id as ticket_id, t.user_id, u.full_name as user_name, 
                           t.subject, t.status, t.created_at
                    FROM tickets t
                    JOIN users u ON t.user_id = u.user_id
                    WHERE t.id = ?;
                """, (ticket_id,))
                main_info_row = db.fetchone()
                
                if main_info_row:
                    ticket_data = {}
                    column_names = [desc[0] for desc in db.cursor.description]
                    ticket_data = dict(zip(column_names, main_info_row))

                    # Fetch ticket messages
                    db.execute("""
                        SELECT tm.id as message_id, tm.user_id, tm.message, tm.timestamp, tm.is_admin
                        FROM ticket_messages tm
                        WHERE tm.ticket_id = ?
                        ORDER BY tm.timestamp ASC;
                    """, (ticket_id,))
                    
                    messages_rows = db.fetchall()
                    messages = []
                    if messages_rows:
                        msg_column_names = [desc[0] for desc in db.cursor.description]
                        for msg_row in messages_rows:
                            messages.append(dict(zip(msg_column_names, msg_row)))
                    ticket_data['messages'] = messages

            except sqlite3.Error as e:
                print(f"SQLite error in get_ticket_details for ticket_id {ticket_id}: {e}")
                ticket_data = None # Indicate failure
            finally:
                db.close()
        return ticket_data

    @staticmethod
    def add_ticket_message(ticket_id, user_id, message, is_admin_message=False, update_status=True):
        """Adds a message to a ticket and optionally updates ticket's status and updated_at."""
        db = Database()
        success = False
        if db.connect():
            try:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                db.execute("""
                    INSERT INTO ticket_messages (ticket_id, user_id, message, timestamp, is_admin)
                    VALUES (?, ?, ?, ?, ?);
                """, (ticket_id, user_id, message, now, 1 if is_admin_message else 0))
                
                if update_status:
                    new_status = 'pending_user_reply' if is_admin_message else 'pending_admin_reply'
                    db.execute("UPDATE tickets SET status = ? WHERE id = ?;", (new_status, ticket_id))

                db.commit()
                success = True
            except sqlite3.Error as e:
                print(f"SQLite error in add_ticket_message for ticket_id {ticket_id}: {e}")
                if db.conn:
                    db.conn.rollback()  # Use the connection object for rollback
            finally:
                db.close()
        return success
        return success

    @staticmethod
    def update_ticket_status(ticket_id, new_status):
        """Updates the status of a ticket."""
        db = Database()
        success = False
        if db.connect():
            try:
                # now = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # If also updating updated_at
                # db.execute("UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?;", 
                #            (new_status, now, ticket_id))
                db.execute("UPDATE tickets SET status = ? WHERE id = ?;", (new_status, ticket_id))
                db.commit()
                success = True
            except sqlite3.Error as e:
                print(f"SQLite error in update_ticket_status for ticket_id {ticket_id}: {e}")
                if db.conn:
                    db.conn.rollback()
            finally:
                db.close()
        return success

    @staticmethod
    def get_all_active_subscribers():
        """Get all users with active subscriptions"""
        db = Database()
        if db.connect():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                """SELECT u.user_id, u.full_name, u.username, u.phone, s.start_date, s.end_date, p.name as plan_name
                FROM subscriptions s
                JOIN users u ON s.user_id = u.user_id
                JOIN plans p ON s.plan_id = p.id
                WHERE s.status = 'active' AND s.end_date > ?
                ORDER BY s.end_date ASC""",
                (now,)
            )
            result = db.fetchall()
            db.close()
            return result
        return []
    
    # Payment-related queries
    @staticmethod
    def add_payment(user_id, amount, payment_method, description=None, transaction_id=None, status="pending", plan_id=None):
        """Add a new payment"""
        db = Database()
        if db.connect():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                """INSERT INTO payments 
                (user_id, plan_id, amount, payment_date, payment_method, transaction_id, description, status) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, plan_id, amount, now, payment_method, transaction_id, description, status)
            )
            payment_id = db.cursor.lastrowid
            db.commit()
            db.close()
            return payment_id
        return None
    
    @staticmethod
    def create_payment(user_id: int, plan_id: int, amount: float, payment_method: str, status: str = "pending", description: str = None, transaction_id: str = None):
        """Backwards compatible alias expected by some handlers."""
        return DatabaseQueries.add_payment(
            user_id=user_id,
            amount=amount,
            payment_method=payment_method,
            description=description,
            transaction_id=transaction_id,
            status=status,
            plan_id=plan_id,
        )

    @staticmethod
    def get_payment(payment_id):
        """Get payment details by its primary key `payment_id`. (Legacy alias for `get_payment_by_id`.)"""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT * FROM payments WHERE payment_id = ?",
                (payment_id,)
            )
            result = db.fetchone()
            db.close()
            return result
        return None
    
    @staticmethod
    def get_payment_by_id(payment_id):
        """Alias for `get_payment` so existing handlers calling this name work."""
        return DatabaseQueries.get_payment(payment_id)
    
    @staticmethod
    def update_payment_status(payment_id, status, transaction_id=None, error_message=None):
        """Update payment status and optionally an error message in description."""
        db = Database()
        if db.connect():
            sql_query = "UPDATE payments SET status = ?"
            params = [status]

            if transaction_id:
                sql_query += ", transaction_id = ?"
                params.append(transaction_id)
        
            if error_message:
                sql_query += ", description = ?"
                params.append(error_message)
        
            sql_query += " WHERE payment_id = ?"
            params.append(payment_id)

            db.execute(sql_query, tuple(params))
            db.commit()
            db.close()
            return True
        return False
    # Plan-related queries

    @staticmethod
    def get_active_plans():
        """Get all active subscription plans, ordered by display_order."""
        db = Database()
        if db.connect():
            now_str = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                """
                SELECT * FROM plans 
                WHERE is_active = 1 
                AND (expiration_date IS NULL OR expiration_date > ?)
                ORDER BY display_order
                """,
                (now_str,)
            )
            result = db.fetchall()
            db.close()
            return result
        return []

    @staticmethod
    def count_subscriptions_for_plan(plan_id):
        """Count the number of active subscriptions for a given plan."""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT COUNT(id) FROM subscriptions WHERE plan_id = ? AND status = 'active'",
                (plan_id,)
            )
            count = db.fetchone()[0]
            db.close()
            return count
        return 0

    @staticmethod
    def has_user_subscribed_to_plan(user_id, plan_id):
        """Check if a user has an active subscription to a specific plan."""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT 1 FROM subscriptions WHERE user_id = ? AND plan_id = ? AND status = 'active'",
                (user_id, plan_id)
            )
            result = db.fetchone()
            db.close()
            return result is not None
        return False

    # Support ticket queries
    @staticmethod
    def create_ticket(user_id, subject, message):
        """Create a new support ticket"""
# ... (rest of the code remains the same)
        db = Database()
        if db.connect():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                """INSERT INTO tickets 
                (user_id, subject, created_at, status) 
                VALUES (?, ?, ?, 'open')""",
                (user_id, subject, now)
            )
            ticket_id = db.cursor.lastrowid
            
            # Add initial message
            db.execute(
                """INSERT INTO ticket_messages 
                (ticket_id, user_id, message, timestamp, is_admin) 
                VALUES (?, ?, ?, ?, 0)""",
                (ticket_id, user_id, message, now)
            )
            
            db.commit()
            db.close()
            return ticket_id
        return None
    
    @staticmethod
    def get_user_tickets(user_id):
        """Get all tickets created by a user"""
        db = Database()
        if db.connect():
            db.execute(
                """SELECT * FROM tickets 
                WHERE user_id = ? 
                ORDER BY created_at DESC""",
                (user_id,)
            )
            result = db.fetchall()
            db.close()
            return result
        return []
    
    @staticmethod
    def get_ticket(ticket_id):
        """Get ticket details"""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT * FROM tickets WHERE id = ?",
                (ticket_id,)
            )
            result = db.fetchone()
            db.close()
            return result
        return None
    
    @staticmethod
    def get_ticket_messages(ticket_id):
        """Get all messages for a ticket"""
        db = Database()
        if db.connect():
            db.execute(
                """SELECT tm.*, u.full_name, u.username 
                FROM ticket_messages tm
                LEFT JOIN users u ON tm.user_id = u.user_id
                WHERE tm.ticket_id = ? 
                ORDER BY tm.timestamp ASC""",
                (ticket_id,)
            )
            result = db.fetchall()
            db.close()
            return result
        return []
    

    
    @staticmethod
    def update_ticket_status(ticket_id, status):
        """Update ticket status"""
        db = Database()
        if db.connect():
            db.execute(
                "UPDATE tickets SET status = ? WHERE id = ?",
                (status, ticket_id)
            )
            db.commit()
            db.close()
            return True
        return False
    
    @staticmethod
    def has_user_used_free_plan(user_id, plan_id):
        """Check if the user has ever had a subscription for a specific free plan."""
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "SELECT 1 FROM subscriptions WHERE user_id = ? AND plan_id = ?",
                    (user_id, plan_id)
                )
                result = db.fetchone()
                return result is not None
            finally:
                db.close()
        return False

    @staticmethod
    def count_total_subscriptions_for_plan(plan_id):
        """Count the total number of subscriptions ever created for a given plan."""
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "SELECT COUNT(id) FROM subscriptions WHERE plan_id = ?",
                    (plan_id,)
                )
                count = db.fetchone()[0]
                return count
            finally:
                db.close()
        return 0

    @staticmethod
    def deactivate_plan(plan_id):
        """Deactivates a plan by setting its is_active flag to False."""
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "UPDATE plans SET is_active = 0 WHERE id = ?",
                    (plan_id,)
                )
                db.commit()
                return True
            finally:
                db.close()
        return False

    @staticmethod
    def get_open_tickets():
        """Get all open tickets"""
        db = Database()
        if db.connect():
            db.execute(
                """SELECT t.*, u.full_name, u.username, u.phone
                FROM tickets t
                JOIN users u ON t.user_id = u.user_id
                WHERE t.status = 'open'
                ORDER BY t.created_at ASC"""
            )
            result = db.fetchall()
            db.close()
            return result
        return []
        


    @staticmethod
    def get_users_with_non_active_subscription_records():
        """Fetches users with non-active (e.g., expired, cancelled) subscription records."""
        db = Database()
        users = []
        if db.connect():
            try:
                # Assuming 'active' is the status for an active subscription.
                # Adjust the query if your status column or 'active' value is different.
                # This query selects distinct user_ids to avoid processing the same user multiple times
                # if they have multiple non-active records.
                # It also ensures status is not NULL or empty.
                query = """
                    SELECT DISTINCT user_id, status 
                    FROM subscriptions 
                    WHERE status IS NOT NULL AND status != '' AND status != 'active';
                """
                # Note: If a user has NO record in the subscriptions table at all,
                # they won't be caught by this query. This query targets users
                # who HAD a subscription that is now in a non-active state.
                # To catch users in the 'users' table but not in 'subscriptions',
                # a more complex query (e.g., LEFT JOIN) would be needed.
                
                db.execute(query)
                records = db.fetchall()
                for row in records:
                    users.append({'user_id': row[0], 'status': row[1]})
                # self.logger.debug(f"DB: Found {len(users)} users with non-active subscriptions.") # Use logger if available
            except sqlite3.Error as e:
                # Consider using a logger here instead of print for consistency
                print(f"SQLite error in get_users_with_non_active_subscription_records: {e}")
            finally:
                db.close()
        return users
    



        
    @staticmethod
    def close_ticket(ticket_id, admin_id):
        db = Database()
        if db.connect():
            try:
                query = """
                UPDATE tickets 
                SET status = 'closed', closed_at = datetime('now'), closed_by = ?
                WHERE ticket_id = ?
                """
                if db.execute(query, (admin_id, ticket_id)):
                    db.commit()
                    return True
            except sqlite3.Error as e:
                print(f"SQLite error in close_ticket: {e}")
            finally:
                db.close()
        return False

    # --- Discount Management ---

    @staticmethod
    def create_discount(code: str, discount_type: str, value: float, start_date: str = None, end_date: str = None, max_uses: int = None, is_active: bool = True) -> int:
        """Creates a new discount code and returns its ID."""
        db = Database()
        if db.connect():
            try:
                query = """
                    INSERT INTO discounts (code, type, value, start_date, end_date, max_uses, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """
                params = (code, discount_type, value, start_date, end_date, max_uses, is_active)
                if db.execute(query, params):
                    discount_id = db.cursor.lastrowid
                    db.commit()
                    return discount_id
            except sqlite3.Error as e:
                print(f"SQLite error in create_discount: {e}")
            finally:
                db.close()
        return None

    @staticmethod
    def get_discount_by_code(code: str):
        """Retrieves a discount by its code."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT * FROM discounts WHERE code = ?"
                if db.execute(query, (code,)):
                    return db.fetchone()
            except sqlite3.Error as e:
                print(f"SQLite error in get_discount_by_code: {e}")
            finally:
                db.close()
        return None

    @staticmethod
    def get_all_discounts():
        """Retrieves all discounts from the database."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT * FROM discounts ORDER BY id DESC"
                if db.execute(query):
                    return db.fetchall()
            except sqlite3.Error as e:
                print(f"SQLite error in get_all_discounts: {e}")
            finally:
                db.close()
        return []

    @staticmethod
    def toggle_discount_status(discount_id: int, is_active: bool) -> bool:
        """Activates or deactivates a discount."""
        db = Database()
        if db.connect():
            try:
                query = "UPDATE discounts SET is_active = ? WHERE id = ?"
                if db.execute(query, (is_active, discount_id)):
                    db.commit()
                    return True
            except sqlite3.Error as e:
                print(f"SQLite error in toggle_discount_status: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def assign_discount_to_plan(discount_id: int, plan_id: int) -> bool:
        """Assigns a discount to a specific plan."""
        db = Database()
        if db.connect():
            try:
                query = "INSERT INTO plan_discounts (discount_id, plan_id) VALUES (?, ?)"
                if db.execute(query, (discount_id, plan_id)):
                    db.commit()
                    return True
            except sqlite3.Error as e:
                print(f"SQLite error in assign_discount_to_plan: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def link_discount_to_plans(discount_id: int, plan_ids: list) -> bool:
        """Links a discount to one or more plans."""
        db = Database()
        if db.connect():
            try:
                query = "INSERT INTO plan_discounts (discount_id, plan_id) VALUES (?, ?)"
                params_list = [(discount_id, plan_id) for plan_id in plan_ids]
                if db.executemany(query, params_list):
                    db.commit()
                    return True
            except sqlite3.Error as e:
                print(f"SQLite error in link_discount_to_plans: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def get_plans_for_discount(discount_id: int) -> list:
        """Returns a list of plan records associated with a discount."""
        db = Database()
        if db.connect():
            try:
                query = """
                    SELECT p.id, p.name FROM plans p
                    JOIN plan_discounts pd ON p.id = pd.plan_id
                    WHERE pd.discount_id = ?
                """
                if db.execute(query, (discount_id,)):
                    return db.fetchall()
            except sqlite3.Error as e:
                print(f"SQLite error in get_plans_for_discount: {e}")
            finally:
                db.close()
        return []

    @staticmethod
    def increment_discount_usage(discount_id: int) -> bool:
        """Increments the usage count of a discount."""
        db = Database()
        if db.connect():
            try:
                query = "UPDATE discounts SET uses_count = uses_count + 1 WHERE id = ?"
                if db.execute(query, (discount_id,)):
                    db.commit()
                    return True
            except sqlite3.Error as e:
                print(f"SQLite error in increment_discount_usage: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def get_all_plans():
        """Retrieves all subscription plans."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT id, name, price FROM plans ORDER BY display_order"
                if db.execute(query):
                    return db.fetchall()
            except sqlite3.Error as e:
                print(f"SQLite error in get_all_plans: {e}")
            finally:
                db.close()
        return []

    @staticmethod
    def get_user_by_telegram_id(telegram_id):
        """Get user by telegram ID"""
        db = Database()
        if db.connect():
            db.execute("SELECT * FROM users WHERE user_id = ?", (telegram_id,))
            result = db.fetchone()
            db.close()
            return result
        return None
