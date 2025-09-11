"""
سیستم بازیابی گزارش‌های فروش از دست رفته
این اسکریپت تمام تراکنش‌های موفق را بررسی می‌کند و گزارش‌های از دست رفته را ارسال می‌کند
"""

import asyncio
import sqlite3
from datetime import datetime, timedelta
import jdatetime
from telegram import Bot
import config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SalesReportRecovery:
    def __init__(self, db_path=None):
        self.db_path = db_path or r"c:\Users\ramti\Documents\GitHub\Telegram_bot\database\data\daraei_academy.db"
        self.bot = None
        self.channel_id = config.SALE_CHANNEL_ID
        
    async def initialize_bot(self):
        """Initialize Telegram bot"""
        self.bot = Bot(token=config.MAIN_BOT_TOKEN)
        await self.bot.initialize()
        
    async def shutdown_bot(self):
        """Shutdown bot properly"""
        if self.bot:
            await self.bot.shutdown()
    
    def get_unreported_subscriptions(self, days_back=30):
        """Get all subscriptions that might not have been reported"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get subscriptions from last N days
        date_threshold = datetime.now() - timedelta(days=days_back)
        
        query = """
        SELECT 
            s.id as subscription_id,
            s.user_id,
            s.plan_id,
            s.payment_id,
            s.amount_paid,
            s.payment_method,
            s.created_at,
            p.name as plan_name,
            u.username,
            u.full_name,
            u.phone
        FROM subscriptions s
        LEFT JOIN plans p ON s.plan_id = p.id
        LEFT JOIN users u ON s.user_id = u.user_id
        WHERE s.payment_method IN ('zarinpal', 'crypto')
        AND s.created_at >= ?
        ORDER BY s.created_at DESC
        """
        
        cursor.execute(query, (date_threshold.strftime("%Y-%m-%d"),))
        results = cursor.fetchall()
        conn.close()
        
        return results
    
    def get_payment_details(self, payment_id):
        """Get payment details for additional info"""
        if not payment_id:
            return None
            
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check regular payments
        cursor.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,))
        payment = cursor.fetchone()
        
        if not payment:
            # Check crypto payments
            cursor.execute("SELECT * FROM crypto_payments WHERE payment_id = ?", (payment_id,))
            payment = cursor.fetchone()
        
        conn.close()
        return dict(payment) if payment else None
    
    async def send_recovery_report(self, subscription):
        """Send a recovery sales report for a missed subscription"""
        try:
            # Prepare report message
            username = subscription['username']
            user_display = f"@{username}" if username else f"ID:{subscription['user_id']}"
            full_name = subscription['full_name'] or 'نامشخص'
            plan_name = subscription['plan_name'] or f"پلن #{subscription['plan_id']}"
            payment_method = subscription['payment_method']
            amount = subscription['amount_paid']
            
            # Format date
            created_at = subscription['created_at']
            try:
                dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                persian_date = jdatetime.datetime.fromgregorian(datetime=dt).strftime("%Y/%m/%d %H:%M")
            except:
                persian_date = created_at
            
            # Determine payment type and format
            if payment_method == 'crypto':
                purchase_tag = "#خرید_کریپتو"
                amount_formatted = f"{amount:.2f} USDT"
            elif payment_method == 'zarinpal':
                purchase_tag = "#خرید_نقدی"
                amount_formatted = f"{int(amount):,} ریال"
            else:
                purchase_tag = "#خرید_بازیابی"
                amount_formatted = f"{amount}"
            
            # Build message
            message_parts = [
                f"🔄 {purchase_tag} (بازیابی)",
                "━━━━━━━━━━━━━━━",
                f"📅 تاریخ: {persian_date}",
                f"👤 کاربر: {user_display}",
                f"👤 نام کامل: {full_name}",
                f"📦 محصول: {plan_name}",
                f"💰 مبلغ: {amount_formatted}",
                f"🆔 Subscription ID: {subscription['subscription_id']}",
                "━━━━━━━━━━━━━━━",
                "⚠️ این گزارش به صورت بازیابی ارسال شده است"
            ]
            
            # Send to channel
            await self.bot.send_message(
                chat_id=self.channel_id,
                text="\n".join(message_parts)
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send recovery report for subscription {subscription['subscription_id']}: {e}")
            return False
    
    async def recover_all(self, days_back=30, dry_run=False):
        """Recover all missed sales reports"""
        print("\n" + "="*70)
        print("🔄 بازیابی گزارش‌های فروش از دست رفته")
        print("="*70)
        
        # Initialize bot
        await self.initialize_bot()
        
        # Get unreported subscriptions
        subscriptions = self.get_unreported_subscriptions(days_back)
        
        print(f"\n📊 تعداد کل اشتراک‌های {days_back} روز اخیر: {len(subscriptions)}")
        
        if dry_run:
            print("\n⚠️ حالت Dry Run - فقط نمایش، ارسال نمی‌شود")
        
        # Count by payment method
        zarinpal_count = sum(1 for s in subscriptions if s['payment_method'] == 'zarinpal')
        crypto_count = sum(1 for s in subscriptions if s['payment_method'] == 'crypto')
        
        print(f"   • پرداخت زرین‌پال: {zarinpal_count}")
        print(f"   • پرداخت کریپتو: {crypto_count}")
        
        if not dry_run:
            confirm = input("\n❓ آیا می‌خواهید گزارش‌ها ارسال شوند؟ (yes/no): ")
            if confirm.lower() != 'yes':
                print("❌ لغو شد")
                await self.shutdown_bot()
                return
        
        # Process each subscription
        success_count = 0
        failed_count = 0
        
        for i, subscription in enumerate(subscriptions, 1):
            print(f"\n[{i}/{len(subscriptions)}] Processing subscription {subscription['subscription_id']}...")
            
            if dry_run:
                print(f"   • User: {subscription['user_id']}")
                print(f"   • Plan: {subscription['plan_name']}")
                print(f"   • Amount: {subscription['amount_paid']}")
                print(f"   • Method: {subscription['payment_method']}")
                print(f"   • Date: {subscription['created_at']}")
            else:
                success = await self.send_recovery_report(subscription)
                if success:
                    success_count += 1
                    print(f"   ✅ گزارش ارسال شد")
                else:
                    failed_count += 1
                    print(f"   ❌ خطا در ارسال")
                
                # Add delay to avoid rate limiting
                await asyncio.sleep(0.5)
        
        # Summary
        print("\n" + "="*70)
        print("📊 خلاصه عملیات:")
        print(f"   • کل اشتراک‌ها: {len(subscriptions)}")
        if not dry_run:
            print(f"   • موفق: {success_count}")
            print(f"   • ناموفق: {failed_count}")
        print("="*70)
        
        await self.shutdown_bot()

async def main():
    """Main function"""
    import sys
    
    # Check command line arguments
    dry_run = '--dry-run' in sys.argv
    days_back = 30
    
    for arg in sys.argv:
        if arg.startswith('--days='):
            try:
                days_back = int(arg.split('=')[1])
            except:
                pass
    
    recovery = SalesReportRecovery()
    await recovery.recover_all(days_back=days_back, dry_run=dry_run)

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════╗
║         سیستم بازیابی گزارش‌های فروش از دست رفته          ║
╚══════════════════════════════════════════════════════════════╝

استفاده:
  python recover_missed_sales_reports.py [options]

Options:
  --dry-run        فقط نمایش، بدون ارسال واقعی
  --days=N         بررسی N روز گذشته (پیش‌فرض: 30)

مثال:
  python recover_missed_sales_reports.py --dry-run --days=7
""")
    
    asyncio.run(main())
