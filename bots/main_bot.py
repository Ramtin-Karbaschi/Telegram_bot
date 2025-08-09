"""
Main Telegram bot for Daraei Academy
"""
import sys
import os
import asyncio
import os

# Add the project root directory to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import logging
import re
from telegram.ext import MessageHandler, filters
import html
import json
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from utils.constants import all_constants as constants

# Basic logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot_activity.log"),  # Log to a file
        logging.StreamHandler()  # Log to console
    ]
)

# Set higher logging level for httpx to avoid noisy DEBUG messages
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: "telegram.ext.CallbackContext") -> None:
    """Log Errors caused by Updates."""
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # Handle JobLookupError gracefully (common ConversationHandler timeout issue)
    if isinstance(context.error, Exception) and 'JobLookupError' in str(type(context.error)):
        logger.warning(f"JobLookupError handled gracefully: {context.error}")
        return  # Don't spam admins with these common timeout issues

    # Collect essential error info (truncated to avoid message too long)
    error_type = type(context.error).__name__
    error_msg = str(context.error)[:500]  # Limit error message
    
    # Get limited traceback (last 5 lines)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "\n".join(tb_list[-5:])  # Only last 5 lines
    
    # Prepare concise message for admin
    user_id = getattr(update, 'effective_user', {}).id if hasattr(update, 'effective_user') and update.effective_user else 'Unknown'
    chat_id = getattr(update, 'effective_chat', {}).id if hasattr(update, 'effective_chat') and update.effective_chat else 'Unknown'
    
    message = (
        f"🚨 Bot Error Alert\n\n"
        f"Error Type: {error_type}\n"
        f"User ID: {user_id}\n"
        f"Chat ID: {chat_id}\n\n"
        f"Error: {html.escape(error_msg)}\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )
    
    # Ensure message is not too long (Telegram limit is 4096 chars)
    if len(message) > 4000:
        message = message[:3900] + "\n\n... (truncated)"

    # Send error message to all configured admin contacts for the main bot
    admin_contact_ids = getattr(config, 'MAIN_BOT_ERROR_CONTACT_IDS', [])
    if admin_contact_ids:
        for admin_id in admin_contact_ids:
            try:
                await context.bot.send_message(
                    chat_id=admin_id, text=message, parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to send error message to admin {admin_id}: {e}")
    else:
        logger.warning("MAIN_BOT_ERROR_CONTACT_IDS not configured in config.py or is empty. Cannot send error details to admin.")

    # Optionally, send a generic message to the user
    if update and hasattr(update, 'effective_chat') and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="متاسفانه مشکلی در پردازش درخواست شما پیش آمده است. تیم پشتیبانی در جریان قرار گرفت."
            )
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")

from telegram import Update, BotCommand, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes, TypeHandler, # Added TypeHandler
    PicklePersistence  # Added for application persistence
)
from telegram.request import HTTPXRequest
from utils.text_utils import buttonize_markdown
import config
from database.queries import DatabaseQueries as Database
from database.models import Database as DBConnection
from handlers.core import (
     start_handler as core_start_handler, help_handler, menu_handler, rules_handler,
     unknown_message_handler, handle_back_to_main,
     registration_message_handler, # subscription_status_message_handler removed
     support_message_handler
)
from handlers.profile_handlers import start_profile_edit_conversation
from handlers.subscription.subscription_handlers import subscription_status_handler
from services.zarinpal_service import ZarinpalPaymentService
from database.queries import DatabaseQueries
from handlers.subscription.subscription_handlers import activate_or_extend_subscription
from handlers.free_package.free_package_handlers import free_packages_menu, start_free_package_flow, start_free_package_flow_text, show_queue_position, show_queue_position_message
from handlers.video_access_handlers import video_access_handler
from handlers.altseason_handler import AltSeasonHandler
from handlers.user_survey_handlers import user_survey_handler

from utils.constants.all_constants import (
    CALLBACK_BACK_TO_MAIN_MENU,
    TEXT_MAIN_MENU_STATUS,
    ZARINPAL_PAYMENT_VERIFIED_SUCCESS_AND_SUB_ACTIVATED_MESSAGE_USER,
    ZARINPAL_PAYMENT_VERIFIED_SUCCESS_SUB_ACTIVATION_FAILED_MESSAGE_USER,
    ZARINPAL_PAYMENT_VERIFIED_SUCCESS_PLAN_NOT_FOUND_MESSAGE_USER,
    TEXT_MAIN_MENU_SUPPORT,
    TEXT_MAIN_MENU_HELP,
    TEXT_MAIN_MENU_RULES,
    TEXT_MAIN_MENU_EDIT_PROFILE,
    TEXT_MAIN_MENU_FREE_PACKAGE,
    ZARINPAL_VERIFY_SUCCESS_STATUS, ZARINPAL_ALREADY_VERIFIED_STATUS
)

from telegram.ext import CommandHandler
from telegram.constants import ParseMode

