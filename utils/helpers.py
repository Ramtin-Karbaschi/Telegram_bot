"""
Helper functions for the Daraei Academy Telegram bot
"""

import re

def is_valid_full_name(name: str) -> bool:
    """Validate that the full name contains only Persian letters and spaces, and is at least 3 characters long."""
    # This regex allows only Persian letters and spaces.
    if len(name) < 3:
        return False
    if re.fullmatch(r'^[\u0600-\u06FF\s]+$', name) and not name.isspace():
        return True
    return False

import datetime
import random
import string
import pytz
from telegram import Update
from telegram.ext import ContextTypes
from functools import wraps
import config
from config import ALL_ADMINS_LIST

def get_current_time():
    """Get current time in Tehran timezone"""
    tehran_tz = pytz.timezone(config.TEHRAN_TIMEZONE)
    return datetime.datetime.now(tehran_tz)

def calculate_days_left(end_date_str):
    """Calculate days left until subscription expires"""
    end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
    now = datetime.datetime.now()
    delta = end_date - now
    return max(0, delta.days)

async def send_expired_notification(bot, user_id):
    """Send notification about expired subscription"""
    try:
        from utils.constants import MEMBERSHIP_EXPIRED
        
        await bot.send_message(
            chat_id=user_id,
            text=MEMBERSHIP_EXPIRED
        )
        
        from database.queries import DatabaseQueries as Database
        
        # Record notification in database
        Database.add_notification(user_id, "expired")
        
        return True
    except Exception as e:
        print(f"Error sending expired notification: {e}")
        return False

def is_admin(user_id: int, admin_ids_list: list[int]) -> bool:
    """
    Checks if the given user_id is present in the provided list of admin IDs.
    """
    # The original implementation iterated through ALL_ADMINS_LIST (list of dicts).
    # The new ADMIN_USER_IDS in config.py is a direct list of integer IDs.
    # So, a simple 'in' check is sufficient and more efficient.
    return user_id in admin_ids_list

# --- Admin & Support User Helper Functions ---

def is_user_in_admin_list(user_id: int, admin_config: list | dict) -> bool:
    """
    Check if the given user_id belongs to an admin in the provided admin_config.
    admin_config can be a list of dicts (e.g., MAIN_BOT_SUPPORT_STAFF_LIST)
    or a dict (e.g., MANAGER_BOT_ADMINS_DICT).
    """
    if isinstance(admin_config, list): # Assumes list of dicts like [{"chat_id": id, ...}, ...]
        for admin_user in admin_config:
            if isinstance(admin_user, dict) and admin_user.get("chat_id") == user_id:
                return True
    elif isinstance(admin_config, dict): # Assumes dict like {chat_id: alias, ...}
        return user_id in admin_config
    return False

def get_alias_from_admin_list(user_id: int, admin_config: list | dict) -> str | None:
    """
    Get the alias for a given admin user_id from the provided admin_config.
    admin_config can be a list of dicts or a dict.
    """
    if isinstance(admin_config, list): # Assumes list of dicts like [{"chat_id": id, "alias": "name"}, ...]
        for admin_user in admin_config:
            if isinstance(admin_user, dict) and admin_user.get("chat_id") == user_id:
                return admin_user.get("alias")
    elif isinstance(admin_config, dict): # Assumes dict like {chat_id: alias, ...}
        return admin_config.get(user_id)
    return None


def staff_only_decorator(func):
    """Decorator to allow access for admins *or* support staff."""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        from database.queries import DatabaseQueries
        from telegram import CallbackQuery

        if isinstance(update, CallbackQuery):
            user = update.from_user
        else:
            user = getattr(update, 'effective_user', None)

        user_id = user.id if user else None
        is_admin_flag = False
        if hasattr(self, 'admin_config'):
            from utils.helpers import is_user_in_admin_list
            is_admin_flag = user_id is not None and is_user_in_admin_list(user_id, self.admin_config)
        is_support_flag = user_id is not None and DatabaseQueries.is_support_user(user_id)

        if not (is_admin_flag or is_support_flag):
            if update.effective_message:
                await update.effective_message.reply_text("دسترسی محدود است.")
            elif update.callback_query:
                await update.callback_query.answer("شما اجازه دسترسی به این عمل را ندارید.", show_alert=True)
            return
        return await func(self, update, context, *args, **kwargs)
    return wrapper

# existing admin_only_decorator remains below

