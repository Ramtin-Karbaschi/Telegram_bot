"""
Subscription handlers for the Daraei Academy Telegram bot
"""

from datetime import datetime # Added this import
import jdatetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode # Added for message formatting
from telegram.ext import ContextTypes, ConversationHandler
import config # Added for TELEGRAM_CHANNELS_INFO
from database.queries import DatabaseQueries as Database
from utils.keyboards import get_main_menu_keyboard, get_subscription_plans_keyboard
from utils.constants import (
    SUBSCRIPTION_STATUS_NONE, SUBSCRIPTION_STATUS_ACTIVE,
    SUBSCRIPTION_STATUS_EXPIRED,
    CALLBACK_START_PROFILE_EDIT  # Added for profile edit callback
)
from utils.helpers import calculate_days_left, is_admin
import logging

# Configure logger
logger = logging.getLogger(__name__)

async def activate_or_extend_subscription(
    user_id: int,
    telegram_id: int, # telegram_id might be the same as user_id from DB users table
    plan_id: int,
    plan_name: str,
    payment_amount: float,
    payment_method: str,
    transaction_id: str, # Blockchain TXID or Bank Transaction ID
    context: ContextTypes.DEFAULT_TYPE,
    payment_table_id: int # This is the ID from either 'payments' or 'crypto_payments' table
) -> tuple[bool, str]:
    """Activates a new subscription or extends an existing one for the user."""
    logger.info(f"Attempting to activate/extend subscription for user_id: {user_id}, plan_id: {plan_id}, payment_method: {payment_method}, payment_table_id: {payment_table_id}")

    try:
        plan_details = Database.get_plan_by_id(plan_id)
        if not plan_details:
            logger.error(f"Plan with ID {plan_id} not found for user_id: {user_id}.")
            return False, "اطلاعات طرح اشتراک یافت نشد."

        plan_duration_days = plan_details.get('days')
        if plan_duration_days is None:
            logger.error(f"Plan duration (days) not found for plan_id: {plan_id}, user_id: {user_id}.")
            return False, "مدت زمان طرح اشتراک مشخص نشده است."

        # The payment_id argument in add_subscription refers to the ID in the 'payments' or 'crypto_payments' table.
        subscription_id = Database.add_subscription(
            user_id=user_id,
            plan_id=plan_id,
            payment_id=payment_table_id, # Crucial: This is the ID from the respective payment table
            plan_duration_days=plan_duration_days,
            amount_paid=payment_amount,
            payment_method=payment_method,
            # status is 'active' by default in add_subscription
        )

        if subscription_id:
            logger.info(f"Successfully activated/extended subscription_id: {subscription_id} for user_id: {user_id} with plan '{plan_name}'. Payment ID: {payment_table_id} ({payment_method}).")
            # UserAction.log_user_action(user_id, "subscription_activated", {details...}) # TODO: Implement UserAction
            
            # Optionally send a direct confirmation here, or rely on the calling handler
            # await context.bot.send_message(telegram_id, f"اشتراک شما برای طرح '{plan_name}' با موفقیت فعال/تمدید شد.")
            return True, f"اشتراک شما برای طرح '{plan_name}' با موفقیت فعال/تمدید شد."
        else:
            logger.error(f"Failed to add/extend subscription in DB for user_id: {user_id}, plan_id: {plan_id}, payment_table_id: {payment_table_id}.")
            return False, "خطا در فعال‌سازی یا تمدید اشتراک در پایگاه داده."

    except Exception as e:
        logger.exception(f"Exception in activate_or_extend_subscription for user_id: {user_id}, plan_id: {plan_id}: {e}")
        return False, f"خطای سیستمی در هنگام فعال‌سازی اشتراک: {e}"


# Conversation states
SUBSCRIPTION_STATUS = 0

