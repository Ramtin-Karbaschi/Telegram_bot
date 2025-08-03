# handlers/admin/admin_payment_verification.py

import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from database.models import Database
import config

logger = logging.getLogger(__name__)

# States for admin verification conversation
VERIFY_PENDING, ADMIN_ACTION = range(2)

class AdminPaymentVerifier:
    """سیستم تایید دستی/خودکار پرداخت‌های تتری توسط ادمین برای حل مشکل Toobit و سایر موارد"""
    
    @staticmethod
    async def show_pending_payments_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش پرداخت‌های در انتظار تایید"""
        query = update.callback_query
        if query:
            await query.answer()
        
        db = Database()
        # دریافت پرداخت‌های pending و expired که ممکن است نیاز به تایید دستی داشته باشند
        pending_payments = db.get_pending_crypto_payments()
        
        if not pending_payments:
            text = "هیچ پرداخت تتری در انتظار بررسی نیست."
            keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]]
        else:
            text = f"🔍 **پرداخت‌های در انتظار تایید** ({len(pending_payments)} مورد)\n\n"
            keyboard = []
            
            for payment in pending_payments[:10]:  # محدود به 10 مورد جدید
                user_id = payment.get('user_id', 'N/A')
                amount = payment.get('usdt_amount_requested', 0)
                payment_id = payment.get('payment_id')
                created_at = payment.get('created_at', '')
                status = payment.get('status', 'pending')
                
                # محاسبه مدت زمان انتظار
                try:
                    created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    wait_time = datetime.now() - created_time.replace(tzinfo=None)
                    wait_hours = int(wait_time.total_seconds() / 3600)
                    time_info = f"({wait_hours}h ago)" if wait_hours > 0 else "(< 1h ago)"
                except:
                    time_info = ""
                
                button_text = f"💰 {amount:.2f} USDT - User: {user_id} {time_info}"
                keyboard.append([
                    InlineKeyboardButton(button_text, callback_data=f"verify_payment_{payment_id}")
                ])
            
            keyboard.append([InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_crypto_verify_menu")])
            keyboard.append([InlineKeyboardButton("⚙️ تنظیمات خودکار", callback_data="admin_auto_verify_settings")])
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])
        
        markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    
    @staticmethod
    async def show_payment_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش جزئیات یک پرداخت برای تایید/رد ادمین"""
        query = update.callback_query
        await query.answer()
        
        payment_id = query.data.split("_")[-1]
        
        db = Database()
        payment = db.get_payment_by_id(payment_id)
        
        if not payment:
            await query.edit_message_text("پرداخت یافت نشد.", 
                                        reply_markup=InlineKeyboardMarkup([[
                                            InlineKeyboardButton("🔙 بازگشت", callback_data="admin_crypto_verify_menu")
                                        ]]))
            return
        
        user_id = payment.get('user_id')
        amount = payment.get('usdt_amount_requested', 0)
        wallet = payment.get('wallet_address', config.CRYPTO_WALLET_ADDRESS)
        created_at = payment.get('created_at', '')
        status = payment.get('status', 'pending')
        tx_hash = payment.get('transaction_id', 'ندارد')
        
        # بررسی خودکار tx hash اگر وجود دارد
        auto_verify_result = ""
        if tx_hash and tx_hash != 'ندارد':
            # Use new verification wrapper (async)
            from services.comprehensive_payment_system import verify_payment_by_tx_hash
            try:
                verified, _verified_tx, actual_amount, _meta = await verify_payment_by_tx_hash(tx_hash, payment)
            except Exception as verify_exc:
                logger.error("Error during on-chain verification for %s: %s", payment_id, verify_exc, exc_info=True)
                verified, actual_amount = False, 0.0
            if verified:
                auto_verify_result = f"\n✅ **تایید خودکار:** تراکنش معتبر ({actual_amount:.6f} USDT)"
            else:
                auto_verify_result = f"\n❌ **تایید خودکار:** تراکنش نامعتبر یا ناکافی"
        
        # دریافت اطلاعات کاربر
        user_info = db.get_user_by_telegram_id(user_id)
        username = user_info.get('username', 'ندارد') if user_info else 'ندارد'
        
        text = f"""
🔍 **جزئیات پرداخت تتری**

👤 **کاربر:** {user_id} (@{username})
💰 **مبلغ:** {amount:.6f} USDT
📅 **تاریخ:** {created_at[:16]}
🏦 **آدرس کیف پول:** `{wallet}`
🔗 **TX Hash:** `{tx_hash}`
📊 **وضعیت:** {status}
{auto_verify_result}

**گزینه‌های ادمین:**
"""
        
        keyboard = [
            [InlineKeyboardButton("✅ تایید دستی", callback_data=f"approve_payment_{payment_id}")],
            [InlineKeyboardButton("❌ رد پرداخت", callback_data=f"reject_payment_{payment_id}")],
            [InlineKeyboardButton("🔄 بررسی مجدد", callback_data=f"recheck_payment_{payment_id}")],
            [InlineKeyboardButton("💬 پیام به کاربر", callback_data=f"message_user_{payment_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_crypto_verify_menu")]
        ]
        
        await query.edit_message_text(
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode="Markdown"
        )
    
    @staticmethod
    async def approve_payment_manually(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تایید دستی پرداخت توسط ادمین"""
        query = update.callback_query
        await query.answer()
        
        payment_id = query.data.split("_")[-1]
        
        db = Database()
        payment = db.get_payment_by_id(payment_id)
        
        if not payment:
            await query.edit_message_text("پرداخت یافت نشد.")
            return
        
        # به‌روزرسانی پرداخت به عنوان تایید شده
        tx_hash = payment.get('transaction_id') or f"ADMIN_APPROVED_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        amount = payment.get('usdt_amount_requested', 0)
        
        success = db.update_crypto_payment_on_success(payment_id, tx_hash, amount)
        
        if success:
            # فعال‌سازی اشتراک کاربر
            user_id = payment.get('user_id')
            plan_id = payment.get('plan_id')
            
            # TODO: فراخوانی تابع activate_subscription
            from handlers.payment.payment_handlers import activate_or_extend_subscription
            try:
                await activate_or_extend_subscription(user_id, plan_id, payment_id)
                
                # ارسال پیام به کاربر
                from telegram import Bot
                bot = context.bot
                await bot.send_message(
                    chat_id=user_id,
                    text=f"✅ پرداخت شما به مبلغ {amount:.2f} USDT توسط ادمین تایید شد.\nاشتراک شما فعال گردید.",
                    parse_mode="Markdown"
                )
                
                await query.edit_message_text(
                    f"✅ پرداخت {payment_id} تایید شد و اشتراک کاربر {user_id} فعال گردید.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 بازگشت", callback_data="admin_crypto_verify_menu")
                    ]])
                )
                
            except Exception as e:
                logger.error(f"خطا در فعال‌سازی اشتراک: {e}")
                await query.edit_message_text(
                    f"⚠️ پرداخت تایید شد اما خطا در فعال‌سازی اشتراک: {e}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 بازگشت", callback_data="admin_crypto_verify_menu")
                    ]])
                )
        else:
            await query.edit_message_text(
                "❌ خطا در به‌روزرسانی پرداخت.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت", callback_data="admin_crypto_verify_menu")
                ]])
            )
    
    @staticmethod
    async def auto_verify_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنظیمات تایید خودکار"""
        query = update.callback_query
        await query.answer()
        
        # خواندن تنظیمات فعلی
        db = Database()
        auto_verify_enabled = db.get_setting("auto_crypto_verify", "0") == "1"
        tolerance_percent = float(db.get_setting("crypto_tolerance_percent", "5.0"))
        max_auto_amount = float(db.get_setting("max_auto_verify_usdt", "100.0"))
        
        text = f"""
⚙️ **تنظیمات تایید خودکار**

🤖 **تایید خودکار:** {'✅ فعال' if auto_verify_enabled else '❌ غیرفعال'}
📊 **حد تحمل:** {tolerance_percent}% (پرداخت‌های بیشتر از مبلغ درخواستی)
💰 **حداکثر مبلغ خودکار:** {max_auto_amount} USDT

**توضیحات:**
• تایید خودکار برای پرداخت‌هایی که مبلغ دقیق یا تا {tolerance_percent}% بیشتر پرداخت شده
• فقط برای مبالغ کمتر از {max_auto_amount} USDT
• مابقی نیاز به تایید دستی ادمین دارند
"""
        
        keyboard = [
            [InlineKeyboardButton(
                "🤖 تغییر تایید خودکار" + (" (غیرفعال)" if auto_verify_enabled else " (فعال)"), 
                callback_data="toggle_auto_verify"
            )],
            [InlineKeyboardButton("📊 تنظیم حد تحمل", callback_data="set_tolerance")],
            [InlineKeyboardButton("💰 تنظیم حداکثر مبلغ", callback_data="set_max_amount")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_crypto_verify_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

def get_handlers():
    """بازگرداندن handlers مربوط به تایید پرداخت‌های ادمین"""
    from telegram.ext import CallbackQueryHandler
    
    return [
        CallbackQueryHandler(
            AdminPaymentVerifier.show_pending_payments_menu, 
            pattern="^admin_crypto_verify_menu$"
        ),
        CallbackQueryHandler(
            AdminPaymentVerifier.show_payment_details, 
            pattern="^verify_payment_"
        ),
        CallbackQueryHandler(
            AdminPaymentVerifier.approve_payment_manually, 
            pattern="^approve_payment_"
        ),
        CallbackQueryHandler(
            AdminPaymentVerifier.auto_verify_settings, 
            pattern="^admin_auto_verify_settings$"
        ),
    ]
