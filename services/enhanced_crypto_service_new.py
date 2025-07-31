# services/enhanced_crypto_service.py
"""
🚀 Enhanced Crypto Service - New TronPy Implementation
=====================================================

A complete replacement of the old crypto verification system using tronpy
for direct blockchain interaction and advanced fraud prevention.

This service provides backward compatibility with existing handlers while
delivering superior performance, security, and reliability.

Author: AI Assistant (Cascade)
Date: 2025-01-30
"""

import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict
from decimal import Decimal

# Import our new advanced TRON service
from services.advanced_tron_service import (
    get_tron_service, 
    verify_payment_by_tx_hash,
    search_automatic_payments,
    VerificationStatus
)
from database.models import Database
import config

logger = logging.getLogger(__name__)

# Legacy verification result class for backward compatibility
class VerificationResult:
    """Legacy verification result for backward compatibility"""
    def __init__(self, result: str, tx_hash: str = "", amount: float = 0.0, message: str = ""):
        self.result = result
        self.tx_hash = tx_hash
        self.amount = amount
        self.message = message
    
    # Legacy constants
    SUCCESS = "SUCCESS"
    INSUFFICIENT_AMOUNT = "INSUFFICIENT_AMOUNT"
    WRONG_ADDRESS = "WRONG_ADDRESS"
    FRAUD_DETECTED = "FRAUD_DETECTED"
    NOT_FOUND = "NOT_FOUND"
    PENDING = "PENDING"
    FAILED = "FAILED"