async def send_and_schedule_deletion(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup, delay_seconds: int):
    """Sends a message and schedules its deletion."""
    message = await update.message.reply_text(text, reply_markup=reply_markup)
    
    async def delete_message_task():
        await asyncio.sleep(delay_seconds)
        try:
            await context.bot.delete_message(chat_id=message.chat_id, message_id=message.message_id)
            logger.info(f"Automatically deleted channel link message {message.message_id} from chat {message.chat_id}.")
        except Exception as e:
            logger.error(f"Failed to auto-delete channel link message {message.message_id}: {e}")

    asyncio.create_task(delete_message_task())


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    # Check for Zarinpal deep link
    if args and args[0].startswith('zarinpal_verify_'):
        authority = args[0].replace('zarinpal_verify_', '')
        logger.info(f"User {user_id} returned from Zarinpal with authority: {authority}")

        payment = DatabaseQueries.get_payment_by_authority(authority)

        if not payment:
            logger.warning(f"No payment record found for authority: {authority}. User: {user_id}")
            await update.message.reply_text("خطا: اطلاعات این تراکنش در سیستم یافت نشد. لطفاً با پشتیبانی تماس بگیرید.")
            return

        payment_db_id = payment['payment_id']
        plan_id = payment['plan_id']
        rial_amount = payment['amount']

        if payment['status'] == 'completed':
            logger.info(f"Payment {payment_db_id} for user {user_id} was already completed.")
            await update.message.reply_text("✅ پرداخت شما قبلاً با موفقیت تایید و اشتراک شما فعال شده است.")
            # Optionally, show main menu
            await core_start_handler(update, context)
            return

        # Verify with Zarinpal
        await update.message.reply_text("در حال بررسی و تایید پرداخت شما... لطفاً چند لحظه صبر کنید.")
        verification_result = ZarinpalPaymentService.verify_payment(amount=int(rial_amount), authority=authority)

        if verification_result and verification_result.get('status') in [ZARINPAL_VERIFY_SUCCESS_STATUS, ZARINPAL_ALREADY_VERIFIED_STATUS]:
            ref_id = verification_result.get('ref_id')
            logger.info(f"Zarinpal verification successful for payment {payment_db_id}. RefID: {ref_id}")
            
            # Update database and then re-fetch to ensure data consistency
            update_success = DatabaseQueries.update_payment_verification_status(payment_db_id, 'completed', str(ref_id))

            if update_success:
                # Re-fetch payment details to ensure we have the latest status and ref_id
                updated_payment_details = DatabaseQueries.get_payment_by_id(payment_db_id)
                if updated_payment_details and updated_payment_details['status'] == 'completed':
                    plan_info = DatabaseQueries.get_plan_by_id(plan_id)
                    user_record = DatabaseQueries.get_user_details(user_id) # Fetch user record to get internal DB ID
                    if plan_info and user_record:
                        user_db_id = user_record['user_id']
                        subscription_id = DatabaseQueries.add_subscription(
                            user_id=user_db_id, # Use internal DB user_id
                            plan_id=plan_id,
                            payment_id=payment_db_id,
                            plan_duration_days=plan_info['days'],
                            amount_paid=rial_amount,
                            payment_method='zarinpal'
                        )
                        if subscription_id:
                            # --- Send sales report message to channel ---
                            try:
                                sales_channel_id = config.SALE_CHANNEL_ID  # گزارشهای فروش
                                username = update.effective_user.username if update.effective_user and update.effective_user.username else None
                                user_display = f"@{username}" if username else f"ID:{user_id}"
                                price_formatted = f"{int(rial_amount):,} تومان"
                                await context.bot.send_message(
                                    chat_id=sales_channel_id,
                                    text=f"🛒 {user_display} محصول {plan_info['name']} را به قیمت {price_formatted} خریداری کرد."
                                )
                            except Exception as e:
                                logger.error(f"Failed to send sales report message: {e}")

                            # Increment discount usage count if a discount was applied
                            did = context.user_data.get('discount_id') if 'discount_id' in context.user_data else payment.get('discount_id')
                            if did:
                                DatabaseQueries.increment_discount_usage(did)
                                logger.info(f"Incremented usage for discount ID {did} after successful payment {payment_db_id}")
                            
                            await update.message.reply_text(ZARINPAL_PAYMENT_VERIFIED_SUCCESS_AND_SUB_ACTIVATED_MESSAGE_USER.format(ref_id=ref_id, plan_name=plan_info['name']))
                            
                            # Get category info to customize success message
                            category_id = plan_info.get('category_id')
                            category_info = None
                            if category_id:
                                category_info = DatabaseQueries.get_category_by_id(category_id)
                            
                            category_name = category_info.get('name', '') if category_info else ''
                            
                            # Customize message based on category
                            if 'VIP' in category_name or 'ویآیپی' in category_name:
                                # کانال VIP - پیام پیش‌فرض با لینک کانال
                                channels_info_str = os.getenv('TELEGRAM_CHANNELS_INFO')
                                if channels_info_str:
                                    try:
                                        channels = json.loads(channels_info_str)
                                        keyboard = [[InlineKeyboardButton(f"ورود به {channel['title']}", url=channel['link'])] for channel in channels]
                                        keyboard.append([InlineKeyboardButton(constants.TEXT_BACK_TO_MAIN_MENU, callback_data=constants.CALLBACK_BACK_TO_MAIN_MENU)])
                                        
                                        reply_markup = InlineKeyboardMarkup(keyboard)
                                        text = "🎉 عالی! اشتراک شما با موفقیت فعال شد. اکنون می‌توانید از طریق دکمه‌های زیر به کانال دسترسی داشته باشید:\n\n⚠️ این لینک‌ها پس از ۵ دقیقه منقضی می‌شوند."
                                        
                                        # Send the message and schedule it for deletion
                                        await send_and_schedule_deletion(update, context, text, reply_markup, 300)

                                    except json.JSONDecodeError:
                                        logger.error("Failed to parse TELEGRAM_CHANNELS_INFO from .env")
                                    except Exception as e:
                                        logger.error(f"An error occurred while sending channel links: {e}")
                                        
                            elif 'آموزش' in category_name:
                                # آموزش - پیام برای دوره‌های ویدیویی
                                keyboard = [[InlineKeyboardButton(constants.TEXT_BACK_TO_MAIN_MENU, callback_data=constants.CALLBACK_BACK_TO_MAIN_MENU)]]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                text = "🎉 عالی! اشتراک شما با موفقیت فعال شد.\n\n📚 دوره‌های ویدیویی آموزشی به زودی در اختیار شما قرار خواهند گرفت.\n\n⚠️ این پیام پس از ۵ دقیقه منقضی می‌شود."
                                
                                await send_and_schedule_deletion(update, context, text, reply_markup, 300)
                                
                            elif 'تورم شکن' in category_name or 'تورم‌شکن' in category_name:
                                # تورم شکن - پیام سازماندهی
                                keyboard = [[InlineKeyboardButton(constants.TEXT_BACK_TO_MAIN_MENU, callback_data=constants.CALLBACK_BACK_TO_MAIN_MENU)]]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                text = "🎉 عالی! اشتراک شما با موفقیت فعال شد.\n\n💼 به زودی سازماندهی خواهید شد. برای کسب اطلاعات بیشتر با آیدی پشتیبان @daraeiposhtibani تماس بگیرید.\n\n⚠️ این پیام پس از ۵ دقیقه منقضی می‌شود."
                                
                                await send_and_schedule_deletion(update, context, text, reply_markup, 300)
                                
                            elif 'مشاوره' in category_name:
                                # مشاوره - پیام ارسال اسکرین‌شات
                                keyboard = [[InlineKeyboardButton(constants.TEXT_BACK_TO_MAIN_MENU, callback_data=constants.CALLBACK_BACK_TO_MAIN_MENU)]]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                text = "🎉 عالی! اشتراک شما با موفقیت فعال شد.\n\n🤝 لطفاً با یک اسکرین‌شات از خرید موفق این محصول به آیدی پشتیبان @daraeiposhtibani پیام ارسال کنید.\n\n⚠️ این پیام پس از ۵ دقیقه منقضی می‌شود."
                                
                                await send_and_schedule_deletion(update, context, text, reply_markup, 300)
                                
                            else:
                                # پیش‌فرض - برای دسته‌بندی‌های نامشخص
                                keyboard = [[InlineKeyboardButton(constants.TEXT_BACK_TO_MAIN_MENU, callback_data=constants.CALLBACK_BACK_TO_MAIN_MENU)]]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                text = "🎉 عالی! اشتراک شما با موفقیت فعال شد.\n\n⚠️ این پیام پس از ۵ دقیقه منقضی می‌شود."
                                
                                await send_and_schedule_deletion(update, context, text, reply_markup, 300)
                        else:
                            await update.message.reply_text(ZARINPAL_PAYMENT_VERIFIED_SUCCESS_SUB_ACTIVATION_FAILED_MESSAGE_USER.format(ref_id=ref_id))
                    else:
                        await update.message.reply_text(ZARINPAL_PAYMENT_VERIFIED_SUCCESS_PLAN_NOT_FOUND_MESSAGE_USER.format(ref_id=ref_id))
                else:
                    logger.error(f"Failed to verify payment update in DB for payment_id {payment_db_id}. Status is not 'completed'.")
                    await update.message.reply_text("خطایی در به‌روزرسانی اطلاعات پرداخت رخ داد. لطفاً با پشتیبانی تماس بگیرید.")
            else:
                logger.error(f"Failed to execute update_payment_verification_status for payment_id {payment_db_id}.")
                await update.message.reply_text("خطایی در ثبت اطلاعات پرداخت رخ داد. لطفاً با پشتیبانی تماس بگیرید.")
        else:
            error_code = verification_result.get('status', 'N/A')
            error_message_zarinpal = verification_result.get('error_message', 'خطای نامشخص')
            logger.error(f"Zarinpal verification failed for payment {payment_db_id}. Status: {error_code}, Message: {error_message_zarinpal}")
            DatabaseQueries.update_payment_status(payment_db_id, 'failed', error_message=f"zarinpal_verify_err_{error_code}")
            
            # Handle different error cases
            if error_code == -51:
                # Error code -51 means payment was not completed by user
                await update.message.reply_text("❌ متاسفانه پرداخت شما تکمیل نشده است. لطفاً مراحل پرداخت خود را تکمیل کنید.")
            else:
                # General error message for other error codes
                await update.message.reply_text(f"❌ متاسفانه در تایید پرداخت شما مشکلی پیش آمد. (کد خطا: {error_code})\nلطفاً با پشتیبانی تماس بگیرید.")
    else:
        # Default start handler behavior
        await core_start_handler(update, context)

