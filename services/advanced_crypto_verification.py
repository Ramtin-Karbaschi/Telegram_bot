"""
🔒 Advanced USDT Payment Verification System
نظام پیشرفته تایید پرداخت USDT با قابلیت‌های ضد تقلب

Features:
- Multi-layer security verification
- Smart fraud detection
- TX hash validation & blockchain confirmation
- Time-window restrictions
- Amount tolerance with precision control
- Trust Wallet optimized verification
- Anti-duplicate payment protection
"""

import re
import hashlib
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

from services.tronscan_service import TronScanService
from database.models import Database
import config

logger = logging.getLogger(__name__)

class VerificationResult(Enum):
    """نتایج تایید پرداخت"""
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    FRAUD_DETECTED = "fraud_detected"
    AMOUNT_MISMATCH = "amount_mismatch"
    TIME_EXPIRED = "time_expired"
    DUPLICATE_TX = "duplicate_tx"
    INVALID_TX_FORMAT = "invalid_tx_format"
    BLOCKCHAIN_ERROR = "blockchain_error"

@dataclass
class PaymentVerificationResult:
    """نتیجه کامل تایید پرداخت"""
    result: VerificationResult
    tx_hash: Optional[str] = None
    amount: Optional[float] = None
    confidence_score: float = 0.0
    fraud_flags: List[str] = None
    error_message: Optional[str] = None
    blockchain_confirmations: int = 0
    processing_time_ms: int = 0
    
    def __post_init__(self):
        if self.fraud_flags is None:
            self.fraud_flags = []

