"""
🎯 سیستم مدیریت دکمه تبلیغاتی دسته‌بندی برای ادمین
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.queries import DatabaseQueries
from database.models import Database
import logging

logger = logging.getLogger(__name__)

class PromotionalCategoryManager:
    """مدیریت دکمه تبلیغاتی دسته‌بندی"""
    
    @staticmethod
    def get_promotional_category_status():
        """دریافت وضعیت فعلی دکمه تبلیغاتی"""
        try:
            db = Database.get_instance()
            # اجرای کوئری با کرسر داخلی Singleton
            db.execute("SELECT * FROM promotional_category_settings ORDER BY id DESC LIMIT 1")
            result = db.fetchone()
            
            if result:
                # Convert Row to dict if needed
                if hasattr(result, 'keys'):
                    result = dict(result)
                return {
                    'enabled': bool(result['enabled']),
                    'category_id': result['category_id'],
                    'button_text': result['button_text'],
                    'category_name': result['category_name']
                }
            else:
                return {
                    'enabled': False,
                    'category_id': None,
                    'button_text': None,
                    'category_name': None
                }
        except Exception as e:
            logger.error(f"Error getting promotional category status: {e}")
            return {'enabled': False, 'category_id': None, 'button_text': None, 'category_name': None}
    
    @staticmethod
    def set_promotional_category(category_id: int, button_text: str, enabled: bool = True):
        """تنظیم دکمه تبلیغاتی"""
        try:
            db = Database.get_instance()
            
            # دریافت نام دسته‌بندی
            category = DatabaseQueries.get_category_by_id(category_id)
            category_name = category['name'] if category else f"دسته {category_id}"
            
            # ایجاد یا بروزرسانی تنظیمات
            db.execute("""
                INSERT OR REPLACE INTO promotional_category_settings 
                (id, category_id, button_text, category_name, enabled, created_at, updated_at)
                VALUES (1, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """, (category_id, button_text, category_name, enabled))
            
            db.commit()
            logger.info(f"Promotional category set: {category_name} -> {button_text} (enabled: {enabled})")
            return True
            
        except Exception as e:
            logger.error(f"Error setting promotional category: {e}")
            return False
    
    @staticmethod
    def toggle_promotional_category():
        """فعال/غیرفعال کردن دکمه تبلیغاتی"""
        try:
            db = Database.get_instance()
            current = PromotionalCategoryManager.get_promotional_category_status()
            
            new_status = not current['enabled']
            
            db.execute("""
                UPDATE promotional_category_settings 
                SET enabled = ?, updated_at = datetime('now')
                WHERE id = 1
            """, (new_status,))
            
            db.commit()
            logger.info(f"Promotional category toggled to: {new_status}")
            return new_status
            
        except Exception as e:
            logger.error(f"Error toggling promotional category: {e}")
            return False

async def show_promotional_category_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی مدیریت دکمه تبلیغاتی"""
    query = update.callback_query
    await query.answer()
    
    # بررسی دسترسی ادمین
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("❌ شما دسترسی لازم را ندارید.")
        return
    
    status = PromotionalCategoryManager.get_promotional_category_status()
    
    status_text = "✅ فعال" if status['enabled'] else "❌ غیرفعال"
    current_cat = status['category_name'] if status['category_id'] else "انتخاب نشده"
    current_text = status['button_text'] if status['button_text'] else "تعریف نشده"
    
    message = (
        "🎯 **مدیریت دکمه تبلیغاتی دسته‌بندی**\n\n"
        f"📊 **وضعیت:** {status_text}\n"
        f"📂 **دسته انتخابی:** {current_cat}\n"
        f"🔤 **متن دکمه:** {current_text}\n\n"
        "💡 این دکمه در کنار دکمه \"🌊 میخوای بدونی آلت‌سیزن چیه؟\" نمایش داده می‌شود."
    )
    
    keyboard = [
        [InlineKeyboardButton("📂 انتخاب دسته‌بندی", callback_data="promo_select_category")],
        [InlineKeyboardButton("✏️ تغییر متن دکمه", callback_data="promo_change_text")],
        [InlineKeyboardButton(f"{'❌ غیرفعال کردن' if status['enabled'] else '✅ فعال کردن'}", callback_data="promo_toggle")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_main_menu")]
    ]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def show_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست دسته‌بندی‌ها برای انتخاب"""
    query = update.callback_query
    await query.answer()
    
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("❌ شما دسترسی لازم را ندارید.")
        return
    
        # دریافت کل درخت دسته‌بندی به‌همراه زیردسته‌ها
    category_tree = DatabaseQueries.get_category_tree() or []

    # Helper to flatten tree with indentation for better visual hint
    def _flatten(tree: list[dict], level: int = 0):
        flat: list[tuple[int, str]] = []
        prefix = "  " * level  # دو فاصله برای هر سطح
        for node in tree:
            cid = node.get("id")
            cname = node.get("name", "-")
            flat.append((cid, f"{prefix}{cname}"))
            children = node.get("children")
            if children:
                flat.extend(_flatten(children, level + 1))
        return flat

    categories_flat = _flatten(category_tree)

    if not categories_flat:
        await query.edit_message_text(
            "❌ هیچ دسته‌بندی یافت نشد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]]),
        )
        return

    message = "📂 **انتخاب دسته‌بندی**\n\nلطفاً دسته‌بندی مورد نظر را انتخاب کنید:"

    keyboard: list[list[InlineKeyboardButton]] = []
    for cid, cname in categories_flat:
        keyboard.append([InlineKeyboardButton(cname, callback_data=f"promo_set_category_{cid}")])

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")])

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )

async def set_promotional_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم دسته‌بندی تبلیغاتی"""
    query = update.callback_query
    await query.answer()
    
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("❌ شما دسترسی لازم را ندارید.")
        return
    
    # استخراج category_id از callback_data
    try:
        category_id = int(query.data.split("_")[-1])
    except:
        await query.edit_message_text("❌ خطا در شناسه دسته‌بندی.")
        return
    
    # دریافت اطلاعات دسته‌بندی
    category = DatabaseQueries.get_category_by_id(category_id)
    if not category:
        await query.edit_message_text("❌ دسته‌بندی یافت نشد.")
        return
    
    # تنظیم دکمه تبلیغاتی
    button_text = f"🛍️ {category['name']}"
    success = PromotionalCategoryManager.set_promotional_category(
        category_id, button_text, enabled=True
    )
    
    if success:
        await query.edit_message_text(
            f"✅ **دکمه تبلیغاتی تنظیم شد!**\n\n"
            f"📂 **دسته:** {category['name']}\n"
            f"🔤 **متن دکمه:** {button_text}\n"
            f"✅ **وضعیت:** فعال\n\n"
            f"💡 این دکمه حالا در منوی اصلی کاربران نمایش داده می‌شود.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")
            ]]),
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            "❌ خطا در تنظیم دکمه تبلیغاتی.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")
            ]])
        )

