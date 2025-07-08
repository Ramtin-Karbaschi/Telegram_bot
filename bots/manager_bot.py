"""
Manager Telegram bot for Daraei Academy
"""

import logging
import asyncio
from database.queries import DatabaseQueries as Database # Added Database import
import datetime
from typing import Optional # Added for type hinting
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from typing import Optional, Tuple
from telegram import ChatMember, ChatMemberUpdated
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, 
    CallbackQueryHandler, ConversationHandler, TypeHandler, ChatMemberHandler # Added ChatMemberHandler
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
import html
from database.queries import DatabaseQueries
from utils.helpers import is_user_in_admin_list, get_alias_from_admin_list, admin_only_decorator as admin_only
import config # For other config vars like CHANNEL_ID
from database.models import Database as DBConnection # For DB connection
from handlers.admin_ticket_handlers import AdminTicketHandler  # Fixed import
from handlers.admin_menu_handlers import AdminMenuHandler  # Import admin menu handler
from handlers.admin_product_handlers import AdminProductHandler  # Import admin product handler
from utils.invite_link_manager import InviteLinkManager  # Import InviteLinkManager

# States for ConversationHandler


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


class DummyQuery:
    """
    A dummy class to simulate a CallbackQuery object from a Message update.
    This allows reusing handlers that expect a CallbackQuery.
    """
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.message = update.message
        self.data = None  # Reply keyboard messages don't have callback_data
        self.context = context

    async def answer(self, *args, **kwargs):
        """A no-op for a dummy query, as there's nothing to 'answer'."""
        pass

    async def edit_message_text(self, text, parse_mode=None, reply_markup=None, **kwargs):
        """
        Reply keyboard messages can't be edited.
        This sends a new message instead.
        """
        await self.message.reply_text(
            text=text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
        return None


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
        
        # Initialize database connection and queries
        self.db = DBConnection(db_name)
        self.db_queries = DatabaseQueries(self.db)
        self.db_queries.init_database()
        self.main_bot_app = main_bot_app  # Store main_bot_app if provided
        
        # Initialize handlers
        self.ticket_handler = AdminTicketHandler()
        self.product_handler = AdminProductHandler(self.db_queries, admin_config=self.admin_config)
        self.menu_handler = AdminMenuHandler(self.db_queries, InviteLinkManager, admin_config=self.admin_config)



        # Setup task handlers
        self.setup_tasks()
        # Setup command and message handlers
        self.setup_handlers()

        # Add ChatMemberHandler to check new members
        self.application.add_handler(ChatMemberHandler(self.handle_chat_member_update, ChatMemberHandler.CHAT_MEMBER))
        
        # Add error handler for ManagerBot
        self.application.add_error_handler(manager_bot_error_handler)

    def setup_tasks(self):
        """Setup background tasks"""
        self.logger.info("Scheduling periodic membership validation job.")
        job_queue = self.application.job_queue
        job_queue.run_repeating(
            self.validate_memberships,
            interval=60,  # Run every 60 seconds
            first=10,     # Start 10 seconds after the bot starts
            name="validate_memberships_job"
        )

    async def start(self):
        """Start the bot"""
        self.logger.info("Starting Manager Bot")
        await self.application.initialize()
        
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

    def is_user_authorized(self, user_id: int) -> bool:
        """Check if a user has an active subscription."""
        # This is now synchronous as DB queries are synchronous
        active_subscriptions = DatabaseQueries.get_all_active_subscribers()
        # fetchall() returns a list of tuples, so we access by index.
        active_user_ids = {sub[0] for sub in active_subscriptions}
        return user_id in active_user_ids

    async def handle_chat_member_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle chat member updates to kick unauthorized users."""
        result = self.extract_status_change(update.chat_member)
        if result is None:
            return

        was_member, is_member = result
        user = update.chat_member.new_chat_member.user
        chat = update.chat_member.chat

        if not was_member and is_member:
            self.logger.info(f"User {user.id} ({user.first_name}) joined chat {chat.id} ({chat.title}). Checking authorization...")
            if not self.is_user_authorized(user.id):
                self.logger.warning(f"User {user.id} is NOT authorized. Kicking from {chat.id}.")
                try:
                    await context.bot.ban_chat_member(chat_id=chat.id, user_id=user.id)
                    await context.bot.unban_chat_member(chat_id=chat.id, user_id=user.id)
                    self.logger.info(f"Successfully kicked unauthorized user {user.id} from {chat.id}")
                except Exception as e:
                    self.logger.error(f"Failed to kick user {user.id} from {chat.id}: {e}")
            else:
                self.logger.info(f"User {user.id} is authorized.")
            # --- Mark one-time invite link as used, if any ---
        if not was_member and is_member:
            invite_link_obj = getattr(update.chat_member, 'invite_link', None)
            if invite_link_obj and invite_link_obj.invite_link:
                try:
                    from database import invite_link_queries as ilq
                    ilq.mark_invite_link_used(invite_link_obj.invite_link)
                    self.logger.info(f"Marked invite link as used for user {user.id}: {invite_link_obj.invite_link}")
                except Exception as e:
                    self.logger.error(f"Failed to mark invite link used for user {user.id}: {e}")
        elif was_member and not is_member:
            status = update.chat_member.new_chat_member.status
            self.logger.info(f"User {user.id} ({user.first_name}) left or was kicked from chat {chat.id} ({chat.title}). New status: {status}")
            # Update user status in the database to 'kicked' or 'left'
            try:
                Database.update_user_single_field(user_id=user.id, field_name='status', field_value=status)
                self.logger.info(f"Updated status for user {user.id} to '{status}' in the database.")
            except Exception as e:
                self.logger.error(f"Failed to update status for user {user.id} in database: {e}")

    @staticmethod
    def extract_status_change(chat_member_update: ChatMemberUpdated) -> Optional[Tuple[bool, bool]]:
        """Takes a ChatMemberUpdated instance and extracts whether the 'old' and 'new' members are part of the chat."""
        status_change = chat_member_update.difference().get("status")
        if status_change is None:
            return None

        old_is_member, new_is_member = status_change
        
        member_statuses = [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]

        was_member = old_is_member in member_statuses
        is_member = new_is_member in member_statuses

        return was_member, is_member

    async def stop(self):
        """Stop the bot"""
        self.logger.info("Stopping Manager Bot")
        if self.application.updater and self.application.updater.running:
            await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        self.logger.info("Manager Bot stopped")



    # --- Command Handlers ---
    @admin_only
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command for admin users and serves as the main menu."""
        user = update.effective_user
        admin_alias = get_alias_from_admin_list(user.id, self.admin_config) or user.first_name
        self.logger.info(f"Admin user {admin_alias} ({user.id}) accessed the main menu.")

        keyboard = [
            [KeyboardButton(self.menu_handler.button_texts['users']), KeyboardButton(self.menu_handler.button_texts['products'])],
            [KeyboardButton(self.menu_handler.button_texts['tickets']), KeyboardButton(self.menu_handler.button_texts['payments'])],
            [KeyboardButton(self.menu_handler.button_texts['broadcast']), KeyboardButton(self.menu_handler.button_texts['stats'])],
            [KeyboardButton(self.menu_handler.button_texts['settings']), KeyboardButton(self.menu_handler.button_texts['back_to_main'])],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.effective_message.reply_text(
            'پنل مدیریت در اختیار شماست. لطفا گزینه مورد نظر را انتخاب کنید:',
            reply_markup=reply_markup
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
                        if "user not found" in str(e).lower() or "participant_id_invalid" in str(e).lower():
                            self.logger.warning(f"User {user_id_to_check} (active DB subscriber) not found in Telegram (for channel '{current_channel_title}').")
                        else:
                            self.logger.error(f"Error checking member {user_id_to_check} in channel '{current_channel_title}' (BadRequest): {e}.")
                    except Forbidden as e:
                        self.logger.error(f"Forbidden to get chat member {user_id_to_check} for channel '{current_channel_title}': {e}.")
                    except Exception as e:
                        self.logger.error(f"Unexpected error checking member {user_id_to_check} in channel '{current_channel_title}': {e}", exc_info=True)
                
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
                                await bot.unban_chat_member(chat_id=current_channel_id, user_id=user_id_to_kick_check)
                                kicked_count += 1
                                self.logger.info(f"User {user_id_to_kick_check} kicked from '{current_channel_title}'.")
                            except BadRequest as e:
                                if "Not enough rights" in e.message:
                                    self.logger.warning(f"Could not kick {user_id_to_kick_check} from {current_channel_title}: Insufficient permissions. Please ensure the bot is an admin with ban rights.")
                                else:
                                    self.logger.error(f"BadRequest error kicking user {user_id_to_kick_check} from '{current_channel_title}': {e}")
                            except Exception as e:
                                self.logger.error(f"Generic error kicking user {user_id_to_kick_check} from '{current_channel_title}': {e}")
                    except BadRequest as e:
                        if "user not found" in str(e).lower() or "member not found" in str(e).lower() or "participant_id_invalid" in str(e).lower():
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
            self.logger.error(f"Error getting administrators for channel '{current_channel_title}' (ID: {channel_id}) (Forbidden): {e}. Ensure bot has rights to get chat administrators.")
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

    # ------------------ Ticket notification ------------------
    async def send_new_ticket_notification(self, notification_text: str):
        """Forward a newly-created ticket alert to all configured admins."""
        if not notification_text:
            return
        if not self.application or not self.application.bot:
            self.logger.error("send_new_ticket_notification called but bot application not initialized.")
            return
        # Extract admin chat IDs from admin_config (dict or list) or fallback to config.MANAGER_BOT_ADMIN_IDS
        admin_ids: list[int] = []
        if isinstance(self.admin_config, dict):
            admin_ids = [int(k) for k in self.admin_config.keys()]
        elif isinstance(self.admin_config, list):
            try:
                # list of dicts [{'chat_id':123,...}]
                admin_ids = [int(a.get('chat_id')) for a in self.admin_config if a.get('chat_id')]
            except Exception:
                admin_ids = [int(a) for a in self.admin_config if a]
        if not admin_ids:
            admin_ids = getattr(config, 'MANAGER_BOT_ADMIN_IDS', []) or []
        if not admin_ids:
            self.logger.warning("No admin IDs configured – cannot deliver ticket notification.")
            return
        sent_count = 0
        for adm in admin_ids:
            try:
                await self.application.bot.send_message(chat_id=adm, text=notification_text, parse_mode=ParseMode.HTML)
                sent_count += 1
            except Exception as e:
                self.logger.error(f"Failed to send ticket notification to admin {adm}: {e}")
        self.logger.info(f"Ticket notification delivered to {sent_count}/{len(admin_ids)} admins.")
    
    async def _admin_reply_keyboard_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.logger.info(f"Admin reply keyboard handler triggered with text: {update.message.text} from user {update.effective_user.id}")
        """Handle admin reply keyboard button presses by sending a new message with the corresponding inline menu."""
        message_text = update.message.text
        user_id = update.message.from_user.id

        # Check if the user is an admin
        admin_ids = []
    
        admin_ids = [admin.get('chat_id') for admin in self.admin_config if isinstance(admin, dict)]

        handler_coro = self.admin_buttons_map.get(message_text)
        if handler_coro:
            # If the handler is start_command, it's the back button. Call it directly.
            if handler_coro == self.start_command:
                await handler_coro(update, context)
            else:
                # Other handlers expect a query-like object.
                dummy_query = DummyQuery(update, context)
                await handler_coro(dummy_query)
            return
        else:
            # If the text doesn't match any button, we can either ignore it or handle it as a generic message.
            # For now, we ignore it, as another handler will pick it up.
            self.logger.debug(f"No admin button matched text: '{message_text}'")

    def setup_handlers(self):
        """Setup command, message, and callback query handlers."""
        application = self.application

        # Command Handlers for admin actions
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("tickets", self.view_tickets_command))
        application.add_handler(CommandHandler("validate_now", self.validate_memberships_now_command))
        application.add_handler(CommandHandler("help", self.help_command))

        # --- Conversation and Callback Handlers ---
        # Add conversation handlers from different modules
        for handler in self.product_handler.get_product_conv_handlers():
            application.add_handler(handler)
        application.add_handler(self.ticket_handler.get_ticket_conversation_handler())
        # Add all handlers from the menu handler, including conversation handlers
        for handler in self.menu_handler.get_handlers():
            application.add_handler(handler)


        # --- Message Handlers for Admin Private Chat ---
        # This handler is specifically for the admin's main menu, which uses ReplyKeyboardMarkup.
        admin_button_filter = filters.Text(list(self.menu_handler.admin_buttons_map.keys()))
        application.add_handler(MessageHandler(
            admin_button_filter & filters.ChatType.PRIVATE, self.menu_handler.route_admin_command
        ), group=0)

        # This is a general message handler for admins, which can be used for features like search.
        # It should not handle commands or the main menu buttons.
        # This is a general message handler for admins, which can be used for features like search.
        # It should not handle commands or the main menu buttons.
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE & ~admin_button_filter,
            self.menu_handler.message_handler
        ), group=1)

        # Generic UpdateHandler for logging (must have low priority)
        application.add_handler(TypeHandler(Update, self.log_all_updates), group=10)

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
        self.logger.error(f"Error getting administrators for channel '{current_channel_title}' (ID: {channel_id}) (Forbidden): {e}. Ensure bot has rights to get chat administrators.")
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