class AdvancedCryptoVerification:
    """سیستم پیشرفته تایید پرداخت کریپتو"""
    
    def __init__(self):
        self.db = Database.get_instance()
        self.tronscan = TronScanService()
        
        # تنظیمات امنیتی
        self.MAX_TX_AGE_HOURS = 1  # حداکثر سن تراکنش قابل قبول
        self.MIN_CONFIRMATIONS = 1  # حداقل تایید شبکه
        self.AMOUNT_TOLERANCE_PERCENT = 0.5  # تلرانس مبلغ (0.5%)
        self.MAX_VERIFICATION_TIME_SEC = 30  # حداکثر زمان تایید
        
        # الگوهای تشخیص تقلب
        self.FRAUD_PATTERNS = {
            'suspicious_amounts': [0.001, 0.01, 0.1],  # مبالغ مشکوک
            'blacklisted_hashes': set(),  # TX های در لیست سیاه
            'rate_limit_per_user': 5,  # حداکثر تلاش در روز
        }
    
    async def verify_payment_comprehensive(
        self, 
        payment_id: str,
        user_provided_tx: Optional[str] = None,
        expected_amount: float = 0.0,
        wallet_address: Optional[str] = None,
        user_id: int = 0
    ) -> PaymentVerificationResult:
        """
        تایید جامع پرداخت با تمام لایه‌های امنیتی
        
        Args:
            payment_id: شناسه پرداخت در دیتابیس
            user_provided_tx: TX hash ارائه شده توسط کاربر
            expected_amount: مبلغ مورد انتظار
            wallet_address: آدرس کیف پول مقصد
            user_id: شناسه کاربر
            
        Returns:
            PaymentVerificationResult: نتیجه کامل تایید
        """
        start_time = datetime.now()
        
        try:
            # مرحله 1: بررسی اولیه و دریافت اطلاعات پرداخت
            logger.info(f"🔍 Starting comprehensive verification for payment {payment_id}")
            
            payment_data = await self._get_payment_data(payment_id)
            if not payment_data:
                return PaymentVerificationResult(
                    result=VerificationResult.FAILED,
                    error_message="Payment record not found",
                    processing_time_ms=self._get_processing_time(start_time)
                )
            
            # استخراج اطلاعات پرداخت
            expected_amount = expected_amount or payment_data.get('usdt_amount_requested', 0)
            wallet_address = wallet_address or payment_data.get('wallet_address') or config.CRYPTO_WALLET_ADDRESS
            user_id = user_id or payment_data.get('user_id', 0)
            
            # مرحله 2: بررسی محدودیت‌های کاربر
            user_check = await self._check_user_limits(user_id)
            if not user_check['allowed']:
                return PaymentVerificationResult(
                    result=VerificationResult.FRAUD_DETECTED,
                    fraud_flags=['rate_limit_exceeded'],
                    error_message=user_check['reason'],
                    processing_time_ms=self._get_processing_time(start_time)
                )
            
            # مرحله 3: تایید TX hash ارائه شده توسط کاربر
            if user_provided_tx and user_provided_tx.strip():
                logger.info(f"🔗 User provided TX hash: {user_provided_tx[:20]}...")
                tx_result = await self._verify_user_provided_tx(
                    user_provided_tx.strip(), 
                    expected_amount, 
                    wallet_address,
                    payment_id
                )
                if tx_result.result == VerificationResult.SUCCESS:
                    tx_result.processing_time_ms = self._get_processing_time(start_time)
                    return tx_result
            else:
                logger.info("🔍 No TX hash provided, will use automatic search")
            
            # مرحله 4: جستجوی خودکار در بلاک‌چین
            auto_search_result = await self._automatic_blockchain_search(
                expected_amount,
                wallet_address,
                payment_data.get('created_at'),
                payment_id
            )
            
            auto_search_result.processing_time_ms = self._get_processing_time(start_time)
            return auto_search_result
            
        except Exception as e:
            logger.error(f"❌ Comprehensive verification failed for payment {payment_id}: {e}")
            return PaymentVerificationResult(
                result=VerificationResult.BLOCKCHAIN_ERROR,
                error_message=f"Verification system error: {str(e)}",
                processing_time_ms=self._get_processing_time(start_time)
            )
    
    async def _verify_user_provided_tx(
        self, 
        tx_hash: str, 
        expected_amount: float, 
        wallet_address: str,
        payment_id: str
    ) -> PaymentVerificationResult:
        """تایید TX hash ارائه شده توسط کاربر"""
        
        # بررسی فرمت TX hash
        if not self._is_valid_tx_hash_format(tx_hash):
            return PaymentVerificationResult(
                result=VerificationResult.INVALID_TX_FORMAT,
                error_message="TX hash format is invalid",
                fraud_flags=['invalid_format']
            )
        
        # بررسی تکراری نبودن
        duplicate_check = await self._check_duplicate_tx(tx_hash, payment_id)
        if duplicate_check['is_duplicate']:
            return PaymentVerificationResult(
                result=VerificationResult.DUPLICATE_TX,
                error_message="This TX hash has been used before",
                fraud_flags=['duplicate_tx'],
                tx_hash=tx_hash
            )
        
        # تایید از بلاک‌چین
        blockchain_result = await self._verify_on_blockchain(
            tx_hash, expected_amount, wallet_address
        )
        
        return blockchain_result
    
    async def _automatic_blockchain_search(
        self,
        expected_amount: float,
        wallet_address: str,
        payment_created_at: str,
        payment_id: str
    ) -> PaymentVerificationResult:
        """جستجوی خودکار در بلاک‌چین"""
        
        try:
            # محاسبه بازه زمانی جستجو
            if payment_created_at:
                created_time = datetime.fromisoformat(payment_created_at.replace('Z', '+00:00'))
                search_start = created_time - timedelta(minutes=10)
                search_end = created_time + timedelta(hours=self.MAX_TX_AGE_HOURS)
            else:
                search_end = datetime.now()
                search_start = search_end - timedelta(hours=self.MAX_TX_AGE_HOURS)
            
            logger.info(f"🔍 Auto-searching blockchain from {search_start} to {search_end}")
            
            # جستجو در تراکنش‌های واردات کیف پول
            transactions = await self.tronscan.get_wallet_transactions(
                wallet_address, 
                limit=50,
                start_timestamp=int(search_start.timestamp() * 1000),
                end_timestamp=int(search_end.timestamp() * 1000)
            )
            
            if not transactions:
                return PaymentVerificationResult(
                    result=VerificationResult.FAILED,
                    error_message="No transactions found in time window"
                )
            
            # تحلیل تراکنش‌ها
            best_match = await self._find_best_matching_transaction(
                transactions, expected_amount, wallet_address, payment_id
            )
            
            if best_match:
                return PaymentVerificationResult(
                    result=VerificationResult.SUCCESS,
                    tx_hash=best_match['tx_hash'],
                    amount=best_match['amount'],
                    confidence_score=best_match['confidence'],
                    blockchain_confirmations=best_match.get('confirmations', 0)
                )
            
            return PaymentVerificationResult(
                result=VerificationResult.FAILED,
                error_message="No matching transaction found"
            )
            
        except Exception as e:
            logger.error(f"❌ Auto blockchain search failed: {e}")
            return PaymentVerificationResult(
                result=VerificationResult.BLOCKCHAIN_ERROR,
                error_message=f"Blockchain search error: {str(e)}"
            )
    
    async def _verify_on_blockchain(
        self, 
        tx_hash: str, 
        expected_amount: float, 
        wallet_address: str
    ) -> PaymentVerificationResult:
        """تایید تراکنش در بلاک‌چین"""
        
        try:
            # دریافت اطلاعات تراکنش
            tx_info = await self.tronscan.get_transaction_info(tx_hash)
            if not tx_info:
                return PaymentVerificationResult(
                    result=VerificationResult.FAILED,
                    error_message="Transaction not found on blockchain",
                    tx_hash=tx_hash
                )
            
            # تحلیل امنیتی تراکنش
            security_analysis = await self._analyze_transaction_security(tx_info, expected_amount, wallet_address)
            
            if security_analysis['fraud_detected']:
                return PaymentVerificationResult(
                    result=VerificationResult.FRAUD_DETECTED,
                    fraud_flags=security_analysis['fraud_flags'],
                    error_message=security_analysis['reason'],
                    tx_hash=tx_hash
                )
            
            # بررسی مبلغ با تلرانس
            amount_check = self._check_amount_match(
                security_analysis['actual_amount'], 
                expected_amount
            )
            
            if not amount_check['matches']:
                return PaymentVerificationResult(
                    result=VerificationResult.AMOUNT_MISMATCH,
                    error_message=f"Amount mismatch: expected {expected_amount}, got {security_analysis['actual_amount']}",
                    amount=security_analysis['actual_amount'],
                    tx_hash=tx_hash
                )
            
            # تایید موفق
            return PaymentVerificationResult(
                result=VerificationResult.SUCCESS,
                tx_hash=tx_hash,
                amount=security_analysis['actual_amount'],
                confidence_score=security_analysis['confidence_score'],
                blockchain_confirmations=security_analysis.get('confirmations', 0)
            )
            
        except Exception as e:
            logger.error(f"❌ Blockchain verification failed for {tx_hash}: {e}")
            return PaymentVerificationResult(
                result=VerificationResult.BLOCKCHAIN_ERROR,
                error_message=f"Blockchain verification error: {str(e)}",
                tx_hash=tx_hash
            )
    
    async def _analyze_transaction_security(
        self, 
        tx_info: Dict[str, Any], 
        expected_amount: float, 
        wallet_address: str
    ) -> Dict[str, Any]:
        """تحلیل امنیتی جامع تراکنش"""
        
        analysis = {
            'fraud_detected': False,
            'fraud_flags': [],
            'confidence_score': 0.0,
            'actual_amount': 0.0,
            'reason': '',
            'confirmations': 0
        }
        
        try:
            # استخراج اطلاعات کلیدی
            tx_amount = float(tx_info.get('amount', 0)) / 1000000  # TRC20 USDT has 6 decimals
            tx_timestamp = tx_info.get('timestamp', 0)
            tx_to_address = tx_info.get('to_address', '').lower()
            tx_status = tx_info.get('contractRet', 'UNKNOWN')
            
            analysis['actual_amount'] = tx_amount
            analysis['confirmations'] = tx_info.get('confirmations', 0)
            
            # بررسی وضعیت تراکنش
            if tx_status != 'SUCCESS':
                analysis['fraud_detected'] = True
                analysis['fraud_flags'].append('transaction_failed')
                analysis['reason'] = f"Transaction status: {tx_status}"
                return analysis
            
            # بررسی آدرس مقصد
            if tx_to_address != wallet_address.lower():
                analysis['fraud_detected'] = True
                analysis['fraud_flags'].append('wrong_recipient')
                analysis['reason'] = f"Wrong recipient address"
                return analysis
            
            # بررسی زمان تراکنش
            tx_time = datetime.fromtimestamp(tx_timestamp / 1000)
            time_diff = datetime.now() - tx_time
            
            if time_diff.total_seconds() > (self.MAX_TX_AGE_HOURS * 3600):
                analysis['fraud_detected'] = True
                analysis['fraud_flags'].append('transaction_too_old')
                analysis['reason'] = f"Transaction is too old: {time_diff}"
                return analysis
            
            # بررسی مبالغ مشکوک
            if tx_amount in self.FRAUD_PATTERNS['suspicious_amounts']:
                analysis['fraud_flags'].append('suspicious_amount')
                analysis['confidence_score'] -= 0.2
            
            # محاسبه امتیاز اعتماد
            confidence_score = 1.0
            
            # تایید شبکه
            if analysis['confirmations'] >= self.MIN_CONFIRMATIONS:
                confidence_score += 0.2
            else:
                confidence_score -= 0.3
            
            # تطبیق مبلغ
            amount_diff_percent = abs(tx_amount - expected_amount) / expected_amount * 100
            if amount_diff_percent <= self.AMOUNT_TOLERANCE_PERCENT:
                confidence_score += 0.3
            else:
                confidence_score -= 0.4
            
            # زمان تراکنش
            if time_diff.total_seconds() < 3600:  # کمتر از 1 ساعت
                confidence_score += 0.1
            
            analysis['confidence_score'] = max(0.0, min(1.0, confidence_score))
            
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Security analysis failed: {e}")
            analysis['fraud_detected'] = True
            analysis['fraud_flags'].append('analysis_error')
            analysis['reason'] = f"Analysis error: {str(e)}"
            return analysis
    
    async def _find_best_matching_transaction(
        self,
        transactions: List[Dict],
        expected_amount: float,
        wallet_address: str,
        payment_id: str
    ) -> Optional[Dict[str, Any]]:
        """یافتن بهترین تراکنش منطبق"""
        
        best_match = None
        best_score = 0.0
        
        for tx in transactions:
            try:
                tx_hash = tx.get('hash', '')
                tx_amount = float(tx.get('amount', 0)) / 1000000
                
                # بررسی تکراری نبودن
                duplicate_check = await self._check_duplicate_tx(tx_hash, payment_id)
                if duplicate_check['is_duplicate']:
                    continue
                
                # محاسبه امتیاز تطبیق
                amount_diff = abs(tx_amount - expected_amount)
                amount_score = max(0, 1 - (amount_diff / expected_amount))
                
                # امتیاز زمانی
                tx_time = datetime.fromtimestamp(tx.get('timestamp', 0) / 1000)
                time_diff = abs((datetime.now() - tx_time).total_seconds())
                time_score = max(0, 1 - (time_diff / 3600))  # بهتر باشد اگر جدیدتر باشد
                
                # امتیاز کل
                total_score = (amount_score * 0.7) + (time_score * 0.3)
                
                if total_score > best_score and amount_score > 0.95:  # حداقل 95% تطبیق مبلغ
                    best_score = total_score
                    best_match = {
                        'tx_hash': tx_hash,
                        'amount': tx_amount,
                        'confidence': total_score,
                        'confirmations': tx.get('confirmations', 0)
                    }
            
            except Exception as e:
                logger.warning(f"⚠️ Error analyzing transaction {tx.get('hash', 'unknown')}: {e}")
                continue
        
        return best_match
    
    async def _get_payment_data(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """دریافت اطلاعات پرداخت از دیتابیس"""
        try:
            payment = self.db.get_crypto_payment_by_payment_id(payment_id)
            return dict(payment) if payment else None
        except Exception as e:
            logger.error(f"❌ Failed to get payment data for {payment_id}: {e}")
            return None
    
    async def _check_user_limits(self, user_id: int) -> Dict[str, Any]:
        """بررسی محدودیت‌های کاربر"""
        try:
            # بررسی تعداد تلاش‌های روزانه
            today = datetime.now().date()
            
            query = """
                SELECT COUNT(*) as attempt_count 
                FROM auto_verification_logs 
                WHERE user_id = ? AND date(created_at) = ?
            """
            
            if self.db.execute(query, (user_id, today.isoformat())):
                result = self.db.fetchone()
                attempt_count = result['attempt_count'] if result else 0
                
                if attempt_count >= self.FRAUD_PATTERNS['rate_limit_per_user']:
                    return {
                        'allowed': False,
                        'reason': f"Daily verification limit exceeded: {attempt_count}/{self.FRAUD_PATTERNS['rate_limit_per_user']}"
                    }
            
            return {'allowed': True, 'reason': ''}
            
        except Exception as e:
            logger.error(f"❌ User limit check failed for user {user_id}: {e}")
            return {'allowed': True, 'reason': ''}  # در صورت خطا اجازه بده
    
    async def _check_duplicate_tx(self, tx_hash: str, current_payment_id: str) -> Dict[str, Any]:
        """بررسی تکراری بودن TX hash"""
        try:
            query = """
                SELECT payment_id, created_at 
                FROM crypto_payments 
                WHERE transaction_id = ? AND payment_id != ? AND status = 'completed'
            """
            
            if self.db.execute(query, (tx_hash, current_payment_id)):
                existing = self.db.fetchone()
                if existing:
                    return {
                        'is_duplicate': True,
                        'existing_payment_id': existing['payment_id'],
                        'used_at': existing['created_at']
                    }
            
            return {'is_duplicate': False}
            
        except Exception as e:
            logger.error(f"❌ Duplicate check failed for TX {tx_hash}: {e}")
            return {'is_duplicate': False}  # در صورت خطا تکراری فرض نکن
    
    def _is_valid_tx_hash_format(self, tx_hash: str) -> bool:
        """بررسی صحت فرمت TX hash"""
        if not tx_hash or len(tx_hash.strip()) != 64:
            return False
        
        # بررسی hexadecimal pattern
        return bool(re.match(r'^[a-fA-F0-9]{64}$', tx_hash.strip()))
    
    def _check_amount_match(self, actual_amount: float, expected_amount: float) -> Dict[str, Any]:
        """بررسی تطبیق مبلغ با تلرانس"""
        if expected_amount <= 0:
            return {'matches': False, 'reason': 'Invalid expected amount'}
        
        diff_percent = abs(actual_amount - expected_amount) / expected_amount * 100
        
        return {
            'matches': diff_percent <= self.AMOUNT_TOLERANCE_PERCENT,
            'difference_percent': diff_percent,
            'tolerance_percent': self.AMOUNT_TOLERANCE_PERCENT
        }
    
    def _get_processing_time(self, start_time: datetime) -> int:
        """محاسبه زمان پردازش به میلی‌ثانیه"""
        return int((datetime.now() - start_time).total_seconds() * 1000)
    
    async def log_verification_attempt(
        self,
        payment_id: str,
        user_id: int,
        result: PaymentVerificationResult,
        method: str = "advanced_verification"
    ):
        """ثبت لاگ تلاش تایید"""
        try:
            log_data = {
                'payment_id': payment_id,
                'user_id': user_id,
                'tx_hash': result.tx_hash or '',
                'amount': result.amount or 0.0,
                'status': result.result.value,
                'verification_method': method,
                'confidence_score': result.confidence_score,
                'fraud_flags': ','.join(result.fraud_flags),
                'processing_time_ms': result.processing_time_ms,
                'error_message': result.error_message or '',
                'created_at': datetime.now().isoformat()
            }
            
            query = """
                INSERT INTO auto_verification_logs 
                (payment_id, user_id, tx_hash, amount, status, verification_method, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            self.db.execute(query, (
                log_data['payment_id'],
                log_data['user_id'], 
                log_data['tx_hash'],
                log_data['amount'],
                log_data['status'],
                log_data['verification_method'],
                log_data['created_at']
            ))
            self.db.commit()
            
            logger.info(f"📝 Verification attempt logged: {payment_id} -> {result.result.value}")
            
        except Exception as e:
            logger.error(f"❌ Failed to log verification attempt: {e}")

# سیگلتون instance
advanced_verifier = AdvancedCryptoVerification()