async def prompt_promotional_change_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش پیام درخواست متن جدید دکمه"""
    query = update.callback_query
    await query.answer()

    if not _is_admin(query.from_user.id):
        await query.edit_message_text("❌ شما دسترسی لازم را ندارید.")
        return

    await query.edit_message_text(
        "✏️ لطفاً متن جدید برای دکمه تبلیغاتی را ارسال کنید.\n\n" \
        "مثال: 🛒 دوره ویژه",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]])
    )

    # Move conversation to await text state
    from handlers.admin_menu_handlers import AWAIT_PROMO_TEXT  # avoid circular import issues
    return AWAIT_PROMO_TEXT

async def receive_new_promo_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت متن جدید از ادمین و ذخیره آن"""

    user_id = update.effective_user.id
    if not _is_admin(user_id):
        return  # Ignore non-admin

    new_text = update.message.text.strip()
    if not new_text:
        await update.message.reply_text("❌ متن نامعتبر است. لطفاً دوباره تلاش کنید.")
        return

    status = PromotionalCategoryManager.get_promotional_category_status()
    if not status['category_id']:
        await update.message.reply_text("❌ ابتدا باید یک دسته‌بندی انتخاب کنید.")
        context.user_data.pop('awaiting_new_promo_text', None)
        return

    success = PromotionalCategoryManager.set_promotional_category(
        status['category_id'], new_text, enabled=status['enabled']
    )

    if success:
        await update.message.reply_text(f"✅ متن دکمه به «{new_text}» تغییر یافت.")
    else:
        await update.message.reply_text("❌ خطا در ذخیره متن جدید.")

    from telegram.ext import ConversationHandler
    return ConversationHandler.END


async def toggle_promotional_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فعال/غیرفعال کردن دکمه تبلیغاتی"""
    query = update.callback_query
    await query.answer()
    
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("❌ شما دسترسی لازم را ندارید.")
        return
    
    new_status = PromotionalCategoryManager.toggle_promotional_category()
    status_text = "✅ فعال" if new_status else "❌ غیرفعال"
    
    await query.edit_message_text(
        f"🔄 **وضعیت دکمه تبلیغاتی تغییر کرد**\n\n"
        f"📊 **وضعیت جدید:** {status_text}\n\n"
        f"💡 {'دکمه در منوی اصلی کاربران نمایش داده می‌شود.' if new_status else 'دکمه از منوی اصلی کاربران حذف شد.'}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")
        ]]),
        parse_mode="Markdown"
    )

def _is_admin(user_id: int) -> bool:
    """بررسی دسترسی ادمین – هم در جدول ادمین‌ها و هم در تنظیمات config"""
    try:
        admin_ids_db = set(DatabaseQueries.get_admin_user_ids() or [])
    except Exception:
        admin_ids_db = set()

    try:
        import config
        admin_ids_cfg = set(getattr(config, "ADMIN_USER_IDS", []))
    except Exception:
        admin_ids_cfg = set()

    return user_id in admin_ids_db or user_id in admin_ids_cfg

# اضافه کردن جدول به دیتابیس
def create_promotional_category_table():
    """ایجاد جدول تنظیمات دکمه تبلیغاتی"""
    try:
        db = Database.get_instance()
        db.execute("""
            CREATE TABLE IF NOT EXISTS promotional_category_settings (
                id INTEGER PRIMARY KEY,
                category_id INTEGER NOT NULL,
                button_text TEXT NOT NULL,
                category_name TEXT NOT NULL,
                enabled BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()
        logger.info("✅ Promotional category settings table created/verified")
    except Exception as e:
        logger.error(f"Error creating promotional category table: {e}")

# اجرای ایجاد جدول
create_promotional_category_table()
