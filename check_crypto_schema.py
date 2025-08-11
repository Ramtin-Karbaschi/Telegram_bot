#!/usr/bin/env python3
"""Check crypto_payments table schema"""
import sqlite3
import os

db_path = os.path.join('database', 'data', 'daraei_academy.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check if crypto_payments table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crypto_payments'")
if cursor.fetchone():
    print("crypto_payments table exists\n")
    cursor.execute("PRAGMA table_info(crypto_payments)")
    print("crypto_payments table schema:")
    for col in cursor.fetchall():
        print(f"  {col[1]:20} - {col[2]:15} {'NOT NULL' if col[3] else 'NULL':10} {f'DEFAULT {col[4]}' if col[4] else ''}")
else:
    print("crypto_payments table does not exist")

# Check payments table structure
print("\n" + "="*60)
cursor.execute("PRAGMA table_info(payments)")
print("payments table schema:")
for col in cursor.fetchall():
    print(f"  {col[1]:20} - {col[2]:15} {'NOT NULL' if col[3] else 'NULL':10} {f'DEFAULT {col[4]}' if col[4] else ''}")

# Check plans table structure  
print("\n" + "="*60)
cursor.execute("PRAGMA table_info(plans)")
print("plans table schema:")
for col in cursor.fetchall():
    print(f"  {col[1]:20} - {col[2]:15} {'NOT NULL' if col[3] else 'NULL':10} {f'DEFAULT {col[4]}' if col[4] else ''}")

conn.close()
