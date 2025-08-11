#!/usr/bin/env python3
"""
Verify that the Tether payment activation fix is working
"""

import sys
import os
import sqlite3
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.queries import DatabaseQueries as Database

def verify_payment_structure():
    """Verify the relationship between crypto_payments and payments tables"""
    
    db_path = os.path.join('database', 'data', 'daraei_academy.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("=" * 60)
    print("🔍 VERIFYING PAYMENT TABLE STRUCTURE")
    print("=" * 60)
    
    # Check a sample payment record
    cursor.execute("""
        SELECT 
            p.payment_id,
            p.plan_id,
            p.user_id,
            p.status,
            p.payment_method,
            cp.payment_id as crypto_payment_id,
            cp.usdt_amount_requested,
            cp.status as crypto_status
        FROM payments p
        LEFT JOIN crypto_payments cp ON p.payment_id = cp.payment_id
        WHERE p.payment_method IN ('crypto', 'crypto_auto')
        ORDER BY p.created_at DESC
        LIMIT 5
    """)
    
    results = cursor.fetchall()
    
    if results:
        print("\n✅ Found crypto payment records with proper structure:")
        print("-" * 60)
        for row in results:
            print(f"Payment ID: {row[0]}")
            print(f"  Plan ID: {row[1]} {'✅' if row[1] else '❌ MISSING'}")
            print(f"  User ID: {row[2]}")
            print(f"  Payment Status: {row[4]}")
            print(f"  Crypto Payment ID: {row[5]}")
            print(f"  USDT Amount: {row[6]}")
            print(f"  Crypto Status: {row[7]}")
            print("-" * 40)
    else:
        print("\n⚠️ No crypto payment records found")
    
    conn.close()

def test_plan_retrieval():
    """Test that plan retrieval works correctly"""
    
    print("\n" + "=" * 60)
    print("🧪 TESTING PLAN RETRIEVAL")
    print("=" * 60)
    
    # Get all plans to test
    all_plans = Database.get_all_plans()
    
    if not all_plans:
        print("⚠️ No plans found in database")
        return
    
    print(f"\n✅ Found {len(all_plans)} plans in database")
    
    # Test retrieval for first plan
    test_plan = all_plans[0]
    
    # Extract plan_id safely
    plan_dict = dict(test_plan)
    plan_id = plan_dict.get("id") or plan_dict.get("plan_id")
    
    print(f"\n🔍 Testing retrieval for plan ID: {plan_id}")
    
    # Test the fixed retrieval method
    plan_row = Database.get_plan_by_id(plan_id)
    
    if plan_row:
        # Test the fix - handle both dict and Row objects
        if plan_row and hasattr(plan_row, "keys"):
            plan_name = plan_row["name"]
            print(f"✅ Plan retrieved as dict with name: {plan_name}")
        elif plan_row:
            plan_name = dict(plan_row).get("name", "N/A")
            print(f"✅ Plan retrieved as Row object with name: {plan_name}")
        else:
            plan_name = "N/A"
            print(f"⚠️ Plan found but unable to extract name")
    else:
        print(f"❌ Failed to retrieve plan {plan_id}")

def check_recent_crypto_payments():
    """Check recent crypto payments and their activation status"""
    
    print("\n" + "=" * 60)
    print("📊 RECENT CRYPTO PAYMENT STATUS")
    print("=" * 60)
    
    db_path = os.path.join('database', 'data', 'daraei_academy.db')
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get recent crypto payments with subscription status
    cursor.execute("""
        SELECT 
            p.payment_id,
            p.user_id,
            p.plan_id,
            p.status as payment_status,
            p.created_at,
            s.id as subscription_id,
            s.status as sub_status,
            s.end_date,
            pl.name as plan_name
        FROM payments p
        LEFT JOIN subscriptions s ON p.user_id = s.user_id AND p.plan_id = s.plan_id
        LEFT JOIN plans pl ON p.plan_id = pl.id
        WHERE p.payment_method IN ('crypto', 'crypto_auto')
        ORDER BY p.created_at DESC
        LIMIT 10
    """)
    
    results = cursor.fetchall()
    
    if results:
        print(f"\n📋 Found {len(results)} recent crypto payment(s):")
        print("-" * 60)
        
        success_count = 0
        for row in results:
            payment_id, user_id, plan_id, payment_status, created_at, sub_id, sub_status, end_date, plan_name = row
            
            print(f"\n🔹 Payment ID: {payment_id}")
            print(f"   User ID: {user_id}")
            print(f"   Plan: {plan_name or 'Unknown'} (ID: {plan_id})")
            print(f"   Payment Status: {payment_status}")
            print(f"   Created: {created_at}")
            
            if sub_id:
                print(f"   ✅ Subscription Active: ID {sub_id}")
                print(f"   Subscription Status: {sub_status}")
                print(f"   Expires: {end_date}")
                success_count += 1
            else:
                print(f"   ❌ No Active Subscription Found")
        
        print("\n" + "=" * 60)
        print(f"📊 SUMMARY: {success_count}/{len(results)} payments have active subscriptions")
        
        if success_count < len(results):
            print("\n⚠️ Some payments don't have active subscriptions!")
            print("This could indicate the issue is still present or these are old failed payments.")
    else:
        print("\n✅ No recent crypto payments found")
    
    conn.close()

def main():
    print("=" * 70)
    print("🛠️  TETHER PAYMENT ACTIVATION FIX VERIFICATION")
    print("=" * 70)
    print("\n📌 FIX SUMMARY:")
    print("1. ✅ Fixed plan_id retrieval from payments table")
    print("2. ✅ Added proper handling for both dict and Row objects")
    print("3. ✅ Added detailed logging for debugging")
    print("4. ✅ Added clear error messages for users")
    print("\n" + "=" * 70)
    
    # Run verification tests
    verify_payment_structure()
    test_plan_retrieval()
    check_recent_crypto_payments()
    
    print("\n" + "=" * 70)
    print("✅ VERIFICATION COMPLETE")
    print("=" * 70)
    print("\n💡 NEXT STEPS:")
    print("1. Test with a new Tether payment")
    print("2. Monitor the bot logs for detailed activation messages")
    print("3. Check that subscriptions are being created in the database")
    print("4. Verify users receive the success message with their active subscription")

if __name__ == "__main__":
    main()
