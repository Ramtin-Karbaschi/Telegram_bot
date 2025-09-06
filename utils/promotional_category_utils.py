"""
🎯 ابزارهای کمکی برای دکمه تبلیغاتی دسته‌بندی
"""

import logging
from telegram import KeyboardButton

logger = logging.getLogger(__name__)

def get_promotional_category_buttons():
    """دریافت تمام دکمه‌های تبلیغاتی فعال"""
    try:
        from handlers.admin_promotional_category import PromotionalCategoryManager
        buttons = PromotionalCategoryManager.get_all_promotional_buttons()
        
        keyboard_buttons = []
        for button in buttons:
            if button['enabled'] and button['button_text']:
                keyboard_buttons.append(KeyboardButton(button['button_text']))
        
        return keyboard_buttons
            
    except Exception as e:
        logger.error(f"Unable to get promotional category buttons: {e}")
        return []

def get_promotional_category_button():
    """دریافت اولین دکمه تبلیغاتی (برای سازگاری با کد قدیمی)"""
    buttons = get_promotional_category_buttons()
    return buttons[0] if buttons else None

async def handle_promotional_category_button(text: str, update, context):
    """پردازش کلیک روی دکمه‌های تبلیغاتی"""
    try:
        from handlers.admin_promotional_category import PromotionalCategoryManager
        buttons = PromotionalCategoryManager.get_all_promotional_buttons()
        
        # بررسی اینکه آیا متن با یکی از دکمه‌های تبلیغاتی مطابقت دارد
        for button in buttons:
            if (
                button['enabled'] 
                and button['button_text'] 
                and text == button['button_text']
            ):
                # هدایت کاربر به آیتم مربوطه (دسته‌بندی یا محصول)
                item_type = button.get('item_type', 'category')
                item_id = button.get('item_id') or button.get('category_id')
                
                if item_type == 'product':
                    # هدایت به محصول
                    await handle_promotional_product_click(item_id, update, context)
                else:
                    # هدایت به دسته‌بندی
                    await handle_promotional_category_click(item_id, update, context)
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error handling promotional category/product button: {e}")
        return False

async def handle_promotional_product_click(product_id: int, update, context):
    """وقتی کاربر روی دکمهٔ محصول تبلیغاتی کلیک می‌کند مستقیماً وارد مرحلهٔ انتخاب روش پرداخت شود."""
    try:
        from database.queries import DatabaseQueries
        from utils.keyboards import get_payment_methods_keyboard

        from handlers.payment import SELECT_PAYMENT_METHOD, ASK_DISCOUNT
        from config import CRYPTO_PAYMENT_TIMEOUT_MINUTES
        from utils.price_utils import get_usdt_to_irr_rate
        import math
        from datetime import datetime, timedelta

        # ------------------------------
        # 1. دریافت اطلاعات پلن انتخاب‌شده
        # ------------------------------
        product_row = DatabaseQueries.get_plan_by_id(product_id)
        if not product_row:
            await update.message.reply_text("❌ محصول یافت نشد.")
            return False

        product = dict(product_row) if hasattr(product_row, "keys") else product_row
        context.user_data.clear()
        context.user_data["selected_plan_details"] = product

        # ------------------------------
        # 2. محاسبهٔ قیمت لحظه‌ای (ریال/تتر) و ذخیره در context برای مراحل بعدی
        # ------------------------------
        usdt_rate = await get_usdt_to_irr_rate(force_refresh=True)
        if not usdt_rate:
            usdt_rate = 0  # پیدا نشدن نرخ باعث می‌شود مراحل بعدی خطا را هندل کنند

        base_currency = product.get("base_currency", "IRR")
        base_price = product.get("base_price")

        # Back-compat برای فیلدهای قدیمی
        if base_price is None:
            if product.get("price_tether") is not None:
                base_currency = "USDT"
                base_price = product["price_tether"]
            elif product.get("price") is not None:
                base_currency = "IRR"
                base_price = product["price"]

        if base_price is not None:
            if base_currency == "USDT":
                usdt_price = math.ceil(float(base_price))
                irr_price = int(usdt_price * usdt_rate * 10)  # USDT➜تومان➜ریال
            else:
                irr_price = int(float(base_price))
                usdt_price = math.ceil(irr_price / (usdt_rate * 10)) if usdt_rate else 0

            expiry_time = datetime.utcnow() + timedelta(minutes=CRYPTO_PAYMENT_TIMEOUT_MINUTES)
            context.user_data.update({
                "live_usdt_price": usdt_price,
                "live_irr_price": irr_price,
                "price_expiry": expiry_time.isoformat(),
                "base_currency": base_currency,
                "base_price": base_price,
            })

        # ------------------------------
        # 3. بررسی فعال بودن مرحله کد تخفیف و نمایش مناسب
        # ------------------------------
        from database.queries import DatabaseQueries
        from utils.keyboards import get_ask_discount_keyboard, get_payment_methods_keyboard
        from utils.text_utils import buttonize_markdown
        
        # بررسی فعال بودن مرحله کد تخفیف
        discount_step_enabled = DatabaseQueries.get_setting("enable_discount_code_step", "1") == "1"
        
        if discount_step_enabled:
            # نمایش سوال کد تخفیف
            plan_display_name = buttonize_markdown(product.get("name", "محصول"))
            message_text = f"شما پلن «{plan_display_name}» را انتخاب کرده‌اید. آیا کد تخفیف دارید؟"
            
            await update.message.reply_text(
                message_text,
                reply_markup=get_ask_discount_keyboard(),
                parse_mode="HTML"
            )
            
            return ASK_DISCOUNT
        else:
            # رد کردن مرحله کد تخفیف و نمایش مستقیم روش‌های پرداخت
            from utils.constants.all_constants import PAYMENT_METHOD_MESSAGE
            
            plan_display_name = buttonize_markdown(product.get("name", "محصول"))
            plan_price_irr_formatted = f"{irr_price:,}" if 'irr_price' in locals() else "-"
            plan_price_usdt_formatted = f"{usdt_price}" if 'usdt_price' in locals() else "-"
            
            message_text = PAYMENT_METHOD_MESSAGE.format(
                plan_name=plan_display_name,
                plan_price=plan_price_irr_formatted,
                plan_tether=plan_price_usdt_formatted
            )
            message_text += "\n\n⚠️ قیمت‌ها تا ۳۰ دقیقه اعتبار دارند."
            
            await update.message.reply_text(
                message_text,
                reply_markup=get_payment_methods_keyboard(),
                parse_mode="HTML"
            )
            
            return SELECT_PAYMENT_METHOD

    except Exception as e:
        logger.error(f"Error handling promotional product click: {e}")
        await update.message.reply_text("❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.")
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