# ------------------ Ticket notification ------------------
async def send_new_ticket_notification(self, notification_text: str):
    """Forward a newly-created ticket alert to all configured admins."""
    if not notification_text:
        return
    if not self.application or not self.application.bot:
        self.logger.error("send_new_ticket_notification called but bot application not initialized.")
        return
    # Extract admin chat IDs from admin_config (dict or list) or fallback to config.MANAGER_BOT_ADMIN_IDS
    admin_ids: list[int] = []
    if isinstance(self.admin_config, dict):
        admin_ids = [int(k) for k in self.admin_config.keys()]
    elif isinstance(self.admin_config, list):
        try:
            # list of dicts [{'chat_id':123,...}]
            admin_ids = [int(a.get('chat_id')) for a in self.admin_config if a.get('chat_id')]
        except Exception:
            admin_ids = [int(a) for a in self.admin_config if a]
    if not admin_ids:
        admin_ids = getattr(config, 'MANAGER_BOT_ADMIN_IDS', []) or []
    if not admin_ids:
        self.logger.warning("No admin IDs configured – cannot deliver ticket notification.")
        return
    sent_count = 0
    for adm in admin_ids:
        try:
            await self.application.bot.send_message(chat_id=adm, text=notification_text, parse_mode=ParseMode.HTML)
            sent_count += 1
        except Exception as e:
            self.logger.error(f"Failed to send ticket notification to admin {adm}: {e}")
    self.logger.info(f"Ticket notification delivered to {sent_count}/{len(admin_ids)} admins.")
    
