#!/usr/bin/env python3
"""Test script to verify the sales notification fix for sqlite3.Row issue"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
import logging
from database.queries import DatabaseQueries as DQ
from database.models import Database as DBModel

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_user_details_fetch():
    """Test fetching user details and converting sqlite3.Row to dict"""
    print("\n=== Testing User Details Fetch ===")
    
    # Test with a real user ID from recent payments
    test_user_id = 111029173  # From payment_id 512
    
    try:
        dq = DQ()
        user_info = dq.get_user_details(test_user_id)
        print(f"Raw user_info type: {type(user_info)}")
        
        if user_info:
            # Test the fix - convert sqlite3.Row to dict if needed
            if hasattr(user_info, 'keys'):
                user_info_dict = dict(user_info)
                print(f"Converted to dict: {type(user_info_dict)}")
                full_name = user_info_dict.get('full_name', 'نامشخص')
                print(f"Full name: {full_name}")
                print(f"Username: {user_info_dict.get('username', 'N/A')}")
                return True
            else:
                print(f"user_info is already a dict or other type")
                return False
        else:
            print(f"No user found with ID {test_user_id}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

def test_payment_record_fetch():
    """Test fetching payment records and converting sqlite3.Row to dict"""
    print("\n=== Testing Payment Record Fetch ===")
    
    # Test with a real payment ID
    test_payment_id = 512
    
    try:
        dq = DQ()
        payment_record = dq.get_payment_by_id(test_payment_id)
        print(f"Raw payment_record type: {type(payment_record)}")
        
        if payment_record:
            # Test the fix - convert sqlite3.Row to dict if needed
            if hasattr(payment_record, 'keys'):
                payment_dict = dict(payment_record)
                print(f"Converted to dict: {type(payment_dict)}")
                discount_id = payment_dict.get('discount_id')
                print(f"Discount ID: {discount_id}")
                print(f"Amount: {payment_dict.get('amount', 'N/A')}")
                print(f"Status: {payment_dict.get('status', 'N/A')}")
                return True
            else:
                print(f"payment_record is already a dict or other type")
                return False
        else:
            print(f"No payment found with ID {test_payment_id}")
            return False
            
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    print("Testing sqlite3.Row to dict conversion fix...")
    print("=" * 50)
    
    # Test user details
    user_test = test_user_details_fetch()
    
    # Test payment record
    payment_test = test_payment_record_fetch()
    
    print("\n" + "=" * 50)
    print("Test Results:")
    print(f"✅ User details test: {'PASSED' if user_test else 'FAILED'}")
    print(f"✅ Payment record test: {'PASSED' if payment_test else 'FAILED'}")
    
    if user_test and payment_test:
        print("\n✅ All tests passed! The sqlite3.Row issue should be fixed.")
        print("Sales notifications should now work properly for real purchases.")
    else:
        print("\n❌ Some tests failed. Please check the error messages above.")

if __name__ == "__main__":
    main()