class EnhancedCryptoService:
    """
    🚀 Enhanced Crypto Service - Powered by TronPy
    =============================================
    
    New features with tronpy integration:
    - Direct blockchain verification via tronpy
    - Advanced fraud detection algorithms
    - Multi-layer security validation
    - Real-time transaction confirmations
    - Comprehensive audit trails
    - Zero third-party API dependencies
    - Professional-grade security measures
    """
    
    @staticmethod
    async def smart_payment_verification(payment_id: str, user_provided_tx: str = None) -> Tuple[bool, str, float]:
        """
        🎯 Advanced payment verification using tronpy blockchain integration
        
        This method provides backward compatibility while using the new
        tronpy-based verification system for superior performance and security.
        
        Args:
            payment_id: Payment ID in database
            user_provided_tx: TX hash provided by user (optional)
            
        Returns:
            (success: bool, tx_hash: str, amount: float)
        """
        try:
            logger.info(f"🚀 Starting tronpy-based verification for payment {payment_id}")
            
            # Get payment details from database
            db = Database.get_instance()
            payment = db.get_crypto_payment_by_payment_id(payment_id)

            # Fallback: some legacy flows still store crypto payments in the generic `payments` table
            if not payment:
                try:
                    from database.queries import DatabaseQueries as DBQ
                    legacy_payment_row = DBQ.get_payment(payment_id)
                    payment = dict(legacy_payment_row) if legacy_payment_row else None
                    if payment:
                        logger.warning(
                            "📜 Fallback engaged – located payment %s in legacy payments table",
                            payment_id
                        )
                except Exception as fallback_exc:
                    logger.error("Error during legacy payment lookup for %s: %s", payment_id, fallback_exc)

            if not payment:
                logger.error(f"❌ Payment {payment_id} not found in database")
                return False, "", 0.0

            logger.info(f"✅ Payment found: {payment_id}, expected amount: {payment.get('usdt_amount_requested', 0)} USDT")

            # If user provided TX hash, verify it directly
            if user_provided_tx:
                logger.info(f"🔍 Verifying user-provided TX hash: {user_provided_tx}")
                
                success, tx_hash, amount, metadata = await verify_payment_by_tx_hash(
                    user_provided_tx, payment
                )
                
                if success:
                    logger.info(f"✅ Payment verified successfully via TX hash: {tx_hash}")
                    return True, tx_hash, amount
                else:
                    logger.warning(f"❌ TX hash verification failed: {metadata.get('message', 'Unknown error')}")
                    return False, user_provided_tx, 0.0
            
            # If no TX hash provided, search for automatic payments
            logger.info(f"🔍 Searching for automatic payments for payment {payment_id}")
            
            search_results = await search_automatic_payments(payment)
            
            if search_results:
                # Return the first successful match
                for result in search_results:
                    if result['status'] == 'success':
                        logger.info(f"✅ Automatic payment found: {result['tx_hash']}")
                        return True, result['tx_hash'], result['amount']
                
                # If no successful matches, return the first result for feedback
                first_result = search_results[0]
                logger.warning(f"❌ No successful automatic payments found. First result: {first_result['message']}")
                return False, first_result.get('tx_hash', ''), 0.0
            
            logger.warning(f"❌ No payments found for payment {payment_id}")
            return False, "", 0.0
            
        except Exception as e:
            logger.error(f"💥 Critical error in smart_payment_verification for {payment_id}: {e}", exc_info=True)
            return False, "", 0.0

    @staticmethod 
    async def verify_specific_transaction(payment_id: str, tx_hash: str) -> VerificationResult:
        """
        🔍 Verify a specific transaction hash (legacy method for backward compatibility)
        
        Args:
            payment_id: Payment ID in database
            tx_hash: Transaction hash to verify
            
        Returns:
            VerificationResult object with legacy format
        """
        try:
            logger.info(f"🔍 Legacy verification method called for {payment_id}, TX: {tx_hash}")
            
            # Get payment details
            db = Database.get_instance()
            payment = db.get_crypto_payment_by_payment_id(payment_id)
            
            if not payment:
                # Try legacy table
                from database.queries import DatabaseQueries as DBQ
                legacy_payment_row = DBQ.get_payment(payment_id)
                payment = dict(legacy_payment_row) if legacy_payment_row else None
            
            if not payment:
                return VerificationResult(
                    result=VerificationResult.NOT_FOUND,
                    message="Payment not found in database"
                )
            
            # Use new verification system
            success, verified_tx, amount, metadata = await verify_payment_by_tx_hash(tx_hash, payment)
            
            if success:
                return VerificationResult(
                    result=VerificationResult.SUCCESS,
                    tx_hash=verified_tx,
                    amount=amount,
                    message="Transaction verified successfully via tronpy"
                )
            else:
                # Map new status to legacy format
                status = metadata.get('status', 'failed')
                
                if status == 'fraud_detected':
                    result_code = VerificationResult.FRAUD_DETECTED
                elif status == 'insufficient_amount':
                    result_code = VerificationResult.INSUFFICIENT_AMOUNT
                elif status == 'wrong_address':
                    result_code = VerificationResult.WRONG_ADDRESS
                elif status == 'pending':
                    result_code = VerificationResult.PENDING
                else:
                    result_code = VerificationResult.FAILED
                
                return VerificationResult(
                    result=result_code,
                    tx_hash=tx_hash,
                    amount=0.0,
                    message=metadata.get('message', 'Verification failed')
                )
                
        except Exception as e:
            logger.error(f"💥 Error in verify_specific_transaction: {e}", exc_info=True)
            return VerificationResult(
                result=VerificationResult.FAILED,
                message=f"Verification error: {str(e)}"
            )

    @staticmethod
    async def search_user_payments(payment_id: str, time_window_hours: int = 2) -> Dict:
        """
        🔍 Search for user payments automatically (legacy method)
        
        Args:
            payment_id: Payment ID to search for
            time_window_hours: Time window to search in hours
            
        Returns:
            Dictionary with search results
        """
        try:
            logger.info(f"🔍 Legacy search method called for payment {payment_id}")
            
            # Get payment details
            db = Database.get_instance()
            payment = db.get_crypto_payment_by_payment_id(payment_id)
            
            if not payment:
                # Try legacy table
                from database.queries import DatabaseQueries as DBQ
                legacy_payment_row = DBQ.get_payment(payment_id)
                payment = dict(legacy_payment_row) if legacy_payment_row else None
            
            if not payment:
                return {
                    'success': False,
                    'message': 'Payment not found in database',
                    'results': []
                }
            
            # Use new search system
            search_results = await search_automatic_payments(payment)
            
            return {
                'success': len(search_results) > 0,
                'message': f'Found {len(search_results)} potential matches',
                'results': search_results
            }
            
        except Exception as e:
            logger.error(f"💥 Error in search_user_payments: {e}", exc_info=True)
            return {
                'success': False,
                'message': f'Search error: {str(e)}',
                'results': []
            }

    @staticmethod
    def get_payment_statistics(days: int = 30) -> Dict:
        """
        📊 Get payment statistics for the last N days (enhanced with tronpy data)
        """
        try:
            logger.info(f"📊 Generating payment statistics for last {days} days")
            
            db = Database.get_instance()
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            # Get tronpy service stats
            tron_service = get_tron_service()
            tron_stats = tron_service.get_verification_stats()
            
            # Base statistics structure
            stats = {
                "total_payments": 0,
                "successful_payments": 0,
                "pending_payments": 0,
                "failed_payments": 0,
                "total_volume_usdt": 0.0,
                "success_rate": 0.0,
                "tronpy_stats": tron_stats,
                "by_status": {}
            }
            
            # Query crypto payments
            query = """
                SELECT status, COUNT(*) as count, 
                       COALESCE(SUM(usdt_amount_received), 0) as total_usdt,
                       COALESCE(AVG(usdt_amount_received), 0) as avg_usdt
                FROM crypto_payments 
                WHERE created_at >= ? 
                GROUP BY status
            """
            
            if db.execute(query, (cutoff_date,)):
                results = db.fetchall()
                
                for row in results:
                    status = row['status'] if hasattr(row, 'status') else row[0]
                    count = row['count'] if hasattr(row, 'count') else row[1]
                    total_usdt = row['total_usdt'] if hasattr(row, 'total_usdt') else row[2]
                    avg_usdt = row['avg_usdt'] if hasattr(row, 'avg_usdt') else row[3]
                    
                    stats["by_status"][status] = {
                        "count": count,
                        "total_usdt": float(total_usdt),
                        "avg_usdt": float(avg_usdt)
                    }
                    
                    stats["total_payments"] += count
                    
                    if status == "paid":  # crypto_payments uses "paid" instead of "success"
                        stats["successful_payments"] = count
                        stats["total_volume_usdt"] = float(total_usdt)
                    elif status == "pending":
                        stats["pending_payments"] = count
                    elif status in ["failed", "expired"]:
                        stats["failed_payments"] += count
            
            # Calculate success rate
            if stats["total_payments"] > 0:
                stats["success_rate"] = (stats["successful_payments"] / stats["total_payments"]) * 100
            
            logger.info(f"📊 Statistics generated: {stats['total_payments']} total payments, {stats['success_rate']:.1f}% success rate")
            
            return stats
        
        except Exception as e:
            logger.error(f"💥 Error getting payment statistics: {e}", exc_info=True)
            return {"error": str(e)}

    @staticmethod
    def create_payment_report(days: int = 30) -> str:
        """📋 Create comprehensive payment report for admins"""
        stats = EnhancedCryptoService.get_payment_statistics(days)
        
        if "error" in stats:
            return f"❌ Error generating report: {stats['error']}"
        
        # Get tronpy service stats
        tron_stats = stats.get('tronpy_stats', {})
        
        report = f"""
📊 **USDT Payment Report - Last {days} Days**

🚀 **TronPy Service Status:**
• Verified Transactions: {tron_stats.get('verified_transactions_count', 'N/A')}
• Fraud Detection: {'✅ Active' if tron_stats.get('fraud_detection_enabled') else '❌ Inactive'}
• Min Confirmations: {tron_stats.get('minimum_confirmations', 'N/A')}
• Wallet Address: `{tron_stats.get('wallet_address', 'N/A')}`

📈 **Summary Statistics:**
• Total Payments: {stats['total_payments']}
• Successful: {stats['successful_payments']} ({stats['success_rate']:.1f}%)
• Pending: {stats['pending_payments']}
• Failed: {stats['failed_payments']}
• Total Volume: {stats['total_volume_usdt']:.2f} USDT

📋 **Status Breakdown:**
"""
        
        for status, data in stats["by_status"].items():
            status_emoji = {
                "paid": "✅",
                "pending": "🔄", 
                "failed": "❌",
                "expired": "⏰"
            }.get(status, "📊")
            
            report += f"{status_emoji} **{status.title()}:** {data['count']} payments, Total: {data['total_usdt']:.2f} USDT, Avg: {data['avg_usdt']:.2f} USDT\n"
        
        report += f"\n🔒 **Security Features:**\n"
        report += f"• Direct blockchain verification via TronPy\n"
        report += f"• Advanced fraud detection algorithms\n"
        report += f"• Multi-layer transaction validation\n"
        report += f"• Real-time confirmation monitoring\n"
        
        return report

    @staticmethod
    async def health_check() -> Dict:
        """🏥 System health check for tronpy service"""
        try:
            tron_service = get_tron_service()
            
            # Test basic connectivity
            wallet_balance = await tron_service.get_wallet_balance()
            service_stats = tron_service.get_verification_stats()
            
            return {
                'status': 'healthy',
                'tronpy_connected': True,
                'wallet_balance': float(wallet_balance),
                'service_stats': service_stats,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"💥 Health check failed: {e}", exc_info=True)
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
