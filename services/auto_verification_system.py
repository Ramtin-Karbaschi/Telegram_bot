# services/auto_verification_system.py

import logging
import asyncio
from datetime import datetime
from database.models import Database
from services.enhanced_crypto_service import EnhancedCryptoService
from services.advanced_crypto_verification import advanced_verifier, VerificationResult
from handlers.subscription.subscription_helpers import SubscriptionHelper
from services.bot_service import BotService
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

class AutoVerificationSystem:
    """سیستم تایید خودکار 100% پرداخت‌های تتری
    
    این سیستم به طور مداوم:
    1. پرداخت‌های pending را بررسی می‌کند
    2. در بلاک‌چین جستجو می‌کند
    3. پرداخت‌های معتبر را خودکار تایید می‌کند
    4. گزارش کامل از تمام فعالیت‌ها ارائه می‌دهد
    """
    
    def __init__(self):
        self.db = Database.get_instance()
        self.is_running = False
        self.verification_interval = 60  # بررسی هر 60 ثانیه
        self.last_run_time = None

    async def start_auto_verification(self):
        """شروع سیستم تایید خودکار"""
        if self.is_running:
            logger.warning("Auto verification system is already running")
            return
        
        self.is_running = True
        logger.info("🚀 Auto verification system started")
        
        while self.is_running:
            try:
                await self.verify_pending_payments()
                await asyncio.sleep(self.verification_interval)
            except Exception as e:
                logger.error(f"Error in auto verification loop: {e}")
                await asyncio.sleep(5)  # کمی صبر کن و دوباره تلاش کن
    
    def stop_auto_verification(self):
        """توقف سیستم تایید خودکار"""
        self.is_running = False
        logger.info("⏹️ Auto verification system stopped")

    async def verify_pending_payments(self):
        """🔄 تایید پرداخت‌های در انتظار با سیستم پیشرفته"""
        try:
            db = Database.get_instance()
            
            # دریافت پرداخت‌های در انتظار
            pending_payments = db.get_pending_crypto_payments()
            
            if not pending_payments:
                logger.info("✅ No pending crypto payments found")
                return
                
            logger.info(f"🔍 Found {len(pending_payments)} pending crypto payments for verification")
            
            for payment in pending_payments:
                payment_id = payment.get('payment_id')
                try:
                    logger.info(f"🚀 Starting advanced verification for payment {payment_id}")
                    await self.process_single_payment_advanced(payment_id, payment)
                    await asyncio.sleep(3)  # فاصله بین تراکنش‌ها
                except Exception as e:
                    logger.error(f"💥 Error processing payment {payment_id}: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"💥 Critical error in verify_pending_payments: {e}")

    async def process_single_payment_advanced(self, payment_id: str, payment_data: dict):
        """🎯 پردازش یک پرداخت با سیستم پیشرفته"""
        try:
            user_id = payment_data.get('user_id', 0)
            expected_amount = payment_data.get('usdt_amount_requested', 0)
            wallet_address = payment_data.get('wallet_address')
            
            logger.info(
                f"📊 Processing payment {payment_id}: "
                f"User {user_id}, Amount: {expected_amount} USDT"
            )
            
            # فراخوانی سیستم تایید پیشرفته
            verification_result = await advanced_verifier.verify_payment_comprehensive(
                payment_id=payment_id,
                user_provided_tx=None,  # جستجوی خودکار
                expected_amount=expected_amount,
                wallet_address=wallet_address,
                user_id=user_id
            )
            
            # ثبت لاگ تایید
            await advanced_verifier.log_verification_attempt(
                payment_id, user_id, verification_result, "auto_verification_system"
            )
            
            # بررسی نتیجه
            if verification_result.result == VerificationResult.SUCCESS:
                logger.info(
                    f"✅ Payment {payment_id} verified successfully! "
                    f"TX: {verification_result.tx_hash}, "
                    f"Amount: {verification_result.amount} USDT, "
                    f"Confidence: {verification_result.confidence_score:.2f}"
                )
                await self.approve_payment(
                    payment_id, 
                    verification_result.tx_hash, 
                    verification_result.amount
                )
                
            elif verification_result.result == VerificationResult.FRAUD_DETECTED:
                logger.warning(
                    f"🚨 FRAUD DETECTED for payment {payment_id}! "
                    f"Flags: {verification_result.fraud_flags}"
                )
                await self.mark_payment_as_fraud(payment_id, verification_result)
                
            elif verification_result.result == VerificationResult.DUPLICATE_TX:
                logger.warning(
                    f"⚠️ Duplicate TX detected for payment {payment_id}: {verification_result.tx_hash}"
                )
                await self.mark_payment_as_duplicate(payment_id, verification_result)
                
            else:
                logger.info(
                    f"❌ Payment {payment_id} verification failed: "
                    f"{verification_result.result.value} - {verification_result.error_message}"
                )
                # در صورت عدم موفقیت، در انتظار باقی می‌ماند
                
        except Exception as e:
            logger.error(f"💥 Error in process_single_payment_advanced: {e}")

    async def approve_payment(self, payment_id: str, tx_hash: str, amount: float):
        """✅ تایید نهایی پرداخت با ثبت جزئیات امنیتی"""
        try:
            db = Database.get_instance()
            
            # به‌روزرسانی وضعیت پرداخت
            db.execute(
                "UPDATE crypto_payments SET status = 'approved', transaction_id = ?, verified_amount = ?, approved_at = ? WHERE payment_id = ?",
                (tx_hash, amount, datetime.now().isoformat(), payment_id)
            )
            
            # فعال‌سازی اشتراک کاربر
            payment = db.get_crypto_payment_by_payment_id(payment_id)
            if payment:
                user_id = payment.get('user_id')
                plan_type = payment.get('plan_type')
                
                if user_id and plan_type:
                    success = await SubscriptionHelper.activate_subscription(
                        user_id, plan_type, f"crypto_payment_{payment_id}"
                    )
                    
                    if success:
                        logger.info(f"🎉 Subscription activated for user {user_id} with plan {plan_type}")
                        
                        # ارسال پیام تایید به کاربر
                        await self.send_approval_message(user_id, payment_id, amount, tx_hash)
                    else:
                        logger.error(f"💥 Failed to activate subscription for user {user_id}")
                        
            # ثبت لاگ موفقیت
            logger.info(
                f"✅ Payment {payment_id} approved successfully: "
                f"{amount} USDT via TX {tx_hash[:16]}..."
            )
            
        except Exception as e:
            logger.error(f"💥 Error in approve_payment: {e}")

    async def mark_payment_as_fraud(self, payment_id: str, verification_result):
        """🚨 علامت‌گذاری پرداخت به عنوان تقلب"""
        try:
            db = Database.get_instance()
            
            # به‌روزرسانی وضعیت پرداخت
            db.execute(
                "UPDATE crypto_payments SET status = 'fraud_detected', notes = ?, updated_at = ? WHERE payment_id = ?",
                (f"Fraud detected: {verification_result.fraud_flags}", datetime.now().isoformat(), payment_id)
            )
            
            logger.warning(
                f"🚨 Payment {payment_id} marked as FRAUD. "
                f"Flags: {verification_result.fraud_flags}"
            )
            
        except Exception as e:
            logger.error(f"Error marking payment as fraud: {e}")

    async def mark_payment_as_duplicate(self, payment_id: str, verification_result):
        """⚠️ علامت‌گذاری پرداخت به عنوان تکراری"""
        try:
            db = Database.get_instance()
            
            # به‌روزرسانی وضعیت پرداخت
            db.execute(
                "UPDATE crypto_payments SET status = 'duplicate_tx', notes = ?, updated_at = ? WHERE payment_id = ?",
                (f"Duplicate TX: {verification_result.tx_hash}", datetime.now().isoformat(), payment_id)
            )
            
            logger.warning(
                f"⚠️ Payment {payment_id} marked as DUPLICATE. "
                f"TX: {verification_result.tx_hash}"
            )
            
        except Exception as e:
            logger.error(f"Error marking payment as duplicate: {e}")

    async def send_approval_message(self, user_id: int, payment_id: str, amount: float, tx_hash: str):
        """اطلاع‌رسانی موفقیت به کاربر"""
        try:
            from telegram import Bot
            bot = Bot(token=config.MAIN_BOT_TOKEN or config.BOT_TOKEN)
            
            message = f"""
✅ **پرداخت شما تایید شد!**

💰 **مبلغ:** {amount:.6f} USDT
🔗 **شناسه تراکنش:** `{tx_hash}`
🤖 **روش تایید:** خودکار هوشمند
🎯 **اشتراک شما فعال گردید**

برای مشاهده جزئیات اشتراک از منوی اصلی استفاده کنید.
"""
            
            await bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"Error notifying user {user_id}: {e}")

    async def get_security_report(self, hours: int = 24) -> dict:
        """🔒 گزارش امنیتی سیستم"""
        try:
            from datetime import timedelta
            
            # استفاده از آمار پیشرفته
            stats = await EnhancedCryptoService.get_verification_stats(hours=hours)
            
            # افزودن اطلاعات امنیتی
            security_report = {
                **stats,
                'security_status': 'safe' if stats.get('fraud_detected', 0) == 0 else 'alert',
                'fraud_rate': 0.0,
                'system_uptime': self.is_running,
                'last_security_check': datetime.now().isoformat()
            }
            
            # محاسبه نرخ تقلب
            total_attempts = stats.get('total_attempts', 0)
            if total_attempts > 0:
                security_report['fraud_rate'] = stats.get('fraud_detected', 0) / total_attempts
            
            return security_report
            
        except Exception as e:
            logger.error(f"💥 Error generating security report: {e}")
            return {}

    async def get_verification_stats(self) -> dict:
        """📊 آمار جامع سیستم تایید خودکار"""
        try:
            db = Database.get_instance()
            
            stats = {
                'total_verified': 0,
                'successful_verifications': 0,
                'failed_verifications': 0,
                'fraud_detected': 0,
                'duplicate_transactions': 0,
                'last_run': self.last_run_time,
                'is_running': self.is_running,
                'average_confidence': 0.0,
                'success_rate': 0.0
            }
            
            # دریافت آمار کلی
            if db.execute("SELECT COUNT(*) as total FROM auto_verification_logs"):
                result = db.fetchone()
                stats['total_verified'] = result['total'] if result else 0
            
            # آمار موفقیت
            if db.execute("SELECT COUNT(*) as successful FROM auto_verification_logs WHERE status = 'success'"):
                result = db.fetchone()
                stats['successful_verifications'] = result['successful'] if result else 0
            
            # آمار تقلب
            if db.execute("SELECT COUNT(*) as fraud FROM auto_verification_logs WHERE status = 'fraud_detected'"):
                result = db.fetchone()
                stats['fraud_detected'] = result['fraud'] if result else 0
            
            # آمار تکراری
            if db.execute("SELECT COUNT(*) as duplicate FROM auto_verification_logs WHERE status = 'duplicate_tx'"):
                result = db.fetchone()
                stats['duplicate_transactions'] = result['duplicate'] if result else 0
            
            # محاسبه نرخ موفقیت
            if stats['total_verified'] > 0:
                stats['success_rate'] = stats['successful_verifications'] / stats['total_verified']
                stats['failed_verifications'] = stats['total_verified'] - stats['successful_verifications']
            
            # میانگین اعتماد
            if db.execute("SELECT AVG(confidence_score) as avg_confidence FROM auto_verification_logs WHERE status = 'success'"):
                result = db.fetchone()
                stats['average_confidence'] = result['avg_confidence'] if result and result['avg_confidence'] else 0.0
            
            return stats
            
        except Exception as e:
            logger.error(f"💥 Error getting verification stats: {e}")
            return {}

# سینگلتون نمونه برای استفاده در سراسر اپلیکیشن
auto_verification_system = AutoVerificationSystem()
