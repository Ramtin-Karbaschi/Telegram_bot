"""
🔗 یکپارچه‌سازی دکمه تبلیغاتی در handler اصلی
"""

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from utils.promotional_category_utils import handle_promotional_category_button
import logging

logger = logging.getLogger(__name__)

async def promotional_category_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler برای پردازش کلیک روی دکمه تبلیغاتی"""
    try:
        text = update.message.text
        
        # بررسی اینکه آیا این متن مربوط به دکمه تبلیغاتی است
        handled = await handle_promotional_category_button(text, update, context)
        
        if handled:
            logger.info(f"Promotional category button handled for user {update.effective_user.id}")
            return
        
        # اگر handle نشد، ادامه معمولی
        return
        
    except Exception as e:
        logger.error(f"Error in promotional category text handler: {e}")

def get_promotional_category_handler():
    """دریافت handler برای دکمه تبلیغاتی"""
    return MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        promotional_category_text_handler
    )
