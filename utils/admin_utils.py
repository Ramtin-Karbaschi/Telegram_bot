"""
Admin utility functions and decorators
"""

import config
from functools import wraps
from database.queries import DatabaseQueries

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

def is_admin_user(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in config.ADMIN_USER_IDS

def is_mid_level_user(user_id: int) -> bool:
    """Check if user is mid-level staff"""
    # First check database, then config
    if DatabaseQueries.is_mid_level_user(user_id):
        return True
    return any(staff["chat_id"] == user_id for staff in config.MAIN_BOT_MID_LEVEL_STAFF_LIST)

def is_support_user(user_id: int) -> bool:
    """Check if user is support staff"""
    # First check database, then config
    if DatabaseQueries.is_support_user(user_id):
        return True
    return any(staff["chat_id"] == user_id for staff in config.MAIN_BOT_SUPPORT_STAFF_LIST)

def has_ticket_access(user_id: int) -> bool:
    """Check if user has access to ticket management"""
    return is_admin_user(user_id) or is_mid_level_user(user_id) or is_support_user(user_id)

def has_payment_access(user_id: int) -> bool:
    """Check if user has access to payment management"""
    return is_admin_user(user_id) or is_mid_level_user(user_id) or is_support_user(user_id)

def has_broadcast_access(user_id: int) -> bool:
    """Check if user has access to broadcast messaging"""
    return is_admin_user(user_id) or is_mid_level_user(user_id)

def has_settings_access(user_id: int) -> bool:
    """Check if user has access to settings (admin only for now)"""
    return is_admin_user(user_id)

def mid_level_or_admin_required(func):
    """Decorator to check if user is mid-level or admin"""
    @wraps(func)
    async def wrapper(update, context):
        user_id = update.effective_user.id
        if has_broadcast_access(user_id):
            return await func(update, context)
        else:
            if update.message:
                await update.message.reply_text("❌ شما به این بخش دسترسی ندارید.")
            elif update.callback_query:
                await update.callback_query.answer("❌ شما به این بخش دسترسی ندارید.", show_alert=True)
            return
    return wrapper

def staff_required(func):
    """Decorator to check if user is staff (support, mid-level, or admin)"""
    @wraps(func)
    async def wrapper(self, update, context, *args, **kwargs):
        user_id = update.effective_user.id if update.effective_user else None
        if has_ticket_access(user_id):
            return await func(self, update, context, *args, **kwargs)
        else:
            if update.callback_query:
                await update.callback_query.answer("دسترسی محدود است.", show_alert=True)
            elif update.effective_message:
                await update.effective_message.reply_text("دسترسی محدود است.")
            return
    return wrapper
