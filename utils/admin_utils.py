"""
Admin utility functions and decorators
"""

import config
from functools import wraps

def admin_required(func):
    """Decorator to check if user is admin"""
    @wraps(func)
    async def wrapper(update, context):
        user_id = update.effective_user.id
        # Use ADMIN_USER_IDS which is the correct admin list in config
        if user_id in config.ADMIN_USER_IDS:
            return await func(update, context)
        else:
            if update.message:
                await update.message.reply_text("❌ شما به این بخش دسترسی ندارید.")
            elif update.callback_query:
                await update.callback_query.answer("❌ شما به این بخش دسترسی ندارید.", show_alert=True)
            return
    return wrapper
