"""
Subscription handlers for the Daraei Academy Telegram bot
"""

from datetime import datetime # Added this import
import jdatetime
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode # Added for message formatting
from datetime import datetime, timedelta
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
import json

# Configure logger
logger = logging.getLogger(__name__)

async def delete_message_job(context: ContextTypes.DEFAULT_TYPE):
    """Deletes a message."""
    job = context.job
    chat_id = job.chat_id
    message_id = job.data['message_id']
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Successfully deleted channel link message {message_id} from chat {chat_id}.")
    except Exception as e:
        logger.error(f"Failed to delete message {message_id} from chat {chat_id}: {e}")

async def send_channel_links_and_confirmation(telegram_id: int, context: ContextTypes.DEFAULT_TYPE, plan_name: str):
    """Sends a confirmation message with channel links and schedules it for deletion."""
    message_text = f"✅ اشتراک پلن '{plan_name}' برای شما با موفقیت فعال شد.\n\n🎉 اکنون می‌توانید از طریق لینک‌های زیر به کانال‌ها و گروه‌های ویژه دسترسی داشته باشید:"
    
    keyboard = []
    if hasattr(config, 'TELEGRAM_CHANNELS_INFO') and config.TELEGRAM_CHANNELS_INFO:
        # config.TELEGRAM_CHANNELS_INFO may already be a list (parsed in config.py) or a raw JSON string
        try:
            if isinstance(config.TELEGRAM_CHANNELS_INFO, str):
                channels_info = json.loads(config.TELEGRAM_CHANNELS_INFO)
            else:
                channels_info = config.TELEGRAM_CHANNELS_INFO
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse TELEGRAM_CHANNELS_INFO JSON: {e}")
            channels_info = []

        first_row = []
        for channel in channels_info:
            if isinstance(channel, dict) and 'title' in channel and 'link' in channel:
                first_row.append(InlineKeyboardButton(channel['title'], url=channel['link']))
        
        # Only add rows if there are actual buttons to add
        if first_row:
            keyboard.append(first_row)
            # Add the back to main menu button in a new row, only if there are channels
            keyboard.append([InlineKeyboardButton("بازگشت به پروفایل کاربری", callback_data="back_to_main_menu")])
    
    if not keyboard:
        logger.warning(f"TELEGRAM_CHANNELS_INFO is not configured correctly for user {telegram_id}.")
        await context.bot.send_message(
            chat_id=telegram_id,
            text="🎉 اشتراک شما با موفقیت فعال شد!"
        )
        return

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        sent_message = await context.bot.send_message(
            chat_id=telegram_id,
            text=message_text,
            reply_markup=reply_markup
        )
        logger.info(f"Sent channel links to user {telegram_id}. Message ID: {sent_message.message_id}")

        context.job_queue.run_once(
            delete_message_job,
            300,  # 5 minutes
            chat_id=telegram_id,
            data={'message_id': sent_message.message_id},
            name=f"delete_msg_{telegram_id}_{sent_message.message_id}"
        )
        logger.info(f"Scheduled message {sent_message.message_id} for deletion in 5 minutes for user {telegram_id}.")

    except Exception as e:
        logger.error(f"Failed to send channel links message to user {telegram_id}: {e}")

