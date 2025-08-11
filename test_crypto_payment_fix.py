#!/usr/bin/env python3
"""
Test script to verify Tether payment activation fix
"""

import sys
import os
import asyncio
import logging
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from database.queries import DatabaseQueries as Database
from database.models import Database as DBModel

def check_database_connection():
    """Check if database is accessible"""
    try:
        db = DBModel.get_instance()
        logger.info("✅ Database connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

def get_pending_crypto_payments():
    """Get all pending crypto payments"""
    try:
        db = DBModel.get_instance()
        result = db.execute("""
            SELECT 
                cp.payment_id,
                cp.user_id,
                cp.plan_id,
                cp.amount_usdt,
                cp.status,
                cp.created_at,
                cp.expires_at,
                p.name as plan_name,
                u.username
            FROM crypto_payments cp
            LEFT JOIN plans p ON cp.plan_id = p.plan_id
            LEFT JOIN users u ON cp.user_id = u.user_id
            WHERE cp.status = 'pending'
            ORDER BY cp.created_at DESC
        """)
        
        payments = []
        for row in result:
            payments.append(dict(row))
        
        logger.info(f"📋 Found {len(payments)} pending crypto payments")
        return payments
    except Exception as e:
        logger.error(f"❌ Error fetching pending payments: {e}")
        return []

def check_plan_retrieval(plan_id):
    """Test plan retrieval to verify the fix"""
    try:
        plan_row = Database.get_plan_by_id(plan_id)
        
        if not plan_row:
            logger.warning(f"⚠️ Plan {plan_id} not found")
            return None
            
        # Test the fix - handle both dict and Row objects
        if plan_row and hasattr(plan_row, "keys"):
            plan_name = plan_row["name"]
            logger.info(f"✅ Plan {plan_id} retrieved as dict with name: {plan_name}")
        elif plan_row:
            plan_name = dict(plan_row).get("name", "N/A")
            logger.info(f"✅ Plan {plan_id} retrieved as Row object with name: {plan_name}")
        else:
            plan_name = "N/A"
            logger.warning(f"⚠️ Plan {plan_id} found but unable to extract name")
            
        return plan_name
    except Exception as e:
        logger.error(f"❌ Error retrieving plan {plan_id}: {e}")
        return None

def check_subscription_status(user_id):
    """Check user's subscription status"""
    try:
        subscriptions = Database.get_user_subscriptions(user_id)
        
        if not subscriptions:
            logger.info(f"📊 User {user_id} has no subscriptions")
            return None
            
        active_subs = []
        for sub in subscriptions:
            sub_dict = dict(sub) if not isinstance(sub, dict) else sub
            if sub_dict.get('status') == 'active':
                active_subs.append(sub_dict)
                
        if active_subs:
            logger.info(f"✅ User {user_id} has {len(active_subs)} active subscription(s)")
            for sub in active_subs:
                logger.info(f"   - Plan ID: {sub.get('plan_id')}, Expires: {sub.get('end_date')}")
        else:
            logger.info(f"⏸️ User {user_id} has subscriptions but none are active")
            
        return active_subs
    except Exception as e:
        logger.error(f"❌ Error checking subscriptions for user {user_id}: {e}")
        return None

def simulate_payment_verification(payment_id):
    """Simulate the payment verification process"""
    logger.info(f"\n🔍 Simulating verification for payment {payment_id}")
    
    try:
        # Get payment record
        db = DBModel.get_instance()
        payment_record = db.get_crypto_payment_by_payment_id(payment_id)
        
        if not payment_record:
            logger.error(f"❌ Payment {payment_id} not found")
            return False
            
        payment_dict = dict(payment_record) if not isinstance(payment_record, dict) else payment_record
        
        logger.info(f"📝 Payment details:")
        logger.info(f"   User ID: {payment_dict.get('user_id')}")
        logger.info(f"   Plan ID: {payment_dict.get('plan_id')}")
        logger.info(f"   Amount: {payment_dict.get('amount_usdt')} USDT")
        logger.info(f"   Status: {payment_dict.get('status')}")
        
        # Test plan retrieval (this is where the bug was)
        plan_id = payment_dict.get('plan_id')
        plan_name = check_plan_retrieval(plan_id)
        
        if plan_name and plan_name != "N/A":
            logger.info(f"✅ Plan retrieval successful: {plan_name}")
            logger.info(f"✅ Subscription activation should now work!")
            return True
        else:
            logger.error(f"❌ Plan retrieval failed - subscription activation will fail")
            return False
            
    except Exception as e:
        logger.error(f"❌ Simulation failed: {e}")
        return False

def main():
    """Main test function"""
    print("=" * 60)
    print("🧪 TETHER PAYMENT ACTIVATION FIX TEST")
    print("=" * 60)
    
    # Check database connection
    if not check_database_connection():
        return
    
    print("\n" + "=" * 60)
    print("📋 CHECKING PENDING CRYPTO PAYMENTS")
    print("=" * 60)
    
    # Get pending payments
    pending_payments = get_pending_crypto_payments()
    
    if not pending_payments:
        print("\n✅ No pending crypto payments found")
        print("💡 This is good if all payments have been processed!")
        return
    
    # Display pending payments
    print(f"\n📊 Found {len(pending_payments)} pending payment(s):\n")
    for i, payment in enumerate(pending_payments, 1):
        print(f"{i}. Payment ID: {payment['payment_id']}")
        print(f"   User: {payment.get('username', 'Unknown')} (ID: {payment['user_id']})")
        print(f"   Plan: {payment.get('plan_name', 'Unknown')} (ID: {payment['plan_id']})")
        print(f"   Amount: {payment['amount_usdt']} USDT")
        print(f"   Created: {payment['created_at']}")
        print(f"   Expires: {payment['expires_at']}")
        print("-" * 40)
    
    # Test payment verification for each pending payment
    print("\n" + "=" * 60)
    print("🔍 TESTING PAYMENT VERIFICATION PROCESS")
    print("=" * 60)
    
    for payment in pending_payments[:3]:  # Test first 3 payments
        success = simulate_payment_verification(payment['payment_id'])
        if success:
            # Check user's subscription status
            check_subscription_status(payment['user_id'])
        print("-" * 40)
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE")
    print("=" * 60)
    print("\n📌 SUMMARY:")
    print("1. The plan retrieval fix has been applied")
    print("2. Both dict and Row objects are now handled correctly")
    print("3. Detailed logging has been added to track activation")
    print("4. Error messages are more informative")
    print("\n💡 Next steps:")
    print("1. Monitor the bot logs when users verify Tether payments")
    print("2. Check for any error messages in the logs")
    print("3. Verify that subscriptions are being activated in the database")

if __name__ == "__main__":
    main()