def admin_only_decorator(func):
    """Decorator to restrict access to admins only. Assumes it's used on methods of a class
       that has 'self.admin_config' and that 'is_user_in_admin_list' is available.
    """
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        # 'self' here is the instance of the class (e.g., ManagerBot)
        if not hasattr(self, 'admin_config'):
            print("CRITICAL ERROR: admin_only_decorator used on a class instance without 'admin_config' attribute.")
            if update.effective_message:
                await update.effective_message.reply_text("خطای سرور در بررسی دسترسی.")
            elif update.callback_query:
                 await update.callback_query.answer("خطای سرور در بررسی دسترسی.", show_alert=True)
            return

        # Determine user depending on update type
        from telegram import CallbackQuery
        if isinstance(update, CallbackQuery):
            user = update.from_user  # type: ignore[attr-defined]
        else:
            user = getattr(update, 'effective_user', None)

        # Determine if user is admin, mid-level or support
        is_admin_flag = user is not None and is_user_in_admin_list(user.id, self.admin_config)
        from database.queries import DatabaseQueries
        is_support_flag = user is not None and DatabaseQueries.is_support_user(user.id)
        is_mid_level_flag = user is not None and DatabaseQueries.is_mid_level_user(user.id)

        if not (is_admin_flag or is_support_flag or is_mid_level_flag):
            # Unauthorized – show appropriate message / alert
            if update.effective_message:
                await update.effective_message.reply_text("پیام های پشتیبانی در این ربات برای شما ارسال می شود.")
            elif update.callback_query:
                await update.callback_query.answer("شما اجازه دسترسی به این عمل را ندارید.", show_alert=True)
            return
        # Authorized (admin or support) – proceed
        return await func(self, update, context, *args, **kwargs)
    return wrapper

def is_user_registered(user_id: int) -> bool:
    """Return True if the given user_id exists in the database."""
    try:
        from database.queries import DatabaseQueries
        return DatabaseQueries.user_exists(user_id)
    except Exception as e:
        print(f"Error checking user registration: {e}")
        return False



# --- Other Helper Functions ---

import io
import qrcode
from telegram.error import BadRequest
import logging

logger = logging.getLogger(__name__)

def generate_qr_code(data: str) -> io.BytesIO:
    """Generate a QR code image from the given data and return it as BytesIO object."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save image to a bytes buffer
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)  # Rewind the buffer to the beginning
    return img_byte_arr

async def safe_edit_message_text(target, text=None, reply_markup=None, parse_mode=None):
    """
    Safely edit a message's text while handling common Telegram API edge-cases.
    
    Args:
        target: CallbackQuery or Message object
        text: New text content (if None or empty, only reply_markup will be updated)
        reply_markup: New keyboard markup (optional)
        parse_mode: Parse mode for the text (optional)
    
    Returns:
        The result of the edit operation, or None if an error occurred
    """
    # Validate reply_markup - ensure it's either None or a valid keyboard object
    from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup
    if reply_markup is not None:
        if not isinstance(reply_markup, (InlineKeyboardMarkup, ReplyKeyboardMarkup)):
            logger.warning(f"Invalid reply_markup type: {type(reply_markup)}. Setting to None.")
            reply_markup = None
        elif isinstance(reply_markup, str):
            logger.warning(f"reply_markup is a string: '{reply_markup}'. Setting to None.")
            reply_markup = None
    # Helper to detect empty text (None or whitespace)
    def _is_empty(val):
        return val is None or (isinstance(val, str) and val.strip() == "")

    # 1) If no text is provided but we have a reply_markup, update only the markup.
    if _is_empty(text):
        if reply_markup is not None:
            try:
                if hasattr(target, "edit_message_reply_markup"):
                    # CallbackQuery-like
                    return await target.edit_message_reply_markup(reply_markup=reply_markup)
                if hasattr(target, "edit_reply_markup"):
                    # Message-like
                    return await target.edit_reply_markup(reply_markup=reply_markup)
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    return
                raise
        # Nothing to update
        return

    # 2) Try editing text first; fall back to caption if needed.
    try:
        if hasattr(target, "edit_message_text"):
            # CallbackQuery-like
            return await target.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        if hasattr(target, "edit_text"):
            # Message-like
            return await target.edit_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as e:
        s = str(e)
        if "There is no text in the message to edit" in s:
            # Try editing the caption instead
            try:
                if hasattr(target, "edit_message_caption"):
                    return await target.edit_message_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
                if hasattr(target, "edit_caption"):
                    return await target.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)
            except BadRequest as e2:
                if "Message is not modified" in str(e2):
                    return
                raise
        if "Message is not modified" in s:
            return
        # Unexpected error – log and re-raise to preserve behavior for callers that rely on exceptions
        logger.warning("safe_edit_message_text: edit failed: %s", s)
        raise