async def start_subscription_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the subscription status process"""
    user_id = update.effective_user.id
    
    # Update user activity
    Database.update_user_activity(user_id)
    
    # Get active subscription
    subscription = Database.get_user_active_subscription(user_id)
    
    if not subscription:
        # No active subscription
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("خرید اشتراک", callback_data="start_subscription_flow")], # Changed text and callback
            [InlineKeyboardButton("بازگشت به منوی اصلی", callback_data="back_to_main_menu")] # Consistent callback
        ])
        
        await update.message.reply_text(
            SUBSCRIPTION_STATUS_NONE,
            reply_markup=keyboard
        )
    else:
        # Active subscription found
        await view_active_subscription(update, context, subscription)
    
    return SUBSCRIPTION_STATUS

async def view_active_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE, subscription_data=None):
    """Show user profile and active subscription details"""
    user_id = update.effective_user.id
    query = update.callback_query

    if query:
        await query.answer()
        # If subscription_data is not passed, fetch it. 
        # This happens if view_active_subscription is called directly from a callback for example.
        if subscription_data is None:
            subscription_data = Database.get_user_active_subscription(user_id)
    else: # Called from a message, not a callback query
        # If subscription_data is not passed, fetch it. 
        # This is the typical case when called from start_subscription_status after a text message.
        if subscription_data is None:
            subscription_data = Database.get_user_active_subscription(user_id)

    user_details = Database.get_user_details(user_id)

    if not user_details:
        # This should ideally not happen if the user is interacting with this part
        no_user_message = "اطلاعات کاربری شما یافت نشد. لطفاً مجدداً با دستور /start شروع کنید."
        if query:
            await query.message.edit_text(no_user_message)
        else:
            await update.message.reply_text(no_user_message)
        return ConversationHandler.END

    # Initialize with defaults
    full_name = 'ثبت نشده'
    birth_year_str = None
    education = 'ثبت نشده'
    occupation = 'ثبت نشده'
    phone = 'ثبت نشده'

    if user_details: 
        try:
            _full_name = user_details['full_name']
            full_name = _full_name if _full_name else 'ثبت نشده'
        except KeyError:
            full_name = 'ثبت نشده'

        try:
            birth_year_str = user_details['birth_year']
            if not birth_year_str: # Handles None or empty string from DB
                birth_year_str = None
        except KeyError:
            birth_year_str = None

        try:
            _education = user_details['education']
            education = _education if _education else 'ثبت نشده'
        except KeyError:
            education = 'ثبت نشده'

        try:
            _occupation = user_details['occupation']
            occupation = _occupation if _occupation else 'ثبت نشده'
        except KeyError:
            occupation = 'ثبت نشده'

        try:
            _phone = user_details['phone']
            phone = _phone if _phone else 'ثبت نشده'
        except KeyError:
            phone = 'ثبت نشده'

    age_str = "ثبت نشده"
    if birth_year_str:
        try:
            current_year = jdatetime.datetime.now().year
            age = current_year - int(birth_year_str)
            age_str = f"{age} سال"
        except ValueError:
            age_str = "خطا در محاسبه"

    profile_info_parts = [
        f"👤 نام و نام خانوادگی: {full_name}",
        f"🎂 سن: {age_str}",
        f"🎓 تحصیلات: {education}",
        f"💼 شغل: {occupation}",
        f"📱 شماره همراه: {phone}"
    ]
    profile_message = "\n".join(profile_info_parts)

    # Check if user is admin
    hide_main_menu_button = context.user_data.pop('hide_main_menu_button', False)

    if is_admin(user_id, config.ADMIN_USER_IDS):
        subscription_status_text = "شما کاربر ادمین با دسترسی نامحدود هستید."
        final_message = f"اطلاعات حساب کاربری شما:\n\n{profile_message}\n\nوضعیت اشتراک:\n{subscription_status_text}"
        
        keyboard_buttons = []
        if is_active_subscription:
            keyboard_buttons.append([
                InlineKeyboardButton("تمدید اشتراک", callback_data="start_subscription_flow")
            ])
            keyboard_buttons.append([
                InlineKeyboardButton("دریافت لینک کانال", callback_data="get_channel_link")
            ])
        else:
            # InlineKeyboardButton("خرید اشتراک", callback_data="start_subscription_flow") removed for admin
            pass # Placeholder if no other buttons are added here for admin without active sub
        keyboard_buttons.append([
            InlineKeyboardButton("اصلاح و تکمیل اطلاعات", callback_data=CALLBACK_START_PROFILE_EDIT)
        ])

    else:
        # Logic for regular users
        subscription_status_text = SUBSCRIPTION_STATUS_NONE 
        plan_name_for_msg = "نامشخص" # Default plan name
        is_active_subscription = False # Flag to track active subscription

        if subscription_data:
            plan_id = subscription_data['plan_id']
            plan_details = Database.get_plan_by_id(plan_id) # Fetch from DB
            plan_name_for_msg = plan_details['name'] if plan_details else "نامشخص"
            
            days_left = calculate_days_left(subscription_data['end_date'])
            
            if days_left > 0:
                is_active_subscription = True # Set flag
                subscription_status_text = SUBSCRIPTION_STATUS_ACTIVE.format(
                    plan_name=plan_name_for_msg,
                    days_left=days_left,
                    start_date=subscription_data['start_date'][:10],
                    end_date=subscription_data['end_date'][:10]
                )
            else: # Expired 
                pass

        final_message = f"اطلاعات حساب کاربری شما:\n\n{profile_message}\n\nوضعیت اشتراک:\n{subscription_status_text}"

        keyboard_buttons = []
        if is_active_subscription:
            keyboard_buttons.append(
                [InlineKeyboardButton("تمدید اشتراک", callback_data="start_subscription_flow")] # Changed callback to unify flow
            )
            # Add 'Get Channel Link' button if subscription is active
            keyboard_buttons.append(
                [InlineKeyboardButton("دریافت لینک کانال", callback_data="get_channel_link")]
            )
        else: # No active subscription (None or expired)
            # InlineKeyboardButton("خرید اشتراک", callback_data=f"{CALLBACK_VIEW_PLANS_PREFIX}") removed for regular user
            pass # Placeholder if no other buttons are added here for user without active sub
        
        # Common buttons for all regular users
        keyboard_buttons.append(
            [InlineKeyboardButton("اصلاح و تکمیل اطلاعات", callback_data=CALLBACK_START_PROFILE_EDIT)]
        )

    reply_markup = InlineKeyboardMarkup(keyboard_buttons)

    if query:
        await query.message.edit_text(text=final_message, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text=final_message, reply_markup=reply_markup, parse_mode='HTML')

    return SUBSCRIPTION_STATUS

async def get_channel_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Get Channel Link' button press."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    is_admin_user = is_admin(user_id, config.ADMIN_USER_IDS) # Ensure config.ADMIN_USER_IDS is your actual admin list variable
    subscription = Database.get_user_active_subscription(user_id)

    if is_admin_user or (subscription and calculate_days_left(subscription['end_date']) > 0):
        if hasattr(config, 'TELEGRAM_CHANNELS_INFO') and config.TELEGRAM_CHANNELS_INFO:
            channel_links_parts = ["در ادامه لینک کانال‌ها و گروه‌های اختصاصی شما آمده است:"]
            for channel_info in config.TELEGRAM_CHANNELS_INFO:
                title = channel_info.get('title', 'کانال')
                link = channel_info.get('link')
                if link:
                    channel_links_parts.append(f"- [{title}]({link})")
            
            if len(channel_links_parts) > 1: # More than just the intro text
                full_message = "\n".join(channel_links_parts)
                await query.message.reply_text(
                    full_message,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("بازگشت به منوی اصلی", callback_data="back_to_main_menu")]
                    ])
                )
            else: # Only intro text, meaning no valid links were found
                await query.message.reply_text(
                    "در حال حاضر لینک معتبری برای کانال‌ها و گروه‌ها تعریف نشده است. لطفاً با پشتیبانی تماس بگیرید.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("بازگشت به منوی اصلی", callback_data="back_to_main_menu")]
                    ])
                )
        else:
            await query.message.reply_text(
                "هیچ اطلاعاتی برای کانال‌ها و گروه‌ها در پیکربندی یافت نشد. لطفاً با پشتیبانی تماس بگیرید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("بازگشت به منوی اصلی", callback_data="back_to_main_menu")]
                ])
            )
    else:
        await query.message.reply_text(
            "شما اشتراک فعالی برای دریافت لینک کانال ندارید. لطفاً ابتدا اشتراک خود را فعال یا تمدید کنید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("خرید/تمدید اشتراک", callback_data="subscription_renew")],
                [InlineKeyboardButton("بازگشت", callback_data="back_to_main_menu")]
            ])
        )
    return ConversationHandler.END # Or appropriate state if part of a conversation

# Create handler functions that will be imported by main_bot.py
async def subscription_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for subscription status callbacks"""
    # This is a wrapper around view_active_subscription for use with CallbackQueryHandler
    return await view_active_subscription(update, context)

async def subscription_renew_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for subscription renewal callbacks"""
    # This is a wrapper around renew_subscription for use with CallbackQueryHandler
    return await renew_subscription(update, context)
