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
    """مدیریت دکمه تبلیغاتی دسته‌بندی و محصولات"""
    
    @staticmethod
    def get_promotional_category_status():
        """دریافت وضعیت فعلی دکمه تبلیغاتی (برای سازگاری با کد قدیمی)"""
        buttons = PromotionalCategoryManager.get_all_promotional_buttons()
        if buttons:
            # برگرداندن اولین دکمه برای سازگاری
            return buttons[0]
        else:
            return {
                'enabled': False,
                'item_id': None,
                'category_id': None,
                'button_text': None,
                'item_name': None,
                'category_name': None,
                'item_type': None
            }
    
    @staticmethod
    def get_all_promotional_buttons():
        """دریافت تمام دکمه‌های تبلیغاتی فعال"""
        try:
            db = Database.get_instance()
            # جدیدترین دکمه‌ها ابتدا نمایش داده می‌شوند (newest first)
            db.execute("SELECT * FROM promotional_category_settings WHERE enabled = 1 ORDER BY id DESC")
            results = db.fetchall()
            
            buttons = []
            for result in results:
                if hasattr(result, 'keys'):
                    result = dict(result)
                buttons.append({
                    'id': result['id'],
                    'enabled': bool(result['enabled']),
                    'item_id': result.get('category_id') or result.get('item_id'),
                    'category_id': result.get('category_id'),
                    'button_text': result['button_text'],
                    'item_name': result.get('category_name') or result.get('item_name', 'Unknown'),
                    'category_name': result.get('category_name'),
                    'item_type': result.get('item_type', 'category'),
                    'display_order': result.get('display_order', 0)
                })
            return buttons
        except Exception as e:
            logger.error(f"Error getting promotional buttons: {e}")
            return []
    
    @staticmethod
    def set_promotional_category(category_id: int, button_text: str, enabled: bool = True):
        """تنظیم دکمه تبلیغاتی دسته‌بندی (برای مطابقت با قدیمی)"""
        try:
            db = Database.get_instance()
            
            # دریافت نام دسته‌بندی
            category = DatabaseQueries.get_category_by_id(category_id)
            category_name = category['name'] if category else f"دسته {category_id}"
            
            # اضافه کردن دکمه جدید (بدون جایگزینی)
            db.execute("""
                INSERT INTO promotional_category_settings 
                (category_id, item_id, button_text, category_name, item_name, item_type, enabled, display_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT COALESCE(MAX(display_order), 0) + 1 FROM promotional_category_settings), datetime('now'), datetime('now'))
            """, (category_id, category_id, button_text, category_name, category_name, 'category', enabled))
            
            db.commit()
            logger.info(f"Promotional category set: {category_name} -> {button_text} (enabled: {enabled})")
            return True
            
        except Exception as e:
            logger.error(f"Error setting promotional category: {e}")
            return False
    
    @staticmethod
    def set_promotional_item(item_id: int, button_text: str, item_name: str, item_type: str = "category", enabled: bool = True):
        """تنظیم دکمه تبلیغاتی (دسته‌بندی یا محصول)"""
        try:
            db = Database.get_instance()
            
            # برای مطابقت با طرح اولیهٔ جدول که ستون‌های «category_id» و «category_name» را NOT NULL تعریف کرده بود،
            # این ستون‌ها را همیشه مقداردهی می‌کنیم. در حالت محصول، این مقادیر صرفاً همان شناسه و نام محصول خواهند بود.
            # این کار از بروز خطای «NOT NULL constraint failed» جلوگیری می‌کند و در منطق فعلیِ بازیابی داده‌ها نیز مشکلی ایجاد نمی‌کند.
            category_id = item_id  # حتی برای محصول مقداردهی می‌شود تا محدودیت NOT NULL نقض نشود
            category_name = item_name
            
            # اضافه کردن آیتم جدید (بدون جایگزینی)
            db.execute("""
                INSERT INTO promotional_category_settings 
                (category_id, item_id, button_text, category_name, item_name, item_type, enabled, display_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, (SELECT COALESCE(MAX(display_order), 0) + 1 FROM promotional_category_settings), datetime('now'), datetime('now'))
            """, (category_id, item_id, button_text, category_name, item_name, item_type, enabled))
            
            db.commit()
            logger.info(f"Promotional {item_type} set: {item_name} -> {button_text} (enabled: {enabled})")
            return True
            
        except Exception as e:
            logger.error(f"Error setting promotional {item_type}: {e}")
            return False
    
    @staticmethod
    def add_promotional_button(item_id: int, button_text: str, item_name: str, item_type: str = "category"):
        """اضافه کردن دکمه تبلیغاتی جدید"""
        return PromotionalCategoryManager.set_promotional_item(item_id, button_text, item_name, item_type, enabled=True)
    
    @staticmethod
    def remove_promotional_button(button_id: int):
        """حذف دکمه تبلیغاتی"""
        try:
            db = Database.get_instance()
            db.execute("DELETE FROM promotional_category_settings WHERE id = ?", (button_id,))
            db.commit()
            logger.info(f"Promotional button {button_id} removed")
            return True
        except Exception as e:
            logger.error(f"Error removing promotional button: {e}")
            return False
    
    @staticmethod
    def get_promotional_button_by_id(button_id: int):
        """دریافت اطلاعات دکمه تبلیغاتی با ID"""
        try:
            db = Database.get_instance()
            db.execute("""
                SELECT id, category_id, item_id, button_text, category_name, item_name, 
                       item_type, enabled, display_order, created_at, updated_at
                FROM promotional_category_settings 
                WHERE id = ?
            """, (button_id,))
            result = db.fetchone()
            if result:
                return {
                    'id': result[0],
                    'category_id': result[1],
                    'item_id': result[2],
                    'button_text': result[3],
                    'category_name': result[4],
                    'item_name': result[5],
                    'item_type': result[6],
                    'enabled': bool(result[7]),
                    'display_order': result[8],
                    'created_at': result[9],
                    'updated_at': result[10]
                }
            return None
        except Exception as e:
            logger.error(f"Error getting promotional button by ID: {e}")
            return None
    
    @staticmethod
    def toggle_promotional_button(button_id: int):
        """فعال/غیرفعال کردن دکمه تبلیغاتی"""
        try:
            db = Database.get_instance()
            db.execute("SELECT enabled FROM promotional_category_settings WHERE id = ?", (button_id,))
            result = db.fetchone()
            if result:
                new_status = not bool(result[0])
                db.execute("UPDATE promotional_category_settings SET enabled = ?, updated_at = datetime('now') WHERE id = ?", (new_status, button_id))
                db.commit()
                logger.info(f"Promotional button {button_id} toggled to {new_status}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error toggling promotional button: {e}")
            return False
    
    @staticmethod
    def update_button_order(button_id: int, new_order: int):
        """تغییر ترتیب نمایش دکمه"""
        try:
            db = Database.get_instance()
            db.execute("UPDATE promotional_category_settings SET display_order = ?, updated_at = datetime('now') WHERE id = ?", (new_order, button_id))
            db.commit()
            logger.info(f"Button {button_id} order updated to {new_order}")
            return True
        except Exception as e:
            logger.error(f"Error updating button order: {e}")
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
    """نمایش منوی مدیریت دکمه‌های تبلیغاتی"""
    query = update.callback_query
    await query.answer()
    
    # بررسی دسترسی ادمین
    if not _is_admin(update.effective_user.id):
        await query.edit_message_text("❌ شما دسترسی ادمین ندارید.")
        return
    
    # دریافت تمام دکمه‌های تبلیغاتی
    buttons = PromotionalCategoryManager.get_all_promotional_buttons()
    
    # ساخت متن وضعیت
    if buttons:
        status_text = f"📊 تعداد دکمه‌های فعال: {len(buttons)}\n\n"
        for i, button in enumerate(buttons, 1):
            status_icon = "✅" if button['enabled'] else "❌"
            status_text += f"{i}. {status_icon} {button['item_name']}\n"
            status_text += f"   🔤 متن: {button['button_text']}\n\n"
        status_text += "💡 این دکمه‌ها در کنار دکمه \"🌊 میخوای بدونی آلت‌سیزن چیه؟\" نمایش داده می‌شوند."
    else:
        status_text = "📊 وضعیت: ❌ هیچ دکمه تبلیغاتی فعالی وجود ندارد.\n\n💡 برای شروع، یک دکمه تبلیغاتی اضافه کنید."
    
    text = f"🎯 مدیریت دکمه‌های تبلیغاتی\n\n{status_text}"
    
    # ساخت کیبورد
    keyboard = [
        [InlineKeyboardButton("➕ افزودن دکمه جدید", callback_data="promo_select_category")]
    ]
    
    # اضافه کردن گزینه مدیریت دکمه‌های موجود اگر دکمه‌ای وجود دارد
    if buttons:
        keyboard.append([InlineKeyboardButton("📝 مدیریت دکمه‌های موجود", callback_data="manage_existing_buttons")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_settings")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def show_category_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست دسته‌بندی‌ها و محصولات برای انتخاب"""
    query = update.callback_query
    await query.answer()
    
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("❌ شما دسترسی لازم را ندارید.")
        return
    
    # دریافت کل درخت دسته‌بندی به‌همراه زیردسته‌ها
    category_tree = DatabaseQueries.get_category_tree() or []
    
    # دریافت تمامی محصولات فعال
    all_plans = DatabaseQueries.get_all_plans() or []

    # Helper to flatten tree with indentation for better visual hit
    def _flatten(tree: list[dict], level: int = 0):
        flat: list[tuple[int, str, str]] = []  # (id, name, type)
        prefix = "  " * level  # دو فاصله برای هر سطح
        for node in tree:
            cid = node.get("id")
            cname = node.get("name", "-")
            flat.append((cid, f"{prefix}📂 {cname}", "category"))
            children = node.get("children")
            if children:
                flat.extend(_flatten(children, level + 1))
        return flat

    categories_flat = _flatten(category_tree)
    
    # اضافه کردن محصولات به لیست
    items_list = categories_flat.copy()
    for plan in all_plans:
        try:
            # تبدیل به dict برای اطمینان
            if hasattr(plan, 'keys'):
                plan_dict = dict(plan)
            else:
                plan_dict = plan
            
            # دریافت ID و نام
            if isinstance(plan_dict, dict):
                plan_id = plan_dict.get("id")
                plan_name = plan_dict.get("name", "-")
            else:
                # اگر هنوز sqlite3.Row هست
                plan_id = plan_dict["id"]
                plan_name = plan_dict["name"] if "name" in plan_dict else "-"
            
            items_list.append((plan_id, f"📦 {plan_name}", "product"))
        except Exception as e:
            logger.error(f"Error processing plan: {e}")
            continue

    if not items_list:
        await query.edit_message_text(
            "❌ هیچ دسته‌بندی یا محصولی یافت نشد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]]),
        )
        return

    message = "📂 **انتخاب دسته‌بندی یا محصول**\n\nلطفاً دسته‌بندی یا محصول مورد نظر را انتخاب کنید:\n\n📂 = دسته‌بندی\n📦 = محصول"

    keyboard: list[list[InlineKeyboardButton]] = []
    for item_id, item_name, item_type in items_list:
        if item_type == "category":
            callback_data = f"promo_set_category_{item_id}"
        else:  # product
            callback_data = f"promo_set_product_{item_id}"
        keyboard.append([InlineKeyboardButton(item_name, callback_data=callback_data)])

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
    
    # تبدیل sqlite3.Row به dict اگر لازم باشد
    if hasattr(category, 'keys'):
        category_dict = dict(category)
    else:
        category_dict = category
    
    if isinstance(category_dict, dict):
        category_name = category_dict.get('name', f'دسته {category_id}')
    else:
        category_name = category_dict['name'] if 'name' in category_dict else f'دسته {category_id}'
    
    # تنظیم دکمه تبلیغاتی
    button_text = f"🛍️ {category_name}"
    success = PromotionalCategoryManager.set_promotional_item(
        item_id=category_id, 
        button_text=button_text, 
        item_name=category_name,
        item_type="category",
        enabled=True
    )
    
    if success:
        await query.edit_message_text(
            f"✅ **دکمه تبلیغاتی تنظیم شد!**\n\n"
            f"📂 **دسته:** {category_name}\n"
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
    if not status['item_id']:
        await update.message.reply_text("❌ ابتدا باید یک دسته‌بندی یا محصول انتخاب کنید.")
        context.user_data.pop('awaiting_new_promo_text', None)
        return

    success = PromotionalCategoryManager.set_promotional_item(
        item_id=status['item_id'], 
        button_text=new_text, 
        item_name=status['item_name'],
        item_type=status['item_type'],
        enabled=status['enabled']
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

async def set_promotional_product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم محصول تبلیغاتی"""
    query = update.callback_query
    await query.answer()
    
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("❌ شما دسترسی لازم را ندارید.")
        return
    
    # استخراج ID محصول از callback data
    try:
        product_id = int(query.data.split("_")[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(
            "❌ خطا در دریافت اطلاعات محصول.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]]),
        )
        return
    
    # دریافت اطلاعات محصول
    product = DatabaseQueries.get_plan_by_id(product_id)
    if not product:
        await query.edit_message_text(
            "❌ محصول یافت نشد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]]),
        )
        return
    
    # تبدیل sqlite3.Row به dict اگر لازم باشد
    if hasattr(product, 'keys'):
        product_dict = dict(product)
    else:
        product_dict = product
    
    if isinstance(product_dict, dict):
        product_name = product_dict.get('name', f'محصول {product_id}')
    else:
        product_name = product_dict['name'] if 'name' in product_dict else f'محصول {product_id}'
    
    # پیام پیش‌فرض برای دکمه تبلیغاتی محصول
    default_button_text = f"🌟 {product_name} - ویژه!"
    
    success = PromotionalCategoryManager.set_promotional_item(
        item_id=product_id, 
        button_text=default_button_text, 
        item_name=product_name,
        item_type="product",
        enabled=True
    )
    
    if success:
        await query.edit_message_text(
            f"✅ **محصول تبلیغاتی تنظیم شد**\n\n"
            f"📦 **محصول:** {product_name}\n"
            f"🔤 **متن دکمه:** {default_button_text}\n\n"
            f"💡 می‌توانید متن دکمه را تغییر دهید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ تغییر متن دکمه", callback_data="promo_change_text")],
                [InlineKeyboardButton("🔄 فعال/غیرفعال", callback_data="promo_toggle")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]
            ]),
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text(
            "❌ خطا در تنظیم محصول تبلیغاتی.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]]),
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
        
        # بررسی وجود جدول
        db.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='promotional_category_settings'
        """)
        table_exists = db.fetchone() is not None
        
        if not table_exists:
            # ایجاد جدول جدید با تمام فیلدها
            db.execute("""
                CREATE TABLE promotional_category_settings (
                    id INTEGER PRIMARY KEY,
                    category_id INTEGER,
                    item_id INTEGER,
                    button_text TEXT NOT NULL,
                    category_name TEXT,
                    item_name TEXT,
                    item_type TEXT DEFAULT 'category',
                    enabled BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            logger.info("✅ Created new promotional_category_settings table with all fields")
        else:
            # بررسی و اضافه کردن فیلدهای گمشده
            # بررسی وجود فیلد item_id
            db.execute("PRAGMA table_info(promotional_category_settings)")
            columns = [row[1] for row in db.fetchall()]  # column names
            
            missing_columns = []
            if 'item_id' not in columns:
                missing_columns.append('item_id')
            if 'item_name' not in columns:
                missing_columns.append('item_name')
            if 'item_type' not in columns:
                missing_columns.append('item_type')
            if 'display_order' not in columns:
                missing_columns.append('display_order')
            
            # اضافه کردن فیلدهای گمشده
            for column in missing_columns:
                if column == 'item_id':
                    db.execute("ALTER TABLE promotional_category_settings ADD COLUMN item_id INTEGER")
                elif column == 'item_name':
                    db.execute("ALTER TABLE promotional_category_settings ADD COLUMN item_name TEXT")
                elif column == 'item_type':
                    db.execute("ALTER TABLE promotional_category_settings ADD COLUMN item_type TEXT DEFAULT 'category'")
                elif column == 'display_order':
                    db.execute("ALTER TABLE promotional_category_settings ADD COLUMN display_order INTEGER DEFAULT 0")
                logger.info(f"✅ Added missing column: {column}")
            
            # به‌روزرسانی رکوردهای قدیمی
            if missing_columns:
                db.execute("""
                    UPDATE promotional_category_settings 
                    SET item_id = COALESCE(item_id, category_id), 
                        item_name = COALESCE(item_name, category_name), 
                        item_type = COALESCE(item_type, 'category')
                    WHERE id = 1
                """)
                logger.info("✅ Updated existing records with new field values")
        
        db.commit()
        logger.info("✅ Promotional category settings table verified and updated")
    except Exception as e:
        logger.error(f"Error creating/updating promotional category table: {e}")
        # در صورت خطا، جدول را بازسازی کنیم
        try:
            logger.warning("Attempting to recreate table...")
            db.execute("DROP TABLE IF EXISTS promotional_category_settings_backup")
            db.execute("CREATE TABLE promotional_category_settings_backup AS SELECT * FROM promotional_category_settings")
            db.execute("DROP TABLE promotional_category_settings")
            
            db.execute("""
                CREATE TABLE promotional_category_settings (
                    id INTEGER PRIMARY KEY,
                    category_id INTEGER,
                    item_id INTEGER,
                    button_text TEXT NOT NULL,
                    category_name TEXT,
                    item_name TEXT,
                    item_type TEXT DEFAULT 'category',
                    enabled BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # بازگرداندن داده‌ها
            db.execute("""
                INSERT INTO promotional_category_settings 
                (id, category_id, item_id, button_text, category_name, item_name, item_type, enabled, created_at, updated_at)
                SELECT id, category_id, category_id, button_text, category_name, category_name, 'category', enabled, created_at, updated_at
                FROM promotional_category_settings_backup
            """)
            
            db.execute("DROP TABLE promotional_category_settings_backup")
            db.commit()
            logger.info("✅ Successfully recreated table with backup data")
        except Exception as e2:
            logger.error(f"Failed to recreate table: {e2}")

# اجرای اجباری ایجاد و به‌روزرسانی جدول
try:
    create_promotional_category_table()
    # Force migration check again
    logger.info("🔧 Running forced migration check...")
    db = Database.get_instance()
    
    # Check if we have the new columns
    db.execute("PRAGMA table_info(promotional_category_settings)")
    columns = [row[1] for row in db.fetchall()]
    
    if 'item_id' not in columns:
        logger.warning("❌ item_id column still missing, attempting direct migration...")
        db.execute("ALTER TABLE promotional_category_settings ADD COLUMN item_id INTEGER")
        db.execute("ALTER TABLE promotional_category_settings ADD COLUMN item_name TEXT")
        db.execute("ALTER TABLE promotional_category_settings ADD COLUMN item_type TEXT DEFAULT 'category'")
        db.execute("""
            UPDATE promotional_category_settings 
            SET item_id = category_id, item_name = category_name, item_type = 'category'
            WHERE category_id IS NOT NULL
        """)
        db.commit()
        logger.info("✅ Direct migration completed successfully")
    else:
        logger.info("✅ All required columns exist")
        
    # Check if we need to fix category_id NOT NULL constraint
    try:
        # Try inserting a test record with NULL category_id
        db.execute("""
            INSERT OR IGNORE INTO promotional_category_settings 
            (category_id, item_id, button_text, item_name, item_type, enabled) 
            VALUES (NULL, 999, 'test', 'test', 'product', 0)
        """)
        db.execute("DELETE FROM promotional_category_settings WHERE item_id = 999")
        db.commit()
        logger.info("✅ category_id NULL constraint is working correctly")
    except Exception as constraint_error:
        logger.warning(f"❌ category_id constraint issue detected: {constraint_error}")
        logger.info("🔧 Recreating table to fix constraints...")
        # Force table recreation
        db.execute("DROP TABLE IF EXISTS promotional_category_settings_temp")
        db.execute("""
            CREATE TABLE promotional_category_settings_temp (
                id INTEGER PRIMARY KEY,
                category_id INTEGER,
                item_id INTEGER,
                button_text TEXT NOT NULL,
                category_name TEXT,
                item_name TEXT,
                item_type TEXT DEFAULT 'category',
                enabled BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Copy existing data
        db.execute("""
            INSERT INTO promotional_category_settings_temp 
            (id, category_id, item_id, button_text, category_name, item_name, item_type, enabled, created_at, updated_at)
            SELECT id, category_id, 
                   COALESCE(item_id, category_id) as item_id,
                   button_text, category_name, 
                   COALESCE(item_name, category_name) as item_name,
                   COALESCE(item_type, 'category') as item_type,
                   enabled, created_at, updated_at
            FROM promotional_category_settings
        """)
        
        # Replace tables
        db.execute("DROP TABLE promotional_category_settings")
        db.execute("ALTER TABLE promotional_category_settings_temp RENAME TO promotional_category_settings")
        db.commit()
        logger.info("✅ Successfully recreated table with fixed constraints")
except Exception as e:
    logger.error(f"❌ Migration failed: {e}")

# ---- Handler های جدید برای مدیریت چندین دکمه تبلیغاتی ----

async def manage_existing_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست دکمه‌های موجود برای مدیریت"""
    query = update.callback_query
    await query.answer()
    
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("❌ شما دسترسی ادمین ندارید.")
        return
    
    # دریافت تمام دکمه‌های تبلیغاتی
    buttons = PromotionalCategoryManager.get_all_promotional_buttons()
    
    if not buttons:
        await query.edit_message_text(
            "📭 هیچ دکمه تبلیغاتی موجود نیست.\n\n"
            "برای اضافه کردن دکمه جدید، از گزینه 'افزودن دکمه جدید' استفاده کنید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]
            ])
        )
        return
    
    # ساخت پیام و کیبورد
    message = "📋 **مدیریت دکمه‌های تبلیغاتی**\n\n"
    keyboard = []
    
    for i, button in enumerate(buttons, 1):
        status_icon = "✅" if button.get('enabled', True) else "❌"
        button_text = button.get('button_text', 'نامشخص')
        button_id = button.get('id')
        
        message += f"{i}. {status_icon} **{button.get('item_name', 'نامشخص')}**\n"
        message += f"   🔤 متن: {button_text}\n"
        message += f"   🏷️ نوع: {button.get('item_type', 'نامشخص')}\n\n"
        
        # دکمه‌های مدیریت برای هر آیتم
        keyboard.append([
            InlineKeyboardButton(f"✏️ ویرایش متن #{i}", callback_data=f"edit_button_text_{button_id}"),
            InlineKeyboardButton(f"🔄 تغییر وضعیت #{i}", callback_data=f"toggle_button_{button_id}")
        ])
        keyboard.append([
            InlineKeyboardButton(f"🗑️ حذف #{i}", callback_data=f"delete_button_{button_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")])
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
        )

async def edit_button_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ویرایش متن دکمه تبلیغاتی"""
    query = update.callback_query
    await query.answer()
    
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("❌ شما دسترسی ادمین ندارید.")
        return
    
    # استخراج ID دکمه از callback_data
    try:
        button_id = int(query.data.split('_')[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(
            "❌ خطا در شناسایی دکمه.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت", callback_data="manage_existing_buttons")]
            ])
        )
        return
    
    # دریافت اطلاعات دکمه
    button = PromotionalCategoryManager.get_promotional_button_by_id(button_id)
    if not button:
        await query.edit_message_text(
            "❌ دکمه یافت نشد.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت", callback_data="manage_existing_buttons")]
            ])
        )
        return
    
    # ذخیره ID دکمه در context برای استفاده در مرحله بعد
    context.user_data['editing_button_id'] = button_id
    
    await query.edit_message_text(
        f"✏️ **ویرایش متن دکمه**\n\n"
        f"📦 **دکمه:** {button.get('item_name', 'نامشخص')}\n"
        f"🔤 **متن فعلی:** {button.get('button_text', 'نامشخص')}\n\n"
        f"💬 لطفاً متن جدید دکمه را ارسال کنید:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ لغو", callback_data="manage_existing_buttons")]
        ]),
        parse_mode="Markdown"
    )
    
    # Return conversation state for button text editing
    return 1  # AWAIT_BUTTON_TEXT

async def receive_new_button_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت متن جدید دکمه از کاربر"""
    if not _is_admin(update.effective_user.id):
        await update.message.reply_text("❌ شما دسترسی ادمین ندارید.")
        return
    
    # بررسی وجود ID دکمه در context
    button_id = context.user_data.get('editing_button_id')
    if not button_id:
        # اگر در حال ویرایش نیستیم، پیام را نادیده می‌گیریم
        return
    
    new_text = update.message.text.strip()
    if not new_text:
        await update.message.reply_text("❌ متن نمی‌تواند خالی باشد.")
        return
    
    # به‌روزرسانی متن دکمه
    try:
        db = Database.get_instance()
        db.execute(
            "UPDATE promotional_category_settings SET button_text = ?, updated_at = datetime('now') WHERE id = ?",
            (new_text, button_id)
        )
        db.commit()
        
        # پاک کردن context
        context.user_data.pop('editing_button_id', None)
        
        # دریافت اطلاعات به‌روزرسانی شده
        button = PromotionalCategoryManager.get_promotional_button_by_id(button_id)
        
        await update.message.reply_text(
            f"✅ **متن دکمه به‌روزرسانی شد**\n\n"
            f"📦 **دکمه:** {button.get('item_name', 'نامشخص')}\n"
            f"🔤 **متن جدید:** {new_text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 مدیریت دکمه‌ها", callback_data="manage_existing_buttons")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]
            ]),
            parse_mode="Markdown"
        )
        
        # End conversation
        from telegram.ext import ConversationHandler
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error updating button text: {e}")
        await update.message.reply_text(
            "❌ خطا در به‌روزرسانی متن دکمه.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 مدیریت دکمه‌ها", callback_data="manage_existing_buttons")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]
            ])
        )
        
        # End conversation even on error
        from telegram.ext import ConversationHandler
        return ConversationHandler.END

