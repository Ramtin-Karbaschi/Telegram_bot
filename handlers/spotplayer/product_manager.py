"""
SpotPlayer Product Manager
Manages SpotPlayer products with different prices and configurations
"""

import logging
import os
from typing import Dict, List, Optional

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
    MessageHandler,
    filters
)

logger = logging.getLogger(__name__)

# Conversation states
EDIT_PRODUCT = 1
ENTER_VALUE = 2

class SpotPlayerProductManager:
    """Manages SpotPlayer products"""
    
    def __init__(self, db_queries):
        """Initialize product manager"""
        self.db = db_queries
        
        # Get channels from environment
        self.available_channels = self._load_channels_from_env()
        
    def _load_channels_from_env(self) -> Dict:
        """Load channel configurations from environment"""
        channels = {}
        
        # Example channel IDs from env
        # You should adjust these based on your actual .env structure
        vip_channel = os.getenv('VIP_CHANNEL_ID', '-1001234567890')
        forex_channel = os.getenv('FOREX_CHANNEL_ID', '-1009876543210')
        
        channels['vip'] = {
            'id': vip_channel,
            'username': os.getenv('VIP_CHANNEL_USERNAME', '@vip_channel'),
            'name': 'کانال VIP'
        }
        
        channels['forex'] = {
            'id': forex_channel,
            'username': os.getenv('FOREX_CHANNEL_USERNAME', '@forex_channel'),
            'name': 'کانال فارکس'
        }
        
        return channels
    
    async def show_products_menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """Show products management menu"""
        query = update.callback_query
        if query:
            await query.answer()
        
        products = self.get_all_products()
        
        message = (
            "🎬 **مدیریت محصولات SpotPlayer**\n\n"
            f"تعداد محصولات: {len(products)}\n\n"
            "محصولات فعال:"
        )
        
        keyboard = []
        
        for product in products:
            if product.get('is_active'):
                btn_text = f"📦 {product['name']} ({self._format_price(product['price'] // 10)} تومان)"
                keyboard.append([
                    InlineKeyboardButton(
                        btn_text,
                        callback_data=f"sp_product_{product['product_id']}"
                    )
                ])
        
        keyboard.append([
            InlineKeyboardButton(
                "➕ افزودن محصول جدید",
                callback_data="sp_add_product"
            )
        ])
        
        keyboard.append([
            InlineKeyboardButton(
                "🔄 به‌روزرسانی قیمت‌ها",
                callback_data="sp_update_prices"
            )
        ])
        
        keyboard.append([
            InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data="admin_spotplayer_menu"
            )
        ])
        
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
    
    async def show_product_details(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """Show details of a specific product"""
        query = update.callback_query
        await query.answer()
        
        # Extract product ID from callback data
        product_id = int(query.data.split('_')[-1])
        
        product = self.get_product_by_id(product_id)
        
        if not product:
            await query.edit_message_text("❌ محصول یافت نشد")
            return
        
        # Get purchase stats
        stats = self.get_product_stats(product_id)
        
        message = (
            f"📦 **محصول: {product['name']}**\n\n"
            f"📝 توضیحات: {product.get('description', 'ندارد')}\n"
            f"💰 قیمت: {self._format_price(product['price'] // 10)} تومان\n"
            f"📅 مدت اشتراک: {product['subscription_days']} روز\n"
            f"🔑 Course ID: `{product['spotplayer_course_id']}`\n"
            f"📢 کانال: {product.get('channel_username', 'نامشخص')}\n"
            f"✅ وضعیت: {'فعال' if product.get('is_active') else 'غیرفعال'}\n\n"
            f"📊 **آمار:**\n"
            f"• کل خریدها: {stats['total_purchases']}\n"
            f"• درآمد: {self._format_price(stats['total_revenue'])} تومان"
        )
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "✏️ ویرایش",
                    callback_data=f"sp_edit_{product_id}"
                ),
                InlineKeyboardButton(
                    "🗑 حذف" if product.get('is_active') else "✅ فعال کردن",
                    callback_data=f"sp_toggle_{product_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 بازگشت",
                    callback_data="sp_products_menu"
                )
            ]
        ]
        
        await query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def add_product_start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """Start adding a new product"""
        query = update.callback_query
        await query.answer()
        
        # Store state
        context.user_data['sp_adding_product'] = {
            'step': 'name'
        }
        
        await query.edit_message_text(
            "➕ **افزودن محصول جدید**\n\n"
            "لطفاً نام محصول را وارد کنید:\n"
            "مثال: دوره آموزشی هایپربول",
            parse_mode=ParseMode.MARKDOWN
        )
        
        return ENTER_VALUE
    
    def get_all_products(self) -> List[Dict]:
        """Get all SpotPlayer products"""
        try:
            cursor = self.db.connection.cursor()
            cursor.execute(
                """SELECT * FROM spotplayer_products 
                ORDER BY price ASC"""
            )
            
            columns = [desc[0] for desc in cursor.description]
            products = []
            
            for row in cursor.fetchall():
                product = dict(zip(columns, row))
                products.append(product)
            
            return products
            
        except Exception as e:
            logger.error(f"Error getting products: {e}")
            return []
    
    def get_product_by_id(self, product_id: int) -> Optional[Dict]:
        """Get product by ID"""
        try:
            cursor = self.db.connection.cursor()
            cursor.execute(
                "SELECT * FROM spotplayer_products WHERE product_id = ?",
                (product_id,)
            )
            
            row = cursor.fetchone()
            if not row:
                return None
            
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
            
        except Exception as e:
            logger.error(f"Error getting product: {e}")
            return None
    
    def get_product_by_price(self, price_rials: int, tolerance: float = 0.05) -> Optional[Dict]:
        """Get product by price with tolerance"""
        products = self.get_all_products()
        
        for product in products:
            if not product.get('is_active'):
                continue
                
            expected = product['price']
            min_price = expected * (1 - tolerance)
            max_price = expected * (1 + tolerance)
            
            if min_price <= price_rials <= max_price:
                return product
        
        return None
    
    def add_product(
        self,
        name: str,
        description: str,
        price: int,
        course_id: str,
        subscription_days: int,
        channel_id: str,
        channel_username: str = None
    ) -> Optional[int]:
        """Add a new product"""
        try:
            cursor = self.db.connection.cursor()
            cursor.execute(
                """INSERT INTO spotplayer_products 
                (name, description, price, spotplayer_course_id, 
                subscription_days, channel_id, channel_username)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, description, price, course_id, 
                 subscription_days, channel_id, channel_username)
            )
            
            self.db.connection.commit()
            return cursor.lastrowid
            
        except Exception as e:
            logger.error(f"Error adding product: {e}")
            return None
    
    def update_product(self, product_id: int, **kwargs) -> bool:
        """Update product details"""
        try:
            # Build update query
            updates = []
            values = []
            
            for key, value in kwargs.items():
                if key in ['name', 'description', 'price', 'spotplayer_course_id',
                          'subscription_days', 'channel_id', 'channel_username', 'is_active']:
                    updates.append(f"{key} = ?")
                    values.append(value)
            
            if not updates:
                return False
            
            values.append(product_id)
            
            cursor = self.db.connection.cursor()
            cursor.execute(
                f"""UPDATE spotplayer_products 
                SET {', '.join(updates)}, updated_at = datetime('now')
                WHERE product_id = ?""",
                values
            )
            
            self.db.connection.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error updating product: {e}")
            return False
    
    def toggle_product_status(self, product_id: int) -> bool:
        """Toggle product active status"""
        try:
            cursor = self.db.connection.cursor()
            
            # Get current status
            cursor.execute(
                "SELECT is_active FROM spotplayer_products WHERE product_id = ?",
                (product_id,)
            )
            
            current = cursor.fetchone()
            if not current:
                return False
            
            new_status = 0 if current[0] else 1
            
            cursor.execute(
                """UPDATE spotplayer_products 
                SET is_active = ?, updated_at = datetime('now')
                WHERE product_id = ?""",
                (new_status, product_id)
            )
            
            self.db.connection.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error toggling product: {e}")
            return False
    
    def get_product_stats(self, product_id: int) -> Dict:
        """Get statistics for a product"""
        try:
            cursor = self.db.connection.cursor()
            
            cursor.execute(
                """SELECT 
                    COUNT(*) as total_purchases,
                    SUM(amount) as total_revenue
                FROM spotplayer_purchases
                WHERE product_id = ?""",
                (product_id,)
            )
            
            result = cursor.fetchone()
            
            return {
                'total_purchases': result[0] or 0,
                'total_revenue': (result[1] or 0) // 10  # Convert to Tomans
            }
            
        except Exception as e:
            logger.error(f"Error getting product stats: {e}")
            return {
                'total_purchases': 0,
                'total_revenue': 0
            }
    
    def _format_price(self, amount: int) -> str:
        """Format price with thousand separators"""
        return f"{amount:,}"
    
    def initialize_default_products(self):
        """Initialize default products based on requirements"""
        default_products = [
            {
                'name': 'هایپربول',
                'description': 'دوره آموزشی هایپربول',
                'price': 50000,  # 5000 tomans = 50000 rials
                'course_id': 'hyperbole_course',  # Replace with actual course ID
                'subscription_days': 120,
                'channel': 'vip'
            },
            {
                'name': 'فارکس',
                'description': 'دوره آموزشی فارکس',
                'price': 1000,  # 100 tomans = 1000 rials
                'course_id': 'forex_course',  # Replace with actual course ID
                'subscription_days': 90,
                'channel': 'forex'
            }
        ]
        
        for product_data in default_products:
            # Check if product exists
            existing = self.get_product_by_name(product_data['name'])
            
            if not existing:
                channel_info = self.available_channels.get(product_data['channel'], {})
                
                self.add_product(
                    name=product_data['name'],
                    description=product_data['description'],
                    price=product_data['price'],
                    course_id=product_data['course_id'],
                    subscription_days=product_data['subscription_days'],
                    channel_id=channel_info.get('id', ''),
                    channel_username=channel_info.get('username', '')
                )
                
                logger.info(f"Initialized product: {product_data['name']}")
    
    async def handle_product_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle product-related callbacks"""
        query = update.callback_query
        await query.answer()
        
        # Extract action from callback data
        data = query.data
        if data.startswith("sp_product_view_"):
            product_id = int(data.split("_")[-1])
            await self.show_product_detail(update, context, product_id)
    
    async def add_product_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start adding a new product"""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "➕ افزودن محصول SpotPlayer جدید\n\n"
            "برای افزودن محصول جدید، از بخش مدیریت محصولات استفاده کنید.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data="spotplayer_admin_menu")
            ]])
        )
    
    async def edit_product_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start editing a product"""
        query = update.callback_query
        await query.answer()
        
        product_id = int(query.data.split("_")[-1])
        await query.edit_message_text(
            f"✏️ ویرایش محصول {product_id}\n\n"
            "از بخش مدیریت محصولات برای ویرایش استفاده کنید.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data=f"sp_admin_product_{product_id}")
            ]])
        )
    
    async def delete_product_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirm product deletion"""
        query = update.callback_query
        await query.answer()
        
        product_id = int(query.data.split("_")[-1])
        
        keyboard = [
            [
                InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"sp_confirm_delete_{product_id}"),
                InlineKeyboardButton("❌ خیر", callback_data=f"sp_admin_product_{product_id}")
            ]
        ]
        
        await query.edit_message_text(
            "⚠️ آیا از حذف این محصول اطمینان دارید؟\n"
            "این عمل قابل بازگشت نیست!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def handle_product_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show product sales report"""
        query = update.callback_query
        await query.answer()
        
        product_id = int(query.data.split("_")[-1])
        
        await query.edit_message_text(
            f"📊 گزارش فروش محصول {product_id}\n\n"
            "گزارش فروش در حال آماده‌سازی است...",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data=f"sp_admin_product_{product_id}")
            ]])
        )
    
    async def show_product_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int):
        """Show detailed view of a product"""
        query = update.callback_query
        
        await query.edit_message_text(
            f"📦 جزئیات محصول {product_id}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data="sp_admin_products")
            ]])
        )
    
    def get_product_by_name(self, name: str) -> Optional[Dict]:
        """Get product by name"""
        try:
            cursor = self.db.connection.cursor()
            cursor.execute(
                "SELECT * FROM spotplayer_products WHERE name = ?",
                (name,)
            )
            
            row = cursor.fetchone()
            if not row:
                return None
            
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
            
        except Exception as e:
            logger.error(f"Error getting product by name: {e}")
            return None

def get_product_manager_handlers(db_queries):
    """Return list of handlers for product manager"""
    manager = SpotPlayerProductManager(db_queries)
    
    return [
        CallbackQueryHandler(
            manager.show_products_menu, 
            pattern="^sp_admin_products$"
        ),
        CallbackQueryHandler(
            manager.handle_product_callback,
            pattern="^sp_product_"
        ),
        CallbackQueryHandler(
            manager.add_product_start,
            pattern="^sp_admin_add_product$"
        ),
        CallbackQueryHandler(
            manager.edit_product_start,
            pattern="^sp_admin_edit_"
        ),
        CallbackQueryHandler(
            manager.delete_product_confirm,
            pattern="^sp_admin_delete_"
        ),
        CallbackQueryHandler(
            manager.handle_product_report,
            pattern="^sp_admin_product_report_"
        )
    ]
