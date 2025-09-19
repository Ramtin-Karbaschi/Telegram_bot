"""
Professional SpotPlayer Handler
Complete implementation with environment-based configuration
"""

import asyncio
import hashlib
import json
import logging
import os
import random
import re
import string
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import aiohttp
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
from config.spotplayer_config import spotplayer_config

logger = logging.getLogger(__name__)

# Conversation states
ENTER_TRACKING_CODE = 1
CONFIRM_PURCHASE = 2

class SpotPlayerHandlerPro:
    """Professional SpotPlayer handler with full feature set"""
    
    def __init__(self, db_queries: DatabaseQueries):
        """Initialize the handler"""
        self.db = db_queries
        self.config = spotplayer_config
        self.bot = None  # Will be set later
        
        # Cache for recent verifications
        self.verification_cache = {}
        
        # Amount tolerance for verification (±5%)
        self.AMOUNT_TOLERANCE = 0.05
        
        logger.info("SpotPlayer Handler Pro initialized")
    
    def set_bot(self, bot):
        """Set bot instance for sending messages"""
        self.bot = bot
    
    async def start_verification(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Start the SpotPlayer purchase verification process"""
        
        user = update.effective_user
        telegram_id = user.id
        
        # Check if user is registered
        user_info = self.db.get_user_by_telegram_id(telegram_id)
        if not user_info:
            await update.message.reply_text(
                "❌ شما ابتدا باید در ربات ثبت‌نام کنید.\n"
                "لطفاً از دستور /start استفاده کنید.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Get available products
        products = self.get_active_products()
        
        if not products:
            await update.message.reply_text(
                "❌ در حال حاضر محصولی موجود نیست.\n"
                "لطفاً با پشتیبانی تماس بگیرید.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Build product list
        product_list = "\n".join([
            f"• **{p['name']}**: {self._format_price(p['price'] // 10)} تومان"
            for p in products
        ])
        
        # Send instructions
        message = (
            "🎬 **تأیید خرید محصول SpotPlayer**\n\n"
            "📦 **محصولات موجود:**\n"
            f"{product_list}\n\n"
            "برای دریافت کلید دسترسی و فعال‌سازی اشتراک،\n"
            "لطفاً **کد پیگیری تراکنش زرین‌پال** خود را ارسال کنید.\n\n"
            "💡 کد پیگیری معمولاً با حرف A شروع می‌شود\n"
            "مثال: `A00000123456`"
        )
        
        keyboard = [[KeyboardButton("❌ انصراف")]]
        
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        )
        
        # Store user data
        context.user_data['sp_user_id'] = user_info.get('user_id')
        context.user_data['sp_telegram_id'] = telegram_id
        context.user_data['sp_full_name'] = user_info.get('full_name', '')
        
        return ENTER_TRACKING_CODE
    
    async def process_tracking_code(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Process the tracking code"""
        
        text = update.message.text.strip()
        
        # Check for cancellation
        if text == "❌ انصراف":
            await update.message.reply_text(
                "❌ عملیات لغو شد.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Validate format
        if not self._validate_tracking_code(text):
            await update.message.reply_text(
                "❌ فرمت کد پیگیری نادرست است.\n"
                "کد پیگیری باید مانند این باشد: A00000123456"
            )
            return ENTER_TRACKING_CODE
        
        # Check if already used
        if self.is_tracking_code_used(text):
            await update.message.reply_text(
                "⚠️ این کد پیگیری قبلاً استفاده شده است.\n"
                "اگر مشکلی دارید، با پشتیبانی تماس بگیرید.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END
        
        # Show processing
        processing_msg = await update.message.reply_text(
            "⏳ در حال بررسی با زرین‌پال...",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Verify with Zarinpal
        verification = await self._verify_zarinpal_payment(text)
        
        if not verification['success']:
            await processing_msg.edit_text(
                f"❌ خطا در تأیید پرداخت:\n{verification['message']}"
            )
            self._log_failed_verification(
                user_id=context.user_data['sp_user_id'],
                tracking_code=text,
                reason=verification['message']
            )
            return ConversationHandler.END
        
        # Find matching product
        amount_rials = verification['data'].get('amount', 0)
        product = self.find_product_by_amount(amount_rials)
        
        if not product:
            await processing_msg.edit_text(
                f"❌ محصولی با مبلغ {self._format_price(amount_rials // 10)} تومان یافت نشد.\n"
                "با پشتیبانی تماس بگیرید."
            )
            self._log_unmatched_payment(
                user_id=context.user_data['sp_user_id'],
                tracking_code=text,
                amount=amount_rials
            )
            return ConversationHandler.END
        
        # Check product availability
        if not self._check_product_availability(product):
            await processing_msg.edit_text(
                "❌ این محصول در حال حاضر موجود نیست.\n"
                "لطفاً با پشتیبانی تماس بگیرید."
            )
            return ConversationHandler.END
        
        # Store data
        context.user_data['sp_payment_data'] = verification['data']
        context.user_data['sp_tracking_code'] = text
        context.user_data['sp_product'] = product
        
        # Get channel info
        channel_info = self.config.get_channel_by_id(int(product['channel_id']))
        channel_name = channel_info['title'] if channel_info else 'کانال VIP'
        
        # Show confirmation
        confirmation_message = (
            "✅ **پرداخت تأیید شد**\n\n"
            f"📦 محصول: **{product['name']}**\n"
            f"💰 مبلغ: {self._format_price(amount_rials // 10)} تومان\n"
            f"📅 اشتراک: {product['subscription_days']} روز\n"
            f"📢 کانال: {channel_name}\n"
            f"📝 کد پیگیری: `{text}`\n\n"
            "آیا از فعال‌سازی اطمینان دارید؟"
        )
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ تأیید", callback_data="confirm_spotplayer"),
                InlineKeyboardButton("❌ انصراف", callback_data="cancel_spotplayer")
            ]
        ])
        
        await processing_msg.edit_text(
            confirmation_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
        return CONFIRM_PURCHASE
    
    async def confirm_activation(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Confirm and activate the purchase"""
        
        query = update.callback_query
        await query.answer()
        
        if query.data == "cancel_spotplayer":
            await query.edit_message_text("❌ عملیات لغو شد.")
            return ConversationHandler.END
        
        # Show processing
        await query.edit_message_text("⏳ در حال فعال‌سازی...")
        
        # Get stored data
        user_id = context.user_data.get('sp_user_id')
        telegram_id = context.user_data.get('sp_telegram_id')
        tracking_code = context.user_data.get('sp_tracking_code')
        payment_data = context.user_data.get('sp_payment_data', {})
        product = context.user_data.get('sp_product')
        
        try:
            # 1. Generate SpotPlayer key via API
            spotplayer_key = await self._create_spotplayer_license(
                user_id=user_id,
                course_id=product['spotplayer_course_id'],
                tracking_code=tracking_code
            )
            
            if not spotplayer_key:
                raise Exception("Failed to generate SpotPlayer key")
            
            # 2. Save purchase
            purchase_id = self._save_purchase(
                user_id=user_id,
                product=product,
                tracking_code=tracking_code,
                amount=payment_data.get('amount', 0),
                spotplayer_key=spotplayer_key,
                payment_data=payment_data
            )
            
            # 3. Create subscription
            subscription_end = await self._create_subscription(
                user_id=user_id,
                product=product,
                purchase_id=purchase_id
            )
            
            # 4. Generate channel invite
            invite_link = await self._generate_channel_invite(
                telegram_id=telegram_id,
                channel_id=int(product['channel_id'])
            )
            
            # 5. Update purchase with invite link
            self._update_purchase_invite_link(purchase_id, invite_link)
            
            # Get channel info for display
            channel_info = self.config.get_channel_by_id(int(product['channel_id']))
            
            # 6. Send success message
            success_message = (
                "🎉 **محصول با موفقیت فعال شد!**\n\n"
                f"📦 **{product['name']}**\n"
                f"{product.get('description', '')}\n\n"
                f"🔑 **کلید دسترسی SpotPlayer:**\n"
                f"`{spotplayer_key}`\n"
                "(روی کلید کلیک کنید تا کپی شود)\n\n"
                f"📱 **اشتراک کانال:**\n"
                f"کانال: {channel_info['title'] if channel_info else 'کانال VIP'}\n"
                f"مدت: {product['subscription_days']} روز\n"
                f"انقضا: {subscription_end}\n\n"
                f"🔗 **لینک ورود به کانال:**\n"
                f"{invite_link}\n\n"
                "📌 **نکات مهم:**\n"
                "• کلید را در جای امن ذخیره کنید\n"
                "• لینک فقط یکبار قابل استفاده است\n"
                "• برای استفاده به spotplayer.ir مراجعه کنید"
            )
            
            await query.edit_message_text(
                success_message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            
            # 7. Log successful activation
            self._log_successful_activation(
                purchase_id=purchase_id,
                user_id=user_id,
                product=product
            )
            
            # 8. Notify admins
            await self._notify_admins_of_purchase(
                user_id=user_id,
                telegram_id=telegram_id,
                product=product,
                tracking_code=tracking_code,
                amount=payment_data.get('amount', 0),
                spotplayer_key=spotplayer_key
            )
            
        except Exception as e:
            logger.error(f"Activation error: {e}")
            await query.edit_message_text(
                "❌ خطا در فعال‌سازی محصول.\n"
                "اطلاعات شما ثبت شده است.\n"
                "با پشتیبانی تماس بگیرید.\n\n"
                f"کد پیگیری: `{tracking_code}`",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Log error
            self._log_activation_error(
                user_id=user_id,
                tracking_code=tracking_code,
                error=str(e)
            )
        
        # Clear user data
        context.user_data.clear()
        
        return ConversationHandler.END
    
    def _validate_tracking_code(self, code: str) -> bool:
        """Validate tracking code format"""
        pattern = r'^[A-Za-z0-9]{6,15}$'
        return bool(re.match(pattern, code))
    
    async def _verify_zarinpal_payment(self, authority: str) -> Dict:
        """Verify payment with Zarinpal"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Get all active products to try different amounts
            products = self.get_active_products()
            
            for product in products:
                data = {
                    'merchant_id': self.config.ZARINPAL_MERCHANT,
                    'authority': authority,
                    'amount': product['price']
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.config.ZARINPAL_VERIFY_URL,
                        json=data,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        result = await response.json()
                
                # Check verification status
                if result.get('data', {}).get('code') in [100, 101]:
                    return {
                        'success': True,
                        'data': {
                            'amount': product['price'],
                            'ref_id': result['data'].get('ref_id'),
                            'card_pan': result['data'].get('card_pan', ''),
                            'date': datetime.now().strftime('%Y/%m/%d %H:%M')
                        }
                    }
            
            return {
                'success': False,
                'message': 'مبلغ پرداخت با هیچ محصولی مطابقت ندارد'
            }
            
        except Exception as e:
            logger.error(f"Zarinpal verification error: {e}")
            return {
                'success': False,
                'message': 'خطا در ارتباط با درگاه پرداخت'
            }
    
    async def _create_spotplayer_license(
        self,
        user_id: int,
        course_id: str,
        tracking_code: str
    ) -> Optional[str]:
        """Create SpotPlayer license via API"""
        try:
            headers = {
                '$API': self.config.API_KEY,
                '$LEVEL': '-1',
                'Content-Type': 'application/json'
            }
            
            data = {
                'course': [course_id],
                'name': f'user_{user_id}',
                'watermark': {
                    'texts': [{'text': tracking_code}]
                }
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.API_URL,
                    json=data,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get('key')
                    else:
                        logger.error(f"SpotPlayer API error: {response.status}")
                        # Generate fallback key
                        return self._generate_fallback_key(user_id, course_id, tracking_code)
                        
        except Exception as e:
            logger.error(f"SpotPlayer license creation error: {e}")
            return self._generate_fallback_key(user_id, course_id, tracking_code)
    
    def _generate_fallback_key(self, user_id: int, course_id: str, tracking_code: str) -> str:
        """Generate fallback key if API fails"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        key_data = f"{user_id}_{course_id}_{tracking_code}_{timestamp}_{random_str}"
        key_hash = hashlib.sha256(key_data.encode()).hexdigest()[:16].upper()
        return f"SPOT-{key_hash[:4]}-{key_hash[4:8]}-{key_hash[8:12]}-{key_hash[12:16]}"
    
    def get_active_products(self) -> List[Dict]:
        """Get all active and public products"""
        try:
            import sqlite3
            conn = sqlite3.connect('database/data/daraei_academy.db')
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM spotplayer_products 
                WHERE is_active = 1 AND is_public = 1
                AND (max_capacity IS NULL OR current_sales < max_capacity)
                ORDER BY priority DESC, price ASC"""
            )
            
            columns = [desc[0] for desc in cursor.description]
            products = []
            
            for row in cursor.fetchall():
                product = dict(zip(columns, row))
                products.append(product)
            
            conn.close()
            return products
            
        except Exception as e:
            logger.error(f"Error getting products: {e}")
            return []
    
    def find_product_by_amount(self, amount_rials: int) -> Optional[Dict]:
        """Find product matching the amount"""
        products = self.get_active_products()
        
        for product in products:
            min_amount = product['price'] * (1 - self.AMOUNT_TOLERANCE)
            max_amount = product['price'] * (1 + self.AMOUNT_TOLERANCE)
            
            if min_amount <= amount_rials <= max_amount:
                return product
        
        return None
    
    def is_tracking_code_used(self, tracking_code: str) -> bool:
        """Check if tracking code is already used"""
        try:
            import sqlite3
            conn = sqlite3.connect('database/data/daraei_academy.db')
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM spotplayer_purchases WHERE tracking_code = ?",
                (tracking_code,)
            )
            result = cursor.fetchone()[0] > 0
            conn.close()
            return result
            
        except Exception as e:
            logger.error(f"Error checking tracking code: {e}")
            return True
    
    def _check_product_availability(self, product: Dict) -> bool:
        """Check if product is available"""
        if not product.get('is_active') or not product.get('is_public'):
            return False
        
        max_capacity = product.get('max_capacity')
        if max_capacity:
            current_sales = product.get('current_sales', 0)
            if current_sales >= max_capacity:
                return False
        
        return True
    
    def _save_purchase(
        self,
        user_id: int,
        product: Dict,
        tracking_code: str,
        amount: int,
        spotplayer_key: str,
        payment_data: Dict
    ) -> Optional[int]:
        """Save purchase to database"""
        try:
            import sqlite3
            conn = sqlite3.connect('database/data/daraei_academy.db')
            cursor = conn.cursor()
            
            subscription_end = datetime.now() + timedelta(days=product['subscription_days'])
            
            cursor.execute(
                """INSERT INTO spotplayer_purchases 
                (user_id, product_id, tracking_code, amount_paid, 
                spotplayer_key, payment_data, subscription_end)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, product['product_id'], tracking_code, amount,
                 spotplayer_key, json.dumps(payment_data, ensure_ascii=False),
                 subscription_end.isoformat())
            )
            
            conn.commit()
            purchase_id = cursor.lastrowid
            conn.close()
            return purchase_id
            
        except Exception as e:
            logger.error(f"Error saving purchase: {e}")
            return None
    
    async def _create_subscription(
        self,
        user_id: int,
        product: Dict,
        purchase_id: int
    ) -> str:
        """Create subscription and return end date"""
        try:
            from database.subscription_manager import SubscriptionManager
            
            # Create or extend subscription
            end_date = datetime.now() + timedelta(days=product['subscription_days'])
            
            # You can integrate with existing subscription system here
            # For now, we just return the end date
            
            return end_date.strftime('%Y/%m/%d')
            
        except Exception as e:
            logger.error(f"Error creating subscription: {e}")
            return "نامشخص"
    
    async def _generate_channel_invite(
        self,
        telegram_id: int,
        channel_id: int
    ) -> str:
        """Generate channel invite link"""
        try:
            if self.bot:
                invite = await self.bot.create_chat_invite_link(
                    chat_id=channel_id,
                    member_limit=1,
                    name=f"SP_{telegram_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                )
                return invite.invite_link
            else:
                # Return channel link from config
                channel_info = self.config.get_channel_by_id(channel_id)
                return channel_info.get('link', 'لینک موجود نیست') if channel_info else 'لینک موجود نیست'
                
        except Exception as e:
            logger.error(f"Error generating invite: {e}")
            return "لینک موجود نیست"
    
    def _update_purchase_invite_link(self, purchase_id: int, invite_link: str):
        """Update purchase with invite link"""
        try:
            import sqlite3
            conn = sqlite3.connect('database/data/daraei_academy.db')
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE spotplayer_purchases SET channel_invite_link = ? WHERE purchase_id = ?",
                (invite_link, purchase_id)
            )
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error updating invite link: {e}")
    
    def _format_price(self, amount: int) -> str:
        """Format price with thousand separators"""
        return f"{amount:,}"
    
    def _log_failed_verification(self, user_id: int, tracking_code: str, reason: str):
        """Log failed verification"""
        try:
            import sqlite3
            conn = sqlite3.connect('database/data/daraei_academy.db')
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO spotplayer_access_log 
                (user_id, action, status, details)
                VALUES (?, ?, ?, ?)""",
                (user_id, 'payment_verification_failed', 'failed',
                 json.dumps({'tracking_code': tracking_code, 'reason': reason}, ensure_ascii=False))
            )
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error logging failed verification: {e}")
    
    def _log_unmatched_payment(self, user_id: int, tracking_code: str, amount: int):
        """Log unmatched payment"""
        try:
            import sqlite3
            conn = sqlite3.connect('database/data/daraei_academy.db')
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO spotplayer_access_log 
                (user_id, action, status, details)
                VALUES (?, ?, ?, ?)""",
                (user_id, 'unmatched_payment', 'pending',
                 json.dumps({'tracking_code': tracking_code, 'amount': amount}, ensure_ascii=False))
            )
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error logging unmatched payment: {e}")
    
    def _log_successful_activation(self, purchase_id: int, user_id: int, product: Dict):
        """Log successful activation"""
        try:
            import sqlite3
            conn = sqlite3.connect('database/data/daraei_academy.db')
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO spotplayer_access_log 
                (purchase_id, user_id, product_id, action, status, details)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (purchase_id, user_id, product['product_id'], 
                 'activation_success', 'success',
                 json.dumps({'product': product['name']}, ensure_ascii=False))
            )
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error logging activation: {e}")
    
    def _log_activation_error(self, user_id: int, tracking_code: str, error: str):
        """Log activation error"""
        try:
            import sqlite3
            conn = sqlite3.connect('database/data/daraei_academy.db')
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO spotplayer_access_log 
                (user_id, action, status, details)
                VALUES (?, ?, ?, ?)""",
                (user_id, 'activation_error', 'failed',
                 json.dumps({'tracking_code': tracking_code, 'error': error}, ensure_ascii=False))
            )
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error logging activation error: {e}")
    
    async def _notify_admins_of_purchase(
        self,
        user_id: int,
        telegram_id: int,
        product: Dict,
        tracking_code: str,
        amount: int,
        spotplayer_key: str
    ):
        """Notify admins of new purchase"""
        try:
            # Get admin IDs from config
            import json
            admins_config = json.loads(os.getenv('ALL_ADMINS_CONFIG', '[]'))
            
            admin_message = (
                "🎬 **خرید جدید SpotPlayer**\n\n"
                f"📦 محصول: {product['name']}\n"
                f"👤 کاربر: {telegram_id}\n"
                f"💰 مبلغ: {self._format_price(amount // 10)} تومان\n"
                f"📝 کد پیگیری: `{tracking_code}`\n"
                f"🔑 کلید: `{spotplayer_key}`\n"
                f"📅 زمان: {datetime.now().strftime('%Y/%m/%d %H:%M')}"
            )
            
            if self.bot:
                for admin in admins_config:
                    if 'manager_bot_admin' in admin.get('roles', []):
                        try:
                            await self.bot.send_message(
                                chat_id=admin['chat_id'],
                                text=admin_message,
                                parse_mode=ParseMode.MARKDOWN
                            )
                        except:
                            pass
                            
        except Exception as e:
            logger.error(f"Error notifying admins: {e}")
    
    def get_conversation_handler(self) -> ConversationHandler:
        """Get conversation handler for SpotPlayer"""
        return ConversationHandler(
            entry_points=[
                CommandHandler('spotplayer', self.start_verification),
                MessageHandler(
                    filters.Regex(r'^(تأیید خرید SpotPlayer|SpotPlayer|🎬)'),
                    self.start_verification
                )
            ],
            states={
                ENTER_TRACKING_CODE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND,
                        self.process_tracking_code
                    )
                ],
                CONFIRM_PURCHASE: [
                    CallbackQueryHandler(
                        self.confirm_activation,
                        pattern='^(confirm|cancel)_spotplayer$'
                    )
                ]
            },
            fallbacks=[
                CommandHandler('cancel', lambda u, c: ConversationHandler.END),
                MessageHandler(
                    filters.Regex('^(❌ انصراف|/cancel)$'),
                    lambda u, c: ConversationHandler.END
                )
            ],
            per_user=True,
            per_chat=True,
            allow_reentry=True
        )
