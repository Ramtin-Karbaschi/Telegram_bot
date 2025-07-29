#!/usr/bin/env python3
"""
بررسی داده‌های درآمد در پایگاه داده
"""

from database.models import Database

def check_revenue_data():
    db = Database()
    if not db.connect():
        print("❌ خطا در اتصال به دیتابیس")
        return
        
    try:
        print("🔍 بررسی داده‌های درآمد...\n")
        
        # بررسی جدول payments
        print("📊 جدول payments:")
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT payment_id, amount, status, plan_id, payment_method, usdt_amount_requested
            FROM payments 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                print(f"  Payment ID: {row[0]}, Amount: {row[1]}, Status: {row[2]}, Plan: {row[3]}, Method: {row[4]}, USDT: {row[5]}")
        else:
            print("  هیچ رکوردی یافت نشد")
            
        # بررسی جدول crypto_payments  
        print("\n💰 جدول crypto_payments:")
        cursor.execute("""
            SELECT id, rial_amount, usdt_amount_received, usdt_amount_requested, status
            FROM crypto_payments 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                print(f"  Crypto ID: {row[0]}, Rial: {row[1]}, USDT Received: {row[2]}, USDT Requested: {row[3]}, Status: {row[4]}")
        else:
            print("  هیچ رکوردی یافت نشد")
            
        # آمار کلی پرداخت‌ها
        print("\n📈 آمار کلی پرداخت‌ها:")
        
        # IRR از payments
        cursor.execute("""
            SELECT COUNT(*), SUM(amount) 
            FROM payments 
            WHERE status IN ('paid', 'completed', 'successful', 'verified')
            AND amount IS NOT NULL
        """)
        row = cursor.fetchone()
        print(f"  IRR Payments: {row[0]} تراکنش، مجموع: {row[1] or 0} ریال")
        
        # USDT از payments
        cursor.execute("""
            SELECT COUNT(*), SUM(usdt_amount_requested) 
            FROM payments 
            WHERE status IN ('paid', 'completed', 'successful', 'verified')
            AND usdt_amount_requested IS NOT NULL
        """)
        row = cursor.fetchone()
        print(f"  USDT از payments: {row[0]} تراکنش، مجموع: {row[1] or 0} USDT")
        
        # USDT از crypto_payments
        cursor.execute("""
            SELECT COUNT(*), SUM(usdt_amount_received) 
            FROM crypto_payments 
            WHERE status IN ('paid', 'completed', 'successful', 'verified')
            AND usdt_amount_received IS NOT NULL
        """)
        row = cursor.fetchone()
        print(f"  USDT از crypto_payments: {row[0]} تراکنش، مجموع: {row[1] or 0} USDT")
        
        # IRR از crypto_payments
        cursor.execute("""
            SELECT COUNT(*), SUM(rial_amount) 
            FROM crypto_payments 
            WHERE status IN ('paid', 'completed', 'successful', 'verified')
            AND rial_amount IS NOT NULL
        """)
        row = cursor.fetchone()
        print(f"  IRR از crypto_payments: {row[0]} تراکنش، مجموع: {row[1] or 0} ریال")
        
    except Exception as e:
        print(f"❌ خطا: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_revenue_data()
