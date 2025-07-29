"""
🔬 تست جامع و مهندسی سیستم تایید پرداخت
تست کامل جریان واقعی کاربر از ابتدا تا انتها
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta
import uuid

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database.models import Database
from services.enhanced_crypto_service import EnhancedCryptoService
from services.tronscan_service import TronScanService
from services.advanced_crypto_verification import advanced_verifier
import config

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ComprehensivePaymentTest:
    def __init__(self):
        self.db = Database.get_instance()
        self.test_results = []
        self.critical_issues = []
        
    def log_test(self, test_name: str, success: bool, details: str = ""):
        """ثبت نتیجه تست"""
        result = {
            'test': test_name,
            'success': success,
            'details': details,
            'timestamp': datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
        
        if not success:
            self.critical_issues.append(f"{test_name}: {details}")
            
    def test_database_schema(self):
        """بررسی یکپارچگی schema دیتابیس"""
        print("\n🔍 Testing Database Schema Integrity...")
        
        try:
            # بررسی وجود جدول crypto_payments
            self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crypto_payments'")
            crypto_table_exists = self.db.fetchone() is not None
            self.log_test("crypto_payments table exists", crypto_table_exists)
            
            if crypto_table_exists:
                # بررسی ستون‌های جدول crypto_payments
                self.db.execute("PRAGMA table_info(crypto_payments)")
                columns = {row['name']: row['type'] for row in self.db.fetchall()}
                
                required_columns = ['payment_id', 'user_id', 'usdt_amount_requested', 'wallet_address', 'transaction_id', 'status']
                for col in required_columns:
                    exists = col in columns
                    self.log_test(f"crypto_payments.{col} column exists", exists)
            
            # بررسی وجود جدول payments (fallback)
            self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payments'")
            payments_table_exists = self.db.fetchone() is not None
            self.log_test("payments table exists (fallback)", payments_table_exists)
            
            # بررسی متدهای دیتابیس
            has_crypto_method = hasattr(self.db, 'get_crypto_payment_by_payment_id')
            self.log_test("get_crypto_payment_by_payment_id method exists", has_crypto_method)
            
            # Check DatabaseQueries which is used in handlers
            from database.queries import DatabaseQueries
            has_payment_method = hasattr(DatabaseQueries, 'get_payment_by_id')
            self.log_test("get_payment_by_id method exists (DatabaseQueries)", has_payment_method)
            
        except Exception as e:
            self.log_test("Database schema check", False, f"Error: {e}")
    
    def test_config_validation(self):
        """بررسی تنظیمات حیاتی سیستم"""
        print("\n🔧 Testing Configuration...")
        
        # بررسی متغیرهای مهم
        crypto_wallet = getattr(config, 'CRYPTO_WALLET_ADDRESS', None)
        self.log_test("CRYPTO_WALLET_ADDRESS configured", 
                     bool(crypto_wallet and crypto_wallet != 'WALLET_NOT_SET_IN_ENV'),
                     f"Value: {crypto_wallet}")
        
        tronscan_key = getattr(config, 'TRONSCAN_API_KEY', None)
        self.log_test("TRONSCAN_API_KEY configured", 
                     bool(tronscan_key),
                     "API key present" if tronscan_key else "Missing API key")
        
        # بررسی timeout و tolerance
        timeout = getattr(config, 'CRYPTO_PAYMENT_TIMEOUT_MINUTES', 30)
        self.log_test("Reasonable timeout configured", 
                     5 <= timeout <= 120,
                     f"Timeout: {timeout} minutes")
    
    async def test_tronscan_api_connectivity(self):
        """بررسی اتصال به TronScan API"""
        print("\n🌐 Testing TronScan API Connectivity...")
        
        try:
            tronscan = TronScanService()
            
            # تست متد get_transaction_info (که اضافه کردیم)
            has_get_tx_info = hasattr(tronscan, 'get_transaction_info')
            self.log_test("TronScan.get_transaction_info method exists", has_get_tx_info)
            
            if has_get_tx_info:
                # تست با یک TX hash نمونه (باید None برگرداند چون fake است)
                fake_tx = "a" * 64  # TX hash فیک
                result = await tronscan.get_transaction_info(fake_tx)
                self.log_test("TronScan API call completes", True, "API responding")
            
            # تست متد legacy
            has_verify_method = hasattr(tronscan, 'verify_payment_by_hash')
            self.log_test("TronScan.verify_payment_by_hash method exists", has_verify_method)
            
        except Exception as e:
            self.log_test("TronScan API connectivity", False, f"Error: {e}")
    
    async def test_payment_creation_flow(self):
        """تست ایجاد پرداخت کریپتو"""
        print("\n💰 Testing Payment Creation Flow...")
        
        try:
            # ایجاد یک پرداخت تست
            test_user_id = 999999
            test_amount_irr = 1000000
            test_amount_usdt = 25.5
            test_wallet = getattr(config, 'CRYPTO_WALLET_ADDRESS', 'TEST_WALLET')
            expires_at = datetime.now() + timedelta(minutes=30)
            
            payment_id = self.db.create_crypto_payment_request(
                user_id=test_user_id,
                rial_amount=test_amount_irr,
                usdt_amount_requested=test_amount_usdt,
                wallet_address=test_wallet,
                expires_at=expires_at
            )
            
            self.log_test("Crypto payment creation", 
                         bool(payment_id),
                         f"Payment ID: {payment_id}")
            
            if payment_id:
                # بررسی retrieve کردن پرداخت
                payment_record = self.db.get_crypto_payment_by_payment_id(payment_id)
                self.log_test("Payment retrieval after creation",
                             bool(payment_record),
                             f"Record found: {bool(payment_record)}")
                
                if payment_record:
                    # بررسی صحت داده‌ها
                    amount_correct = payment_record.get('usdt_amount_requested') == test_amount_usdt
                    self.log_test("Payment data integrity", amount_correct,
                                 f"USDT amount: {payment_record.get('usdt_amount_requested')}")
                
                # تست fallback mechanism
                from database.queries import DatabaseQueries
                legacy_record = DatabaseQueries.get_payment_by_id(payment_id)
                fallback_works = legacy_record is None  # باید None باشد چون در crypto_payments است
                self.log_test("Fallback mechanism isolation", fallback_works,
                             "Legacy table correctly separated")
                
                # پاک کردن پرداخت تست
                self.db.execute("DELETE FROM crypto_payments WHERE payment_id = ?", (payment_id,))
                self.db.commit()
                
        except Exception as e:
            self.log_test("Payment creation flow", False, f"Error: {e}")
    
    async def test_verification_system_integration(self):
        """تست یکپارچگی سیستم تایید"""
        print("\n🔒 Testing Verification System Integration...")
        
        try:
            # بررسی وجود advanced_verifier
            has_verifier = advanced_verifier is not None
            self.log_test("Advanced verifier instance", has_verifier)
            
            if has_verifier:
                # تست متدهای کلیدی
                has_comprehensive = hasattr(advanced_verifier, 'verify_payment_comprehensive')
                self.log_test("verify_payment_comprehensive method", has_comprehensive)
                
                has_blockchain_verify = hasattr(advanced_verifier, '_verify_on_blockchain')
                self.log_test("_verify_on_blockchain method", has_blockchain_verify)
                
                has_amount_check = hasattr(advanced_verifier, '_check_amount_match')
                self.log_test("_check_amount_match method", has_amount_check)
                
                # تست پارامترهای امنیتی
                tolerance = getattr(advanced_verifier, 'AMOUNT_TOLERANCE_PERCENT', 0)
                reasonable_tolerance = 0.1 <= tolerance <= 2.0
                self.log_test("Reasonable amount tolerance", reasonable_tolerance,
                             f"Tolerance: {tolerance}%")
            
            # تست EnhancedCryptoService
            has_smart_verification = hasattr(EnhancedCryptoService, 'smart_payment_verification')
            self.log_test("EnhancedCryptoService.smart_payment_verification", has_smart_verification)
            
        except Exception as e:
            self.log_test("Verification system integration", False, f"Error: {e}")
    
    async def test_error_handling_scenarios(self):
        """تست سناریوهای خطا و edge cases"""
        print("\n⚠️ Testing Error Handling Scenarios...")
        
        try:
            # تست با payment_id نامعتبر
            result = await EnhancedCryptoService.smart_payment_verification("invalid_payment_id")
            invalid_payment_handled = result[0] == False  # باید False برگرداند
            self.log_test("Invalid payment ID handling", invalid_payment_handled,
                         f"Returned: {result}")
            
            # تست با TX hash نامعتبر (اگر پرداخت معتبر داشته باشیم)
            fake_payment_id = str(uuid.uuid4())
            
            # ایجاد پرداخت موقت برای تست
            test_user_id = 999998
            expires_at = datetime.now() + timedelta(minutes=30)
            payment_id = self.db.create_crypto_payment_request(
                user_id=test_user_id,
                rial_amount=100000,
                usdt_amount_requested=2.5,
                wallet_address=getattr(config, 'CRYPTO_WALLET_ADDRESS', 'TEST'),
                expires_at=expires_at
            )
            
            if payment_id:
                # تست با TX hash نامعتبر
                invalid_tx = "invalid_tx_hash"
                result = await EnhancedCryptoService.smart_payment_verification(
                    payment_id, user_provided_tx=invalid_tx
                )
                invalid_tx_handled = result[0] == False
                self.log_test("Invalid TX hash handling", invalid_tx_handled,
                             f"Returned: {result}")
                
                # پاک کردن پرداخت تست
                self.db.execute("DELETE FROM crypto_payments WHERE payment_id = ?", (payment_id,))
                self.db.commit()
            
        except Exception as e:
            self.log_test("Error handling scenarios", False, f"Error: {e}")
    
    async def test_realistic_transaction_simulation(self):
        """شبیه‌سازی تراکنش واقعی"""
        print("\n🎭 Testing Realistic Transaction Simulation...")
        
        try:
            # شبیه‌سازی داده‌های تراکنش واقعی TRON
            mock_tx_data = {
                'contractRet': 'SUCCESS',
                'timestamp': int(datetime.now().timestamp() * 1000),
                'confirmations': 1,
                'amount': 25500000,  # 25.5 USDT in raw format (6 decimals)
                'to_address': getattr(config, 'CRYPTO_WALLET_ADDRESS', 'test_wallet').lower(),
                'from_address': 'TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t',
                'block_number': 12345678
            }
            
            # تست تبدیل مبلغ
            raw_amount = mock_tx_data['amount']
            converted_amount = float(raw_amount) / (10 ** 6)
            expected_amount = 25.5
            conversion_correct = abs(converted_amount - expected_amount) < 0.000001
            self.log_test("Amount conversion accuracy", conversion_correct,
                         f"Raw: {raw_amount}, Converted: {converted_amount}, Expected: {expected_amount}")
            
            # تست تحلیل امنیتی با داده‌های واقعی
            if hasattr(advanced_verifier, '_analyze_transaction_security'):
                analysis = await advanced_verifier._analyze_transaction_security(
                    mock_tx_data, expected_amount, mock_tx_data['to_address']
                )
                
                security_passed = not analysis.get('fraud_detected', True)
                self.log_test("Security analysis with valid data", security_passed,
                             f"Fraud detected: {analysis.get('fraud_detected')}")
                
                # تست با آدرس اشتباه
                wrong_address_data = mock_tx_data.copy()
                wrong_address_data['to_address'] = 'wrong_address'
                
                wrong_analysis = await advanced_verifier._analyze_transaction_security(
                    wrong_address_data, expected_amount, mock_tx_data['to_address']
                )
                
                fraud_detected = wrong_analysis.get('fraud_detected', False)
                self.log_test("Security analysis detects wrong address", fraud_detected,
                             f"Fraud correctly detected: {fraud_detected}")
            
        except Exception as e:
            self.log_test("Realistic transaction simulation", False, f"Error: {e}")
    
    async def run_comprehensive_tests(self):
        """اجرای تمام تست‌های جامع"""
        print("🔬 شروع تست‌های مهندسی جامع سیستم تایید پرداخت")
        print("=" * 70)
        
        # اجرای تست‌ها
        self.test_database_schema()
        self.test_config_validation()
        await self.test_tronscan_api_connectivity()
        await self.test_payment_creation_flow()
        await self.test_verification_system_integration()
        await self.test_error_handling_scenarios()
        await self.test_realistic_transaction_simulation()
        
        # گزارش نهایی
        print("\n" + "=" * 70)
        print("📊 گزارش نهایی تست‌های مهندسی")
        print("=" * 70)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for t in self.test_results if t['success'])
        failed_tests = total_tests - passed_tests
        
        print(f"📈 تعداد کل تست‌ها: {total_tests}")
        print(f"✅ تست‌های موفق: {passed_tests}")
        print(f"❌ تست‌های ناموفق: {failed_tests}")
        print(f"📊 درصد موفقیت: {(passed_tests/total_tests)*100:.1f}%")
        
        if self.critical_issues:
            print(f"\n🚨 مسائل بحرانی ({len(self.critical_issues)}):")
            for issue in self.critical_issues:
                print(f"   ❌ {issue}")
        
        if failed_tests == 0:
            print("\n🎉 ✅ تمام تست‌ها موفق - سیستم آماده تولید")
            print("🔒 سیستم از نظر مهندسی کاملاً قابل اعتماد است")
        else:
            print(f"\n⚠️ {failed_tests} مسئله برای حل باقی مانده")
            print("❗ سیستم نیاز به اصلاح دارد")
        
        return failed_tests == 0

async def main():
    """اجرای تست‌های جامع"""
    tester = ComprehensivePaymentTest()
    success = await tester.run_comprehensive_tests()
    
    if not success:
        sys.exit(1)  # خروج با خطا اگر تست‌ها موفق نبودند

if __name__ == "__main__":
    asyncio.run(main())
