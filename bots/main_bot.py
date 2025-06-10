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
import html
import json
import traceback

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

    # Collect traceback
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Prepare the message for the admin
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        f"</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

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

from telegram import Update, BotCommand # Added for type hinting in error_handler and BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes, TypeHandler, # Added TypeHandler
    PicklePersistence  # Added for application persistence
)
import config
from database.queries import DatabaseQueries as Database
from database.models import Database as DBConnection
from handlers.core import (
    start_handler, help_handler, menu_handler, rules_handler,
    unknown_message_handler, handle_back_to_main,
    registration_message_handler, # subscription_status_message_handler removed
    support_message_handler
)
from handlers.registration import (
    registration_conversation
)
from handlers.profile_handlers import (
    get_profile_edit_conv_handler, start_profile_edit_conversation # Corrected function name
)
from handlers.payment import (
    payment_conversation, select_plan, 
    select_payment_method, verify_payment_status,
    show_qr_code_handler # Added for QR code display
)
from handlers.subscription import (
    subscription_status_handler, subscription_renew_handler,
    get_channel_link_handler, view_active_subscription # Added view_active_subscription
)
from handlers.support import (
    support_menu_handler, support_ticket_list_handler,
    new_ticket_handler, ticket_conversation, view_ticket_handler,
    close_ticket_handler, reopen_ticket_handler
)
from utils.keyboards import (
    get_main_menu_keyboard, get_back_button
)
from utils.helpers import (
    get_current_time, format_datetime, calculate_days_left,
    generate_channel_link, send_expiration_reminder,
    send_expired_notification, send_invalid_membership_notification
)
from utils.constants import (
    CALLBACK_VIEW_SUBSCRIPTION_STATUS_FROM_REG,
    WELCOME_MESSAGE, HELP_MESSAGE, RULES_MESSAGE,
    TEXT_MAIN_MENU_EDIT_PROFILE, # Added constant for edit profile button text
    TEXT_MAIN_MENU_JOIN_OR_REGISTER, # Added constant for the new join/register button
    TEXT_MAIN_MENU_BUY_SUBSCRIPTION, # Added constant for buy subscription button
    # Assuming these constants exist or will be added for other menu items for consistency
    TEXT_MAIN_MENU_REGISTRATION,
    TEXT_MAIN_MENU_SUPPORT, TEXT_MAIN_MENU_RULES, TEXT_MAIN_MENU_HELP
)

# Global function for logging all updates
async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log any update received by the bot for debugging purposes."""
    logger.critical(f"CRITICAL_LOG: UNHANDLED_UPDATE_RECEIVED: Type={type(update)}, Content={update}")

class MainBot:
    """Main Telegram bot for Daraei Academy"""

    def __init__(self):
        """Initialize the bot"""
        self.logger = logging.getLogger(__name__)
                # Create a persistence object
        persistence = PicklePersistence(filepath="database/data/bot_persistence.pkl")
        
        self.application = Application.builder().token(config.MAIN_BOT_TOKEN).persistence(persistence).build()
        
        # Initialize database
        self.db = DBConnection(config.DATABASE_NAME)
        Database.init_database()  # Changed from initialize_database to init_database
        
        # Setup handlers
        self.setup_handlers()
        # Add error handler
        self.application.add_error_handler(error_handler)

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
        
        # Payment conversation handler
        self.application.add_handler(payment_conversation)

        # Handler for back button from payment method selection to plan selection
        self.application.add_handler(CommandHandler('subscribe', select_plan))
        self.application.add_handler(CallbackQueryHandler(select_plan, pattern='^start_subscription_flow$'))

        # Handler for back button from subscription plan selection
        self.application.add_handler(CallbackQueryHandler(handle_back_to_main, pattern=r"^back_to_main_menu_from_plans$"))

        # Handler for showing USDT QR code
        self.application.add_handler(CallbackQueryHandler(show_qr_code_handler, pattern=r'^show_qr_code_'))

        # Generic handler for 'back_to_main' callback (e.g., from support menu)
        self.application.add_handler(CallbackQueryHandler(handle_back_to_main, pattern=r"^back_to_main$"))
        self.application.add_handler(CallbackQueryHandler(handle_back_to_main, pattern=r"^main_menu_back$")) # Handler for back from help/rules
        
        # Profile edit conversation handler
        self.application.add_handler(get_profile_edit_conv_handler())
        
        # Support conversation handler
        self.application.add_handler(ticket_conversation)
        
        # Command handlers
        self.application.add_handler(CommandHandler("start", start_handler))
        self.application.add_handler(CommandHandler("help", help_handler))
        self.application.add_handler(CommandHandler("rules", rules_handler))
        self.application.add_handler(CommandHandler("register", registration_message_handler))
        self.application.add_handler(CommandHandler("status", view_active_subscription))
        self.application.add_handler(CommandHandler("support", support_message_handler))
        
        # Text message handlers for menu items
        self.application.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(f"^{TEXT_MAIN_MENU_SUPPORT}$"), support_message_handler
        ))
        self.application.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(f"^{TEXT_MAIN_MENU_RULES}$"), rules_handler # Using constant
        ))
        self.application.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(f"^{TEXT_MAIN_MENU_EDIT_PROFILE}$"), start_profile_edit_conversation # Handler for Edit Profile button
        ))
        self.application.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(f"^{TEXT_MAIN_MENU_HELP}$"), help_handler # Handler for Help button
        ))
        self.application.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(f"^{TEXT_MAIN_MENU_BUY_SUBSCRIPTION}$"), select_plan # Handler for Buy Subscription button
        ))
        
        # Generic Update Logger - Should be one of the last handlers or in a high group number
        # to catch updates not handled by more specific handlers.
        self.application.add_handler(TypeHandler(Update, log_all_updates), group=100) # High group number means lower priority
        self.logger.info("CRITICAL_LOG: Generic TypeHandler (log_all_updates) has been set up in group 100.")

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
        self.application.add_handler(CallbackQueryHandler(
            close_ticket_handler, pattern="^close_ticket_"
        ))
        self.application.add_handler(CallbackQueryHandler(
            handle_back_to_main, pattern=r"^back_to_main_menu_from_plans$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            reopen_ticket_handler, pattern=r"^reopen_ticket_"
        ))

        # Channel link handler
        self.application.add_handler(CallbackQueryHandler(
            get_channel_link_handler, pattern="^get_channel_link$"
        ))

        # Generic Update Logger - Should be one of the last handlers or in a high group number
        # to catch updates not handled by more specific handlers.
        self.application.add_handler(TypeHandler(Update, log_all_updates), group=100) # High group number means lower priority
        self.logger.info("CRITICAL_LOG: Generic TypeHandler (log_all_updates) has been set up in group 100.")
        
        # Back to main menu handler
        self.application.add_handler(CallbackQueryHandler(
            handle_back_to_main, pattern="^back_to_main_menu$"
        ))
        
        # Unknown message handler (must be added last)
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, unknown_message_handler
        ))
        
        self.logger.info("All handlers have been set up")

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
        ]
        await self.application.bot.set_my_commands(commands)
        self.logger.info("Bot commands have been set.")
        await self.application.start()
        await self.application.updater.start_polling()
        self.logger.info("Main bot started")
    
    async def stop(self):
        """Stop the bot"""
        self.logger.info("Stopping main bot")
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        self.logger.info("Main bot stopped")
