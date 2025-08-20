#!/usr/bin/env python
"""Test script to verify the ban enforcement system."""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from database.queries import DatabaseQueries


def test_ban_system():
    """Test the ban system functionality."""
    print("=" * 60)
    print("BAN ENFORCEMENT SYSTEM TEST")
    print("=" * 60)
    
    # Test user ID (you can change this to test with different users)
    test_user_id = 166444605  # The user from the logs
    
    print(f"\n1. Checking current status for user {test_user_id}...")
    current_status = DatabaseQueries.get_user_status(test_user_id)
    print(f"   Current status: {current_status}")
    
    if current_status != 'banned':
        print(f"\n2. Setting user {test_user_id} as BANNED...")
        success = DatabaseQueries.set_user_status(test_user_id, 'banned')
        print(f"   Ban operation: {'SUCCESS' if success else 'FAILED'}")
        
        # Verify the ban
        new_status = DatabaseQueries.get_user_status(test_user_id)
        print(f"   Verified status after ban: {new_status}")
    else:
        print(f"\n2. User {test_user_id} is already BANNED")
    
    print("\n3. Testing with non-existent user...")
    non_existent_user = 999999999
    status = DatabaseQueries.get_user_status(non_existent_user)
    print(f"   Status for non-existent user {non_existent_user}: {status}")
    print(f"   (Should be None - users not in DB are allowed)")
    
    print("\n" + "=" * 60)
    print("BAN SYSTEM TEST COMPLETE")
    print("=" * 60)
    print("\nExpected behavior after ban:")
    print("✓ Banned user receives NO responses from either bot")
    print("✓ All interactions are silently blocked")
    print("✓ First attempt and every 100th attempt are logged")
    print("✓ Rate limiting prevents log spam from DDOS attempts")
    print("\nTo unban a user, use the admin panel or run:")
    print(f"  DatabaseQueries.set_user_status({test_user_id}, 'active')")


if __name__ == "__main__":
    test_ban_system()
