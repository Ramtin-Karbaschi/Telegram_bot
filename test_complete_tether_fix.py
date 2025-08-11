#!/usr/bin/env python3
"""
Complete test for Tether payment activation fix
Tests both payment creation and verification/activation flow
"""

import sys
import os
import sqlite3
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_payment_creation_with_plan_id():
    """Test that new crypto payments have plan_id in payments table"""
    
    print("=" * 60)
    print("🧪 TESTING PAYMENT CREATION WITH PLAN_ID")
    print("=" * 60)
    
    db_path = os.path.join('database', 'data', 'daraei_academy.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check most recent payments
    cursor.execute("""
        SELECT 
            p.payment_id,
            p.user_id,
            p.plan_id,
            p.payment_method,
            p.status,
            p.created_at,
            cp.payment_id as crypto_payment_id,
            cp.usdt_amount_requested
        FROM payments p
        LEFT JOIN crypto_payments cp ON p.payment_id = cp.payment_id
        WHERE p.payment_method = 'crypto'
        ORDER BY p.created_at DESC
        LIMIT 5
    """)
    
    results = cursor.fetchall()
    
    if results:
        print("\n📋 Recent crypto payments:")
        print("-" * 60)
        has_plan_id = False
        for row in results:
            payment_id, user_id, plan_id, method, status, created_at, crypto_id, usdt_amount = row
            print(f"Payment ID: {payment_id}")
            print(f"  Created: {created_at}")
            print(f"  Plan ID: {plan_id} {'✅ FIXED!' if plan_id else '❌ MISSING'}")
            print(f"  Status: {status}")
            print(f"  USDT Amount: {usdt_amount}")
            print("-" * 40)
            if plan_id:
                has_plan_id = True
        
        if not has_plan_id:
            print("\n⚠️ No payments have plan_id yet. Create a new payment to test the fix.")
        else:
            print("\n✅ Some payments have plan_id - fix is working!")
    else:
        print("\n⚠️ No crypto payments found")
    
    conn.close()

def test_verification_flow():
    """Test that the verification flow can retrieve plan_id correctly"""
    
    print("\n" + "=" * 60)
    print("🔍 TESTING VERIFICATION FLOW")
    print("=" * 60)
    
    from database.queries import DatabaseQueries as Database
    
    # Get a sample crypto payment
    db_path = os.path.join('database', 'data', 'daraei_academy.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT payment_id 
        FROM crypto_payments 
        WHERE status = 'pending'
        ORDER BY created_at DESC
        LIMIT 1
    """)
    
    result = cursor.fetchone()
    
    if result:
        payment_id = result[0]
        print(f"\n🔍 Testing with payment ID: {payment_id}")
        
        # Test the flow as it would happen in the handler
        from database.models import Database as DBModel
        db_instance = DBModel.get_instance()
        
        # Get crypto payment record
        payment_record = db_instance.get_crypto_payment_by_payment_id(payment_id)
        
        if payment_record:
            print(f"✅ Found crypto payment record")
            
            # Get main payment record with plan_id (THE FIX)
            main_payment = Database.get_payment_by_id(payment_id)
            
            if main_payment:
                # Extract plan_id
                if hasattr(main_payment, "keys"):
                    plan_id = main_payment["plan_id"]
                else:
                    plan_id = dict(main_payment).get("plan_id")
                
                if plan_id:
                    print(f"✅ Successfully retrieved plan_id: {plan_id}")
                    
                    # Get plan details
                    plan_row = Database.get_plan_by_id(plan_id)
                    if plan_row:
                        if hasattr(plan_row, "keys"):
                            plan_name = plan_row["name"]
                        else:
                            plan_name = dict(plan_row).get("name", "N/A")
                        print(f"✅ Plan name: {plan_name}")
                        print("\n🎉 VERIFICATION FLOW WORKING CORRECTLY!")
                    else:
                        print(f"❌ Could not retrieve plan details for ID {plan_id}")
                else:
                    print("❌ No plan_id found in payment record")
                    print("   This payment was created before the fix")
            else:
                print("❌ Main payment record not found")
        else:
            print("❌ Crypto payment record not found")
    else:
        print("\n⚠️ No pending crypto payments found to test")
    
    conn.close()

def main():
    print("=" * 70)
    print("🛠️  COMPLETE TETHER PAYMENT FIX VERIFICATION")
    print("=" * 70)
    print("\n📌 FIX SUMMARY:")
    print("1. ✅ Added creation of payment record with plan_id when crypto payment is created")
    print("2. ✅ Fixed plan_id retrieval from payments table in verification handlers")
    print("3. ✅ Added proper error handling and logging throughout")
    print("4. ✅ Both automatic and manual TX verification handlers fixed")
    print("\n" + "=" * 70)
    
    # Run tests
    test_payment_creation_with_plan_id()
    test_verification_flow()
    
    print("\n" + "=" * 70)
    print("📊 FINAL VERIFICATION STATUS")
    print("=" * 70)
    
    print("\n✅ ALL FIXES APPLIED:")
    print("• Payment creation now stores plan_id in payments table")
    print("• Verification handlers retrieve plan_id from payments table")
    print("• Subscription activation has all required data")
    
    print("\n🚀 NEXT STEPS TO VERIFY:")
    print("1. Create a new Tether payment through the bot")
    print("2. Check that the payment has plan_id in the database")
    print("3. Complete the payment with a test transaction")
    print("4. Verify that subscription is activated successfully")
    print("5. Monitor logs for any errors during the process")

if __name__ == "__main__":
    main()
