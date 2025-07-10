"""
Database queries for the Daraei Academy Telegram bot
"""

import sqlite3
from datetime import datetime, timedelta
from .models import Database
import config
import logging
from typing import Optional, Any
from database.models import Database
from database.schema import ALL_TABLES
from utils.helpers import get_current_time  # ensure Tehran-tz aware now

class DatabaseQueries:
    """Class for handling database operations"""

    # --- SALES STATS HELPERS -------------------------------------------------
    @staticmethod
    def get_sales_stats_per_plan(only_active: bool = True):
        """Return sales statistics per subscription plan.

        For each plan we calculate:
        • total_subscriptions   – total number of subscriptions ever purchased for the plan
        • active_subscriptions  – current active subscriptions
        • total_revenue_rial    – total IRR revenue (payments.amount) linked to the plan with status = 'paid'
        • total_revenue_usdt    – total USDT revenue (payments.usdt_amount_requested *or* crypto_payments.usdt_amount_requested)

        Note: because our schema has two payment sources (payments & crypto_payments) and
        may not always store plan_id in crypto_payments, we only aggregate what is reliably
        available.
        """
        db = Database()
        stats: list[dict] = []
        if not db.connect():
            return stats

        try:
            now_str = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
            # Build base plans query
            plan_cond = "WHERE p.is_active = 1" if only_active else ""
            # SQL aggregates using correlated sub-queries for clarity & SQLite compatibility
            sql = f"""
                SELECT
                    p.id                                         AS plan_id,
                    p.name                                       AS plan_name,
                    (
                        SELECT COUNT(*) FROM subscriptions s
                        WHERE s.plan_id = p.id
                    )                                            AS total_subscriptions,
                    (
                        SELECT COUNT(*) FROM subscriptions s
                        WHERE s.plan_id = p.id AND s.status = 'active'
                    )                                            AS active_subscriptions,
                    COALESCE((
                        SELECT SUM(amount) FROM payments pay
                        WHERE pay.plan_id = p.id AND pay.status IN ('paid','completed','successful','verified')
                    ), 0)                                         AS total_revenue_rial,
                    COALESCE((
                        SELECT SUM(usdt_amount_requested) FROM payments pay2
                        WHERE pay2.plan_id = p.id AND pay2.usdt_amount_requested IS NOT NULL AND pay2.status IN ('paid','completed','successful','verified')
                    ), 0)                                         AS total_revenue_usdt
                FROM plans p
                {plan_cond}
                ORDER BY p.display_order, p.id
            """
            db.execute(sql)
            rows = db.fetchall()
            if rows:
                # Convert to list of dicts for easier consumption
                col_names = [desc[0] for desc in db.cursor.description]
                for row in rows:
                    stats.append(dict(zip(col_names, row)))
        except sqlite3.Error as e:
            logging.error("SQLite error in get_sales_stats_per_plan: %s", e)
        finally:
            db.close()
        return stats
    def __init__(self, db: Database | None = None):
        # Allow passing None to use singleton Database.get_instance() or create default
        from database.models import Database as DBModel
        self.db = db or DBModel.get_instance()

    def init_database(self):
        """Initialize the database and create tables if they don't exist."""
        if self.db.connect():
            # Add is_active and is_public to plans table if they don't exist
            try:
                self.db.execute("PRAGMA table_info(plans)")
                columns = [column['name'] for column in self.db.fetchall()]

                # Add duration_days column if missing
                if 'duration_days' not in columns:
                    self.db.execute("ALTER TABLE plans ADD COLUMN duration_days INTEGER")
                    # If legacy 'days' column exists, copy data across
                    if 'days' in columns:
                        try:
                            self.db.execute("UPDATE plans SET duration_days = days WHERE duration_days IS NULL OR duration_days = 0")
                        except sqlite3.Error as copy_err:
                            logging.error(f"Error migrating days to duration_days: {copy_err}")

                # Ensure is_active / is_public & capacity columns exist
                if 'is_active' not in columns:
                    self.db.execute("ALTER TABLE plans ADD COLUMN is_active BOOLEAN DEFAULT 1")
                if 'is_public' not in columns:
                    self.db.execute("ALTER TABLE plans ADD COLUMN is_public BOOLEAN DEFAULT 1")
                # Add capacity INTEGER column (nullable) if missing
                if 'capacity' not in columns:
                    self.db.execute("ALTER TABLE plans ADD COLUMN capacity INTEGER")
                self.db.commit()
            except sqlite3.Error as e:
                logging.error(f"Error checking/adding columns to plans table: {e}")

            # Ensure 'usdt_amount_requested' column in payments table
            try:
                self.db.execute("PRAGMA table_info(payments)")
                pay_cols = [c['name'] for c in self.db.fetchall()]
                # Add missing columns for crypto payments
                if 'usdt_amount_requested' not in pay_cols:
                    self.db.execute("ALTER TABLE payments ADD COLUMN usdt_amount_requested REAL")
                if 'wallet_address' not in pay_cols:
                    self.db.execute("ALTER TABLE payments ADD COLUMN wallet_address TEXT")
                if 'expires_at' not in pay_cols:
                    self.db.execute("ALTER TABLE payments ADD COLUMN expires_at TEXT")
            except sqlite3.Error as col_err:
                logging.error(f"Error ensuring usdt_amount_requested column: {col_err}")

            self.db.commit()
            return self.db.create_tables(ALL_TABLES)
        return False

    # -----------------------------------
    # Product Management
    # -----------------------------------
    def add_plan(self, name: str, price: float | None, duration_days: int, description: str | None = None, *, capacity: int | None = None, price_tether: float | None = None, original_price_irr: float | None = None, original_price_usdt: float | None = None, is_active: bool = True, is_public: bool = True):
        """Add a new plan to the database with active and public status."""
        try:
            # Determine if legacy 'days' column exists
            self.db.execute("PRAGMA table_info(plans)")
            columns = [col['name'] for col in self.db.fetchall()]
            column_names = ["name"]
            values: list[Any] = [name]

            # Handle IRR price (legacy) if provided
            if price is not None:
                column_names.append("price")
                values.append(price)

            # Duration column
            duration_col = "duration_days" if "duration_days" in columns else "days"
            column_names.append(duration_col)
            values.append(duration_days)

            # If legacy 'days' column exists, keep it in sync
            if 'days' in columns:
                column_names.append("days")
                values.append(duration_days)

            # Description may be optional
            column_names.append("description")
            values.append(description)

            # Capacity if supported
            if 'capacity' in columns:
                column_names.append("capacity")
                values.append(capacity)

            # USDT pricing columns if present in schema and provided
            if 'price_tether' in columns and price_tether is not None:
                column_names.append("price_tether")
                values.append(price_tether)
            if 'original_price_irr' in columns and original_price_irr is not None:
                column_names.append("original_price_irr")
                values.append(original_price_irr)
            if 'original_price_usdt' in columns and original_price_usdt is not None:
                column_names.append("original_price_usdt")
                values.append(original_price_usdt)

            # Activation & visibility flags
            column_names.extend(["is_active", "is_public"])
            values.extend([is_active, is_public])

            placeholders = ", ".join(["?" for _ in column_names])
            columns_sql = ", ".join(column_names)
            sql = f"INSERT INTO plans ({columns_sql}) VALUES ({placeholders})"
            params = tuple(values)
            self.db.execute(sql, params)
            self.db.commit()
            return self.db.cursor.lastrowid
        except sqlite3.Error as e:
            logging.error(f"SQLite error in add_plan: {e}")
            return None

    def get_all_plans(self, public_only=False):
        """Retrieve plans from the database. Can filter for public-only plans."""
        query = "SELECT id, name, price, duration_days, description, is_active, is_public FROM plans ORDER BY id"
        params = ()
        if public_only:
            query = "SELECT id, name, price, duration_days, description, is_active, is_public FROM plans WHERE is_public = ? AND is_active = ? ORDER BY id"
            params = (True, True)
        try:
            self.db.execute(query, params)
            return self.db.fetchall()
        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_all_plans: {e}")
            return []

    def get_plan_by_id(self, plan_id: int):
        """Retrieve a single plan by its ID."""
        try:
            self.db.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
            return self.db.fetchone()
        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_plan_by_id: {e}")
            return None

    def update_plan(self, plan_id: int, *, name: str | None = None, price: float | None = None, duration_days: int | None = None, capacity: int | None = None, description: str | None = None, price_tether: float | None = None, original_price_irr: float | None = None, original_price_usdt: float | None = None):
        """Update an existing plan's details."""
        try:
            # Ensure both duration_days and legacy days are updated if applicable
            self.db.execute("PRAGMA table_info(plans)")
            cols = [c['name'] for c in self.db.fetchall()]
            set_clauses: list[str] = []
            params: list[Any] = []

            def add_field(field_name: str, value):
                if value is not None:
                    set_clauses.append(f"{field_name} = ?")
                    params.append(value)

            add_field("name", name)
            add_field("price", price)
            if duration_days is not None:
                if 'duration_days' in cols:
                    add_field("duration_days", duration_days)
                elif 'days' in cols:
                    add_field("days", duration_days)
            add_field("description", description)
            if 'capacity' in cols:
                # None means leave unchanged; explicit value (including 0) sets.
                if capacity is not None:
                    add_field("capacity", capacity)
            if 'price_tether' in cols:
                add_field("price_tether", price_tether)
            if 'original_price_irr' in cols:
                add_field("original_price_irr", original_price_irr)
            if 'original_price_usdt' in cols:
                add_field("original_price_usdt", original_price_usdt)

            if not set_clauses:
                return False  # Nothing to update

            set_sql = ", ".join(set_clauses)
            sql = f"UPDATE plans SET {set_sql} WHERE id = ?"
            params.append(plan_id)
            self.db.execute(sql, params)
            self.db.commit()
            return self.db.cursor.rowcount > 0
        except sqlite3.Error as e:
            logging.error(f"SQLite error in update_plan: {e}")
            return False

    def set_plan_visibility(self, plan_id: int, is_public: bool | None = None):
        """Set the public visibility of a plan."""
        try:
            # If is_public is None, toggle the current value
            if is_public is None:
                self.db.execute("SELECT is_public FROM plans WHERE id = ?", (plan_id,))
                row = self.db.fetchone()
                if row is None:
                    return False
                is_public = not bool(row[0] if isinstance(row, tuple) else row['is_public'])
            self.db.execute("UPDATE plans SET is_public = ? WHERE id = ?", (is_public, plan_id))
            self.db.commit()
            return self.db.cursor.rowcount > 0
        except sqlite3.Error as e:
            logging.error(f"SQLite error in set_plan_visibility: {e}")
            return False

    def set_plan_activation(self, plan_id: int, is_active: bool | None = None):
        """Set the activation status of a plan."""
        try:
            # If is_active is None, toggle the current value
            if is_active is None:
                self.db.execute("SELECT is_active FROM plans WHERE id = ?", (plan_id,))
                row = self.db.fetchone()
                if row is None:
                    return False
                is_active = not bool(row[0] if isinstance(row, tuple) else row['is_active'])
            self.db.execute("UPDATE plans SET is_active = ? WHERE id = ?", (is_active, plan_id))
            self.db.commit()
            return self.db.cursor.rowcount > 0
        except sqlite3.Error as e:
            logging.error(f"SQLite error in set_plan_activation: {e}")
            return False

    def delete_plan(self, plan_id: int):
        """Delete a plan from the database."""
        try:
            self.db.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
            self.db.commit()
            return self.db.cursor.rowcount > 0
        except sqlite3.Error as e:
            logging.error(f"SQLite error in delete_plan: {e}")
            return False

    # ... (rest of the methods converted similarly) ...

    def search_users(self, term: str):
        """Search users by user_id, username, or full_name."""
        results = []
        try:
            if term.isdigit():
                self.db.execute("SELECT user_id, full_name, username FROM users WHERE user_id = ?", (int(term),))
            else:
                like_term = f"%{term}%"
                self.db.execute("SELECT user_id, full_name, username FROM users WHERE username LIKE ? OR full_name LIKE ?", (like_term, like_term))
            results = self.db.fetchall()
        except sqlite3.Error as e:
            logging.error(f"SQLite error in search_users: {e}")
        return results

    @staticmethod
    def get_recent_payments(limit: int = 20):
        """Return recent payment records."""
        payments = []
        db = Database()
        if db.connect():
            try:
                sql = f"""
                    SELECT id, user_id, amount AS amount_rial, 'rial' AS payment_type, payment_method, plan_id, status, created_at
                    FROM payments
                    UNION ALL
                    SELECT id, user_id, rial_amount AS amount_rial, 'crypto' AS payment_type, 'crypto' AS payment_method, NULL as plan_id, status, created_at
                    FROM crypto_payments
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                db.execute(sql, (limit,))
                payments = db.fetchall()
            except sqlite3.Error as e:
                logging.error(f"SQLite error in get_recent_payments: {e}")
            finally:
                db.close()
        return payments

    def _ensure_video_table(self):
        """Ensure the video_files table exists and has the correct schema."""
        create_sql = """
            CREATE TABLE IF NOT EXISTS video_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT UNIQUE,
                telegram_file_id TEXT
            );
        """
        self.db.execute(create_sql)
        try:
            self.db.execute("PRAGMA table_info(video_files)")
            columns_info = self.db.fetchall()
            existing_columns = {row['name'] for row in columns_info}
            if "telegram_file_id" not in existing_columns:
                self.db.execute("ALTER TABLE video_files ADD COLUMN telegram_file_id TEXT")
            self.db.commit()
        except sqlite3.Error as e:
            logging.error(f"Error ensuring video table schema: {e}")

    def get_video_file_id(self, file_name: str):
        """Return cached telegram_file_id for a video filename."""
        try:
            self._ensure_video_table()
            self.db.execute("SELECT telegram_file_id FROM video_files WHERE file_name = ?", (file_name,))
            row = self.db.fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            logging.error(f"Error getting video file id: {e}")
            return None

    def save_video_file_id(self, file_name: str, file_id: str):
        """Upsert telegram_file_id for a video filename."""
        try:
            self._ensure_video_table()
            self.db.execute(
                "INSERT OR REPLACE INTO video_files (file_name, telegram_file_id) VALUES (?, ?)",
                (file_name, file_id),
            )
            self.db.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error saving video file_id for {file_name}: {e}")
            return False

    # ------------------------------------------------------------------
    # User existence / registration helpers (instance + static versions)
    # ------------------------------------------------------------------
    def user_exists(self, user_id):
        """Instance method: check if a user exists."""
        try:
            self.db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
            return self.db.fetchone() is not None
        except sqlite3.Error as e:
            logging.error(f"Error checking if user exists: {e}")
            return False

    @staticmethod
    def user_exists_static(user_id):
        """Static helper so that code can call DatabaseQueries.user_exists(user_id)."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
                return db.fetchone() is not None
            except sqlite3.Error as e:
                logging.error(f"SQLite error in user_exists_static: {e}")
            finally:
                db.close()
        return False


    def add_user(self, user_id, username=None):
        """Add a new user."""
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute(
                "INSERT INTO users (user_id, username, registration_date, last_activity) VALUES (?, ?, ?, ?)",
                (user_id, username, now, now)
            )
            self.db.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error adding user: {e}")
            return False

    def update_user_activity(self, user_id):
        """Update user's last activity timestamp."""
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute(
                "UPDATE users SET last_activity = ? WHERE user_id = ?",
                (now, user_id)
            )
            self.db.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error updating user activity: {e}")
            return False

    def get_user_details(self, user_id):
        """Get user details."""
        try:
            self.db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            return self.db.fetchone()
        except sqlite3.Error as e:
            logging.error(f"Error getting user details: {e}")
            return None

    def update_user_profile(self, user_id, **kwargs):
        """Update user profile information."""
        allowed_fields = ['full_name', 'phone', 'email', 'education', 'city', 'age', 'occupation', 'birth_date']
        updates = []
        params = []
        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                updates.append(f"{key} = ?")
                params.append(value)
        
        if not updates:
            return False

        query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
        params.append(user_id)
        try:
            self.db.execute(query, tuple(params))
            self.db.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error updating user profile: {e}")
            return False

    @staticmethod
    def update_user_single_field(user_id: int, field_name: str, value):
        """Update a single field for a user.

        This method was converted to a static method so that callers can invoke it
        directly via ``DatabaseQueries.update_user_single_field`` without needing to
        manually instantiate ``DatabaseQueries`` with an already-connected
        ``Database`` instance.  Internally it takes care of opening a connection,
        executing the update, committing and finally closing the connection.
        """
        allowed_fields = [
            'full_name', 'phone', 'email', 'education', 'city', 'age', 'occupation', 'birth_date'
        ]
        if field_name not in allowed_fields:
            logging.warning(f"Attempted to update disallowed field '{field_name}'.")
            return False

        db = Database()
        if db.connect():
            try:
                db.execute(f"UPDATE users SET {field_name} = ? WHERE user_id = ?", (value, user_id))
                db.commit()
                return db.cursor.rowcount > 0
            except sqlite3.Error as e:
                logging.error(f"SQLite error when updating single field {field_name}: {e}")
                return False
            finally:
                db.close()
        return False

    def add_user_activity_log(self, telegram_id: int, action_type: str, details: str = None, user_id: int = None):
        """Add a user activity log."""
        now = datetime.now().isoformat()
        try:
            self.db.execute(
                "INSERT INTO user_activity_logs (user_id, telegram_id, action_type, timestamp, details) VALUES (?, ?, ?, ?, ?)",
                (user_id, telegram_id, action_type, now, details)
            )
            self.db.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"SQLite error when adding user activity log: {e}")
            return False

    def is_registered(self, user_id):
        """Instance method: check if a user has completed registration."""
        try:
            self.db.execute("SELECT full_name, phone FROM users WHERE user_id = ?", (user_id,))
            result = self.db.fetchone()
            if result:
                full_name_present = result['full_name'] is not None and str(result['full_name']).strip() != ""
                phone_present = result['phone'] is not None and str(result['phone']).strip() != ""
                return full_name_present and phone_present
        except (sqlite3.Error, IndexError, KeyError) as e:
            logging.error(f"Error checking registration status for user {user_id}: {e}")
        return False

    @staticmethod
    def get_user_by_phone(phone: str):
        """Return user row dict for given phone digits. Accepts phone with +98 or 0 prefix; only digits are compared."""
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) < 8:
            return None
        db = Database()
        if db.connect():
            try:
                # Use LIKE to match ending digits (handles country codes)
                db.execute("SELECT * FROM users WHERE REPLACE(REPLACE(phone, '+', ''), ' ', '') LIKE ? LIMIT 1", (f"%{digits}",))
                row = db.fetchone()
                return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"SQLite error in get_user_by_phone: {e}")
            finally:
                db.close()
        return None

    @staticmethod
    def is_registered_static(user_id):
        """Static helper so that code can call DatabaseQueries.is_registered(user_id)."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT full_name, phone FROM users WHERE user_id = ?", (user_id,))
                result = db.fetchone()
                if result:
                    full_name_present = result['full_name'] is not None and str(result['full_name']).strip() != ""
                    phone_present = result['phone'] is not None and str(result['phone']).strip() != ""
                    return full_name_present and phone_present
            except (sqlite3.Error, IndexError, KeyError) as e:
                logging.error(f"SQLite error in is_registered_static for user {user_id}: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def create_crypto_payment_request(user_id: int, rial_amount: float, usdt_amount_requested: float = None, wallet_address: str = None, expires_at: datetime = None, description: str = "Crypto payment"):
        """Creates a preliminary crypto payment request.

        Args:
            user_id: The ID of the user making the payment
            rial_amount: Amount in Rials
            usdt_amount_requested: Optional amount in USDT
            wallet_address: Wallet address for the crypto payment
            expires_at: When this payment request expires
            description: Optional payment description

        Returns:
            Integer payment_id if successful, None otherwise
        """
        db = Database()
        if db.connect():
            now_iso = datetime.now().isoformat()
            # Set default expiration to 24 hours if not provided
            expires_at_iso = expires_at.isoformat() if expires_at else (datetime.now() + timedelta(hours=24)).isoformat()
            
            try:
                # The multi-line string should not have extra indentation
                db.execute(
                    """INSERT INTO payments (user_id, amount, usdt_amount_requested, payment_method, status, description, wallet_address, expires_at, created_at, updated_at)
                       VALUES (?, ?, ?, 'crypto', 'pending', ?, ?, ?, ?, ?)""",
                    (user_id, rial_amount, usdt_amount_requested, description, wallet_address, expires_at_iso, now_iso, now_iso)
                )
                payment_id = db.cursor.lastrowid
                db.commit()
                return payment_id
            except sqlite3.Error as e:
                # Use the configured logger
                config.logger.error(f"SQLite error in create_crypto_payment_request: {e}")
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
    def get_subscription_stats():
        """Calculates and returns subscription statistics."""
        db = Database()
        cursor = db.cursor

        # Total registered users
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        # Active subscribers
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM subscriptions WHERE status = 'active'")
        active_subscribers = cursor.fetchone()[0]

        # Expired subscribers
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM subscriptions WHERE status != 'active'")
        expired_subscribers = cursor.fetchone()[0]

        # Total revenue
        total_revenue_usdt = 0
        total_revenue_irr = 0
        try:
            cursor.execute("SELECT SUM(usdt_amount_received) FROM crypto_payments WHERE status = 'paid'")
            result = cursor.fetchone()[0]
            total_revenue_usdt = result if result is not None else 0
            
            cursor.execute("SELECT SUM(amount) FROM payments WHERE status = 'paid' AND currency = 'IRR'")
            result = cursor.fetchone()[0]
            total_revenue_irr = result if result is not None else 0
        except sqlite3.OperationalError:
            pass

        return {
            "total_users": total_users,
            "active_subscribers": active_subscribers,
            "expired_subscribers": expired_subscribers,
            "total_revenue_usdt": total_revenue_usdt,
            "total_revenue_irr": total_revenue_irr,
        }

    @staticmethod
    def get_all_registered_users():
        """Fetch all users that have ever registered (row exists in users table). Returns list of rows with at least user_id column."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT user_id FROM users")
                result = db.fetchall()
                db.close()
                return result
            except sqlite3.Error as exc:
                logging.error("SQLite error in get_all_registered_users: %s", exc)
                if db.conn:
                    db.conn.rollback()
                db.close()
                return []
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

    # -----------------------------------
    # Additional subscription helpers
    # -----------------------------------
    @staticmethod
    def get_user_active_subscription(user_id: int):
        """Return the currently active subscription row for a user, or None."""
        db = Database()
        if db.connect():
            try:
                query = """
                    SELECT * FROM subscriptions
                     WHERE user_id = ? AND status = 'active'
                  ORDER BY end_date DESC LIMIT 1
                """
                db.execute(query, (user_id,))
                return db.fetchone()
            except sqlite3.Error as exc:
                logging.error("SQLite error in get_user_active_subscription: %s", exc)
            finally:
                db.close()
        return None

    @staticmethod
    def get_all_active_subscribers():
        """Return list of users that have at least one active subscription."""
        db = Database()
        if db.connect():
            try:
                query = """
                    SELECT DISTINCT u.user_id, u.full_name, u.username
                      FROM users u
                      JOIN subscriptions s ON u.user_id = s.user_id
                     WHERE s.status = 'active' AND datetime(s.end_date) > datetime('now')
                """
                if db.execute(query):
                    return db.fetchall()
            except sqlite3.Error as exc:
                logging.error("SQLite error in get_all_active_subscribers: %s", exc)
            finally:
                db.close()
        return []

    @staticmethod
    def get_active_plans():
        """Return list of plans that are marked active."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT id, name FROM plans WHERE is_active = 1 ORDER BY display_order"
                if db.execute(query):
                    return db.fetchall()
            except sqlite3.Error as exc:
                logging.error("SQLite error in get_active_plans: %s", exc)
            finally:
                db.close()
        return []

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
                result = db.fetchone()
                db.close()
                return result
            except sqlite3.Error as e:
                logging.error(f"SQLite error in get_plan_by_id: {e}")
                return None
            finally:
                db.close()
        return None

    @staticmethod
    def get_plan(plan_id: int):
        return DatabaseQueries.get_plan_by_id(plan_id)

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
    def update_payment_expires_at(payment_id: int, expires_at: datetime):
        """Set/Update the *expires_at* timestamp for a payment row."""
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "UPDATE payments SET expires_at = ?, updated_at = ? WHERE payment_id = ?",
                    (expires_at.isoformat(), datetime.now().isoformat(), payment_id),
                )
                db.commit()
                return db.cursor.rowcount > 0
            except sqlite3.Error as e:
                config.logger.error(f"SQLite error in update_payment_expires_at for payment_id {payment_id}: {e}")
                return False
            finally:
                db.close()
        return False

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
                    SELECT DISTINCT u.user_id,
                           COALESCE(s.status, 'no_subscription') AS status
                    FROM users u
                    LEFT JOIN subscriptions s
                          ON s.user_id = u.user_id
                          AND s.status = 'active'
                          AND s.end_date > ?
                    WHERE s.user_id IS NULL          -- user has no active subscription
                       OR s.status IS NULL           -- safety check
                       OR s.status != 'active'
                       OR s.end_date <= ?
                """
                # Note: If a user has NO record in the subscriptions table at all,
                # they won't be caught by this query. This query targets users
                # who HAD a subscription that is now in a non-active state.
                # To catch users in the 'users' table but not in 'subscriptions',
                # a more complex query (e.g., LEFT JOIN) would be needed.
                
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                db.execute(query, (current_time, current_time))
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
    def get_discount_by_id(discount_id: int):
        """Retrieves a discount by its unique ID."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT * FROM discounts WHERE id = ?"
                if db.execute(query, (discount_id,)):
                    return db.fetchone()
            except sqlite3.Error as e:
                print(f"SQLite error in get_discount_by_id: {e}")
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

    # NEW METHODS FOR DISCOUNT CRUD
    @staticmethod
    def update_discount(discount_id: int, **kwargs) -> bool:
        """Update fields of a discount. Pass column=value pairs via kwargs."""
        if not kwargs:
            return False
        db = Database()
        if db.connect():
            try:
                set_clause = ", ".join([f"{col} = ?" for col in kwargs.keys()])
                params = list(kwargs.values()) + [discount_id]
                query = f"UPDATE discounts SET {set_clause} WHERE id = ?"
                if db.execute(query, params):
                    db.commit()
                    return True
            except sqlite3.Error as e:
                print(f"SQLite error in update_discount: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def delete_discount(discount_id: int) -> bool:
        """Deletes a discount and its plan associations."""
        db = Database()
        if db.connect():
            try:
                db.execute("DELETE FROM discounts WHERE id = ?", (discount_id,))
                db.execute("DELETE FROM plan_discounts WHERE discount_id = ?", (discount_id,))
                db.commit()
                return True
            except sqlite3.Error as e:
                print(f"SQLite error in delete_discount: {e}")
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

    # ---------- Ticket helper ----------

    @staticmethod
    def get_tickets_by_user(user_id: int, limit: int = 20):
        """Fetch recent tickets for a given user id ordered by newest."""
        db = Database()
        rows = []
        if db.connect():
            try:
                sql = "SELECT id, subject, status, created_at FROM tickets WHERE user_id = ? ORDER BY created_at DESC LIMIT ?"
                db.execute(sql, (user_id, limit))
                rows = db.fetchall()
            except Exception as e:
                logging.error(f"SQLite error in get_tickets_by_user: {e}")
            finally:
                db.close()
        return rows

    # ---------- Support Users ----------
    @staticmethod
    def add_support_user(telegram_id: int, added_by: int = None) -> bool:
        """Add a new support staff user."""
        db = Database()
        if db.connect():
            try:
                query = "INSERT OR IGNORE INTO support_users (telegram_id, added_by) VALUES (?, ?)"
                if db.execute(query, (telegram_id, added_by)):
                    db.commit()
                    return True
            except Exception as e:
                logging.error(f"SQLite error in add_support_user: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def remove_support_user(telegram_id: int) -> bool:
        db = Database()
        if db.connect():
            try:
                if db.execute("DELETE FROM support_users WHERE telegram_id = ?", (telegram_id,)):
                    db.commit()
                    return True
            except Exception as e:
                logging.error(f"SQLite error in remove_support_user: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def is_support_user(telegram_id: int) -> bool:
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT 1 FROM support_users WHERE telegram_id = ? LIMIT 1", (telegram_id,))
                return db.fetchone() is not None
            except Exception as e:
                logging.error(f"SQLite error in is_support_user: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def get_all_support_users():
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT telegram_id, added_by, added_at FROM support_users")
                return db.fetchall()
            except Exception as e:
                logging.error(f"SQLite error in get_all_support_users: {e}")
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
                query = "SELECT id, name, price, is_active, is_public FROM plans ORDER BY display_order"
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

    @staticmethod
    def get_user_status(user_id: int) -> Optional[str]:
        """Get the status of a user (e.g., 'active', 'banned')."""
        sql = "SELECT status FROM users WHERE user_id = ?"
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(sql, (user_id,))
                result = cursor.fetchone()
                return result[0] if result else None
        except sqlite3.Error as e:
            logger.error(f"Database error in get_user_status for user {user_id}: {e}")
            return None

    @staticmethod
    def set_user_status(user_id: int, status: str) -> bool:
        """Set the status of a user (e.g., 'active', 'banned')."""
        if status not in ['active', 'banned']:
            logger.warning(f"Invalid status '{status}' provided for set_user_status.")
            return False
        sql = "UPDATE users SET status = ? WHERE user_id = ?"
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(sql, (status, user_id))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"Database error in set_user_status for user {user_id}: {e}")
            return False
