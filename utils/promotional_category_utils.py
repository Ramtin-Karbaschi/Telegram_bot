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
        
        # اگر آیتم تبلیغاتی از نوع «محصول» باشد، دکمهٔ reply-keyboard را نشان ندهیم.
        # برای محصولات، تنها دکمهٔ inline در منوی اصلی نمایش داده می‌شود تا مستقیماً به مرحلهٔ خرید برود.
        if promo_status['enabled'] and promo_status['button_text']:
            return KeyboardButton(promo_status['button_text'])
        return None
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
            # هدایت کاربر به آیتم مربوطه (دسته‌بندی یا محصول)
            item_type = promo_status.get('item_type', 'category')
            item_id = promo_status.get('item_id') or promo_status.get('category_id')
            
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

        from handlers.payment.payment_handlers import CRYPTO_PAYMENT_TIMEOUT_MINUTES
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
        # 3. ارسال پیام انتخاب روش پرداخت (مطابق مسیر VIP)
        # ------------------------------
        from utils.constants.all_constants import PAYMENT_METHOD_MESSAGE
        from utils.text_utils import buttonize_markdown as _btn_md

        plan_display_name = _btn_md(product.get("name", "محصول"))
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
        # جریان مکالمه باید به SELECT_PAYMENT_METHOD هدایت شود؛ مقدار ثابت را از ماژول پرداخت وارد می‌کنیم.
        from handlers.payment.payment_handlers import SELECT_PAYMENT_METHOD as _SELECT_PAYMENT_METHOD
        return _SELECT_PAYMENT_METHOD

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