async def _admin_reply_keyboard_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    self.logger.info(f"Admin reply keyboard handler triggered with text: {update.message.text} from user {update.effective_user.id}")
    """Handle admin reply keyboard button presses by sending a new message with the corresponding inline menu."""
    message_text = update.message.text
    user_id = update.message.from_user.id

    # Check if the user is an admin
    admin_ids = []
    
    admin_ids = [admin.get('chat_id') for admin in self.admin_config if isinstance(admin, dict)]

    handler_coro = self.admin_buttons_map.get(message_text)
    if handler_coro:
        # If the handler is start_command, it's the back button. Call it directly.
        if handler_coro == self.start_command:
            await handler_coro(update, context)
        else:
            # Other handlers expect a query-like object.
            dummy_query = DummyQuery(update, context)
            await handler_coro(dummy_query)
        return
    else:
        # If the text doesn't match any button, we can either ignore it or handle it as a generic message.
        # For now, we ignore it, as another handler will pick it up.
        self.logger.debug(f"No admin button matched text: '{message_text}'")

def setup_handlers(self):
    """Setup command, message, and callback query handlers."""
    application = self.application

    # Command Handlers for admin actions
    application.add_handler(CommandHandler("start", self.start_command))
    application.add_handler(CommandHandler("tickets", self.view_tickets_command))
    application.add_handler(CommandHandler("validate_now", self.validate_memberships_now_command))
    application.add_handler(CommandHandler("help", self.help_command))

    # --- Conversation and Callback Handlers ---
    # Add conversation handlers from different modules
    for handler in self.product_handler.get_product_conv_handlers():
        application.add_handler(handler)
    for handler in self.product_handler.get_static_product_handlers():
        application.add_handler(handler)
    application.add_handler(self.ticket_handler.get_ticket_conversation_handler())
    application.add_handler(self.menu_handler.get_invite_link_conv_handler())
    application.add_handler(self.menu_handler.get_ban_unban_conv_handler())
    application.add_handler(self.menu_handler.get_broadcast_conv_handler())

    # --- CallbackQuery Handlers for static menus ---
    # This handles callbacks from non-conversation inline keyboards, like the main settings menu.
    application.add_handler(CallbackQueryHandler(self.menu_handler.callback_query_handler))

    # --- Message Handlers for Admin Private Chat (Group 0) ---
    # This handler is specifically for the admin's main menu, which uses ReplyKeyboardMarkup.
    admin_button_filter = filters.Text(list(self.admin_buttons_map.keys()))
    application.add_handler(MessageHandler(
        admin_button_filter & filters.ChatType.PRIVATE,
        self._admin_reply_keyboard_handler
    ))

    # This is a general message handler for admins, which can be used for features like search.
    # It should not handle commands or the main menu buttons.
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE & ~admin_button_filter,
        self.menu_handler.message_handler
    ))

    # Generic UpdateHandler for logging (Group 100)
    application.add_handler(TypeHandler(Update, self.log_all_updates), group=100)