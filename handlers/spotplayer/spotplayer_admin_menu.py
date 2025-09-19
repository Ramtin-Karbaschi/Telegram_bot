"""
SpotPlayer Admin Menu Handler
Complete admin interface for SpotPlayer management
"""

import logging
import sqlite3
from typing import Dict, List, Optional
from datetime import datetime
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
from handlers.spotplayer.product_manager import SpotPlayerProductManager
from handlers.spotplayer.admin_spotplayer_handler import AdminSpotPlayerHandler

logger = logging.getLogger(__name__)

# Conversation states
ADD_PRODUCT_NAME = 1
ADD_PRODUCT_PRICE = 2
ADD_PRODUCT_DAYS = 3
ADD_PRODUCT_COURSE = 4
ADD_PRODUCT_CHANNEL = 5
ADD_PRODUCT_DESC = 6
ADD_PRODUCT_CAPACITY = 7

EDIT_PRODUCT_FIELD = 1
EDIT_PRODUCT_VALUE = 2

class SpotPlayerAdminMenu:
    """Admin menu for SpotPlayer management"""
    
    def __init__(self, db_queries):
        """Initialize handler"""
        self.db = db_queries
        self.product_manager = SpotPlayerProductManager(db_queries)
        self.manual_handler = AdminSpotPlayerHandler(db_queries, spotplayer_config)
        self.config = spotplayer_config
    
    async def show_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main SpotPlayer admin menu"""
        query = update.callback_query
        await query.answer()
        
        # Get current status
        conn = sqlite3.connect('database/data/daraei_academy.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT value FROM settings WHERE key = 'spotplayer_enabled'")
        result = cursor.fetchone()
        spotplayer_enabled = result and result[0] == '1'
        
        # Get product count
        cursor.execute("SELECT COUNT(*) FROM spotplayer_products WHERE is_active = 1")
        active_products = cursor.fetchone()[0]
        
        # Get total purchases
        cursor.execute("SELECT COUNT(*) FROM spotplayer_purchases WHERE status = 'completed'")
        total_purchases = cursor.fetchone()[0]
        
        conn.close()
        
        text = (
            "🎬 **مدیریت SpotPlayer**\n\n"
            f"📊 وضعیت: {'✅ فعال' if spotplayer_enabled else '❌ غیرفعال'}\n"
            f"📦 محصولات فعال: {active_products}\n"
            f"💳 کل خریدها: {total_purchases}\n\n"
            "انتخاب کنید:"
        )
        
        toggle_text = "🔴 غیرفعال کردن" if spotplayer_enabled else "🟢 فعال کردن"
        
        keyboard = [
            [
                InlineKeyboardButton("📦 مدیریت محصولات", callback_data="sp_admin_products"),
                InlineKeyboardButton("➕ محصول جدید", callback_data="sp_admin_add_product")
            ],
            [
                InlineKeyboardButton("📊 گزارش فروش", callback_data="sp_admin_sales_report"),
                InlineKeyboardButton("🔍 جستجوی خرید", callback_data="sp_admin_search_purchase")
            ],
            [
                InlineKeyboardButton("✏️ فعال‌سازی دستی", callback_data="sp_admin_manual_activate"),
                InlineKeyboardButton("📝 لاگ دسترسی", callback_data="sp_admin_access_log")
            ],
            [
                InlineKeyboardButton(toggle_text, callback_data="sp_admin_toggle_system")
            ],
            [
                InlineKeyboardButton("🔙 بازگشت", callback_data="admin_products_menu")
            ]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def toggle_system(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle SpotPlayer system on/off"""
        query = update.callback_query
        await query.answer()
        
        # Toggle the setting
        conn = sqlite3.connect('database/data/daraei_academy.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT value FROM settings WHERE key = 'spotplayer_enabled'")
        result = cursor.fetchone()
        current = result[0] if result else '0'
        
        new_value = '0' if current == '1' else '1'
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ('spotplayer_enabled', new_value)
        )
        
        # Also update category visibility
        if new_value == '1':
            cursor.execute(
                "UPDATE categories SET is_active = 1 WHERE name = '🎬 SpotPlayer'"
            )
            status_msg = "✅ سیستم SpotPlayer فعال شد"
        else:
            cursor.execute(
                "UPDATE categories SET is_active = 0 WHERE name = '🎬 SpotPlayer'"
            )
            status_msg = "🔴 سیستم SpotPlayer غیرفعال شد"
        
        conn.commit()
        conn.close()
        
        await query.answer(status_msg, show_alert=True)
        await self.show_menu(update, context)
    
    async def show_products(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all SpotPlayer products"""
        query = update.callback_query
        await query.answer()
        
        conn = sqlite3.connect('database/data/daraei_academy.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM spotplayer_products 
            ORDER BY is_active DESC, priority DESC, price ASC
        """)
        
        columns = [desc[0] for desc in cursor.description]
        products = []
        for row in cursor.fetchall():
            products.append(dict(zip(columns, row)))
        
        conn.close()
        
        if not products:
            await query.edit_message_text(
                "⚠️ هیچ محصولی یافت نشد.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("➕ محصول جدید", callback_data="sp_admin_add_product"),
                    InlineKeyboardButton("🔙 بازگشت", callback_data="spotplayer_admin_menu")
                ]])
            )
            return
        
        text = "📦 **لیست محصولات SpotPlayer:**\n\n"
        keyboard = []
        
        for product in products:
            status_icon = "✅" if product['is_active'] else "🔴"
            public_icon = "👁" if product['is_public'] else "🔒"
            
            text += (
                f"{status_icon} {public_icon} **{product['name']}**\n"
                f"   💰 {product['price']:,} ریال | 📅 {product['subscription_days']} روز\n"
            )
            
            if product.get('max_capacity'):
                remaining = product['max_capacity'] - (product.get('current_sales', 0) or 0)
                text += f"   📊 ظرفیت: {remaining}/{product['max_capacity']}\n"
            
            text += "\n"
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_icon} {product['name']}",
                    callback_data=f"sp_admin_product_{product['product_id']}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton("➕ محصول جدید", callback_data="sp_admin_add_product"),
            InlineKeyboardButton("🔙 بازگشت", callback_data="spotplayer_admin_menu")
        ])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def show_product_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed view of a product"""
        query = update.callback_query
        await query.answer()
        
        product_id = int(query.data.split("_")[-1])
        
        conn = sqlite3.connect('database/data/daraei_academy.db')
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM spotplayer_products WHERE product_id = ?",
            (product_id,)
        )
        
        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
        
        if not row:
            await query.answer("محصول یافت نشد", show_alert=True)
            return
        
        product = dict(zip(columns, row))
        
        # Get purchase count
        cursor.execute(
            "SELECT COUNT(*) FROM spotplayer_purchases WHERE product_id = ?",
            (product_id,)
        )
        purchase_count = cursor.fetchone()[0]
        
        conn.close()
        
        # Get course and channel info
        course = self.config.get_course_by_id(product.get('spotplayer_course_id'))
        channel = self.config.get_channel_by_id(product.get('channel_id'))
        
        text = (
            f"📦 **{product['name']}**\n\n"
            f"🆔 شناسه: `{product['product_id']}`\n"
            f"💰 قیمت: **{product['price']:,} ریال**\n"
            f"📅 مدت اشتراک: **{product['subscription_days']} روز**\n"
            f"🎬 دوره: **{course['name'] if course else 'نامشخص'}**\n"
            f"📢 کانال: **{channel['title'] if channel else 'نامشخص'}**\n"
            f"📊 فروش: **{purchase_count} عدد**\n"
            f"🎯 اولویت: **{product.get('priority', 0)}**\n"
        )
        
        if product.get('max_capacity'):
            remaining = product['max_capacity'] - (product.get('current_sales', 0) or 0)
            text += f"📊 ظرفیت: **{remaining}/{product['max_capacity']}**\n"
        
        text += f"\n📌 وضعیت: **{'فعال' if product['is_active'] else 'غیرفعال'}**\n"
        text += f"👁 نمایش عمومی: **{'بله' if product['is_public'] else 'خیر'}**\n"
        
        if product.get('description'):
            text += f"\n📝 **توضیحات:**\n{product['description']}\n"
        
        text += f"\n📅 ایجاد: {product['created_at'][:16]}"
        
        # Build keyboard
        toggle_active_text = "🔴 غیرفعال کردن" if product['is_active'] else "✅ فعال کردن"
        toggle_public_text = "🔒 خصوصی کردن" if product['is_public'] else "👁 عمومی کردن"
        
        keyboard = [
            [
                InlineKeyboardButton(toggle_active_text, callback_data=f"sp_admin_toggle_active_{product_id}"),
                InlineKeyboardButton(toggle_public_text, callback_data=f"sp_admin_toggle_public_{product_id}")
            ],
            [
                InlineKeyboardButton("✏️ ویرایش", callback_data=f"sp_admin_edit_{product_id}"),
                InlineKeyboardButton("🗑 حذف", callback_data=f"sp_admin_delete_{product_id}")
            ],
            [
                InlineKeyboardButton("📊 گزارش فروش", callback_data=f"sp_admin_product_report_{product_id}")
            ],
            [
                InlineKeyboardButton("🔙 بازگشت", callback_data="sp_admin_products")
            ]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def toggle_product_active(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle product active status"""
        query = update.callback_query
        await query.answer()
        
        product_id = int(query.data.split("_")[-1])
        
        conn = sqlite3.connect('database/data/daraei_academy.db')
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE spotplayer_products SET is_active = NOT is_active WHERE product_id = ?",
            (product_id,)
        )
        
        conn.commit()
        conn.close()
        
        await query.answer("✅ وضعیت محصول تغییر کرد", show_alert=True)
        await self.show_product_detail(update, context)
    
    async def toggle_product_public(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle product public visibility"""
        query = update.callback_query
        await query.answer()
        
        product_id = int(query.data.split("_")[-1])
        
        conn = sqlite3.connect('database/data/daraei_academy.db')
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE spotplayer_products SET is_public = NOT is_public WHERE product_id = ?",
            (product_id,)
        )
        
        conn.commit()
        conn.close()
        
        await query.answer("✅ وضعیت نمایش تغییر کرد", show_alert=True)
        await self.show_product_detail(update, context)
    
    async def show_sales_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show sales report for all products"""
        query = update.callback_query
        await query.answer()
        
        conn = sqlite3.connect('database/data/daraei_academy.db')
        cursor = conn.cursor()
        
        # Get overall stats
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT product_id) as product_count,
                COUNT(*) as total_purchases,
                SUM(amount_paid) as total_revenue
            FROM spotplayer_purchases
            WHERE status = 'completed'
        """)
        
        stats = cursor.fetchone()
        
        # Get product-wise breakdown
        cursor.execute("""
            SELECT 
                p.name,
                COUNT(sp.purchase_id) as sales,
                SUM(sp.amount_paid) as revenue
            FROM spotplayer_products p
            LEFT JOIN spotplayer_purchases sp ON p.product_id = sp.product_id
            WHERE sp.status = 'completed' OR sp.status IS NULL
            GROUP BY p.product_id
            ORDER BY revenue DESC NULLS LAST
        """)
        
        product_stats = cursor.fetchall()
        
        conn.close()
        
        # Handle None values
        total_products = stats[0] if stats[0] else 0
        total_sales = stats[1] if stats[1] else 0  
        total_revenue = stats[2] if stats[2] else 0
        
        text = (
            "📊 **گزارش فروش SpotPlayer**\n\n"
            f"📦 تعداد محصولات: {total_products}\n"
            f"🛍 کل فروش: {total_sales} عدد\n"
            f"💰 کل درآمد: {total_revenue:,} ریال\n\n"
            "**جزئیات محصولات:**\n"
        )
        
        for name, sales, revenue in product_stats:
            sales_count = sales if sales else 0
            revenue_amount = revenue if revenue else 0
            if sales_count > 0:
                text += f"\n▫️ **{name}**\n"
                text += f"   فروش: {sales_count} | درآمد: {revenue_amount:,} ریال\n"
        
        keyboard = [
            [InlineKeyboardButton("📤 خروجی اکسل", callback_data="sp_admin_export_sales")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="spotplayer_admin_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def show_access_log(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent access log"""
        query = update.callback_query
        await query.answer()
        
        conn = sqlite3.connect('database/data/daraei_academy.db')
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                l.action,
                l.status,
                l.created_at,
                u.full_name,
                u.user_id
            FROM spotplayer_access_log l
            LEFT JOIN users u ON l.user_id = u.user_id
            ORDER BY l.log_id DESC
            LIMIT 20
        """)
        
        logs = cursor.fetchall()
        conn.close()
        
        if not logs:
            text = "📝 هیچ لاگی موجود نیست."
        else:
            text = "📝 **آخرین فعالیت‌ها:**\n\n"
            
            action_icons = {
                'activation_success': '✅',
                'payment_verification_failed': '❌',
                'unmatched_payment': '⚠️',
                'activation_error': '🔴',
                'manual_activation': '✏️'
            }
            
            for action, status, created_at, full_name, telegram_id in logs:
                icon = action_icons.get(action, '📌')
                text += f"{icon} {full_name or 'ناشناس'} ({telegram_id})\n"
                text += f"   {action} - {created_at[:16]}\n\n"
        
        keyboard = [[
            InlineKeyboardButton("🔙 بازگشت", callback_data="spotplayer_admin_menu")
        ]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

def register_spotplayer_admin_handlers(application, db_queries):
    """Register all SpotPlayer admin handlers"""
    handler = SpotPlayerAdminMenu(db_queries)
    
    # Main menu callbacks
    application.add_handler(CallbackQueryHandler(
        handler.show_menu,
        pattern="^spotplayer_admin_menu$"
    ))
    
    application.add_handler(CallbackQueryHandler(
        handler.toggle_system,
        pattern="^sp_admin_toggle_system$"
    ))
    
    application.add_handler(CallbackQueryHandler(
        handler.show_products,
        pattern="^sp_admin_products$"
    ))
    
    application.add_handler(CallbackQueryHandler(
        handler.show_product_detail,
        pattern="^sp_admin_product_\\d+$"
    ))
    
    application.add_handler(CallbackQueryHandler(
        handler.toggle_product_active,
        pattern="^sp_admin_toggle_active_\\d+$"
    ))
    
    application.add_handler(CallbackQueryHandler(
        handler.toggle_product_public,
        pattern="^sp_admin_toggle_public_\\d+$"
    ))
    
    application.add_handler(CallbackQueryHandler(
        handler.show_sales_report,
        pattern="^sp_admin_sales_report$"
    ))
    
    application.add_handler(CallbackQueryHandler(
        handler.show_access_log,
        pattern="^sp_admin_access_log$"
    ))
    
    # Register product manager handlers
    from handlers.spotplayer.product_manager import get_product_manager_handlers
    pm_handlers = get_product_manager_handlers(db_queries)
    for h in pm_handlers:
        application.add_handler(h)
    
    # Register manual activation handler  
    from handlers.spotplayer.admin_spotplayer_handler import get_admin_spotplayer_handlers
    manual_handlers = get_admin_spotplayer_handlers(db_queries, None)
    for h in manual_handlers:
        application.add_handler(h)
    
    logger.info("SpotPlayer admin handlers registered")
