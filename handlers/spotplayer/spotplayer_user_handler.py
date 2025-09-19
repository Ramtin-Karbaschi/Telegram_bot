"""
SpotPlayer User Interface Handler
Handles user interactions in main bot
"""

import logging
from typing import Optional, Dict
import sqlite3
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters
)

from config.spotplayer_config import spotplayer_config
from handlers.spotplayer.spotplayer_handler_pro import SpotPlayerHandlerPro

logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_CODE = 1

class SpotPlayerUserHandler:
    """Handler for SpotPlayer menu in main bot"""
    
    def __init__(self, db_queries):
        """Initialize handler"""
        self.db = db_queries
        self.handler = SpotPlayerHandlerPro(db_queries)
        self.config = spotplayer_config
    
    async def show_spotplayer_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show SpotPlayer products menu when user clicks on SpotPlayer category"""
        query = update.callback_query
        if query:
            await query.answer()
        
        user_id = update.effective_user.id
        
        # Check if SpotPlayer is enabled
        conn = sqlite3.connect('database/data/daraei_academy.db')
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'spotplayer_enabled'")
        result = cursor.fetchone()
        conn.close()
        
        if not result or result[0] != '1':
            text = "⚠️ این سرویس موقتاً غیرفعال است."
            if query:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(text, parse_mode=ParseMode.HTML)
            return
        
        # Get active products
        products = self.handler.get_active_products()
        
        if not products:
            text = (
                "🎬 **SpotPlayer**\n\n"
                "⚠️ در حال حاضر محصولی موجود نیست.\n"
                "لطفاً بعداً مراجعه کنید."
            )
            keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="products_menu")]]
            
            if query:
                await query.edit_message_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        
        # Build products menu
        text = (
            "🎬 **SpotPlayer - دسترسی ویژه**\n\n"
            "محصولات زیر را می‌توانید با کد پیگیری زرین‌پال فعال کنید:\n\n"
        )
        
        keyboard = []
        for product in products:
            # Format product info
            product_text = f"{product['name']} - {product['price']:,} ریال"
            if product.get('description'):
                description = product['description'][:50] + '...' if len(product['description']) > 50 else product['description']
                product_text += f"\n{description}"
            
            text += f"▫️ **{product['name']}**\n"
            text += f"   💰 قیمت: {product['price']:,} ریال\n"
            text += f"   📅 مدت: {product['subscription_days']} روز\n"
            if product.get('description'):
                text += f"   📝 {product['description']}\n"
            text += "\n"
            
            # Add button for product
            keyboard.append([
                InlineKeyboardButton(
                    f"{product['name']} ({product['price']:,} ریال)",
                    callback_data=f"spotplayer_product_{product['product_id']}"
                )
            ])
        
        # Add activation button
        keyboard.append([
            InlineKeyboardButton("✅ فعال‌سازی با کد پیگیری", callback_data="spotplayer_activate")
        ])
        
        # Add back button
        keyboard.append([
            InlineKeyboardButton("🔙 بازگشت", callback_data="products_menu")
        ])
        
        if query:
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Don't end conversation - let user interact with buttons
        return
    
    async def show_product_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed information about a specific product"""
        query = update.callback_query
        await query.answer()
        
        # Extract product ID
        product_id = int(query.data.split("_")[-1])
        
        # Get product details
        conn = sqlite3.connect('database/data/daraei_academy.db')
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM spotplayer_products WHERE product_id = ? AND is_active = 1",
            (product_id,)
        )
        
        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            await query.edit_message_text(
                "⚠️ محصول یافت نشد.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت", callback_data="spotplayer_menu")
                ]])
            )
            return
        
        product = dict(zip(columns, row))
        
        # Get course info
        course = self.config.get_course_by_id(product.get('spotplayer_course_id'))
        course_name = course['name'] if course else 'نامشخص'
        
        # Get channel info
        channel = self.config.get_channel_by_id(product.get('channel_id'))
        channel_name = channel['title'] if channel else 'نامشخص'
        
        text = (
            f"📦 **{product['name']}**\n\n"
            f"💰 قیمت: **{product['price']:,} ریال**\n"
            f"📅 مدت اشتراک: **{product['subscription_days']} روز**\n"
            f"🎬 دوره: **{course_name}**\n"
            f"📢 کانال: **{channel_name}**\n"
        )
        
        if product.get('description'):
            text += f"\n📝 **توضیحات:**\n{product['description']}\n"
        
        # Check availability
        if product.get('max_capacity'):
            remaining = product['max_capacity'] - (product.get('current_sales', 0) or 0)
            if remaining > 0:
                text += f"\n⚠️ ظرفیت باقی‌مانده: **{remaining} عدد**"
            else:
                text += "\n❌ **ظرفیت تکمیل شده**"
        
        text += (
            "\n\n**نحوه فعال‌سازی:**\n"
            "1️⃣ ابتدا از طریق درگاه زرین‌پال پرداخت کنید\n"
            "2️⃣ کد پیگیری را دریافت کنید\n"
            "3️⃣ با کلیک روی دکمه زیر، کد را وارد کنید"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ فعال‌سازی با کد پیگیری", callback_data="spotplayer_activate")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="spotplayer_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def start_activation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the activation process by asking for tracking code"""
        query = update.callback_query
        await query.answer()
        
        text = (
            "🔑 **فعال‌سازی SpotPlayer**\n\n"
            "لطفاً کد پیگیری پرداخت خود را از زرین‌پال وارد کنید:\n\n"
            "💡 کد پیگیری معمولاً به شکل A00000012345678 است.\n\n"
            "⚠️ توجه: کد پیگیری باید برای خرید محصول SpotPlayer باشد."
        )
        
        keyboard = [[
            InlineKeyboardButton("❌ انصراف", callback_data="spotplayer_menu")
        ]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Set state to wait for tracking code
        context.user_data['waiting_for_spotplayer_code'] = True
        return WAITING_FOR_CODE
    
    async def process_tracking_code(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process the tracking code entered by user"""
        user_id = update.effective_user.id
        tracking_code = update.message.text.strip()
        
        # Delete user's message for privacy
        try:
            await update.message.delete()
        except:
            pass
        
        # Show processing message
        processing_msg = await update.message.reply_text(
            "⏳ در حال بررسی کد پیگیری...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Call the main handler's process method
        result = await self.handler.process_verification_request(
            update, context, tracking_code
        )
        
        # Delete processing message
        try:
            await processing_msg.delete()
        except:
            pass
        
        return ConversationHandler.END
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the activation process"""
        query = update.callback_query
        if query:
            await query.answer("❌ عملیات لغو شد")
            await self.show_spotplayer_menu(update, context)
        else:
            await update.message.reply_text(
                "❌ عملیات لغو شد",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت به منو", callback_data="spotplayer_menu")
                ]])
            )
        return ConversationHandler.END

def get_spotplayer_conversation_handler(db_queries):
    """Create and return SpotPlayer conversation handler"""
    handler = SpotPlayerUserHandler(db_queries)
    
    # Create handlers list
    handlers = []
    
    # Add standalone callback handlers for navigation
    handlers.append(
        CallbackQueryHandler(handler.show_spotplayer_menu, pattern="^spotplayer_menu$")
    )
    handlers.append(
        CallbackQueryHandler(handler.show_product_details, pattern="^spotplayer_product_\\d+$")
    )
    
    # Add conversation handler for activation flow
    activation_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handler.start_activation, pattern="^spotplayer_activate$"),
        ],
        states={
            WAITING_FOR_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handler.process_tracking_code),
                CallbackQueryHandler(handler.cancel, pattern="^spotplayer_menu$"),
                CommandHandler("cancel", handler.cancel)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(handler.cancel, pattern="^spotplayer_menu$"),
            CommandHandler("cancel", handler.cancel)
        ],
        name="spotplayer_activation",
        persistent=True
    )
    
    handlers.append(activation_conv)
    
    # Add command handler
    handlers.append(CommandHandler("spotplayer", handler.show_spotplayer_menu))
    
    return handlers
