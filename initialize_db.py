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
    subscription_plans = [
        (1, "یک ماهه", "اشتراک یک ماهه دارای اکادمی", 500000, 30, "دسترسی به تمام محتوای اکادمی", 1),
        (2, "سه ماهه", "اشتراک سه ماهه دارای اکادمی با ۱۰٪ تخفیف", 1350000, 90, "دسترسی به تمام محتوای اکادمی", 1),
        (3, "شش ماهه", "اشتراک شش ماهه دارای اکادمی با ۲۰٪ تخفیف", 2400000, 180, "دسترسی به تمام محتوای اکادمی + جلسات پرسش و پاسخ", 1),
        (4, "یک ساله", "اشتراک یک ساله دارای اکادمی با ۳۰٪ تخفیف", 4200000, 365, "دسترسی به تمام محتوای اکادمی + جلسات پرسش و پاسخ + مشاوره اختصاصی", 1)
    ]
    
    cursor.executemany(
        "INSERT INTO plans (id, name, description, price, duration, features, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
        subscription_plans
    )
    
    # Commit changes and close connection
    conn.commit()
    conn.close()
    
    print(f"Database initialized successfully: {config.DATABASE_NAME}")
    print(f"Added {len(subscription_plans)} subscription plans")

if __name__ == "__main__":
    initialize_database()