async def toggle_promotional_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغییر وضعیت فعال/غیرفعال دکمه تبلیغاتی"""
    query = update.callback_query
    await query.answer()
    
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("❌ شما دسترسی ادمین ندارید.")
        return
    
    # استخراج ID دکمه از callback_data
    try:
        button_id = int(query.data.split('_')[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(
            "❌ خطا در شناسایی دکمه.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت", callback_data="manage_existing_buttons")]
            ])
        )
        return
    
    # تغییر وضعیت دکمه
    success = PromotionalCategoryManager.toggle_promotional_button(button_id)
    
    if success:
        # دریافت وضعیت جدید
        button = PromotionalCategoryManager.get_promotional_button_by_id(button_id)
        if button:
            status = "فعال" if button.get('enabled', True) else "غیرفعال"
            await query.edit_message_text(
                f"✅ **وضعیت دکمه تغییر یافت**\n\n"
                f"📦 **دکمه:** {button.get('item_name', 'نامشخص')}\n"
                f"🔄 **وضعیت جدید:** {status}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 مدیریت دکمه‌ها", callback_data="manage_existing_buttons")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]
                ]),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                "✅ وضعیت دکمه تغییر یافت.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 مدیریت دکمه‌ها", callback_data="manage_existing_buttons")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]
                ])
            )
    else:
        await query.edit_message_text(
            "❌ خطا در تغییر وضعیت دکمه.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 مدیریت دکمه‌ها", callback_data="manage_existing_buttons")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]
            ])
        )

async def delete_promotional_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف دکمه تبلیغاتی"""
    query = update.callback_query
    await query.answer()
    
    if not _is_admin(query.from_user.id):
        await query.edit_message_text("❌ شما دسترسی ادمین ندارید.")
        return
    
    # استخراج ID دکمه از callback_data
    try:
        button_id = int(query.data.split('_')[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(
            "❌ خطا در شناسایی دکمه.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت", callback_data="manage_existing_buttons")]
            ])
        )
        return
    
    # دریافت اطلاعات دکمه قبل از حذف
    button = PromotionalCategoryManager.get_promotional_button_by_id(button_id)
    button_name = button.get('item_name', 'نامشخص') if button else 'نامشخص'
    
    # حذف دکمه
    success = PromotionalCategoryManager.remove_promotional_button(button_id)
    
    if success:
        await query.edit_message_text(
            f"✅ **دکمه حذف شد**\n\n"
            f"🗑️ **دکمه حذف شده:** {button_name}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 مدیریت دکمه‌ها", callback_data="manage_existing_buttons")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]
            ]),
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            "❌ خطا در حذف دکمه.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 مدیریت دکمه‌ها", callback_data="manage_existing_buttons")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="promo_category_admin")]
            ])
        )
