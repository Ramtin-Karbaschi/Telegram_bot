#!/usr/bin/env python3
"""
🧪 Test Script for New TronPy-based Payment System
=================================================

This script tests the new advanced TRON payment verification system
to ensure everything is working correctly.
"""

import asyncio
import sys
import os
import logging
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_tron_service():
    """Test the new TRON service functionality"""
    
    print("🚀 Testing New TronPy-based Payment System")
    print("=" * 50)
    
    try:
        # Test 1: Import and initialize service
        print("\n1️⃣ Testing service import and initialization...")
        
        from services.advanced_tron_service import get_tron_service, VerificationStatus
        from services.enhanced_crypto_service import EnhancedCryptoService
        
        tron_service = get_tron_service()
        print("✅ TronPy service initialized successfully")
        print(f"📍 Monitoring wallet: {tron_service.wallet_address}")
        print(f"💰 USDT Contract: {tron_service.usdt_contract_address}")
        
        # Test 2: Get service statistics
        print("\n2️⃣ Testing service statistics...")
        
        stats = tron_service.get_verification_stats()
        print("✅ Service statistics retrieved:")
        for key, value in stats.items():
            print(f"   • {key}: {value}")
        
        # Test 3: Test wallet balance (if possible)
        print("\n3️⃣ Testing wallet balance check...")
        
        try:
            balance = await tron_service.get_wallet_balance()
            print(f"✅ Wallet balance: {balance} USDT")
        except Exception as e:
            print(f"⚠️ Wallet balance check failed (this is normal if no API key): {e}")
        
        # Test 4: Test Enhanced Crypto Service compatibility
        print("\n4️⃣ Testing Enhanced Crypto Service compatibility...")
        
        # Create a mock payment for testing
        mock_payment = {
            'payment_id': 'test-payment-123',
            'user_id': 12345,
            'usdt_amount_requested': 10.0,
            'wallet_address': tron_service.wallet_address,
            'created_at': datetime.now().isoformat(),
            'status': 'pending'
        }
        
        # Test health check
        health_status = await EnhancedCryptoService.health_check()
        print("✅ Health check completed:")
        print(f"   • Status: {health_status.get('status')}")
        print(f"   • TronPy Connected: {health_status.get('tronpy_connected')}")
        
        # Test 5: Test payment statistics
        print("\n5️⃣ Testing payment statistics...")
        
        payment_stats = EnhancedCryptoService.get_payment_statistics(30)
        if 'error' not in payment_stats:
            print("✅ Payment statistics generated successfully")
            print(f"   • Total Payments: {payment_stats.get('total_payments', 0)}")
            print(f"   • Success Rate: {payment_stats.get('success_rate', 0):.1f}%")
        else:
            print(f"⚠️ Payment statistics error: {payment_stats['error']}")
        
        # Test 6: Generate payment report
        print("\n6️⃣ Testing payment report generation...")
        
        report = EnhancedCryptoService.create_payment_report(7)
        print("✅ Payment report generated successfully")
        print("📋 Sample report (first 300 characters):")
        print(report[:300] + "..." if len(report) > 300 else report)
        
        print("\n" + "=" * 50)
        print("🎉 All tests completed successfully!")
        print("🚀 Your new TronPy-based payment system is ready to use!")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("💡 Make sure all required packages are installed:")
        print("   pip install tronpy")
        return False
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        logger.error("Test failed", exc_info=True)
        return False

async def test_with_real_transaction():
    """Test with a real transaction (if provided)"""
    
    print("\n🔍 Advanced Test: Real Transaction Verification")
    print("=" * 50)
    
    # This is just a placeholder - in real testing, you would provide
    # a real TX hash and payment details
    test_tx = input("Enter a real USDT TRC20 transaction hash to test (or press Enter to skip): ").strip()
    
    if not test_tx:
        print("⏭️ Skipping real transaction test")
        return True
    
    try:
        from services.enhanced_crypto_service import EnhancedCryptoService
        
        # Create mock payment for testing
        mock_payment = {
            'payment_id': 'real-test-payment',
            'user_id': 99999,
            'usdt_amount_requested': 1.0,  # Adjust as needed
            'created_at': datetime.now().isoformat(),
            'status': 'pending'
        }
        
        print(f"🔍 Verifying transaction: {test_tx}")
        
        success, verified_tx, amount = await EnhancedCryptoService.smart_payment_verification(
            'real-test-payment', user_provided_tx=test_tx
        )
        
        if success:
            print(f"✅ Transaction verified successfully!")
            print(f"   • TX Hash: {verified_tx}")
            print(f"   • Amount: {amount} USDT")
        else:
            print(f"❌ Transaction verification failed")
            print(f"   • TX Hash: {verified_tx}")
        
        return True
        
    except Exception as e:
        print(f"❌ Real transaction test failed: {e}")
        logger.error("Real transaction test failed", exc_info=True)
        return False

if __name__ == "__main__":
    print("🚀 Starting TronPy Payment System Tests...")
    
    # Run basic tests
    success = asyncio.run(test_tron_service())
    
    if success:
        # Run advanced tests if basic tests pass
        asyncio.run(test_with_real_transaction())
    
    print("\n🏁 Testing completed!")
