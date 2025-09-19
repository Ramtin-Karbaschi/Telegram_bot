"""
Admin SpotPlayer Handler
Manual activation and management for SpotPlayer purchases
"""

import logging
from datetime import datetime
from typing import Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove
)
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

from database.queries import DatabaseQueries
from handlers.spotplayer.spotplayer_handler_pro import SpotPlayerHandlerPro as SpotPlayerHandler

logger = logging.getLogger(__name__)

# Conversation states
SELECT_USER = 1
ENTER_TRACKING = 2
CONFIRM_MANUAL = 3

class AdminSpotPlayerHandler:
    """Admin handler for manual SpotPlayer activation"""
    
    def __init__(self, db_queries: DatabaseQueries, config):
        """Initialize the handler"""
        self.db = db_queries
        self.config = config
        
        # Initialize the main SpotPlayer handler
        self.spotplayer_handler = SpotPlayerHandler(db_queries)
        
    async def show_spotplayer_menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """Show SpotPlayer admin menu"""
        query = update.callback_query
        if query:
            await query.answer()
        
        # Get statistics
        stats = self._get_spotplayer_stats()
        
        message = (
            "🎬 **مدیریت SpotPlayer**\n\n"
            f"📊 **آمار:**\n"
            f"• کل خریدها: {stats['total_purchases']}\n"
            f"• خریدهای امروز: {stats['today_purchases']}\n"
            f"• درآمد کل: {self._format_price(stats['total_revenue'])} تومان\n\n"
            "از گزینه‌های زیر انتخاب کنید:"
        )
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "➕ فعال‌سازی دستی",
                    callback_data="admin_spotplayer_manual"
                )
            ],
            [
                InlineKeyboardButton(
                    "📋 لیست خریدها",
                    callback_data="admin_spotplayer_list"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔍 جستجو با کد پیگیری",
                    callback_data="admin_spotplayer_search"
                )
            ],
            [
                InlineKeyboardButton(
                    "📊 گزارش مفصل",
                    callback_data="admin_spotplayer_report"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 بازگشت",
                    callback_data="admin_main_menu"
                )
            ]
        ]
        
        if query:
            await query.edit_message_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    async def start_manual_activation(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Start manual activation process"""
        query = update.callback_query
        await query.answer()
        
        message = (
            "🔧 **فعال‌سازی دستی SpotPlayer**\n\n"
            "لطفاً شناسه کاربری (User ID) یا یوزرنیم کاربر را ارسال کنید:\n\n"
            "مثال:\n"
            "• User ID: `123456789`\n"
            "• Username: `@username`"
        )
        
        keyboard = [
            [KeyboardButton("❌ انصراف")]
        ]
        
        await query.edit_message_text(message, parse_mode=ParseMode.MARKDOWN)
        await query.message.reply_text(
            "شناسه یا یوزرنیم را وارد کنید:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
        return SELECT_USER
    
    async def process_user_selection(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Process user selection for manual activation"""
        
        text = update.message.text.strip()
        
        if text == "❌ انصراف":
            await update.message.reply_text(
                "❌ عملیات لغو شد.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Find user
        user_info = None
        
        if text.startswith('@'):
            # Search by username
            username = text[1:]
            user_info = self.db.get_user_by_username(username)
        elif text.isdigit():
            # Search by telegram ID
            telegram_id = int(text)
            user_info = self.db.get_user_by_telegram_id(telegram_id)
        else:
            # Search by name
            users = self.db.search_users_by_name(text)
            if users and len(users) == 1:
                user_info = users[0]
            elif users and len(users) > 1:
                # Multiple users found
                message = "⚠️ چند کاربر با این نام یافت شد:\n\n"
                for user in users[:5]:
                    message += f"• {user['full_name']} (ID: {user['user_id']})\n"
                message += "\nلطفاً دقیق‌تر جستجو کنید."
                
                await update.message.reply_text(message)
                return SELECT_USER
        
        if not user_info:
            await update.message.reply_text(
                "❌ کاربر یافت نشد.\n"
                "لطفاً دوباره تلاش کنید یا روی «انصراف» کلیک کنید."
            )
            return SELECT_USER
        
        # Store user info
        context.user_data['manual_user_id'] = user_info.get('user_id')
        context.user_data['manual_user_name'] = user_info.get('full_name', 'نامشخص')
        context.user_data['manual_telegram_id'] = user_info.get('telegram_id')
        
        # Ask for tracking code
        message = (
            f"✅ کاربر یافت شد:\n"
            f"👤 نام: {user_info.get('full_name', 'نامشخص')}\n"
            f"🆔 ID: {user_info.get('user_id')}\n\n"
            "حالا کد پیگیری زرین‌پال را وارد کنید:\n"
            "(برای فعال‌سازی بدون کد پیگیری، عبارت MANUAL را وارد کنید)"
        )
        
        await update.message.reply_text(message)
        return ENTER_TRACKING
    
    async def process_tracking_code(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Process tracking code for manual activation"""
        
        text = update.message.text.strip()
        
        if text == "❌ انصراف":
            await update.message.reply_text(
                "❌ عملیات لغو شد.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Store tracking code
        context.user_data['manual_tracking'] = text
        
        # If MANUAL, skip verification
        if text.upper() == 'MANUAL':
            context.user_data['manual_verified'] = False
            context.user_data['manual_amount'] = self.spotplayer_handler.SPOTPLAYER_CONFIG['price'] // 10
        else:
            # Try to verify with Zarinpal
            verification = await self.spotplayer_handler._verify_zarinpal_payment(text)
            
            if verification['success']:
                context.user_data['manual_verified'] = True
                context.user_data['manual_amount'] = verification['data']['amount']
                context.user_data['manual_payment_data'] = verification['data']
            else:
                # Verification failed, ask for confirmation
                context.user_data['manual_verified'] = False
                context.user_data['manual_amount'] = self.spotplayer_handler.SPOTPLAYER_CONFIG['price'] // 10
        
        # Show confirmation
        user_name = context.user_data.get('manual_user_name')
        amount = context.user_data.get('manual_amount')
        verified = context.user_data.get('manual_verified')
        
        message = (
            "📋 **تأیید فعال‌سازی دستی**\n\n"
            f"👤 کاربر: {user_name}\n"
            f"💰 مبلغ: {self._format_price(amount)} تومان\n"
            f"📝 کد پیگیری: `{text}`\n"
            f"✅ وضعیت تأیید: {'تأیید شده' if verified else 'تأیید نشده (دستی)'}\n\n"
            "**آیا مایل به فعال‌سازی هستید؟**"
        )
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ فعال‌سازی", callback_data="confirm_manual_spot"),
                InlineKeyboardButton("❌ انصراف", callback_data="cancel_manual_spot")
            ]
        ])
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
        return CONFIRM_MANUAL
    
    async def confirm_manual_activation(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Confirm and execute manual activation"""
        
        query = update.callback_query
        await query.answer()
        
        if query.data == "cancel_manual_spot":
            await query.edit_message_text("❌ عملیات لغو شد.")
            await query.message.reply_text(
                "بازگشت به منوی اصلی",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Show processing
        await query.edit_message_text("⏳ در حال فعال‌سازی...")
        
        # Get data
        user_id = context.user_data.get('manual_user_id')
        telegram_id = context.user_data.get('manual_telegram_id')
        tracking_code = context.user_data.get('manual_tracking')
        amount = context.user_data.get('manual_amount')
        payment_data = context.user_data.get('manual_payment_data', {})
        
        # Generate SpotPlayer key
        spotplayer_key = await self.spotplayer_handler._generate_spotplayer_key(
            user_id, tracking_code
        )
        
        if not spotplayer_key:
            await query.edit_message_text(
                "❌ خطا در تولید کلید دسترسی."
            )
            return ConversationHandler.END
        
        # Save to database
        self.spotplayer_handler._save_spotplayer_purchase(
            user_id=user_id,
            tracking_code=tracking_code,
            amount=amount,
            spotplayer_key=spotplayer_key,
            payment_data=payment_data
        )
        
        # Activate subscription
        from database.subscription_manager import SubscriptionManager
        
        plan_id = self.spotplayer_handler._get_or_create_spotplayer_plan()
        
        subscription_result = SubscriptionManager.create_or_extend_subscription(
            user_id=user_id,
            plan_id=plan_id,
            payment_method='admin_manual_spotplayer',
            amount_paid=amount,
            admin_id=update.effective_user.id
        )
        
        # Generate invite link
        invite_link = "لینک دعوت (به کاربر ارسال شد)"
        
        try:
            # Try to send to user
            if telegram_id:
                actual_link = await context.bot.create_chat_invite_link(
                    chat_id=self.spotplayer_handler.SPOTPLAYER_CONFIG['channel_id'],
                    member_limit=1,
                    name=f"SpotPlayer_Manual_{telegram_id}"
                )
                
                user_message = (
                    "🎉 **محصول SpotPlayer برای شما فعال شد!**\n\n"
                    f"🔑 **کلید دسترسی:**\n`{spotplayer_key}`\n\n"
                    f"🔗 **لینک ورود به کانال VIP:**\n{actual_link.invite_link}\n\n"
                    "این فعال‌سازی توسط مدیر سیستم انجام شده است.\n"
                    "در صورت هرگونه سؤال با پشتیبانی تماس بگیرید."
                )
                
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=user_message,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
                
                invite_link = actual_link.invite_link
                
        except Exception as e:
            logger.error(f"Error sending to user: {e}")
        
        # Success message
        success_message = (
            "✅ **فعال‌سازی با موفقیت انجام شد!**\n\n"
            f"👤 کاربر: {context.user_data.get('manual_user_name')}\n"
            f"🔑 کلید: `{spotplayer_key}`\n"
            f"💰 مبلغ: {self._format_price(amount)} تومان\n"
            f"📝 کد پیگیری: {tracking_code}\n"
            f"📅 تاریخ: {datetime.now().strftime('%Y/%m/%d %H:%M')}\n\n"
            "پیام فعال‌سازی برای کاربر ارسال شد ✅"
        )
        
        await query.edit_message_text(
            success_message,
            parse_mode=ParseMode.MARKDOWN
        )
        
        await query.message.reply_text(
            "عملیات کامل شد.",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Clear data
        context.user_data.clear()
        
        return ConversationHandler.END
    
    async def show_purchases_list(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """Show list of recent SpotPlayer purchases"""
        query = update.callback_query
        await query.answer()
        
        # Get recent purchases
        purchases = self._get_recent_purchases(limit=10)
        
        if not purchases:
            await query.edit_message_text(
                "📋 هنوز خریدی ثبت نشده است.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت", callback_data="admin_spotplayer_menu")
                ]])
            )
            return
        
        message = "📋 **لیست خریدهای اخیر:**\n\n"
        
        for purchase in purchases:
            user_name = purchase.get('user_name', 'نامشخص')
            amount = purchase.get('amount', 0)
            date = purchase.get('created_at', '')
            key = purchase.get('spotplayer_key', '')[:8] + '...'
            
            message += (
                f"👤 {user_name}\n"
                f"💰 {self._format_price(amount)} تومان\n"
                f"🔑 {key}\n"
                f"📅 {date}\n"
                "━━━━━━━━━━━\n"
            )
        
        keyboard = [[
            InlineKeyboardButton("🔙 بازگشت", callback_data="admin_spotplayer_menu")
        ]]
        
        await query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    def _get_spotplayer_stats(self) -> dict:
        """Get SpotPlayer statistics"""
        try:
            cursor = self.db.connection.cursor()
            
            # Total purchases
            cursor.execute(
                "SELECT COUNT(*), SUM(amount) FROM spotplayer_purchases"
            )
            total_count, total_revenue = cursor.fetchone()
            
            # Today's purchases
            cursor.execute(
                """SELECT COUNT(*), SUM(amount) FROM spotplayer_purchases 
                WHERE DATE(created_at) = DATE('now')"""
            )
            today_count, today_revenue = cursor.fetchone()
            
            return {
                'total_purchases': total_count or 0,
                'total_revenue': total_revenue or 0,
                'today_purchases': today_count or 0,
                'today_revenue': today_revenue or 0
            }
            
        except:
            return {
                'total_purchases': 0,
                'total_revenue': 0,
                'today_purchases': 0,
                'today_revenue': 0
            }
    
    def _get_recent_purchases(self, limit: int = 10) -> list:
        """Get recent SpotPlayer purchases"""
        try:
            cursor = self.db.connection.cursor()
            
            query = """
                SELECT 
                    sp.*, 
                    u.full_name as user_name
                FROM spotplayer_purchases sp
                LEFT JOIN users u ON sp.user_id = u.user_id
                ORDER BY sp.created_at DESC
                LIMIT ?
            """
            
            cursor.execute(query, (limit,))
            
            columns = [desc[0] for desc in cursor.description]
            purchases = []
            
            for row in cursor.fetchall():
                purchase = dict(zip(columns, row))
                purchases.append(purchase)
            
            return purchases
            
        except Exception as e:
            logger.error(f"Error getting purchases: {e}")
            return []
    
    def _format_price(self, amount: int) -> str:
        """Format price with thousand separators"""
        return f"{amount:,}"
    
    def get_handlers(self) -> list:
        """Get all handlers for admin SpotPlayer management"""
        handlers = []
        
        # Menu handlers
        handlers.append(
            CallbackQueryHandler(
                self.show_spotplayer_menu,
                pattern='^admin_spotplayer_menu$'
            )
        )
        
        handlers.append(
            CallbackQueryHandler(
                self.show_purchases_list,
                pattern='^admin_spotplayer_list$'
            )
        )
        
        # Manual activation conversation
        manual_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.start_manual_activation,
                    pattern='^admin_spotplayer_manual$'
                )
            ],
            states={
                SELECT_USER: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.process_user_selection
                    )
                ],
                ENTER_TRACKING: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.process_tracking_code
                    )
                ],
                CONFIRM_MANUAL: [
                    CallbackQueryHandler(
                        self.confirm_manual_activation,
                        pattern='^(confirm|cancel)_manual_spot$'
                    )
                ]
            },
            fallbacks=[
                CommandHandler('cancel', lambda u, c: ConversationHandler.END),
                MessageHandler(
                    filters.Regex('^❌ انصراف$'),
                    lambda u, c: ConversationHandler.END
                )
            ],
            per_user=True,
            per_chat=True,
            allow_reentry=True
        )
        
        handlers.append(manual_conv)
        
        return handlers

def get_admin_spotplayer_handlers(db_queries, config):
    """Factory function to create handlers for SpotPlayer admin"""
    handler = AdminSpotPlayerHandler(db_queries, config)
    return handler.get_handlers()
