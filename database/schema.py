"""Database schema definitions for the Daraei Academy Telegram bot."""

# SQL statements for creating database tables
USERS_TABLE = '''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    phone TEXT,
    full_name TEXT,
    age INTEGER,
    birth_date TEXT,
    education TEXT,
    occupation TEXT,
    city TEXT,
    email TEXT,
    registration_date TEXT,
    last_activity TEXT,
    status TEXT DEFAULT 'active' NOT NULL
)
'''

PLANS_TABLE = '''
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    price REAL NOT NULL,       -- Final payable price in IRR
    original_price_irr REAL, -- Original price in IRR before discount, nullable
    price_tether REAL,         -- Final payable price in USDT
    original_price_usdt REAL,  -- Original price in USDT before discount, nullable
    days INTEGER NOT NULL,     -- Duration in days
    features TEXT, -- JSON string for list of features
    plan_type TEXT DEFAULT 'subscription' NOT NULL, -- e.g., 'subscription', 'one_time_content'
    expiration_date TEXT DEFAULT NULL, -- Date when the plan is no longer available, NULL for no expiry
    is_active INTEGER DEFAULT 1, -- 0 for inactive, 1 for active
    display_order INTEGER DEFAULT 0, -- For ordering plans in lists
    capacity INTEGER DEFAULT NULL -- Maximum number of subscribers, NULL for unlimited
)
'''

SUBSCRIPTIONS_TABLE = '''
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    plan_id INTEGER,
    payment_id INTEGER,          -- ID of the payment record for this specific transaction
    start_date TEXT,             -- Initial start date of the subscription period
    end_date TEXT,               -- Current expiration date of the subscription
    amount_paid REAL,            -- The actual amount paid for the latest transaction that activated/extended this subscription
    payment_method TEXT,         -- Method used for the latest transaction (e.g., 'rial', 'tether')
    status TEXT DEFAULT 'active',-- Status of the subscription (e.g., 'active', 'expired', 'cancelled')
    created_at TEXT,             -- Timestamp of when the subscription record was first created
    updated_at TEXT,             -- Timestamp of when the subscription record was last updated (e.g., on renewal)
    FOREIGN KEY (user_id) REFERENCES users (user_id),
    FOREIGN KEY (plan_id) REFERENCES plans (id),
    FOREIGN KEY (payment_id) REFERENCES payments (payment_id) -- Updated foreign key for payment_id
)
'''

PAYMENTS_TABLE = '''
CREATE TABLE IF NOT EXISTS payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    plan_id INTEGER,            -- Added to link payment to a specific plan
    amount REAL,
    payment_date TEXT,          -- Should be populated when payment is initiated or confirmed
    payment_method TEXT,        -- e.g., 'zarinpal', 'crypto_usdt_trc20'
    transaction_id TEXT,        -- Stores Zarinpal Authority or initial Crypto Tx Hash provided by user
    gateway_ref_id TEXT,        -- Stores final Zarinpal RefID or confirmed Crypto Tx Hash from network
    description TEXT,
    status TEXT DEFAULT 'pending', -- e.g., pending, pending_verification, completed, failed, cancelled, expired, refunded
    created_at TEXT,            -- Timestamp of when the payment record was created
    updated_at TEXT,            -- Timestamp of when the payment record was last updated
    FOREIGN KEY (user_id) REFERENCES users (user_id),
    FOREIGN KEY (plan_id) REFERENCES plans (id) -- Added foreign key for plan_id
)
'''

TICKETS_TABLE = '''
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    subject TEXT,
    created_at TEXT,
    status TEXT DEFAULT 'open',
    FOREIGN KEY (user_id) REFERENCES users (user_id)
)
'''

TICKET_MESSAGES_TABLE = '''
CREATE TABLE IF NOT EXISTS ticket_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER,
    user_id INTEGER,
    message TEXT,
    timestamp TEXT,
    is_admin INTEGER DEFAULT 0,
    FOREIGN KEY (ticket_id) REFERENCES tickets (id),
    FOREIGN KEY (user_id) REFERENCES users (user_id)
)
'''

INVITE_LINKS_TABLE = '''
CREATE TABLE IF NOT EXISTS invite_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    invite_link TEXT,
    creation_date TEXT,
    expiration_date TEXT,
    is_used INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
)
'''

