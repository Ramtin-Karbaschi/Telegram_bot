"""
🎯 ابزارهای کمکی برای دکمه تبلیغاتی دسته‌بندی
"""

import logging
from telegram import KeyboardButton

logger = logging.getLogger(__name__)

def get_promotional_category_button():
    """دریافت دکمه تبلیغاتی دسته‌بندی در صورت فعال بودن"""
    try:
        from handlers.admin_promotional_category import PromotionalCategoryManager
        promo_status = PromotionalCategoryManager.get_promotional_category_status()
        
        if promo_status['enabled'] and promo_status['button_text']:
            return KeyboardButton(promo_status['button_text'])
        else:
            return None
            
    except Exception as e:
        logger.error(f"Unable to get promotional category button: {e}")
        return None

async def handle_promotional_category_button(text: str, update, context):
    """پردازش کلیک روی دکمه تبلیغاتی"""
    try:
        from handlers.admin_promotional_category import PromotionalCategoryManager
        promo_status = PromotionalCategoryManager.get_promotional_category_status()
        
        # بررسی اینکه آیا متن دکمه با دکمه تبلیغاتی مطابقت دارد
        if (
            promo_status['enabled'] 
            and promo_status['button_text'] 
            and text == promo_status['button_text']
        ):
            # هدایت کاربر به دسته‌بندی مربوطه
            await handle_promotional_category_click(
                promo_status['category_id'], update, context
            )
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error handling promotional category button: {e}")
        return False

async def handle_promotional_category_click(category_id: int, update, context):
    """پردازش کلیک روی دکمه دسته‌بندی تبلیغاتی"""
    try:
        from utils.keyboards.categories_keyboard import get_categories_keyboard
        from utils.keyboards import get_subscription_plans_keyboard
        from database.queries import DatabaseQueries
        
        # دریافت اطلاعات دسته‌بندی
        category = DatabaseQueries.get_category_by_id(category_id)
        if not category:
            await update.message.reply_text("❌ دسته‌بندی یافت نشد.")
            return
        
        # بررسی اینکه آیا این دسته‌بندی فرزند دارد یا خیر
        children = DatabaseQueries.get_children_categories(category_id)
        
        if children:
            # نمایش زیردسته‌ها
            await update.message.reply_text(
                f"📂 **{category['name']}**\n\nلطفاً زیردسته مورد نظر را انتخاب کنید:",
                reply_markup=get_categories_keyboard(parent_id=category_id),
                parse_mode="Markdown"
            )
        else:
            # نمایش محصولات این دسته‌بندی
            keyboard = get_subscription_plans_keyboard(
                telegram_id=update.effective_user.id, 
                category_id=category_id
            )
            
            await update.message.reply_text(
                f"🛍️ **{category['name']}**\n\nمحصولات موجود:",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        
        # ذخیره اطلاعات در context برای navigation
        context.user_data['current_parent_category_id'] = category_id
        
        return True
        
    except Exception as e:
        logger.error(f"Error handling promotional category click: {e}")
        await update.message.reply_text("❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")
        return False
