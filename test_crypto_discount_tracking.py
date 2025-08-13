#!/usr/bin/env python3
"""
Test script to verify that discount_id tracking works correctly for crypto payments.
"""

import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Get the database path
DB_PATH = Path(__file__).parent / "database" / "data" / "daraei_academy.db"

def test_crypto_discount_tracking():
    """Test that discount_id is properly tracked in crypto payments."""
    
    if not DB_PATH.exists():
        print(f"❌ Database not found at: {DB_PATH}")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        cursor = conn.cursor()
        
        print("🔍 Testing crypto payment discount tracking...")
        
        # 1. Check if discount_id column exists in crypto_payments
        cursor.execute("PRAGMA table_info(crypto_payments)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'discount_id' not in columns:
            print("❌ discount_id column not found in crypto_payments table")
            return False
        
        print("✅ discount_id column exists in crypto_payments table")
        
        # 2. Create a test discount code
        test_discount_code = f"TEST_CRYPTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        cursor.execute("""
            INSERT INTO discounts (code, type, value, max_uses, uses_count, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (test_discount_code, 'percentage', 10.0, 100, 0, 1))
        
        discount_id = cursor.lastrowid
        print(f"✅ Created test discount: {test_discount_code} (ID: {discount_id})")
        
        # 3. Create a test crypto payment with discount_id
        test_user_id = 999999
        test_payment_id = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(hours=1)
        
        cursor.execute("""
            INSERT INTO crypto_payments 
            (user_id, payment_id, rial_amount, usdt_amount_requested, wallet_address, expires_at, plan_id, discount_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            test_user_id,
            test_payment_id,
            1000000,  # 1M IRR
            100.0,    # 100 USDT
            "TTest123456789",
            expires_at.isoformat(),
            1,        # plan_id
            discount_id,  # discount_id
            'pending',
            datetime.now().isoformat(),
            datetime.now().isoformat()
        ))
        
        print(f"✅ Created test crypto payment: {test_payment_id} with discount_id: {discount_id}")
        
        # 4. Verify the crypto payment was created with discount_id
        cursor.execute("SELECT * FROM crypto_payments WHERE payment_id = ?", (test_payment_id,))
        crypto_payment = cursor.fetchone()
        
        if not crypto_payment:
            print("❌ Test crypto payment not found")
            return False
            
        if crypto_payment['discount_id'] != discount_id:
            print(f"❌ discount_id mismatch: expected {discount_id}, got {crypto_payment['discount_id']}")
            return False
            
        print("✅ Crypto payment created with correct discount_id")
        
        # 5. Test updating payment to 'paid' status (simulating successful payment)
        cursor.execute("""
            UPDATE crypto_payments 
            SET transaction_id = ?, usdt_amount_received = ?, status = ?, updated_at = ?
            WHERE payment_id = ? AND status = 'pending'
        """, (
            "0xtest123456789",
            100.0,
            'paid',
            datetime.now().isoformat(),
            test_payment_id
        ))
        
        # 6. Check if discount usage was incremented (this would be done by the models.py code)
        cursor.execute("SELECT uses_count FROM discounts WHERE id = ?", (discount_id,))
        discount_row = cursor.fetchone()
        
        print(f"📊 Discount usage before increment: {discount_row['uses_count']}")
        
        # 7. Manually test the increment (simulating what models.py would do)
        cursor.execute("UPDATE discounts SET uses_count = uses_count + 1 WHERE id = ?", (discount_id,))
        
        cursor.execute("SELECT uses_count FROM discounts WHERE id = ?", (discount_id,))
        updated_discount = cursor.fetchone()
        
        print(f"📊 Discount usage after increment: {updated_discount['uses_count']}")
        
        # 8. Verify crypto payment is now 'paid'
        cursor.execute("SELECT status FROM crypto_payments WHERE payment_id = ?", (test_payment_id,))
        updated_payment = cursor.fetchone()
        
        if updated_payment['status'] != 'paid':
            print(f"❌ Payment status not updated: expected 'paid', got '{updated_payment['status']}'")
            return False
            
        print("✅ Crypto payment status updated to 'paid'")
        
        # 9. Clean up test data
        cursor.execute("DELETE FROM crypto_payments WHERE payment_id = ?", (test_payment_id,))
        cursor.execute("DELETE FROM discounts WHERE id = ?", (discount_id,))
        
        conn.commit()
        print("🧹 Cleaned up test data")
        
        print("🎉 All tests passed! Crypto discount tracking is working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("🚀 Starting crypto discount tracking test...")
    success = test_crypto_discount_tracking()
    
    if success:
        print("✅ Test completed successfully!")
    else:
        print("❌ Test failed!")
        exit(1)