from handlers.registration import (
    registration_conversation
)
from handlers.profile_handlers import (
    get_profile_edit_conv_handler, start_profile_edit_conversation # Corrected function name
)
from handlers.payment import (
    payment_conversation,
    start_subscription_flow,
    show_qr_code_handler,
    verify_payment_status
)
from handlers.subscription import (
    subscription_status_handler, subscription_renew_handler,
    view_active_subscription # Added view_active_subscription
)
from handlers.support import (
    support_menu_handler, support_ticket_list_handler,
    new_ticket_handler, ticket_conversation, view_ticket_handler, ticket_history_handler,
)
from handlers.admin.discount_handlers import get_create_discount_conv_handler
from handlers.admin_product_handlers import AdminProductHandler
from handlers.user_survey_handlers import user_survey_handler
from handlers.video_access_handlers import video_access_handler
from handlers.altseason_handler import AltSeasonHandler
from utils.keyboards import (
    get_main_menu_keyboard, get_back_button
)
from handlers.free_package.free_package_handlers import get_free_package_conv_handler
from utils.helpers import (
    get_current_time, calculate_days_left,
    send_expired_notification
)
from utils.expiration_reminder import (
    get_expiring_subscriptions,
    was_reminder_sent_today,
    log_reminder_sent,
)
from utils.constants import (
    CALLBACK_VIEW_SUBSCRIPTION_STATUS_FROM_REG,
    WELCOME_MESSAGE, HELP_MESSAGE, RULES_MESSAGE,
    TEXT_MAIN_MENU_EDIT_PROFILE, # Added constant for edit profile button text
    TEXT_MAIN_MENU_BUY_SUBSCRIPTION, # Added constant for buy subscription button
    # Assuming these constants exist or will be added for other menu items for consistency
    TEXT_MAIN_MENU_REGISTRATION,
    TEXT_MAIN_MENU_SUPPORT, TEXT_MAIN_MENU_RULES, TEXT_MAIN_MENU_HELP, TEXT_MAIN_MENU_FREE_PACKAGE
)

