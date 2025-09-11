"""
سیستم ممیزی جامع پرداخت‌ها و گزارش‌های فروش
این سیستم تمام مسیرهای پرداخت را بررسی می‌کند و اطمینان حاصل می‌کند که همه از activate_or_extend_subscription استفاده می‌کنند
"""

import os
import re
import ast
import sqlite3
from datetime import datetime, timedelta

class PaymentAuditSystem:
    def __init__(self, project_path=r"c:\Users\ramti\Documents\GitHub\Telegram_bot"):
        self.project_path = project_path
        self.issues = []
        self.payment_paths = []
        
    def find_payment_handlers(self):
        """Find all files that handle payments"""
        payment_files = []
        
        for root, dirs, files in os.walk(self.project_path):
            # Skip test files and backups
            if 'test' in root.lower() or 'backup' in root.lower():
                continue
                
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # Look for payment-related code
                            if any(keyword in content for keyword in [
                                'add_subscription', 
                                'activate_or_extend_subscription',
                                'payment',
                                'subscription',
                                'zarinpal',
                                'crypto'
                            ]):
                                payment_files.append(file_path)
                    except Exception as e:
                        pass
        
        return payment_files
    
    def analyze_file(self, file_path):
        """Analyze a file for payment handling patterns"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.split('\n')
        
        issues = []
        
        # Check for direct add_subscription usage (should use activate_or_extend_subscription)
        for i, line in enumerate(lines, 1):
            # Skip comments and test files
            if '#' in line and line.strip().startswith('#'):
                continue
            if 'test' in file_path.lower():
                continue
                
            # Check for problematic patterns
            if 'DatabaseQueries.add_subscription' in line or 'Database.add_subscription' in line:
                # Check if it's not in activate_or_extend_subscription function
                context_start = max(0, i-10)
                context_end = min(len(lines), i+10)
                context = '\n'.join(lines[context_start:context_end])
                
                if 'def activate_or_extend_subscription' not in context and \
                   'def add_subscription' not in context:
                    issues.append({
                        'file': file_path,
                        'line': i,
                        'type': 'DIRECT_ADD_SUBSCRIPTION',
                        'code': line.strip(),
                        'severity': 'HIGH'
                    })
            
            # Check for payment verification without sales report
            if 'update_payment_verification_status' in line and 'completed' in line:
                # Check if activate_or_extend_subscription is called nearby
                context_start = max(0, i-5)
                context_end = min(len(lines), i+20)
                context = '\n'.join(lines[context_start:context_end])
                
                if 'activate_or_extend_subscription' not in context:
                    issues.append({
                        'file': file_path,
                        'line': i,
                        'type': 'PAYMENT_WITHOUT_REPORT',
                        'code': line.strip(),
                        'severity': 'MEDIUM'
                    })
        
        return issues
    
    def check_database_integrity(self, db_path):
        """Check database for unreported transactions"""
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get payments vs subscriptions mismatch
        cursor.execute("""
            SELECT COUNT(*) as payment_count 
            FROM payments 
            WHERE status = 'completed'
        """)
        completed_payments = cursor.fetchone()['payment_count']
        
        cursor.execute("""
            SELECT COUNT(*) as crypto_count 
            FROM crypto_payments 
            WHERE status IN ('confirmed', 'completed')
        """)
        completed_crypto = cursor.fetchone()['crypto_count']
        
        cursor.execute("""
            SELECT COUNT(*) as sub_count 
            FROM subscriptions 
            WHERE payment_method IN ('zarinpal', 'crypto')
        """)
        paid_subscriptions = cursor.fetchone()['sub_count']
        
        # Check for orphaned payments (payments without subscriptions)
        cursor.execute("""
            SELECT p.payment_id, p.user_id, p.amount, p.created_at
            FROM payments p
            LEFT JOIN subscriptions s ON p.payment_id = s.payment_id
            WHERE p.status = 'completed' 
            AND s.id IS NULL
            ORDER BY p.created_at DESC
            LIMIT 10
        """)
        orphaned_payments = cursor.fetchall()
        
        conn.close()
        
        return {
            'completed_payments': completed_payments,
            'completed_crypto': completed_crypto,
            'paid_subscriptions': paid_subscriptions,
            'orphaned_payments': orphaned_payments
        }
    
    def generate_report(self):
        """Generate comprehensive audit report"""
        print("\n" + "="*80)
        print("📊 گزارش ممیزی جامع سیستم پرداخت")
        print("="*80)
        
        # Find and analyze payment files
        print("\n🔍 بررسی فایل‌های پرداخت...")
        payment_files = self.find_payment_handlers()
        
        all_issues = []
        for file in payment_files:
            issues = self.analyze_file(file)
            if issues:
                all_issues.extend(issues)
        
        # Report issues by severity
        high_severity = [i for i in all_issues if i['severity'] == 'HIGH']
        medium_severity = [i for i in all_issues if i['severity'] == 'MEDIUM']
        
        print(f"\n📁 فایل‌های بررسی شده: {len(payment_files)}")
        print(f"⚠️ مشکلات یافت شده: {len(all_issues)}")
        
        if high_severity:
            print("\n🔴 مشکلات با اولویت بالا (باید فوراً حل شوند):")
            for issue in high_severity[:5]:  # Show first 5
                file_name = os.path.basename(issue['file'])
                print(f"   • {file_name}:{issue['line']}")
                print(f"     نوع: {issue['type']}")
                print(f"     کد: {issue['code'][:80]}...")
        
        if medium_severity:
            print("\n🟡 مشکلات با اولویت متوسط:")
            for issue in medium_severity[:5]:  # Show first 5
                file_name = os.path.basename(issue['file'])
                print(f"   • {file_name}:{issue['line']}")
                print(f"     نوع: {issue['type']}")
        
        # Check database integrity
        print("\n💾 بررسی یکپارچگی دیتابیس:")
        
        # Check main database
        main_db = r"c:\Users\ramti\Documents\GitHub\Telegram_bot\database\data\daraei_academy.db"
        if os.path.exists(main_db):
            main_integrity = self.check_database_integrity(main_db)
            print("\n   دیتابیس اصلی:")
            print(f"   • پرداخت‌های تکمیل شده: {main_integrity['completed_payments']}")
            print(f"   • پرداخت‌های کریپتو تأیید شده: {main_integrity['completed_crypto']}")
            print(f"   • اشتراک‌های پولی: {main_integrity['paid_subscriptions']}")
            
            if main_integrity['orphaned_payments']:
                print(f"\n   ⚠️ پرداخت‌های بدون اشتراک: {len(main_integrity['orphaned_payments'])}")
                for payment in main_integrity['orphaned_payments'][:3]:
                    print(f"      • Payment ID: {payment['payment_id']}, User: {payment['user_id']}, Amount: {payment['amount']}")
        
        # Check backup database
        backup_db = r"c:\Users\ramti\Documents\GitHub\Telegram_bot\database\data\TelegramBOT_backup\New folder\daraei_academy.db"
        if os.path.exists(backup_db):
            backup_integrity = self.check_database_integrity(backup_db)
            print("\n   دیتابیس بکاپ (سرور):")
            print(f"   • پرداخت‌های تکمیل شده: {backup_integrity['completed_payments']}")
            print(f"   • پرداخت‌های کریپتو تأیید شده: {backup_integrity['completed_crypto']}")
            print(f"   • اشتراک‌های پولی: {backup_integrity['paid_subscriptions']}")
            
            total_expected = backup_integrity['completed_payments'] + backup_integrity['completed_crypto']
            discrepancy = total_expected - backup_integrity['paid_subscriptions']
            
            if discrepancy > 0:
                print(f"\n   🔴 اختلاف: {discrepancy} پرداخت موفق بدون اشتراک!")
                print(f"      این پرداخت‌ها احتمالاً گزارش نشده‌اند")
        
        # Recommendations
        print("\n📝 توصیه‌ها:")
        
        if high_severity:
            print("\n1. اصلاح فوری موارد با اولویت بالا:")
            print("   • تمام موارد استفاده از DatabaseQueries.add_subscription")
            print("     باید به activate_or_extend_subscription تغییر کنند")
        
        print("\n2. اضافه کردن لاگ‌گیری دقیق:")
        print("   • لاگ هر پرداخت موفق")
        print("   • لاگ هر گزارش ارسال شده به کانال")
        print("   • لاگ هر خطا در ارسال گزارش")
        
        print("\n3. ایجاد Job بازیابی خودکار:")
        print("   • بررسی هر ساعت برای پرداخت‌های گزارش نشده")
        print("   • ارسال خودکار گزارش‌های از دست رفته")
        
        print("\n" + "="*80)
        
        return all_issues

def main():
    """Run comprehensive audit"""
    auditor = PaymentAuditSystem()
    issues = auditor.generate_report()
    
    # Save detailed report
    with open('payment_audit_report.txt', 'w', encoding='utf-8') as f:
        f.write("Payment System Audit Report\n")
        f.write(f"Generated: {datetime.now()}\n")
        f.write("="*80 + "\n\n")
        
        for issue in issues:
            f.write(f"File: {issue['file']}\n")
            f.write(f"Line: {issue['line']}\n")
            f.write(f"Type: {issue['type']}\n")
            f.write(f"Severity: {issue['severity']}\n")
            f.write(f"Code: {issue['code']}\n")
            f.write("-"*40 + "\n")
    
    if issues:
        print(f"\n💾 گزارش کامل در payment_audit_report.txt ذخیره شد")

if __name__ == "__main__":
    main()
