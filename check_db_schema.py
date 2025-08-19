import sqlite3

conn = sqlite3.connect('database/data/daraei_academy.db')
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(plans)")
print("Plans table columns:")
for col in cursor.fetchall():
    print(f"  {col}")

conn.close()