# Global function for logging all updates
async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log any update received by the bot for debugging purposes and persist a user activity log entry."""
    logger.critical(f"CRITICAL_LOG: UNHANDLED_UPDATE_RECEIVED: Type={type(update)}, Content={update}")

    # --- Ensure username in DB is up-to-date ---
    try:
        from database.models import Database as _DB
        tg_user = update.effective_user
        if tg_user:
            db = _DB()
            if db.connect():
                try:
                    db.execute("INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)", (tg_user.id, tg_user.username or '', tg_user.full_name or ''))
                    db.execute("UPDATE users SET username = ? WHERE user_id = ? AND (username IS NULL OR username != ?)", (tg_user.username or '', tg_user.id, tg_user.username or ''))
                    db.commit()
                finally:
                    db.close()
    except Exception as e:
        logger.error(f"Failed to sync username for user {telegram_id}: {e}")

    # --- Persist user activity in DB (non-blocking, fire-and-forget) ---
    try:
        from utils.user_actions import UserAction  # Local import to avoid circular deps

        telegram_id = update.effective_user.id if update.effective_user else None
        if telegram_id is None:
            return  # Bot/system update, skip

        if update.message:
            action_type = "message"
            details = {
                "text": update.message.text or update.message.caption or "<non-text message>",
                "chat_type": update.message.chat.type,
            }
        elif update.callback_query:
            action_type = "callback_query"
            details = {
                "data": update.callback_query.data,
                "inline_message_id": update.callback_query.inline_message_id,
            }
        else:
            action_type = "update"
            details = {"raw": str(update)[:500]}

        # Non-blocking logging; ignore result
        UserAction.log_user_action(telegram_id=telegram_id, action_type=action_type, details=details)
    except Exception as e:
        logger.error(f"Failed to persist user activity log: {e}")

class MainBot:
    """Main Telegram bot for Daraei Academy"""

    def __init__(self):
        """Initialize the bot"""
        self.logger = logging.getLogger(__name__)
                # Create a persistence object
        persistence = PicklePersistence(filepath="database/data/bot_persistence.pkl")
        
        # Build application with default settings (avoiding HTTPXRequest proxy issues)
        self.application = (
            Application.builder()
            .token(config.MAIN_BOT_TOKEN)
            .persistence(persistence)
            .build()
        )
        # Explicitly set allowed_updates to ensure the bot subscribes to the desired update types and to
        # avoid AttributeError inside the telegram.ext internals (some components expect this attribute).
        self.application.allowed_updates = [
            "message",
            "callback_query",
            "chat_member",
            "my_chat_member",
            "poll_answer",
            "poll"
        ]
        
        # Initialize database connection and ensure tables exist
        self.db = DBConnection(config.DATABASE_NAME)
        
        # Create a DatabaseQueries instance bound to this connection and initialize schema
        self.db_queries = DatabaseQueries(self.db)
        self.db_queries.init_database()
        
        # Initialize video service and sync videos
        from services.video_service import video_service
        video_service.scan_and_sync_videos()
        self.logger.info("Video service initialized and videos synced")
        
        # Setup handlers
        self.setup_handlers()
        # Schedule background jobs (e.g., Free Package validation)
        from tasks.free_package_tasks import schedule_tasks

        schedule_tasks(self.application)

        
        # Schedule daily crypto report for admins only if explicitly enabled in config
        if getattr(config, "ENABLE_DAILY_CRYPTO_REPORT", False):
            from tasks.crypto_reports import send_daily_crypto_report_job
            self.application.job_queue.run_daily(
                send_daily_crypto_report_job,
                time=datetime.strptime("10:00", "%H:%M").time().replace(tzinfo=ZoneInfo("Asia/Tehran")),
                name="daily_crypto_report",
            )
            self.logger.info("Daily crypto report job scheduled at 10:00 Asia/Tehran")
        else:
            self.logger.info("Daily crypto report job NOT scheduled (disabled via config)")

        # Schedule expiration reminder task
        self.logger.info("Scheduling daily expiration reminder job at 10:00 Asia/Tehran")
        self.application.job_queue.run_daily(
            self.send_expiration_reminders,
            time=datetime.strptime("10:00", "%H:%M").time().replace(tzinfo=ZoneInfo("Asia/Tehran")),
            name="daily_expiration_reminders",
        )
        # Also run once on startup after 30 seconds
        self.application.job_queue.run_once(self.send_expiration_reminders, when=30)
        
        # Add error handler
        self.application.add_error_handler(error_handler)
        
        # شروع سیستم تایید خودکار پرداخت‌های تتری
        self._setup_auto_verification_system()

    # setup_handlers should be defined here, at the class level indentation
    def setup_handlers(self):
        """Setup all handlers for the bot"""
        # Generic callback_query logger (should be in a high group to run after specific ones)
        # async def generic_callback_logger(update: Update, context: ContextTypes.DEFAULT_TYPE):
        #     if update.callback_query:
        #         self.logger.info(f"GENERIC_CALLBACK_LOGGER: Received callback_query with data: '{update.callback_query.data}' from user {update.effective_user.id}")
        #     # This handler should not interfere, so it doesn't return or change state.
        # # Generic callback logger (should be last or have a high group number)
        # # self.application.add_handler(CallbackQueryHandler(generic_callback_logger), group=10) # High group number
        # # self.logger.info("GENERIC_CALLBACK_LOGGER has been set up in group 10.")

        # Registration conversation handler
        self.application.add_handler(registration_conversation)

        # ---------------- Free Package Handlers FIRST (higher priority) ----------------
        # AltSeason handler setup
        self.altseason_handler = AltSeasonHandler()
        for h in self.altseason_handler.get_handlers():
            self.application.add_handler(h, group=0)
        # Promotional category button handler will be added to payment conversation instead

        # Free Package conversation handler
        self.application.add_handler(get_free_package_conv_handler(), group=0)
        # Queue position (inline and text)
        self.application.add_handler(CallbackQueryHandler(show_queue_position, pattern=r"^freepkg_queue_pos$"), group=0)
        self.application.add_handler(MessageHandler(filters.Regex(r"^📊 جایگاه صف رایگان$"), show_queue_position_message), group=0)
        # Free packages submenu (text button) - removed duplicate, handled in group=-1
        # Callback for Toobit package selection from submenu
        self.application.add_handler(CallbackQueryHandler(start_free_package_flow, pattern=r"^freepkg_toobit$"), group=0)
        # Callback handlers for expiration reminder buttons
        self.application.add_handler(CallbackQueryHandler(free_packages_menu, pattern=r"^free_package_menu$"), group=0)
        self.application.add_handler(CallbackQueryHandler(start_subscription_flow, pattern=r"^products_menu(?:_\d+)?$"), group=0)
        # Survey conversation handler for start_survey_<id>
        self.application.add_handler(user_survey_handler.get_survey_conversation_handler(), group=0)
        from handlers.payment.payment_handlers import back_to_main_menu_from_categories
        self.application.add_handler(CallbackQueryHandler(back_to_main_menu_from_categories, pattern=r"^back_to_main_menu_from_categories$"), group=0)
        # Callback entry for AltSeason is handled by conversation handler
        # Standalone plan handler for free plans outside conversation (higher group to avoid conflict)
        from handlers.payment.payment_handlers import select_plan_handler, prompt_for_discount_code, show_payment_methods
        self.application.add_handler(CallbackQueryHandler(select_plan_handler, pattern=r'^plan_\d+$'), group=2)
        # Standalone handlers for discount step when flow started outside conversation
        self.application.add_handler(CallbackQueryHandler(prompt_for_discount_code, pattern=r'^have_discount_code$'), group=2)
        self.application.add_handler(CallbackQueryHandler(show_payment_methods, pattern=r'^skip_discount_code$'), group=2)
        # Back to plans from discount/payment step outside conversation
        self.application.add_handler(CallbackQueryHandler(start_subscription_flow, pattern=r'^back_to_plans$'), group=2)

        # ---------------- Payment conversation AFTER free package ----------------
        # Add the 'products' text button as an entry point to the conversation
        payment_conversation.entry_points.append(MessageHandler(filters.TEXT & filters.Regex(r"^🛒 (?:محصولات|خدمات VIP)$"), start_subscription_flow))
        
        # Add promotional category button as entry point to payment conversation
        from handlers.promotional_category_integration import promotional_category_text_handler
        from utils.promotional_category_utils import get_promotional_category_button
        
        # Get promotional button text dynamically and add to conversation entry points
        try:
            promo_button = get_promotional_category_button()
            if promo_button:
                promo_text = promo_button.text
                payment_conversation.entry_points.append(
                    MessageHandler(filters.TEXT & filters.Regex(f"^{promo_text}$"), promotional_category_text_handler)
                )
        except Exception as e:
            logger.error(f"Failed to add promotional button to payment conversation: {e}")
            
        self.application.add_handler(payment_conversation, group=1)

        # Handler for back button from payment method selection to plan selection
        self.application.add_handler(CommandHandler('subscribe', start_subscription_flow))


        # Handler for back button from subscription plan selection
        self.application.add_handler(CallbackQueryHandler(handle_back_to_main, pattern=r"^back_to_main_menu_from_plans$"))

        # Handler for showing USDT QR code
        self.application.add_handler(CallbackQueryHandler(show_qr_code_handler, pattern=r'^show_qr_code_'))
        from handlers.payment.crypto_retry_handler import retry_crypto_payment_check
        self.application.add_handler(CallbackQueryHandler(retry_crypto_payment_check, pattern=r'^crypto_retry:'))

        # Generic handler for 'back_to_main' callback (e.g., from support menu)
        self.application.add_handler(CallbackQueryHandler(handle_back_to_main, pattern=r"^back_to_main$"))
        self.application.add_handler(CallbackQueryHandler(handle_back_to_main, pattern=r"^main_menu_back$")) # Handler for back from help/rules
        


        # Profile edit conversation handler (highest priority to avoid any conflicts)
        self.application.add_handler(get_profile_edit_conv_handler(), group=-3)
        
        # Support conversation handler
        self.application.add_handler(ticket_conversation)
        
        # User survey conversation handler (for start_survey_<id> callbacks)
        survey_conv_handler = user_survey_handler.get_survey_conversation_handler()
        self.application.add_handler(survey_conv_handler, group=0)
        
        # Discount creation handler
        create_discount_conv_handler = get_create_discount_conv_handler()
        self.application.add_handler(create_discount_conv_handler)
        
        # Admin product handlers (integrated into admin panel)
        admin_product_handler = AdminProductHandler(db_queries=self.db_queries)
        
        # Poll message handler for survey creation
        self.application.add_handler(MessageHandler(
            filters.POLL, admin_product_handler._handle_poll_message
        ), group=-1)
        
        # Poll-based survey callback handlers
        self.application.add_handler(CallbackQueryHandler(
            admin_product_handler._handle_create_new_poll, pattern="^create_new_poll$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            admin_product_handler._handle_remove_last_poll, pattern="^remove_last_poll$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            admin_product_handler._handle_confirm_poll_survey, pattern="^confirm_poll_survey$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            admin_product_handler._handle_cancel_poll_creation, pattern="^cancel_poll_creation$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            admin_product_handler._handle_survey_type_selection, pattern="^survey_type_"
        ))
        
        # Video access handlers
        video_handlers = video_access_handler.get_callback_handlers()
        for handler in video_handlers:
            self.application.add_handler(handler)
        
        # Survey conversation handler
        survey_conv_handler = user_survey_handler.get_survey_conversation_handler()
        self.application.add_handler(survey_conv_handler)
        
        # Command handlers
        self.application.add_handler(CommandHandler("start", start_handler))
        self.application.add_handler(CommandHandler("help", help_handler))
        self.application.add_handler(CommandHandler("rules", rules_handler))
        # Admin command is handled by existing admin handlers
        self.application.add_handler(CommandHandler("support", support_message_handler))
        
        # Text message handlers for menu items
        self.application.add_handler(MessageHandler(
             filters.TEXT & filters.Regex(re.escape(TEXT_MAIN_MENU_SUPPORT)), support_message_handler
         ), group=-1)
        self.application.add_handler(MessageHandler(
             filters.TEXT & filters.Regex(re.escape(TEXT_MAIN_MENU_RULES)), rules_handler # Using constant
         ), group=-1)
        # Profile edit is handled by ConversationHandler, not a separate MessageHandler
        # self.application.add_handler(MessageHandler(
        #      filters.TEXT & filters.Regex(re.escape(TEXT_MAIN_MENU_EDIT_PROFILE)), start_profile_edit_conversation
        # ), group=-1)
        self.application.add_handler(MessageHandler(
             filters.TEXT & filters.Regex(re.escape(TEXT_MAIN_MENU_HELP)), help_handler # Handler for Help button
         ), group=-1)
        self.application.add_handler(MessageHandler(
             filters.TEXT & filters.Regex(re.escape(TEXT_MAIN_MENU_FREE_PACKAGE)), free_packages_menu
         ), group=-1)
        self.application.add_handler(MessageHandler(
             filters.TEXT & filters.Regex(re.escape(TEXT_MAIN_MENU_STATUS)), subscription_status_handler
         ), group=-1)
        
        # Callback query handlers for subscription and support
        self.application.add_handler(CallbackQueryHandler(
            subscription_status_handler, pattern="^subscription_status$"
        ))
        # Handler for viewing subscription status from registration flow
        self.application.add_handler(CallbackQueryHandler(
            view_active_subscription, pattern=f"^{CALLBACK_VIEW_SUBSCRIPTION_STATUS_FROM_REG}$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            verify_payment_status, pattern="^verify_payment_"
        ))
        
        # Support handlers
        self.application.add_handler(CallbackQueryHandler(
            support_message_handler, pattern="^main_menu_support$" 
        ))
        self.logger.info(f"CRITICAL_LOG: CallbackQueryHandler for main_menu_support ('main_menu_support') has been set up.")

        # Add CallbackQueryHandlers for main_menu_help and main_menu_rules
        self.application.add_handler(CallbackQueryHandler(
            help_handler, pattern="^main_menu_help$"
        ))
        self.logger.info("CRITICAL_LOG: CallbackQueryHandler for main_menu_help has been set up.")

        self.application.add_handler(CallbackQueryHandler(
            rules_handler, pattern="^main_menu_rules$"
        ))
        self.logger.info("CRITICAL_LOG: CallbackQueryHandler for main_menu_rules has been set up.")

        # Status command handler
        self.application.add_handler(CommandHandler("status", subscription_status_handler))
        self.application.add_handler(CallbackQueryHandler(core_start_handler, pattern=f"^{CALLBACK_BACK_TO_MAIN_MENU}$"))
        self.application.add_handler(CallbackQueryHandler(subscription_status_handler, pattern="^show_status$"))
        self.logger.info("CRITICAL_LOG: CommandHandler for status has been set up.")

        # Handler for the main support menu (e.g., after /support or clicking the support button that leads to the support options)
        self.application.add_handler(CallbackQueryHandler(
            support_menu_handler, pattern="^support_menu$"
        ))
        self.logger.info("CRITICAL_LOG: CallbackQueryHandler for support_menu has been set up.")

        self.application.add_handler(CallbackQueryHandler(
            support_ticket_list_handler, pattern="^ticket_list$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            new_ticket_handler, pattern="^new_ticket$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            view_ticket_handler, pattern="^view_ticket_"
        ))
        # Ticket history handler
        self.application.add_handler(CallbackQueryHandler(
            ticket_history_handler, pattern="^ticket_history$"
        ))

        self.application.add_handler(CallbackQueryHandler(
            handle_back_to_main, pattern=r"^back_to_main_menu_from_plans$"
        ))


        # Admin crypto entry command
        from handlers.admin_crypto_entry import admin_crypto_entry_handler
        self.application.add_handler(admin_crypto_entry_handler)
        self.logger.info("CRITICAL_LOG: Admin crypto entry command has been set up.")
        
        # Admin crypto keyboard handler (high priority group 0)
        from handlers.admin_crypto_keyboard import admin_crypto_keyboard_handler
        self.application.add_handler(admin_crypto_keyboard_handler, group=0)
        self.logger.info("CRITICAL_LOG: Admin crypto keyboard handler has been set up.")
        
        self.application.add_handler(TypeHandler(Update, log_all_updates), group=100) # High group number means lower priority
        self.logger.info("CRITICAL_LOG: Generic TypeHandler (log_all_updates) has been set up in group 100.")


        
        # Back to main menu handler
        self.application.add_handler(CallbackQueryHandler(
            handle_back_to_main, pattern="^back_to_main_menu$"
        ))
        
        # Add the combined start handler with a high priority (low group number) to catch deep links first
        self.application.add_handler(CommandHandler('start', start_handler), group=0)

        # Unknown message handler (must be added last)
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, unknown_message_handler
        ))
        
        self.logger.info("All handlers have been set up")
    
    def _setup_auto_verification_system(self):
        """راه‌اندازی سیستم تایید خودکار پرداخت‌های تتری"""
        try:
            print("🚀 Setting up auto verification system...")
            
            # اضافه کردن handlers پنل ادمین تایید تتری
            from handlers.admin.admin_payment_verification import get_handlers
            admin_handlers = get_handlers()
            
            for handler in admin_handlers:
                self.application.add_handler(handler, group=5)
            
            print("✅ Admin payment verification handlers added")
            
            # راه‌اندازی task برای سیستم خودکار
            import asyncio
            from services.auto_verification_system import auto_verification_system
            
            async def start_auto_verification():
                try:
                    await auto_verification_system.start_auto_verification()
                except Exception as e:
                    print(f"❌ Error starting auto verification: {e}")
            
            # شروع در background
            asyncio.create_task(start_auto_verification())
            
            print("✅ Auto verification system setup completed")
            
        except Exception as e:
            print(f"❌ Error setting up auto verification system: {e}")

    async def start(self):
        """Start the bot"""
        self.logger.info("Starting main bot")
        await self.application.initialize()

        # Define bot commands
        commands = [
            BotCommand("start", "شروع و نمایش منوی اصلی"),
            BotCommand("register", "📝 ثبت نام"),
            BotCommand("status", "👤 وضعیت اشتراک من"),
            BotCommand("help", "💡 راهنما"),
            BotCommand("support", "🤝🏻 پشتیبانی"),
            BotCommand("rules", "⚠ قوانین"),
            # BotCommand("admin", "🔧 پنل مدیریت (فقط ادمین)"),
        ]
        await self.application.bot.set_my_commands(commands)
        self.logger.info("Bot commands have been set.")
        await self.application.start()
        # Explicitly start polling via the Updater to ensure the bot receives updates.
        if self.application.updater:
            await self.application.updater.start_polling(allowed_updates=self.application.allowed_updates)
            self.logger.info("Main bot polling started")
        else:
            self.logger.warning("Updater is not initialized for the main bot; no polling will occur.")
        self.logger.info("Main bot started")
    
    async def send_expiration_reminders(self, context: ContextTypes.DEFAULT_TYPE | None = None):
        """Send daily reminders for subscriptions expiring within 5 days."""
        bot = context.bot if context else self.application.bot
        tz_tehran = ZoneInfo("Asia/Tehran")
        today = datetime.now(tz_tehran).date()
        subs = get_expiring_subscriptions(days=5)
        for sub in subs:
            end_date = datetime.fromisoformat(sub["end_date"]).date()
            days_left = (end_date - today).days
            if days_left < 0 or days_left > 5:
                continue
            user_id = sub["user_id"]
            if was_reminder_sent_today(user_id, days_left):
                self.logger.info(
                    f"Skipping reminder for user {user_id}, already sent today for {days_left} days left."
                )
                continue
            message = (
                "اشتراک شما امروز به پایان می‌رسد! 🎯" if days_left == 0 else f"تنها {days_left} روز تا پایان اشتراک شما باقی‌ست ⏰"
            )
            message += "\n\n💡 برای تمدید اشتراک یکی از گزینه‌های زیر را انتخاب کنید:"
            from database.queries import DatabaseQueries
            # Build renew buttons keyboard based on dynamic visibility settings
            visibility = DatabaseQueries.get_renew_visibility()
            keyboard: list[list[InlineKeyboardButton]] = []

            # -------- Handle visible categories --------
            for cat_id in visibility.get("categories", set()):
                try:
                    cat_id_int = int(cat_id)
                except (TypeError, ValueError):
                    continue
                if cat_id_int == 0:
                    # Special ID for free plans
                    keyboard.append([InlineKeyboardButton("🎁 رایگان", callback_data="free_package_menu")])
                elif cat_id_int == -1:
                    # Special ID for root products menu
                    keyboard.append([InlineKeyboardButton("🛒 محصولات", callback_data="products_menu")])
                else:
                    cat = DatabaseQueries.get_category_by_id(cat_id_int)
                    if cat:
                        name = cat["name"] if isinstance(cat, dict) else cat[1]
                        keyboard.append([
                            InlineKeyboardButton(f"🗂 {buttonize_markdown(name)}", callback_data=f"products_menu_{cat_id_int}")
                        ])

            # -------- Handle visible individual plans --------
            for plan_id in visibility.get("plans", set()):
                try:
                    plan_id_int = int(plan_id)
                except (TypeError, ValueError):
                    continue
                plan = DatabaseQueries.get_plan_by_id(plan_id_int)
                if plan and (plan.get("is_active") if isinstance(plan, dict) else plan[9]):
                    name = plan["name"] if isinstance(plan, dict) else plan[1]
                    keyboard.append([
                        InlineKeyboardButton(buttonize_markdown(name), callback_data=f"plan_{plan_id_int}")
                    ])

            # Fallback – if no buttons configured, default to products menu
            if not keyboard:
                keyboard.append([InlineKeyboardButton("محصولات", callback_data="products_menu")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                await bot.send_message(chat_id=user_id, text=message, reply_markup=reply_markup)
                log_reminder_sent(user_id, days_left)
                self.logger.info(
                    f"Reminder sent to user {user_id} for {days_left} days left."
                )
            except Exception as e:
                self.logger.error(f"Failed to send reminder to user {user_id}: {e}")


    async def stop(self):
        """Stop the bot"""
        self.logger.info("Stopping main bot")
        await self.application.stop()
        await self.application.shutdown()
        self.logger.info("Main bot stopped")
