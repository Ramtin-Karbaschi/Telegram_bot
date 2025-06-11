"""
Manager Telegram bot for Daraei Academy
"""

import logging
import asyncio
from database.queries import DatabaseQueries as Database # Added Database import
import datetime
from typing import Optional # Added for type hinting
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember, ChatMemberUpdated
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, 
    CallbackQueryHandler, ConversationHandler, ChatMemberHandler, TypeHandler # Added TypeHandler
)
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.error import BadRequest, Forbidden
import html
from database.queries import DatabaseQueries
from utils.helpers import is_user_in_admin_list, get_alias_from_admin_list, admin_only_decorator as admin_only
import config # For other config vars like CHANNEL_ID
from database.models import Database as DBConnection # For DB connection
from handlers.admin_ticket_handlers import AdminTicketHandler  # Fixed import

# States for ConversationHandler
VIEWING_TICKET, REPLYING_TO_TICKET = range(2)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def manager_bot_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Log Errors and send a message to admin_users_config with role 'error_contact'."""
    logger.error(f"Exception while handling an update in ManagerBot: {context.error}", exc_info=context.error)
    
    user_info = ""
    if update and hasattr(update, 'effective_user') and update.effective_user:
        user_info = f"User: {update.effective_user.id} ({update.effective_user.username or update.effective_user.first_name})"
    
    error_message = (
        f"خطایی در ربات مدیریت رخ داده است:\n\n"
        f"<pre>{html.escape(str(context.error))}</pre>\n\n"
        f"جزئیات بیشتر در لاگ سرور موجود است.\n"
        f"{user_info}"
    )
    
    if hasattr(config, 'MANAGER_BOT_ERROR_CONTACT_IDS') and config.MANAGER_BOT_ERROR_CONTACT_IDS:
        for chat_id in config.MANAGER_BOT_ERROR_CONTACT_IDS:
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=error_message,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Failed to send error message to manager admin {chat_id}: {e}")
    else:
        logger.warning("MANAGER_BOT_ERROR_CONTACT_IDS is not set in config. Cannot send error notifications for ManagerBot.")

class ManagerBot:
    """Manager Telegram bot for Daraei Academy"""
    
    def __init__(self, manager_bot_token: str, admin_users_config: dict, db_name: str, main_bot_app=None):
        """Initialize the bot"""
        self.logger = logging.getLogger(__name__)
        self.admin_config = admin_users_config  # Store admin configuration from parameters
        builder = Application.builder().token(manager_bot_token) # Use token from parameters
        self.application = builder.build()
        # Explicitly set allowed_updates to ensure chat_member and other necessary updates are received
        self.application.allowed_updates = [
            "chat_member",
            "my_chat_member",
            "message", # For any commands or text messages the manager bot might handle
            "callback_query" # For inline keyboard interactions
        ]
        self.logger.info(f"Application allowed_updates explicitly set to: {self.application.allowed_updates}")
        
        # Initialize database
        self.db = DBConnection(db_name) # Use db_name from parameters
        Database.init_database() 
        self.main_bot_app = main_bot_app # Store main_bot_app if provided
        
        # Initialize ticket handler
        self.ticket_handler = AdminTicketHandler()  # Fixed class name
        
        # Setup task handlers
        self.setup_tasks()
        # Setup command and message handlers
        self.setup_handlers()
        
        # Add error handler for ManagerBot
        self.application.add_error_handler(manager_bot_error_handler)

    def setup_tasks(self):
        """Setup background tasks"""
        # Add any background tasks here if needed
        pass

    async def start(self):
        """Start the bot"""
        self.logger.info("Starting Manager Bot")
        await self.application.initialize()
        
        # Add ChatMemberHandler for channel membership control
        # ChatMemberHandler by default listens to CHAT_MEMBER and MY_CHAT_MEMBER updates.
        class DebugChatMemberHandler(ChatMemberHandler):
            def check_update(self, update):
                # FOR DEBUGGING: Always return True to ensure callback is called
                return True
                
        chat_member_handler = DebugChatMemberHandler(self.handle_chat_member_update)
        self.application.add_handler(chat_member_handler, group=-1) # group=-1 to prioritize it
        self.logger.info("ChatMemberHandler (Debug Version) for channel membership control has been set up.")

        # Add a generic handler to log all updates for debugging
        # Note: Ensure 'Update' is imported from 'telegram'
        all_updates_handler = TypeHandler(Update, self.log_all_updates)
        self.application.add_handler(all_updates_handler, group=10) # Low priority
        self.logger.info("Generic UpdateHandler for logging ALL updates has been set up.")
        
        await self.application.start()
        
        # We call validate_memberships directly, not the command version, as it's an internal startup task.
        self.logger.info("Running initial membership validation on startup.")
        await self.validate_memberships(context=None) # Assuming validate_memberships can handle context=None
        
        self.logger.info("Starting Manager Bot polling...")
        # Start polling for updates
        await self.application.updater.start_polling(allowed_updates=self.application.allowed_updates)
        self.logger.info("Manager Bot started")

    async def log_all_updates(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Logs all incoming updates for debugging purposes."""
        self.logger.info(f"GENERIC_UPDATE_HANDLER: Received update of type {type(update)}: {update}")

    async def stop(self):
        """Stop the bot"""
        self.logger.info("Stopping Manager Bot")
        if self.application.updater and self.application.updater.running:
            await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        self.logger.info("Manager Bot stopped")

    async def handle_chat_member_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.logger.critical(f"CRITICAL_LOG: handle_chat_member_update CALLED for update: {update}")
        """Handles chat member updates to manage channel access based on subscription."""
        if not update.chat_member:
            self.logger.debug("ChatMemberHandler received an update without chat_member data.")
            return

        chat_member_data = update.chat_member
        chat_id = chat_member_data.chat.id
        user = chat_member_data.new_chat_member.user
        bot = context.bot # Get bot instance from context

        # Get monitored channel IDs from config
        monitored_channel_ids = []
        if hasattr(config, 'TELEGRAM_CHANNELS_INFO') and config.TELEGRAM_CHANNELS_INFO:
            monitored_channel_ids = [channel_info['id'] for channel_info in config.TELEGRAM_CHANNELS_INFO if isinstance(channel_info, dict) and 'id' in channel_info]

        # Ensure this update is for one of the monitored channels
        if not monitored_channel_ids:
            self.logger.warning("TELEGRAM_CHANNELS_INFO is not configured or empty. ChatMemberHandler will not process any updates.")
            return
        
        if chat_id not in monitored_channel_ids:
            # self.logger.debug(f"ChatMemberUpdate for chat_id {chat_id} which is not in monitored list. Ignoring.") # Can be noisy
            return

        self.logger.info(f"Chat member update in channel {chat_id} for user {user.id} ({user.full_name}). "
                         f"Old status: {chat_member_data.old_chat_member.status}, New status: {chat_member_data.new_chat_member.status}")

        # Check if a user has effectively joined the channel as a regular member
        is_newly_joined_member = (
            chat_member_data.new_chat_member.status == ChatMemberStatus.MEMBER and
            chat_member_data.old_chat_member.status not in [
                ChatMemberStatus.MEMBER, 
                ChatMemberStatus.ADMINISTRATOR, 
                ChatMemberStatus.OWNER  
            ]
        )
        # Covers cases like: LEFT -> MEMBER, KICKED -> MEMBER (if added by admin after being kicked by bot)

        if is_newly_joined_member:
            user_id_to_check = user.id
            self.logger.info(f"User {user_id_to_check} ({user.full_name}) detected as newly joined/added to channel {chat_id}.")

            # 0. Check if user is an admin of the channel - skip if admin
            try:
                # Get the title of the current chat for logging and potentially for _get_channel_members if it uses it
                current_channel_title = chat_member_data.chat.title if chat_member_data.chat.title else f"Channel ID: {chat_id}"
                admin_user_ids = await self._get_channel_members(bot, channel_id=chat_id, channel_title=current_channel_title)
            except Exception as e:
                self.logger.error(f"Failed to get channel admins in ChatMemberHandler: {e}", exc_info=True)
                admin_user_ids = [] # Proceed with caution, or deny access if admin list is crucial and unavailable
            
            if user_id_to_check in admin_user_ids:
                self.logger.info(f"User {user_id_to_check} is an admin. Skipping membership check.")
                return

            # 1. Check subscription status in DB
            has_active_subscription = False
            try:
                active_subscriptions_db = DatabaseQueries.get_all_active_subscribers()
                active_subscriber_ids_db = {sub['user_id'] for sub in active_subscriptions_db}
                if user_id_to_check in active_subscriber_ids_db:
                    has_active_subscription = True
            except Exception as e:
                self.logger.error(f"Database error while checking subscription for user {user_id_to_check} in ChatMemberHandler: {e}", exc_info=True)
                # Decide behavior: kick or allow if DB check fails? For safety, assume no subscription.
                has_active_subscription = False
            
            if not has_active_subscription:
                self.logger.info(f"User {user_id_to_check} ({user.full_name}) has no active subscription. Kicking from channel {chat_id}.")
                try:
                    await bot.ban_chat_member(chat_id=chat_id, user_id=user_id_to_check, until_date=None)
                    self.logger.info(f"Successfully banned user {user_id_to_check} from channel {chat_id}.")
                    await bot.unban_chat_member(chat_id=chat_id, user_id=user_id_to_check)
                    self.logger.info(f"Successfully unbanned user {user_id_to_check} from channel {chat_id} (to allow rejoining).")
                    
                    reason = "شما اشتراک فعالی برای عضویت در این کانال ندارید و یا اشتراک شما منقضی شده است."
                    await self.send_membership_status_notification(bot, user_id_to_check, reason, is_kicked=True)
                except Forbidden as e_forbidden:
                    self.logger.error(f"FORBIDDEN error when trying to kick user {user_id_to_check} via ChatMemberHandler: {e_forbidden}. Bot might lack permissions or target is admin.")
                except BadRequest as e_bad_request:
                    self.logger.error(f"BAD_REQUEST error when trying to kick user {user_id_to_check} via ChatMemberHandler: {e_bad_request}. (e.g. user not found in chat)")
                except Exception as e_generic:
                    self.logger.error(f"Generic error when trying to kick user {user_id_to_check} via ChatMemberHandler: {e_generic}", exc_info=True)
            else:
                self.logger.info(f"User {user_id_to_check} ({user.full_name}) has an active subscription. Allowing access.")
        elif chat_member_data.new_chat_member.status == ChatMemberStatus.LEFT:
            self.logger.info(f"User {user.id} ({user.full_name}) left channel {chat_id}.")
        elif chat_member_data.new_chat_member.status == ChatMemberStatus.BANNED:
            self.logger.info(f"User {user.id} ({user.full_name}) was kicked/banned from channel {chat_id}.")

    # --- Command Handlers ---
    @admin_only
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command for admin users."""
        user = update.effective_user
        admin_alias = get_alias_from_admin_list(user.id, self.admin_config) or user.first_name
        self.logger.info(f"Admin user {admin_alias} ({user.id}) started the bot.")
        await update.message.reply_text(
            f"سلام {admin_alias}! به ربات مدیریت آکادمی دارایی خوش آمدید.\n"
            f"برای مشاهده دستورات موجود از /help استفاده کنید."
        )

    @admin_only
    async def view_tickets_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display open tickets to admins."""
        user = update.effective_user
        admin_alias = get_alias_from_admin_list(user.id, self.admin_config) or user.first_name
        self.logger.info(f"Admin {admin_alias} ({user.id}) requested to view tickets.")

        try:
            open_tickets = Database.get_open_tickets()
            if not open_tickets:
                await update.message.reply_text("در حال حاضر هیچ تیکت بازی وجود ندارد.")
                return

            response_message = "لیست تیکت‌های باز:\n\n"
            for ticket in open_tickets:
                ticket_id = ticket['id']
                user_id = ticket['user_id']
                subject = ticket['subject']
                created_at = ticket['created_at']
                # Try to get user's alias or name from MainBot if available
                user_display = f"کاربر {user_id}"
                if self.main_bot_app and hasattr(self.main_bot_app, 'user_data_cache') and user_id in self.main_bot_app.user_data_cache:
                    user_display = self.main_bot_app.user_data_cache[user_id].get('name', user_display)
                
                response_message += f"🎫 تیکت ID: {ticket_id}\n"
                response_message += f"👤 از طرف: {user_display}\n"
                response_message += f"موضوع: {subject}\n"
                response_message += f"📅 تاریخ ایجاد: {created_at}\n"
                response_message += "---\n"
            
            keyboard = []
            for ticket in open_tickets:
                keyboard.append([InlineKeyboardButton(f"مشاهده تیکت {ticket['id']} ({ticket['subject']})", callback_data=f"view_ticket_{ticket['id']}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(response_message, reply_markup=reply_markup)

        except Exception as e:
            self.logger.error(f"Error in view_tickets_command: {e}", exc_info=True)
            await update.message.reply_text("خطایی در نمایش تیکت‌ها رخ داد. لطفاً دوباره تلاش کنید.")
    
    @admin_only
    async def validate_memberships_now_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Command to run membership validation immediately. Admin only."""
        user_alias = get_alias_from_admin_list(update.effective_user.id, self.admin_config)
        self.logger.info(f"User {user_alias} ({update.effective_user.id}) triggered validate_memberships_now_command.")
        await update.message.reply_text("در حال شروع اعتبارسنجی عضویت‌ها... این فرآیند ممکن است کمی طول بکشد.")
        try:
            await self.validate_memberships(context) # Pass context if needed by the original method, or None
            await update.message.reply_text("اعتبارسنجی عضویت‌ها با موفقیت انجام شد.")
            self.logger.info("Membership validation triggered by admin completed successfully.")
        except Exception as e:
            self.logger.error(f"Error during admin-triggered membership validation: {e}", exc_info=True)
            await update.message.reply_text(f"خطایی در هنگام اعتبارسنجی عضویت‌ها رخ داد: {e}")

    @admin_only
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Displays help message for admin commands."""
        user_alias = get_alias_from_admin_list(update.effective_user.id, self.admin_config)
        self.logger.info(f"User {user_alias} ({update.effective_user.id}) requested help.")

        help_text = (
            "راهنمای دستورات ربات مدیریت:\n\n"
            "▫️ /start - نمایش پیام خوشامدگویی و اطلاعات ادمین.\n"
            "▫️ /tickets - نمایش لیست تیکت‌های باز کاربران.\n"
            "▫️ /validate_now - اجرای فوری اعتبارسنجی عضویت کاربران در کانال.\n"
            "▫️ /help - نمایش همین پیام راهنما.\n\n"
            "(توجه: برخی قابلیت‌ها مانند پاسخ به تیکت از طریق دکمه‌های شیشه‌ای در پیام تیکت قابل دسترسی هستند.)"
        )
        await update.message.reply_text(help_text)

    async def validate_memberships(self, context: Optional[ContextTypes.DEFAULT_TYPE] = None):
        """Validate channel memberships and kick unauthorized users for all configured channels."""
        self.logger.info("Starting channel membership validation for all configured channels...")
        bot = None
        if context and hasattr(context, 'bot'):
            bot = context.bot
        elif self.application and hasattr(self.application, 'bot') and self.application.bot is not None:
            bot = self.application.bot
        else:
            self.logger.error("ManagerBot: Could not obtain bot instance in validate_memberships. Aborting validation.")
            return

        if not config.TELEGRAM_CHANNELS_INFO:
            self.logger.warning("TELEGRAM_CHANNELS_INFO is not configured or is empty. No channels to validate.")
            return

        for channel_info in config.TELEGRAM_CHANNELS_INFO:
            current_channel_id = channel_info.get('id')
            current_channel_title = channel_info.get('title', f"ID: {current_channel_id}") # Default title if missing

            if not isinstance(current_channel_id, int):
                self.logger.error(f"Channel '{current_channel_title}' has an invalid ID: {current_channel_id}. Skipping validation for this channel.")
                continue
            
            self.logger.info(f"--- Starting validation for channel: '{current_channel_title}' (ID: {current_channel_id}) ---")

            try:
                admin_user_ids = await self._get_channel_members(bot, current_channel_id, current_channel_title)
                self.logger.info(f"Fetched {len(admin_user_ids)} admin user IDs for channel '{current_channel_title}': {admin_user_ids}")
                if not admin_user_ids:
                     self.logger.warning(f"Admin list for channel '{current_channel_title}' is empty. This might be an issue if bot isn't admin or no admins exist.")

                # Part 1: Check users who SHOULD be members (active subscribers in DB)
                active_subscriptions_db = DatabaseQueries.get_all_active_subscribers()
                active_subscriber_ids_db = {sub['user_id'] for sub in active_subscriptions_db}
                self.logger.info(f"Found {len(active_subscriber_ids_db)} active subscribers in DB (applies to all channels). For channel '{current_channel_title}'.")

                for user_id_to_check in list(active_subscriber_ids_db):
                    if user_id_to_check in admin_user_ids:
                        self.logger.info(f"User {user_id_to_check} is an admin in channel '{current_channel_title}', skipping membership status check.")
                        continue

                    try:
                        chat_member = await bot.get_chat_member(chat_id=current_channel_id, user_id=user_id_to_check)
                        self.logger.debug(f"Status of active DB subscriber {user_id_to_check} in channel '{current_channel_title}': {chat_member.status}")
                        if chat_member.status in ['left', 'kicked']:
                            self.logger.warning(f"User {user_id_to_check} has active DB sub but is {chat_member.status} in channel '{current_channel_title}'.")
                    except BadRequest as e:
                        if "user not found" in str(e).lower():
                            self.logger.warning(f"User {user_id_to_check} (active DB subscriber) not found in Telegram (for channel '{current_channel_title}').")
                        else:
                            self.logger.error(f"Error checking member {user_id_to_check} in channel '{current_channel_title}' (BadRequest): {e}.")
                    except Forbidden as e:
                        self.logger.error(f"Forbidden to get chat member {user_id_to_check} for channel '{current_channel_title}': {e}.")
                    except Exception as e:
                        self.logger.error(f"Unexpected error checking member {user_id_to_kick_check} in channel '{current_channel_title}': {e}", exc_info=True)
                
                # Part 2: Identify and kick users in channel with non-active/expired/no DB subscription
                users_with_non_active_subs_db = DatabaseQueries.get_users_with_non_active_subscription_records()
                if users_with_non_active_subs_db is None:
                    users_with_non_active_subs_db = []
                
                self.logger.info(f"Found {len(users_with_non_active_subs_db)} users with non-active/expired DB subscriptions to check in channel '{current_channel_title}'.")

                kicked_count = 0
                for record in users_with_non_active_subs_db:
                    user_id_to_kick_check = record.get('user_id')
                    if not user_id_to_kick_check:
                        self.logger.warning(f"Skipping record due to missing user_id: {record} (for channel '{current_channel_title}')")
                        continue

                    if user_id_to_kick_check in active_subscriber_ids_db:
                        self.logger.info(f"User {user_id_to_kick_check} appeared in non-active list but is active in DB. Skipping kick for channel '{current_channel_title}'.")
                        continue 
                    
                    if user_id_to_kick_check in admin_user_ids:
                        self.logger.info(f"User {user_id_to_kick_check} is an admin in channel '{current_channel_title}', skipping kick check.")
                        continue

                    try:
                        chat_member = await bot.get_chat_member(chat_id=current_channel_id, user_id=user_id_to_kick_check)
                        if chat_member.status not in ['left', 'kicked']:
                            self.logger.info(f"User {user_id_to_kick_check} (DB status: {record.get('status', 'N/A')}) is in channel '{current_channel_title}' (TG status: {chat_member.status}). Attempting kick.")
                            try:
                                await bot.ban_chat_member(chat_id=current_channel_id, user_id=user_id_to_kick_check, until_date=None)
                                self.logger.info(f"Successfully banned user {user_id_to_kick_check} from channel '{current_channel_title}'.")
                                await bot.unban_chat_member(chat_id=current_channel_id, user_id=user_id_to_kick_check)
                                self.logger.info(f"Successfully unbanned user {user_id_to_kick_check} from channel '{current_channel_title}'.")
                                kicked_count += 1
                                reason = f"اشتراک شما ({record.get('status', 'نامعتبر')}) برای دسترسی به '{current_channel_title}' به پایان رسیده یا نامعتبر است."
                                await self.send_membership_status_notification(bot, user_id_to_kick_check, reason, is_kicked=True)
                            except Forbidden as kick_err_forbidden:
                                self.logger.error(f"FORBIDDEN error kicking user {user_id_to_kick_check} from '{current_channel_title}': {kick_err_forbidden}. BOT LACKS BAN PERMISSION?", exc_info=True)
                            except BadRequest as kick_err_bad_request:
                                self.logger.error(f"BAD_REQUEST error kicking user {user_id_to_kick_check} from '{current_channel_title}': {kick_err_bad_request}. USER/CHAT NOT FOUND?", exc_info=True)
                            except Exception as kick_err_generic:
                                self.logger.error(f"Generic error kicking user {user_id_to_kick_check} from '{current_channel_title}': {kick_err_generic}", exc_info=True)
                    except BadRequest as e:
                        if "user not found" in str(e).lower() or "member not found" in str(e).lower():
                            self.logger.info(f"User {user_id_to_kick_check} (to kick) not found in Telegram for channel '{current_channel_title}'. Skipping kick.")
                        elif "chat not found" in str(e).lower():
                            self.logger.error(f"Channel '{current_channel_title}' (ID: {current_channel_id}) not found by bot. Halting validation FOR THIS CHANNEL.")
                            continue # Continue to the next channel in the list
                        else:
                            self.logger.error(f"Error processing user {user_id_to_kick_check} for kick in '{current_channel_title}' (BadRequest): {e}", exc_info=True)
                    except Forbidden as e:
                        self.logger.error(f"Forbidden to check/kick user {user_id_to_kick_check} in '{current_channel_title}': {e}. BOT PERMISSIONS?", exc_info=True)
                    except Exception as e:
                        self.logger.error(f"Unexpected error processing user {user_id_to_kick_check} for kick in '{current_channel_title}': {e}", exc_info=True)

                self.logger.info(f"--- Validation for channel '{current_channel_title}' (ID: {current_channel_id}) completed. {kicked_count} user(s) kicked. ---")

            except AttributeError as e:
                self.logger.error(f"AttributeError during validation for channel '{current_channel_title}' (ID: {current_channel_id}): {e}. DBQueries method?", exc_info=True)
            except Exception as e:
                self.logger.error(f"General error during validation for channel '{current_channel_title}' (ID: {current_channel_id}): {e}", exc_info=True)
        
        self.logger.info("All configured channels processed for membership validation.")
    
    async def _get_channel_members(self, bot, channel_id: int, channel_title: str):
        """
        Get admin members from the specified channel.
        """
        admin_ids = []
        try:
            self.logger.info(f"Attempting to get administrators for channel: '{channel_title}' (ID: {channel_id})")
            if not isinstance(channel_id, int):
                self.logger.error(f"Channel ID provided is not a valid integer: {channel_id} for channel '{channel_title}'. Cannot fetch admins.")
                return admin_ids

            administrators = await bot.get_chat_administrators(chat_id=channel_id, read_timeout=20, connect_timeout=10)
            admin_ids = [admin.user.id for admin in administrators]
            self.logger.info(f"Found {len(admin_ids)} administrators for channel '{channel_title}' (ID: {channel_id}): {admin_ids}")
        except BadRequest as e:
            self.logger.error(f"Error getting administrators for channel '{channel_title}' (ID: {channel_id}) (BadRequest): {e}. Ensure channel ID is correct and bot is admin.")
        except Forbidden as e:
            self.logger.error(f"Error getting administrators for channel '{channel_title}' (ID: {channel_id}) (Forbidden): {e}. Ensure bot has rights to get chat administrators.")
        except Exception as e:
            self.logger.error(f"Unexpected error getting administrators for channel '{channel_title}' (ID: {channel_id}): {e}", exc_info=True)
        return admin_ids

    async def send_membership_status_notification(self, bot, user_id, reason_message, is_kicked=False):
        """
        Sends a notification to the user about their membership status (e.g., kicked).
        """
        action_taken = "از کانال حذف شدید" if is_kicked else "وضعیت عضویت شما تغییر کرده است"
        message = (
            f"کاربر گرامی،\n\n"
            f"به اطلاع می‌رسانیم که شما {action_taken}.\n"
            f"دلیل: {html.escape(reason_message)}\n\n"
            f"در صورت نیاز به پشتیبانی یا داشتن سوال، لطفاً با ادمین‌های ما در ارتباط باشید.\n\n"
            f"با احترام،\nآکادمی دارایی"
        )
        try:
            await bot.send_message(chat_id=user_id, text=message, parse_mode=ParseMode.HTML) # Ensure ParseMode is imported
            self.logger.info(f"Sent membership status notification to user {user_id}.")
        except BadRequest as e:
            self.logger.error(f"Failed to send membership status notification to {user_id} (BadRequest): {e}")
        except Forbidden as e:
            # This can happen if the user has blocked the bot
            self.logger.warning(f"Failed to send membership status notification to {user_id} (Forbidden - user may have blocked bot): {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error sending membership status notification to {user_id}: {e}", exc_info=True)
    
    async def send_expiration_reminders(self, context):
        """Send reminders to users with expiring subscriptions"""
        self.logger.info("Sending expiration reminders")
        
        try:
            # Get bot instance for API calls
            bot = self.application.bot
            
            # Get users with subscriptions expiring soon
            expiring_soon = Database.get_expiring_subscriptions(config.REMINDER_DAYS)
            
            if not expiring_soon:
                self.logger.info("No expiring subscriptions found")
                return
            
            self.logger.info(f"Found {len(expiring_soon)} expiring subscriptions")
            
            # Send reminders to each user
            for subscription in expiring_soon:
                user_id = subscription['user_id']
                days_left = calculate_days_left(subscription['end_date'])
                
                # Send expiration reminder
                await send_expiration_reminder(bot, user_id, days_left)
                
                self.logger.info(f"Sent expiration reminder to user {user_id} ({days_left} days left)")
            
            # Get users with already expired subscriptions who haven't been notified
            expired = Database.get_recently_expired_subscriptions()
            
            if not expired:
                self.logger.info("No recent expired subscriptions found")
                return
            
            self.logger.info(f"Found {len(expired)} expired subscriptions")
            
            # Send expired notifications to each user
            for subscription in expired:
                user_id = subscription['user_id']
                
                # Send expired notification
                await send_expired_notification(bot, user_id)
                
                # Mark as notified
                Database.mark_subscription_notified(subscription['subscription_id'])
                
                self.logger.info(f"Sent expiration notification to user {user_id}")
        
        except Exception as e:
            self.logger.error(f"Error sending expiration reminders: {e}")
    
    def setup_handlers(self):
        """Setup command, message, and callback query handlers."""
        # Command Handlers for admin actions
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("tickets", self.view_tickets_command))
        self.application.add_handler(CommandHandler("validate_now", self.validate_memberships_now_command))
        self.application.add_handler(CommandHandler("help", self.help_command))

        # Add ticket management handlers from the ticket handler
        for handler in self.ticket_handler.get_handlers():
            self.application.add_handler(handler)

    # --- Background Tasks --- (This comment was likely part of process_admin_tickets or similar)
    async def process_admin_tickets(self, context: ContextTypes.DEFAULT_TYPE):
        """Process support tickets that need admin attention"""
        self.logger.info("Processing admin tickets")
        
        try:
            # Get tickets that need admin attention
            # This is a placeholder. Replace with actual database query if 'DatabaseQueries' is the intended class.
            # pending_tickets = DatabaseQueries.get_pending_admin_tickets() 
            pending_tickets = [] # Placeholder until actual query is confirmed
            
            if not pending_tickets:
                # self.logger.info("No pending admin tickets.") # Optional: logging when no tickets
                return
            
            self.logger.info(f"Found {len(pending_tickets)} tickets needing admin attention")
            
            # This is a placeholder for actual admin ticket processing
            # In a real implementation, you would send these tickets to the admin
            # and provide a way for the admin to respond
            
            # For now, we'll just log the tickets
            for ticket in pending_tickets:
                self.logger.info(f"Ticket #{ticket.get('ticket_id', 'N/A')} from user {ticket.get('user_id', 'N/A')} needs attention")
        
        except Exception as e:
            self.logger.error(f"Error processing admin tickets: {e}", exc_info=True)
    
    async def handle_admin_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle responses from admins to support tickets"""
        # This is a placeholder for handling admin responses to tickets
        # In a real implementation, this would parse the admin's message
        # and send it to the user who created the ticket
        user_input = update.message.text
        admin_user = update.effective_user
        self.logger.info(f"Admin {admin_user.id} responded: {user_input}")
        # Example: await update.message.reply_text("پاسخ شما ثبت شد.")
        pass

    async def send_new_ticket_notification(self, notif_message: str):
        """
        Sends a notification message to admins with the 'main_bot_support_staff' role.
        """
        try:
            # First check if we have an admin config
            if not self.admin_config:
                self.logger.warning("ManagerBot: Admin config is not loaded. Cannot send support notification.")
                return

            # Debug log to see what's in admin_config
            self.logger.info(f"ManagerBot: Admin config contains {len(self.admin_config)} entries.")
            
            # Try to send to each admin with the right role
            notified_count = 0
            for admin_info in self.admin_config:
                # Check if admin_info is a dictionary and has the required role and chat_id
                if isinstance(admin_info, dict):
                    roles = admin_info.get('roles', [])
                    chat_id = admin_info.get('chat_id')
                    
                    # Debug the roles to see what's available
                    self.logger.info(f"ManagerBot: Admin {admin_info.get('alias', 'Unknown')} has roles: {roles}")
                    
                    if 'main_bot_support_staff' in roles and chat_id:
                        try:
                            await self.application.bot.send_message(
                                chat_id=chat_id,
                                text=notif_message,
                                parse_mode=ParseMode.HTML
                            )
                            notified_count += 1
                            self.logger.info(f"ManagerBot: Sent new ticket notification to admin {chat_id} ({admin_info.get('alias', 'Unknown')}).")
                        except Exception as e:
                            self.logger.error(f"ManagerBot: Failed to send notification to admin {chat_id}: {e}")
            
            # Log the result
            if notified_count == 0:
                self.logger.warning("ManagerBot: No admins with 'main_bot_support_staff' role found or notifications failed for all targeted admins.")
            else:
                self.logger.info(f"ManagerBot: Successfully sent new ticket notification to {notified_count} support staff admin(s).")
        
        except Exception as e:
            self.logger.error(f"ManagerBot: Error in send_new_ticket_notification: {e}", exc_info=True)