NOTIFICATIONS_TABLE = '''
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    content TEXT,
    sent_date TEXT,
    is_read INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users (user_id)
)
'''

CRYPTO_PAYMENTS_TABLE = '''
CREATE TABLE IF NOT EXISTS crypto_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    payment_id TEXT UNIQUE NOT NULL, -- Unique identifier for this payment attempt (e.g., UUID)
    rial_amount REAL NOT NULL,
    usdt_amount_requested REAL NOT NULL,
    usdt_amount_received REAL, -- Actual USDT amount confirmed on blockchain
    wallet_address TEXT NOT NULL, -- The wallet address payment was requested to
    transaction_id TEXT UNIQUE, -- Blockchain transaction ID, initially NULL
    status TEXT NOT NULL DEFAULT 'pending', -- e.g., pending, paid, expired, failed, error, underpaid, overpaid
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Tracks the last status update
    expires_at TIMESTAMP NOT NULL, -- When this payment request becomes invalid
    FOREIGN KEY (user_id) REFERENCES users (user_id)
)
'''



PAYMENT_STATUS_HISTORY_TABLE = '''
CREATE TABLE IF NOT EXISTS payment_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id TEXT NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_by TEXT NOT NULL DEFAULT 'bot', -- 'bot' or admin username/id
    note TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
'''

USER_ACTIVITY_LOGS_TABLE = '''
CREATE TABLE IF NOT EXISTS user_activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    telegram_id BIGINT NOT NULL,
    action_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    details TEXT, -- JSON string for additional data
    FOREIGN KEY(user_id) REFERENCES users(user_id)
)
'''

BANNED_USERS_TABLE = '''
CREATE TABLE IF NOT EXISTS banned_users (
    user_id INTEGER PRIMARY KEY,
    reason TEXT,
    banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
'''

SUPPORT_USERS_TABLE = '''
CREATE TABLE IF NOT EXISTS support_users (
    telegram_id INTEGER PRIMARY KEY,
    added_by INTEGER,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
'''

DISCOUNTS_TABLE = '''
CREATE TABLE IF NOT EXISTS discounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK(type IN ('percentage', 'fixed_amount')),
    value REAL NOT NULL,
    start_date TIMESTAMP,
    end_date TIMESTAMP,
    max_uses INTEGER,
    uses_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT 1
);
'''

PLAN_DISCOUNTS_TABLE = '''
CREATE TABLE IF NOT EXISTS plan_discounts (
    plan_id INTEGER,
    discount_id INTEGER,
    PRIMARY KEY (plan_id, discount_id),
    FOREIGN KEY (plan_id) REFERENCES plans(id),
    FOREIGN KEY (discount_id) REFERENCES discounts(id)
);
'''

# List of all tables to create
ALL_TABLES = [
    USERS_TABLE,
    PLANS_TABLE,
    SUBSCRIPTIONS_TABLE,
    PAYMENTS_TABLE,
    TICKETS_TABLE,
    TICKET_MESSAGES_TABLE,
    INVITE_LINKS_TABLE,
    NOTIFICATIONS_TABLE,
    CRYPTO_PAYMENTS_TABLE,
    USER_ACTIVITY_LOGS_TABLE,
    DISCOUNTS_TABLE,
    PLAN_DISCOUNTS_TABLE,
    PAYMENT_STATUS_HISTORY_TABLE,
    SUPPORT_USERS_TABLE
]

if __name__ == '__main__':
    import sys
    import os
    # Add the project root to the Python path
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    sys.path.insert(0, project_root)
    from database.models import Database
    print("Initializing database schema...")
    db = Database()
    if db.connect():
        try:
            for table_query in ALL_TABLES:
                print(f"Executing: {table_query[:50].strip()}...") # Print first 50 chars of query
                if not db.execute(table_query):
                    print(f"Failed to create a table. Aborting.")
                    break
            db.commit()
            print("Database schema initialized successfully.")
        except Exception as e:
            print(f"An error occurred during schema initialization: {e}")
        finally:
            db.close()
            print("Database connection closed.")
    else:
        print("Failed to connect to the database.")