async def activate_or_extend_subscription(
    user_id: int,
    telegram_id: int,
    plan_id: int,
    plan_name: str,
    payment_amount: float,
    payment_method: str,
    transaction_id: str,
    context: ContextTypes.DEFAULT_TYPE,
    payment_table_id: int
) -> tuple[bool, str]:
    """Activates a new subscription or extends an existing one, and updates user summary."""
    logger.info(f"Attempting to activate/extend subscription for user_id: {user_id}, plan_id: {plan_id}")

    try:
        plan_details = Database.get_plan_by_id(plan_id)
        if not plan_details:
            logger.error(f"Plan with ID {plan_id} not found for user_id: {user_id}.")
            return False, "اطلاعات طرح اشتراک یافت نشد."

        plan_duration_days = dict(plan_details).get('days')
        if plan_duration_days is None:
            logger.error(f"Plan duration not found for plan_id: {plan_id}, user_id: {user_id}.")
            return False, "مدت زمان طرح اشتراک مشخص نشده است."

        # Add the subscription to the 'subscriptions' table first
        subscription_id = Database.add_subscription(
            user_id=user_id,
            plan_id=plan_id,
            payment_id=payment_table_id,
            plan_duration_days=plan_duration_days,
            amount_paid=payment_amount,
            payment_method=payment_method,
        )

        if not subscription_id:
            logger.error(f"Failed to add subscription to DB for user_id: {user_id}, plan_id: {plan_id}.")
            return False, "خطا در ثبت اولیه اشتراک در پایگاه داده."

        # --- New Logic: Update user's subscription summary ---
        logger.info(f"Updating user subscription summary for user_id: {user_id}")
        
        # 1. Get current summary
        user_summary = Database.get_user_subscription_summary(user_id)
        current_total_days = user_summary['total_subscription_days'] if user_summary and user_summary['total_subscription_days'] is not None else 0
        current_expiration_str = user_summary['subscription_expiration_date'] if user_summary else None

        # 2. Calculate new total days
        new_total_days = current_total_days + plan_duration_days

        # 3. Calculate new expiration date
        now = datetime.now()
        start_date = now
        
        if current_expiration_str:
            try:
                current_expiration_date = datetime.fromisoformat(current_expiration_str)
                # If the current subscription is still active, extend it. Otherwise, start from now.
                if current_expiration_date > now:
                    start_date = current_expiration_date
            except (ValueError, TypeError):
                logger.warning(f"Could not parse current_expiration_date '{current_expiration_str}' for user {user_id}. Starting new subscription from now.")

        new_expiration_date = start_date + timedelta(days=plan_duration_days)
        new_expiration_date_str = new_expiration_date.isoformat()

        # 4. Update the users table
        update_success = Database.update_user_subscription_summary(
            user_id=user_id,
            total_days=new_total_days,
            expiration_date=new_expiration_date_str
        )

        if not update_success:
            # Critical error: subscription was added but user summary failed.
            logger.critical(f"CRITICAL: Failed to update user subscription summary for user_id: {user_id} after adding subscription_id: {subscription_id}. Manual check required.")

        logger.info(f"Successfully activated/extended subscription_id: {subscription_id} for user_id: {user_id}.")
        
        # Call the confirmation function with the plan name
        await send_channel_links_and_confirmation(telegram_id=telegram_id, context=context, plan_name=plan_name)
        
        # Return only boolean, as the message is now sent by the function above
        return True, ""

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
            [InlineKeyboardButton("خرید محصولات", callback_data="start_subscription_flow")], # Changed text and callback
            [InlineKeyboardButton("بازگشت به منو اصلی", callback_data="back_to_main_menu")] # Consistent callback
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
        f"💼 حیطه فعالیت: {occupation}",
        f"📱 شماره همراه: {phone}"
    ]
    profile_message = "\n".join(profile_info_parts)

    # Initialize subscription active flag
    is_active_subscription = False

    # Check if user is admin

    if is_admin(user_id, config.ADMIN_USER_IDS):
        # Admins have unlimited access; treat as active
        is_active_subscription = True
        subscription_status_text = "شما کاربر ادمین با دسترسی نامحدود هستید."
        
        keyboard_buttons = []
        if is_active_subscription:
            keyboard_buttons.append([
                InlineKeyboardButton("تمدید اشتراک", callback_data="start_subscription_flow")
            ])
            keyboard_buttons.append([
                InlineKeyboardButton("دریافت لینک کانال", callback_data="get_channel_link")
            ])
        pass  # Admins without an explicit subscription still retain unlimited access
        keyboard_buttons.append([
             InlineKeyboardButton("اصلاح و تکمیل اطلاعات", callback_data=CALLBACK_START_PROFILE_EDIT)
         ])

        # Build the final message for admin users
        final_message = f"اطلاعات حساب کاربری شما:\n\n{profile_message}\n\nوضعیت اشتراک:\n{subscription_status_text}"

    else:
        # Logic for regular users
        subscription_status_text = SUBSCRIPTION_STATUS_NONE
        plan_name_for_msg = "نامشخص" # Default plan name
        plan_details = None

        if subscription_data:
            # subscription_data is already a dict-like object from the database
            end_date_str = subscription_data['end_date']
            plan_name = subscription_data['plan_name']
            
            # Calculate remaining time
            try:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
                remaining = end_date - datetime.now()
                if remaining.total_seconds() > 0:
                    days = remaining.days
                    hours, remainder = divmod(remaining.seconds, 3600)
                    minutes, _ = divmod(remainder, 60)
                    subscription_status_text = f"فعال ✅\n" \
                                               f"اعتبار باقی‌مانده:\n{days} روز و {hours} ساعت و {minutes} دقیقه"
                else:
                    subscription_status_text = "اشتراک شما به پایان رسیده است."
            except (ValueError, TypeError):
                subscription_status_text = f"فعال ✅\n" \
                                           f"تاریخ پایان نامعتبر"

            if plan_details:
                plan_name_for_msg = plan_details.get('name') if isinstance(plan_details, dict) else "نامشخص"
                
                days_left = calculate_days_left(subscription_data['end_date'])
                
                if days_left > 0:
                    # Active subscription
                    is_active_subscription = True
                    subscription_status_text = SUBSCRIPTION_STATUS_ACTIVE.format(
                        plan_name=plan_name_for_msg,
                        days_left=days_left,
                        start_date=subscription_data['start_date'][:10],
                        end_date=subscription_data['end_date'][:10]
                    )
                else:
                    # Subscription expired
                    subscription_status_text = SUBSCRIPTION_STATUS_EXPIRED.format(
                        plan_name=plan_name_for_msg,
                        start_date=subscription_data['start_date'][:10],
                        end_date=subscription_data['end_date'][:10]
                    )

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
        else:  # No active subscription (None or expired)
            # Provide button for buying/renewing subscription
            keyboard_buttons.append(
                [InlineKeyboardButton("خرید محصولات", callback_data="start_subscription_flow")]
            )
        
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



# Create handler functions that will be imported by main_bot.py
async def subscription_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for subscription status callbacks"""
    # This is a wrapper around view_active_subscription for use with CallbackQueryHandler
    return await view_active_subscription(update, context)

async def subscription_renew_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for subscription renewal callbacks"""
    # This is a wrapper around renew_subscription for use with CallbackQueryHandler
    return await renew_subscription(update, context)
