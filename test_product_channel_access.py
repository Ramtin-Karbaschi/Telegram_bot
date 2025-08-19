#!/usr/bin/env python3
"""
Test script for product-based channel access control system.
This script verifies that users can only access channels for products they've purchased.
"""

import sqlite3
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from database.queries import DatabaseQueries

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def setup_test_data():
    """Create test data for testing product-channel access."""
    
    conn = sqlite3.connect('database/data/daraei_academy.db')
    cursor = conn.cursor()
    
    try:
        logger.info("Setting up test data...")
        
        # Create test products with channel assignments
        test_products = [
            {
                'id': 9001,
                'name': 'Test Product A',
                'channels': [{'id': -1001234567890, 'name': 'Channel A'}]
            },
            {
                'id': 9002,
                'name': 'Test Product B',
                'channels': [{'id': -1001234567891, 'name': 'Channel B'}]
            },
            {
                'id': 9003,
                'name': 'Test Product C',
                'channels': [
                    {'id': -1001234567892, 'name': 'Channel C1'},
                    {'id': -1001234567893, 'name': 'Channel C2'}
                ]
            }
        ]
        
        # Insert test products
        for product in test_products:
            cursor.execute("""
                INSERT OR REPLACE INTO plans (id, name, price, days, plan_type, channels_json, is_active)
                VALUES (?, ?, 100000, 30, 'subscription', ?, 1)
            """, (
                product['id'],
                product['name'],
                json.dumps(product['channels'])
            ))
            logger.info(f"Created test product: {product['name']}")
        
        # Create test users
        test_users = [
            {'id': 8001, 'name': 'Test User 1'},
            {'id': 8002, 'name': 'Test User 2'},
            {'id': 8003, 'name': 'Test User 3'},
        ]
        
        for user in test_users:
            cursor.execute("""
                INSERT OR REPLACE INTO users (user_id, full_name, status)
                VALUES (?, ?, 'active')
            """, (user['id'], user['name']))
            logger.info(f"Created test user: {user['name']}")
        
        # Create test subscriptions
        test_subscriptions = [
            # User 1 has access to Product A (Channel A)
            {
                'user_id': 8001,
                'plan_id': 9001,
                'status': 'active'
            },
            # User 2 has access to Product B (Channel B) and Product C (Channels C1, C2)
            {
                'user_id': 8002,
                'plan_id': 9002,
                'status': 'active'
            },
            {
                'user_id': 8002,
                'plan_id': 9003,
                'status': 'active'
            },
            # User 3 has an expired subscription to Product A
            {
                'user_id': 8003,
                'plan_id': 9001,
                'status': 'expired'
            },
        ]
        
        for sub in test_subscriptions:
            end_date = datetime.now() + timedelta(days=30) if sub['status'] == 'active' else datetime.now() - timedelta(days=1)
            cursor.execute("""
                INSERT OR REPLACE INTO subscriptions (user_id, plan_id, status, start_date, end_date)
                VALUES (?, ?, ?, ?, ?)
            """, (
                sub['user_id'],
                sub['plan_id'],
                sub['status'],
                datetime.now().isoformat(),
                end_date.isoformat()
            ))
            logger.info(f"Created subscription: User {sub['user_id']} -> Plan {sub['plan_id']} ({sub['status']})")
        
        conn.commit()
        logger.info("✅ Test data setup complete")
        return True
        
    except Exception as e:
        logger.error(f"Failed to setup test data: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def run_access_tests():
    """Run comprehensive tests for product-channel access control."""
    
    logger.info("\n" + "=" * 60)
    logger.info("Running Product-Channel Access Control Tests")
    logger.info("=" * 60)
    
    test_cases = [
        # Test Case 1: User with single product access
        {
            'user_id': 8001,
            'test_channels': [
                (-1001234567890, True, "Channel A - should have access"),
                (-1001234567891, False, "Channel B - should NOT have access"),
                (-1001234567892, False, "Channel C1 - should NOT have access"),
            ]
        },
        # Test Case 2: User with multiple product access
        {
            'user_id': 8002,
            'test_channels': [
                (-1001234567890, False, "Channel A - should NOT have access"),
                (-1001234567891, True, "Channel B - should have access"),
                (-1001234567892, True, "Channel C1 - should have access"),
                (-1001234567893, True, "Channel C2 - should have access"),
            ]
        },
        # Test Case 3: User with expired subscription
        {
            'user_id': 8003,
            'test_channels': [
                (-1001234567890, False, "Channel A - should NOT have access (expired)"),
                (-1001234567891, False, "Channel B - should NOT have access"),
            ]
        },
        # Test Case 4: Non-existent user
        {
            'user_id': 9999,
            'test_channels': [
                (-1001234567890, False, "Channel A - non-existent user should NOT have access"),
            ]
        },
    ]
    
    total_tests = 0
    passed_tests = 0
    
    for test in test_cases:
        user_id = test['user_id']
        logger.info(f"\n📋 Testing User {user_id}:")
        
        # Get user's purchased products
        purchased_products = DatabaseQueries.get_user_purchased_products(user_id)
        logger.info(f"  Purchased products: {purchased_products}")
        
        for channel_id, expected_access, description in test['test_channels']:
            total_tests += 1
            has_access = DatabaseQueries.user_has_access_to_channel(user_id, channel_id)
            
            if has_access == expected_access:
                passed_tests += 1
                logger.info(f"  ✅ PASS: {description}")
            else:
                logger.error(f"  ❌ FAIL: {description}")
                logger.error(f"     Expected: {expected_access}, Got: {has_access}")
    
    # Test channel access list functionality
    logger.info("\n📋 Testing get_users_with_channel_access:")
    
    test_channels_access = [
        (-1001234567890, [8001], "Channel A should have User 1"),
        (-1001234567891, [8002], "Channel B should have User 2"),
        (-1001234567892, [8002], "Channel C1 should have User 2"),
        (-1001234567893, [8002], "Channel C2 should have User 2"),
    ]
    
    for channel_id, expected_users, description in test_channels_access:
        total_tests += 1
        authorized_users = DatabaseQueries.get_users_with_channel_access(channel_id)
        
        if set(authorized_users) == set(expected_users):
            passed_tests += 1
            logger.info(f"  ✅ PASS: {description}")
        else:
            logger.error(f"  ❌ FAIL: {description}")
            logger.error(f"     Expected users: {expected_users}, Got: {authorized_users}")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Results Summary")
    logger.info("=" * 60)
    logger.info(f"Total tests: {total_tests}")
    logger.info(f"Passed: {passed_tests}")
    logger.info(f"Failed: {total_tests - passed_tests}")
    
    if passed_tests == total_tests:
        logger.info("✅ All tests passed! Product-channel access control is working correctly.")
        return True
    else:
        logger.error(f"❌ {total_tests - passed_tests} tests failed. Please review the implementation.")
        return False

def cleanup_test_data():
    """Remove test data from database."""
    
    conn = sqlite3.connect('database/data/daraei_academy.db')
    cursor = conn.cursor()
    
    try:
        logger.info("\nCleaning up test data...")
        
        # Remove test subscriptions
        cursor.execute("DELETE FROM subscriptions WHERE user_id BETWEEN 8001 AND 8003")
        
        # Remove test users
        cursor.execute("DELETE FROM users WHERE user_id BETWEEN 8001 AND 8003")
        
        # Remove test products
        cursor.execute("DELETE FROM plans WHERE id BETWEEN 9001 AND 9003")
        
        conn.commit()
        logger.info("✅ Test data cleaned up")
        
    except Exception as e:
        logger.error(f"Failed to cleanup test data: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test product-channel access control')
    parser.add_argument('--no-cleanup', action='store_true', help='Do not cleanup test data after tests')
    args = parser.parse_args()
    
    # Setup test environment
    if setup_test_data():
        # Run tests
        success = run_access_tests()
        
        # Cleanup unless specified otherwise
        if not args.no_cleanup:
            cleanup_test_data()
        else:
            logger.info("\n⚠️ Test data retained in database (--no-cleanup flag used)")
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
    else:
        logger.error("Failed to setup test environment")
        sys.exit(1)
