"""
Database models for the Daraei Academy Telegram bot
"""

import uuid
from datetime import datetime, timedelta
import sqlite3
import os
import config
import threading

# A lock to make the singleton creation thread-safe
_lock = threading.Lock()
_instance = None

class Database:
    """
    SQLite database connection and initialization.
    This class is implemented as a singleton to ensure a single, shared
    database connection is used throughout the application, preventing
    'database is locked' errors in a concurrent environment.
    """
    
    @staticmethod
    def get_instance():
        """Return existing Database singleton instance or create default one."""
        global _instance
        if _instance is None:
            _instance = Database()
        return _instance

    def __new__(cls, *args, **kwargs):
        global _instance
        if _instance is None:
            with _lock:
                if _instance is None:
                    _instance = super().__new__(cls)
        return _instance

    def __init__(self, db_name=None):
        # The __init__ might be called multiple times, but we only want to
        # initialize the connection once.
        if hasattr(self, 'conn') and self.conn is not None:
            return

        if db_name is None:
            if hasattr(config, 'DATABASE_NAME') and config.DATABASE_NAME:
                self.db_name = config.DATABASE_NAME
            else:
                default_db_path = "default_database.db"
                print(f"CRITICAL: DATABASE_NAME not found in config or passed as argument. Using default: {os.path.abspath(default_db_path)}")
                self.db_name = default_db_path
        else:
            self.db_name = db_name
            
        print(f"Database singleton initialized. Attempting to use database at: {os.path.abspath(self.db_name)}") 
        self.conn = None
        self.cursor = None
        self.connect()
        
    def connect(self):
        """Connect to the SQLite database if not already connected."""
        if self.conn is not None:
            return True
        try:
            print(f"Connecting to: {os.path.abspath(self.db_name)}")
            # `check_same_thread=False` is crucial for sharing the connection
            # across different parts of the async application.
            self.conn = sqlite3.connect(self.db_name, timeout=10, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()
            print(f"Successfully connected to {os.path.abspath(self.db_name)}")
            return True
        except sqlite3.Error as e:
            print(f"Database connection error for {os.path.abspath(self.db_name)}: {e}")
            self.conn = None
            return False
            
    def close(self):
        """
        This is a no-op in the singleton implementation to prevent the shared
        connection from being closed prematurely by a single handler.
        """
        pass
            
    def commit(self):
        """Commit changes to the database"""
        if self.conn:
            self.conn.commit()
            
    def execute(self, query, params=()):
        """Execute a database query with parameters"""
        try:
            # Using a single, shared cursor is not ideal for thread-safety,
            # but for an asyncio app, it's often sufficient and avoids
            # major refactoring. The primary goal is to stop opening/closing connections.
            self.cursor.execute(query, params)
            return True
        except sqlite3.Error as e:
            print(f"Query execution error: {e}")
            print(f"Query: {query}")
            print(f"Params: {params}")
            return False
            
    def executemany(self, query, params_list):
        """Execute a database query with multiple parameter sets"""
        try:
            self.cursor.executemany(query, params_list)
            return True
        except sqlite3.Error as e:
            print(f"Query execution error: {e}")
            return False
            
    def fetchone(self):
        """Fetch a single row from the result set"""
        return self.cursor.fetchone()
        
    def fetchall(self):
        """Fetch all rows from the result set"""
        return self.cursor.fetchall()
        
    def create_tables(self, tables):
        """Create database tables if they don't exist"""
        for table_query in tables:
            if not self.execute(table_query):
                return False
        self.commit()
        return True

    # --- Crypto Payment Management ---
    def create_crypto_payment_request(self, user_id, rial_amount, usdt_amount_requested, wallet_address, expires_at):
        """Creates a new crypto payment request and returns its unique payment_id."""
        payment_id = str(uuid.uuid4())
        query = """
            INSERT INTO crypto_payments 
            (user_id, payment_id, rial_amount, usdt_amount_requested, wallet_address, expires_at, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now()
        params = (user_id, payment_id, rial_amount, usdt_amount_requested, wallet_address, expires_at, 'pending', now, now)
        if self.execute(query, params):
            self.commit()
            return payment_id
        return None

    def update_crypto_payment_on_success(self, payment_id, transaction_id, usdt_amount_received):
        """Updates a crypto payment record upon successful confirmation."""
        query = """
            UPDATE crypto_payments 
            SET transaction_id = ?, usdt_amount_received = ?, status = 'paid', updated_at = ?
            WHERE payment_id = ? AND status = 'pending'
        """
        params = (transaction_id, usdt_amount_received, datetime.now(), payment_id)
        if self.execute(query, params):
            self.commit()
            return self.cursor.rowcount > 0
        return False

    def get_crypto_payment_by_payment_id(self, payment_id):
        """Retrieves a crypto payment by its unique payment_id."""
        query = "SELECT * FROM crypto_payments WHERE payment_id = ?"
        if self.execute(query, (payment_id,)):
            return self.fetchone()
        return None

    def get_crypto_payment_by_transaction_id(self, transaction_id):
        """Retrieves a crypto payment by its blockchain transaction_id."""
        query = "SELECT * FROM crypto_payments WHERE transaction_id = ?"
        if self.execute(query, (transaction_id,)):
            return self.fetchone()
        return None

    def get_pending_crypto_payment_by_user_and_amount(self, user_id, usdt_amount_requested):
        """Retrieves a pending crypto payment for a specific user and requested USDT amount."""
        query = """
            SELECT * FROM crypto_payments 
            WHERE user_id = ? AND usdt_amount_requested = ? AND status = 'pending' AND expires_at > ?
            ORDER BY created_at DESC LIMIT 1
        """
        if self.execute(query, (user_id, usdt_amount_requested, datetime.now())):
            return self.fetchone()
        return None

    def get_expired_pending_payments(self):
        """Retrieves all pending crypto payments that have passed their expiration time."""
        query = "SELECT * FROM crypto_payments WHERE status = 'pending' AND expires_at <= ?"
        if self.execute(query, (datetime.now(),)):
            return self.fetchall()
        return []
