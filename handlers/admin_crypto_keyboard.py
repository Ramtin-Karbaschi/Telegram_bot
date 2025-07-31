"""
🔧 Admin Crypto Payment Keyboard System
=====================================

Interactive keyboard-based admin panel for crypto payment management.
No commands required - all features accessible via keyboard buttons.
"""

import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode

from utils.admin_utils import admin_required
from services.enhanced_crypto_service import EnhancedCryptoService
from services.comprehensive_payment_system import get_payment_system

logger = logging.getLogger(__name__)

# Conversation states
MAIN_MENU, TX_VERIFICATION, SECURITY_MENU, REPORTS_MENU, MANUAL_TX_INPUT = range(5)

class AdminCryptoKeyboard:
    """Admin keyboard interface for crypto payment management"""
    
    @staticmethod
    def get_main_keyboard():
        """Get the main admin keyboard"""
        keyboard = [
            [KeyboardButton("🏥 وضعیت سیستم"), KeyboardButton("📊 آمار پرداخت‌ها")],
            [KeyboardButton("🔒 امنیت سیستم"), KeyboardButton("📈 گزارش‌ها")],
            [KeyboardButton("💰 اطلاعات کیف پول"), KeyboardButton("🔍 تست TX دستی")],
            [KeyboardButton("🚫 خروج از پنل ادمین")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    @staticmethod
    def get_reports_keyboard():
        """Get reports submenu keyboard"""
        keyboard = [
            [KeyboardButton("📊 گزارش 24 ساعت"), KeyboardButton("📈 گزارش هفتگی")],
            [KeyboardButton("📋 گزارش ماهانه"), KeyboardButton("🔄 گزارش کامل")],
            [KeyboardButton("🔙 بازگشت به منوی اصلی")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    @staticmethod
    def get_security_keyboard():
        """Get security submenu keyboard"""
        keyboard = [
            [KeyboardButton("🛡️ وضعیت امنیتی"), KeyboardButton("⚠️ آدرس‌های مشکوک")],
            [KeyboardButton("📊 آمار امنیت"), KeyboardButton("🔒 تنظیمات امنیت")],
            [KeyboardButton("🔙 بازگشت به منوی اصلی")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

    @staticmethod
    @admin_required
    async def start_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the admin panel"""
        
        user = update.effective_user
        logger.info(f"👑 Admin {user.id} ({user.first_name}) started crypto admin panel")
        
        # Mark conversation active so admin menu handler ignores further messages
        context.user_data['crypto_active'] = True

        await update.message.reply_text(
            "👑 **پنل مدیریت کریپتو** 👑\n\n"
            "به پنل مدیریت سیستم پرداخت USDT خوش آمدید!\n\n"
            "🔧 **امکانات در دسترس:**\n"
            "• نظارت بر وضعیت سیستم\n"
            "• مشاهده آمار و گزارش‌ها\n"
            "• مدیریت امنیت\n"
            "• تست دستی تراکنش‌ها\n\n"
            "برای شروع، یکی از گزینه‌های زیر را انتخاب کنید:",
            reply_markup=AdminCryptoKeyboard.get_main_keyboard(),
            parse_mode=ParseMode.MARKDOWN
        )
        
        return MAIN_MENU

    @staticmethod
    @admin_required
    async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle main menu selections"""
        
        text = update.message.text
        
        if text == "🏥 وضعیت سیستم":
            return await AdminCryptoKeyboard.show_system_health(update, context)
            
        elif text == "📊 آمار پرداخت‌ها":
            return await AdminCryptoKeyboard.show_payment_stats(update, context)
            
        elif text == "🔒 امنیت سیستم":
            await update.message.reply_text(
                "🔒 **منوی امنیت سیستم**\n\n"
                "یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=AdminCryptoKeyboard.get_security_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
            return SECURITY_MENU
            
        elif text == "📈 گزارش‌ها":
            await update.message.reply_text(
                "📈 **منوی گزارش‌ها**\n\n"
                "یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=AdminCryptoKeyboard.get_reports_keyboard(),
                parse_mode=ParseMode.MARKDOWN
            )
            return REPORTS_MENU
            
        elif text == "💰 اطلاعات کیف پول":
            return await AdminCryptoKeyboard.show_wallet_info(update, context)
            
        elif text == "🔍 تست TX دستی":
            await update.message.reply_text(
                "🔍 **تست تراکنش دستی**\n\n"
                "لطفاً TX Hash مورد نظر خود را ارسال کنید:\n\n"
                "📝 **نکات مهم:**\n"
                "• TX Hash باید 64 کاراکتر باشد\n"
                "• فقط تراکنش‌های TRON TRC20 پشتیبانی می‌شوند\n"
                "• برای لغو از دکمه لغو استفاده کنید\n\n"
                "💡 **مثال TX Hash:**\n"
                "`abc123...def789`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=ReplyKeyboardMarkup([
                    [KeyboardButton("❌ لغو و بازگشت")]
                ], resize_keyboard=True)
            )
            return MANUAL_TX_INPUT
            
        elif text == "🚫 خروج از پنل ادمین":
            # Clear active flag
            context.user_data.pop('crypto_active', None)

            await update.message.reply_text(
                "👋 از پنل ادمین خارج شدید.\n\n"
                "برای بازگشت مجدد از دستور /admin_crypto استفاده کنید.",
                reply_markup=None
            )
            return ConversationHandler.END
            
        else:
            await update.message.reply_text(
                "❌ گزینه نامعتبر! لطفاً از دکمه‌های ارائه شده استفاده کنید.",
                reply_markup=AdminCryptoKeyboard.get_main_keyboard()
            )
            return MAIN_MENU

    @staticmethod
    async def show_system_health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show system health status"""
        
        await update.message.reply_text("🔄 در حال بررسی وضعیت سیستم...")
        
        try:
            health = await EnhancedCryptoService.health_check()
            
            status_emoji = "✅" if health.get('status') == 'healthy' else "❌"
            tronpy_emoji = "✅" if health.get('tronpy_connected') else "❌"
            
            message = f"""
🏥 **وضعیت سیستم پرداخت USDT**

{status_emoji} **وضعیت کلی:** {health.get('status', 'نامشخص')}

💰 **اطلاعات کیف پول:**
• آدرس: `{health.get('wallet_address', 'N/A')}`
• موجودی: {health.get('wallet_balance', 0):.6f} USDT

🔗 **اتصالات:**
{tronpy_emoji} TronPy: {'متصل' if health.get('tronpy_connected') else 'قطع'}

⏰ **زمان بررسی:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🔄 **آخرین بروزرسانی:** همین الان
            """
            
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_main_keyboard()
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ خطا در دریافت وضعیت سیستم:\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_main_keyboard()
            )
        
        return MAIN_MENU

    @staticmethod
    async def show_payment_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show payment statistics"""
        
        await update.message.reply_text("📊 در حال جمع‌آوری آمار...")
        
        try:
            stats = await EnhancedCryptoService.get_payment_statistics(7)
            
            if 'error' not in stats:
                message = f"""
📊 **آمار پرداخت‌ها (7 روز گذشته)**

📈 **آمار کلی:**
• تعداد کل: {stats.get('total_payments', 0)}
• نرخ موفقیت: {stats.get('success_rate', 0):.1f}%
• حجم کل: {stats.get('total_volume_usdt', 0):.2f} USDT

✅ **پرداخت‌های موفق:**
• تعداد: {stats.get('successful_payments', 0)}
• حجم: {stats.get('successful_volume_usdt', 0):.2f} USDT

❌ **پرداخت‌های ناموفق:**
• تعداد: {stats.get('failed_payments', 0)}
• درصد: {stats.get('failure_rate', 0):.1f}%

💰 **میانگین تراکنش:** {stats.get('average_payment_usdt', 0):.2f} USDT

⏰ **زمان تولید:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """
            else:
                message = f"❌ خطا در دریافت آمار:\n`{stats['error']}`"
                
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_main_keyboard()
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ خطا در تولید آمار:\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_main_keyboard()
            )
        
        return MAIN_MENU

    @staticmethod
    async def show_wallet_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show wallet information"""
        
        await update.message.reply_text("💰 در حال دریافت اطلاعات کیف پول...")
        
        try:
            payment_system = get_payment_system()
            wallet_address = payment_system.wallet_address
            
            # Get wallet balance
            try:
                balance = await payment_system.get_wallet_balance()
                balance_text = f"{balance:.6f} USDT"
                balance_emoji = "💰" if balance > 0 else "⚠️"
            except Exception:
                balance_text = "نامشخص (خطا در اتصال)"
                balance_emoji = "❌"
            
            message = f"""
💰 **اطلاعات کیف پول USDT**

📍 **آدرس کیف پول:**
`{wallet_address}`

{balance_emoji} **موجودی فعلی:**
{balance_text}

🔗 **شبکه:** TRON (TRC20)
💎 **توکن:** USDT

🔍 **مشاهده در مرورگر بلاک‌چین:**
[TronScan](https://tronscan.org/#/address/{wallet_address})

⏰ **زمان بررسی:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📝 **نکته:** این آدرس برای دریافت پرداخت‌های USDT TRC20 استفاده می‌شود.
            """
            
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_main_keyboard(),
                disable_web_page_preview=True
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ خطا در دریافت اطلاعات کیف پول:\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_main_keyboard()
            )
        
        return MAIN_MENU

    @staticmethod
    @admin_required
    async def handle_manual_tx_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle manual TX hash input"""
        
        text = update.message.text.strip()
        
        if text == "❌ لغو و بازگشت":
            await update.message.reply_text(
                "✅ عملیات لغو شد.",
                reply_markup=AdminCryptoKeyboard.get_main_keyboard()
            )
            return MAIN_MENU
        
        # Validate TX hash format
        if len(text) != 64 or not all(c in '0123456789abcdefABCDEF' for c in text):
            await update.message.reply_text(
                "❌ **فرمت TX Hash نامعتبر!**\n\n"
                "TX Hash باید:\n"
                "• دقیقاً 64 کاراکتر باشد\n"
                "• فقط شامل اعداد و حروف a-f باشد\n\n"
                "لطفاً مجدداً تلاش کنید:",
                parse_mode=ParseMode.MARKDOWN
            )
            return MANUAL_TX_INPUT
        
        await update.message.reply_text(
            f"🔍 **در حال بررسی تراکنش...**\n\n"
            f"TX Hash: `{text}`\n\n"
            "لطفاً چند لحظه صبر کنید...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            payment_system = get_payment_system()
            
            # Verify transaction
            verification_result = await payment_system.verify_transaction_by_hash(
                text, 
                payment_id="manual-verification"  # Special ID for manual verification
            )
            
            if verification_result.get('success'):
                tx_data = verification_result.get('transaction_data', {})
                
                # Human-readable timestamp
                raw_ts = tx_data.get('timestamp')
                if raw_ts and isinstance(raw_ts, str):
                    from datetime import datetime
                    try:
                        display_ts = datetime.fromisoformat(raw_ts).strftime('%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        display_ts = raw_ts.replace('T', ' ')
                else:
                    display_ts = 'نامشخص'
                
                message = f"""
✅ **تراکنش معتبر تأیید شد!**

🔍 **اطلاعات تراکنش:**
• TX Hash: `{text}`
• مقدار: {tx_data.get('amount', 'نامشخص')} USDT
• فرستنده: `{tx_data.get('from_address', 'نامشخص')}`
• گیرنده: `{tx_data.get('to_address', 'نامشخص')}`
• تأییدات: {tx_data.get('confirmations', 'نامشخص')}
• وضعیت: {'تأیید شده' if tx_data.get('confirmed') else 'در انتظار تأیید'}

⏰ **زمان تراکنش:** {display_ts}

🔗 **مشاهده در TronScan:**
[کلیک کنید](https://tronscan.org/#/transaction/{text})
                """
                
            else:
                error_reason = verification_result.get('error', 'نامشخص')
                message = f"""
❌ **تراکنش نامعتبر یا یافت نشد!**

🔍 **اطلاعات بررسی:**
• TX Hash: `{text}`
• دلیل خطا: {error_reason}

💡 **دلایل احتمالی:**
• تراکنش هنوز تأیید نشده
• TX Hash اشتباه است
• تراکنش مربوط به USDT TRC20 نیست
• تراکنش به آدرس ما ارسال نشده

🔗 **بررسی دستی در TronScan:**
[کلیک کنید](https://tronscan.org/#/transaction/{text})
                """
            
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_main_keyboard(),
                disable_web_page_preview=True
            )
            
        except Exception as e:
            logger.error(f"Error in manual TX verification: {e}")
            await update.message.reply_text(
                f"❌ **خطا در بررسی تراکنش:**\n\n"
                f"`{str(e)}`\n\n"
                f"TX Hash: `{text}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_main_keyboard()
            )
        
        return MAIN_MENU

    @staticmethod
    @admin_required
    async def handle_security_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle security menu selections"""
        
        text = update.message.text
        
        if text == "🔙 بازگشت به منوی اصلی":
            await update.message.reply_text(
                "🔙 بازگشت به منوی اصلی",
                reply_markup=AdminCryptoKeyboard.get_main_keyboard()
            )
            return MAIN_MENU
            
        elif text == "🛡️ وضعیت امنیتی":
            return await AdminCryptoKeyboard.show_security_status(update, context)
            
        elif text == "📊 آمار امنیت":
            return await AdminCryptoKeyboard.show_security_stats(update, context)
            
        else:
            await update.message.reply_text(
                "❌ گزینه نامعتبر! لطفاً از دکمه‌های ارائه شده استفاده کنید.",
                reply_markup=AdminCryptoKeyboard.get_security_keyboard()
            )
            return SECURITY_MENU

    @staticmethod
    async def show_security_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show security status"""
        
        try:
            payment_system = get_payment_system()
            security_stats = payment_system.get_security_stats()
            
            message = f"""
🛡️ **وضعیت امنیت سیستم**

✅ **سیستم امنیتی فعال است**

📊 **آمار امنیت:**
• تراکنش‌های تأیید شده: {security_stats.get('verified_transactions', 0)}
• آدرس‌های مشکوک: {security_stats.get('suspicious_addresses', 0)}
• تشخیص تقلب: {'✅ فعال' if security_stats.get('fraud_detection_enabled') else '❌ غیرفعال'}

🔒 **تنظیمات امنیت:**
• حداقل تأییدات: {payment_system.min_confirmations}
• Rate Limiting: ✅ فعال
• Blacklist Checking: ✅ فعال

⏰ **آخرین بروزرسانی:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_security_keyboard()
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ خطا در دریافت وضعیت امنیت:\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_security_keyboard()
            )
        
        return SECURITY_MENU

    @staticmethod
    async def show_security_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show detailed security statistics"""
        
        try:
            payment_system = get_payment_system()
            security_stats = payment_system.get_security_stats()
            
            message = f"""
📊 **آمار تفصیلی امنیت**

🔍 **تراکنش‌های بررسی شده:**
• تعداد کل: {security_stats.get('verified_transactions', 0)}
• موفق: {security_stats.get('successful_verifications', 0)}
• رد شده: {security_stats.get('rejected_transactions', 0)}

⚠️ **تهدیدات شناسایی شده:**
• آدرس‌های مشکوک: {security_stats.get('suspicious_addresses', 0)}
• تلاش‌های تقلب: {security_stats.get('fraud_attempts', 0)}
• Rate Limit موارد: {security_stats.get('rate_limited_requests', 0)}

🛡️ **سیستم‌های حفاظت:**
• تشخیص تقلب: {'✅' if security_stats.get('fraud_detection_enabled') else '❌'}
• بررسی آدرس: {'✅' if security_stats.get('address_checking_enabled') else '❌'}
• Rate Limiting: {'✅' if security_stats.get('rate_limiting_enabled') else '❌'}

⏰ **زمان تولید:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_security_keyboard()
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ خطا در دریافت آمار امنیت:\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_security_keyboard()
            )
        
        return SECURITY_MENU

    @staticmethod
    @admin_required
    async def handle_reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle reports menu selections"""
        
        text = update.message.text
        
        if text == "🔙 بازگشت به منوی اصلی":
            await update.message.reply_text(
                "🔙 بازگشت به منوی اصلی",
                reply_markup=AdminCryptoKeyboard.get_main_keyboard()
            )
            return MAIN_MENU
            
        elif text == "📊 گزارش 24 ساعت":
            return await AdminCryptoKeyboard.generate_report(update, context, 1)
            
        elif text == "📈 گزارش هفتگی":
            return await AdminCryptoKeyboard.generate_report(update, context, 7)
            
        elif text == "📋 گزارش ماهانه":
            return await AdminCryptoKeyboard.generate_report(update, context, 30)
            
        elif text == "🔄 گزارش کامل":
            return await AdminCryptoKeyboard.generate_report(update, context, 365)
            
        else:
            await update.message.reply_text(
                "❌ گزینه نامعتبر! لطفاً از دکمه‌های ارائه شده استفاده کنید.",
                reply_markup=AdminCryptoKeyboard.get_reports_keyboard()
            )
            return REPORTS_MENU

    @staticmethod
    async def generate_report(update: Update, context: ContextTypes.DEFAULT_TYPE, days: int) -> int:
        """Generate payment report for specified days"""
        
        period_name = {
            1: "24 ساعته",
            7: "هفتگی", 
            30: "ماهانه",
            365: "کامل"
        }.get(days, f"{days} روزه")
        
        await update.message.reply_text(f"📊 در حال تولید گزارش {period_name}...")
        
        try:
            report = await EnhancedCryptoService.create_payment_report(days)
            
            if len(report) > 4000:  # Telegram message limit
                # Split long reports
                chunks = [report[i:i+4000] for i in range(0, len(report), 4000)]
                for i, chunk in enumerate(chunks):
                    await update.message.reply_text(
                        f"📄 **گزارش {period_name} - قسمت {i+1}**\n\n{chunk}",
                        parse_mode=ParseMode.MARKDOWN
                    )
            else:
                await update.message.reply_text(
                    f"📄 **گزارش {period_name}**\n\n{report}",
                    parse_mode=ParseMode.MARKDOWN
                )
            
            await update.message.reply_text(
                "✅ گزارش با موفقیت تولید شد.",
                reply_markup=AdminCryptoKeyboard.get_reports_keyboard()
            )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ خطا در تولید گزارش:\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=AdminCryptoKeyboard.get_reports_keyboard()
            )
        
        return REPORTS_MENU

    @staticmethod
    async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation"""
        await update.message.reply_text(
            "❌ عملیات لغو شد. پنل ادمین بسته شد.",
            reply_markup=None
        )
        return ConversationHandler.END


# Helper function to start crypto panel (used by admin menu callback)
async def start_crypto_panel_from_admin(update, context):
    """Start crypto panel when called from admin menu"""
    return await AdminCryptoKeyboard.start_admin_panel(update, context)

# Create conversation handler
admin_crypto_conversation = ConversationHandler(
    entry_points=[
        # Entry points for crypto keyboard panel
        MessageHandler(filters.Regex("^/start_crypto_panel$") & filters.TEXT, AdminCryptoKeyboard.start_admin_panel),
        MessageHandler(filters.Regex("^🏥 وضعیت سیستم$") & filters.TEXT, AdminCryptoKeyboard.start_admin_panel),
        MessageHandler(filters.Regex("^📊 آمار پرداخت‌ها$") & filters.TEXT, AdminCryptoKeyboard.start_admin_panel),
        MessageHandler(filters.Regex("^🔒 امنیت سیستم$") & filters.TEXT, AdminCryptoKeyboard.start_admin_panel),
        MessageHandler(filters.Regex("^📈 گزارش‌ها$") & filters.TEXT, AdminCryptoKeyboard.start_admin_panel),
        MessageHandler(filters.Regex("^💰 اطلاعات کیف پول$") & filters.TEXT, AdminCryptoKeyboard.start_admin_panel),
        MessageHandler(filters.Regex("^🔍 تست TX دستی$") & filters.TEXT, AdminCryptoKeyboard.start_admin_panel)
    ],
    states={
        MAIN_MENU: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, AdminCryptoKeyboard.handle_main_menu)
        ],
        SECURITY_MENU: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, AdminCryptoKeyboard.handle_security_menu)
        ],
        REPORTS_MENU: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, AdminCryptoKeyboard.handle_reports_menu)
        ],
        MANUAL_TX_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, AdminCryptoKeyboard.handle_manual_tx_input)
        ]
    },
    fallbacks=[
        MessageHandler(filters.Regex("^/cancel$"), AdminCryptoKeyboard.cancel_conversation)
    ],
    per_message=False
)

# Export the conversation handler
admin_crypto_keyboard_handler = admin_crypto_conversation
