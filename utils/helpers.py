"""
Helper functions for the Daraei Academy Telegram bot
"""

import datetime
import random
import string
import pytz
from telegram import Bot, Update
from telegram.ext import ContextTypes
from functools import wraps
import config
from config import ALL_ADMINS_LIST
from database.queries import DatabaseQueries as Database


def get_current_time():
    """Get current time in Tehran timezone"""
    tehran_tz = pytz.timezone(config.TEHRAN_TIMEZONE)
    return datetime.datetime.now(tehran_tz)

def format_datetime(dt_str, format_str="%Y-%m-%d %H:%M:%S"):
    """Format a datetime string for display"""
    dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    # Convert to Persian date if needed (requires jdatetime library)
    # Here we just return a formatted date
    return dt.strftime("%Y/%m/%d %H:%M")

def calculate_days_left(end_date_str):
    """Calculate days left until subscription expires"""
    end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
    now = datetime.datetime.now()
    delta = end_date - now
    return max(0, delta.days)

def generate_random_string(length=10):
    """Generate a random string for unique identifiers"""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

async def generate_channel_link(bot, user_id):
    """Generate a unique channel invitation link for a user"""
    try:
        # Create a unique invitation link
        invite_link = await bot.create_chat_invite_link(
            chat_id=config.CHANNEL_ID,
            member_limit=1,  # One-time use
            expire_date=int((datetime.datetime.now() + datetime.timedelta(hours=24)).timestamp())
        )
        
        # Store the link in database
        if invite_link and invite_link.invite_link:
            Database.create_invite_link(user_id, invite_link.invite_link)
            return invite_link.invite_link
            
    except Exception as e:
        print(f"Error generating channel link: {e}")
        
    return None

async def send_expiration_reminder(bot, user_id, days_left):
    """Send a reminder about subscription expiration"""
    try:
        from utils.constants import MEMBERSHIP_EXPIRING
        
        message = MEMBERSHIP_EXPIRING.format(days_left=days_left)
        
        await bot.send_message(
            chat_id=user_id,
            text=message
        )
        
        # Record notification in database
        Database.add_notification(user_id, f"expiration_{days_left}")
        
        return True
    except Exception as e:
        print(f"Error sending expiration reminder: {e}")
        return False

async def send_expired_notification(bot, user_id):
    """Send notification about expired subscription"""
    try:
        from utils.constants import MEMBERSHIP_EXPIRED
        
        await bot.send_message(
            chat_id=user_id,
            text=MEMBERSHIP_EXPIRED
        )
        
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

# --- Admin User Helper Functions ---

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

        user = update.effective_user
        if not user or not is_user_in_admin_list(user.id, self.admin_config):
            if update.effective_message:
                await update.effective_message.reply_text("شما اجازه دسترسی به این دستور را ندارید.")
            elif update.callback_query:
                await update.callback_query.answer("شما اجازه دسترسی به این عمل را ندارید.", show_alert=True)
            return
        return await func(self, update, context, *args, **kwargs)
    return wrapper

# --- End of Admin User Helper Functions ---

# --- Other Helper Functions ---

import io
import qrcode

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


async def send_invalid_membership_notification(bot, user_id):
    """Send notification about invalid membership"""
    try:
        from utils.constants import INVALID_MEMBERSHIP
        
        await bot.send_message(
            chat_id=user_id,
            text=INVALID_MEMBERSHIP
        )
        
        # Record notification in database
        Database.add_notification(user_id, "invalid")
        
        return True
    except Exception as e:
        print(f"Error sending invalid membership notification: {e}")
        return False
