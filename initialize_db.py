"""
Initialize database with correct schema and sample data
"""

import os
import sqlite3
from database.schema import ALL_TABLES
import config

def initialize_database():
    """Initialize the database with the correct schema and sample data"""
    # Remove existing database if it exists
    if os.path.exists(config.DATABASE_NAME):
        os.remove(config.DATABASE_NAME)
        print(f"Removed existing database: {config.DATABASE_NAME}")
    
    # Make sure the directory exists
    db_dir = os.path.dirname(config.DATABASE_NAME)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        print(f"Created database directory: {db_dir}")
    
    # Create connection
    conn = sqlite3.connect(config.DATABASE_NAME)
    cursor = conn.cursor()
    
    # Create tables
    for table_sql in ALL_TABLES:
        cursor.execute(table_sql)
        
    # Add subscription plans
    # id, name, description, price (IRR final), original_price_irr, price_tether (final), original_price_usdt, days, features, is_active, display_order
    subscription_plans = [
        (1, "یک ماهه", "اشتراک یک ماهه آکادمی دارایی", 500000, 550000, None, None, 30, '["دسترسی به تمام محتوای آکادمی"]', 1, 1),
        (2, "سه ماهه", "اشتراک سه ماهه آکادمی دارایی (۱۰٪ تخفیف)", 1350000, 1500000, None, None, 90, '["دسترسی به تمام محتوای آکادمی"]', 1, 2),
        (3, "شش ماهه", "اشتراک شش ماهه آکادمی دارایی (۲۰٪ تخفیف)", 2400000, 3000000, None, None, 180, '["دسترسی به تمام محتوای آکادمی", "جلسات پرسش و پاسخ"]', 1, 3),
        (4, "یک ساله", "اشتراک یک ساله آکادمی دارایی (۳۰٪ تخفیف)", 4200000, 6000000, None, None, 365, '["دسترسی به تمام محتوای آکادمی", "جلسات پرسش و پاسخ", "مشاوره اختصاصی"]', 1, 4)
        # Add price_tether and original_price_usdt values if/when USDT payment is fully integrated and priced
    ]
    
    cursor.executemany(
        "INSERT INTO plans (id, name, description, price, original_price_irr, price_tether, original_price_usdt, days, features, is_active, display_order) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        subscription_plans
    )
    
    # Commit changes and close connection
    conn.commit()
    conn.close()
    
    print(f"Database initialized successfully: {config.DATABASE_NAME}")
    print(f"Added {len(subscription_plans)} subscription plans")

if __name__ == "__main__":
    initialize_database()
