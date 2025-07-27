"""
Manager Telegram bot for Daraei Academy
"""

import logging
import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
from datetime import datetime, timedelta, timezone, time
import asyncio
from zoneinfo import ZoneInfo
from utils.expiration_reminder import (
    get_expiring_subscriptions,
    was_reminder_sent_today,
    log_reminder_sent,
)
from database.queries import DatabaseQueries
from utils.helpers import is_user_in_admin_list, get_alias_from_admin_list, admin_only_decorator as admin_only, staff_only_decorator as staff_only
import config # For other config vars like CHANNEL_ID
from database.models import Database as DBConnection # For DB connection
from handlers.admin.discount_handlers import get_create_discount_conv_handler
from handlers.admin.free_package_admin_handlers import get_freepkg_admin_handlers  # Fixed import
from handlers.admin.altseason_admin_handler import AdminAltSeasonHandler
from handlers.admin_menu_handlers import AdminMenuHandler  # Import admin menu handler
from handlers.admin_product_handlers import AdminProductHandler
from handlers.admin_category_handlers import AdminCategoryHandler
# from handlers.admin.broadcast_handler import get_broadcast_conv_handler  # Now integrated in admin_menu_handlers
from handlers.video_upload_handlers import get_conv_handler as get_video_upload_conv
from handlers.survey_builder import get_conv_handler as get_survey_builder_conv
from utils.invite_link_manager import InviteLinkManager  # Import InviteLinkManager
from database.invite_link_queries import get_active_invite_link, mark_invite_link_used  # Invite link DB helpers
from handlers.admin_ticket_handlers import AdminTicketHandler  # Fixed import

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
        builder = Application.builder().token(manager_bot_token)  # Use token from parameters
        self.application = builder.build()
        # Register Video Upload conversation handler for admins (high priority)
        self.application.add_handler(get_video_upload_conv(), group=-1)
        # Register Survey Builder conversation handler
        self.altseason_admin_handler = AdminAltSeasonHandler()  # AltSeason admin management
        self.application.add_handler(get_survey_builder_conv(), group=-1)

        # Register Free Package admin command handlers
        for _h in get_freepkg_admin_handlers():
            self.application.add_handler(_h)
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
        self.category_handler = AdminCategoryHandler(admin_config=self.admin_config)
        self.product_handler = AdminProductHandler(self.db_queries, admin_config=self.admin_config)
        self.menu_handler = AdminMenuHandler(self.db_queries, InviteLinkManager, admin_config=self.admin_config, main_bot_app=self.main_bot_app)
        
        # Add poll handler for survey creation
        from telegram.ext import MessageHandler, filters, CallbackQueryHandler
        self.application.add_handler(MessageHandler(
            filters.POLL, self.product_handler._handle_poll_message
        ), group=-1)
        
        # Add poll-based survey callback handlers
        self.application.add_handler(CallbackQueryHandler(
            self.product_handler._handle_create_new_poll, pattern="^create_new_poll$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.product_handler._handle_remove_last_poll, pattern="^remove_last_poll$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.product_handler._handle_confirm_poll_survey, pattern="^confirm_poll_survey$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.product_handler._handle_cancel_poll_creation, pattern="^cancel_poll_creation$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.product_handler._handle_survey_type_selection, pattern="^survey_type_"
        ))



        # Setup task handlers
        self.setup_tasks()
        # Schedule daily Free Package validation at 18:00 Tehran
        tz_tehran = ZoneInfo("Asia/Tehran")
        self.application.job_queue.run_daily(
            self.validate_free_package_subscribers,
            time=time(18,0,tzinfo=tz_tehran),
            name="daily_free_pkg_validation",
        )
        # --- Disabled: Expiration reminders should only be sent from MainBot ---
        # self.logger.info("Scheduling daily expiration reminder job at 10:00 Asia/Tehran")
        # tz_tehran = ZoneInfo("Asia/Tehran")
        # self.application.job_queue.run_daily(
        #     self.send_expiration_reminders,
        #     time=time(10, 0, tzinfo=tz_tehran),
        #     name="daily_expiration_reminders",
        # )
        # Also run once 30s after startup to cover downtime
        # self.application.job_queue.run_once(self.send_expiration_reminders, when=30)  # Disabled – responsibility moved to MainBot
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
            interval=900,  # Run every 15 minutes
            first=60,     # Start 60 seconds after the bot starts
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
        """Log every received update and persist the corresponding user action in the DB."""
        # Console / file log for generic debugging
        self.logger.info(
            f"GENERIC_UPDATE_HANDLER: Received update of type {type(update)}: {update}"
        )

        # --- Persist user activity in DB (fire-and-forget) ---
        try:
            # Local import to avoid any potential circular dependencies
            from utils.user_actions import UserAction

            telegram_id = update.effective_user.id if update.effective_user else None
            if telegram_id is None:
                return  # Probably a service-related update (e.g., MyChatMember)

            if update.message:
                action_type = "manager_message"
                msg_text = update.message.text or update.message.caption or "<non-text>"
                details = {
                    "message_id": update.message.message_id,
                    "text": msg_text,
                    "is_command": bool(msg_text.startswith("/")) if isinstance(msg_text, str) else False,
                    "chat_type": update.message.chat.type,
                    "date": str(update.message.date),
                    "handler": self.log_all_updates.__name__,
                }
            elif update.callback_query:
                action_type = "manager_callback_query"
                details = {
                    "data": update.callback_query.data,
                    "message_id": update.callback_query.message.message_id if update.callback_query.message else None,
                    "chat_id": update.callback_query.message.chat_id if update.callback_query.message else None,
                    "handler": self.log_all_updates.__name__,
                }
            else:
                action_type = "manager_update"
                details = {"raw": str(update)[:500], "handler": self.log_all_updates.__name__}

            # Non-blocking insert (DB layer commits internally)
            # The UserAction helper will auto-resolve the internal user_db_id when not provided
            UserAction.log_user_action(
                telegram_id=telegram_id,
                action_type=action_type,
                details=details,
            )
        except Exception as exc:
            # Never crash the update handler because of logging failures
            self.logger.error(
                f"Failed to persist manager bot user action: {exc}",
                exc_info=True,
            )

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
            self.logger.info(
                f"User {user.id} ({user.first_name}) joined chat {chat.id} ({chat.title}). Checking authorization..."
            )

            is_authorized = self.is_user_authorized(user.id)
            if not is_authorized:
                # Check database for an unused invite link issued to this user
                active_link = None
                try:
                    active_link = get_active_invite_link(user.id)
                except Exception as e:
                    self.logger.error(f"Error while checking active invite link for user {user.id}: {e}")

                if active_link:
                    self.logger.info(
                        f"User {user.id} has a valid one-time invite link in DB. Marking it as used and allowing join."
                    )
                    try:
                        mark_invite_link_used(active_link)
                    except Exception as e:
                        self.logger.error(
                            f"Failed to mark invite link as used for user {user.id}: {e}")
                    is_authorized = True
                else:
                    # Fallback: use invite_link info available in the update object (if bot created link but not stored for some reason)
                    invite_link_obj = getattr(update.chat_member, 'invite_link', None)
                    raw_link = getattr(invite_link_obj, 'invite_link', None) if invite_link_obj else None
                    if raw_link:
                        self.logger.info(
                            f"Invite link object present in update for user {user.id}. Treating as valid, marking as used in DB."
                        )
                        try:
                            mark_invite_link_used(raw_link)
                        except Exception as e:
                            self.logger.error(
                                f"Failed to mark invite link from update as used for user {user.id}: {e}")
                        is_authorized = True

            if not is_authorized:
                self.logger.warning(
                    f"User {user.id} is NOT authorized and has no valid invite link. Kicking from {chat.id}."
                )
                try:
                    await context.bot.ban_chat_member(chat_id=chat.id, user_id=user.id)
                    await context.bot.unban_chat_member(chat_id=chat.id, user_id=user.id)
                    self.logger.info(
                        f"Successfully kicked unauthorized user {user.id} from {chat.id}")
                except Exception as e:
                    self.logger.error(
                        f"Failed to kick user {user.id} from {chat.id}: {e}")
            else:
                self.logger.info(
                    f"User {user.id} is authorized (subscription) or has a valid invite link – allowed to stay.")
        
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

    async def validate_free_package_subscribers(self, context: ContextTypes.DEFAULT_TYPE):
        """Daily job at 18:00:
        1. بررسی فعالیت/حجم کاربران فعال پکیج رایگان.
        2. لغو اشتراک کاربران غیرمجاز در یک تراکنش اتمیک.
        3. فشرده‌سازی صف و ارتقای قدیمی‌ترین افراد تا تکمیل ظرفیت.
        4. ارسال اعلان به کاربران حذف یا ارتقاشده.
        """
        bot = context.bot
        plan_row = self.db.db.execute("SELECT id FROM plans WHERE name = ?", ("پکیج رایگان",)).fetchone()
        if not plan_row:
            return
        plan_id = plan_row[0] if isinstance(plan_row, tuple) else plan_row["id"]

        kicked_users: list[int] = []
        promoted_users: list[int] = []

        svc = ToobitService()
        cutoff = datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(days=7)
        # Rate limit parameters
        BATCH_SIZE = 10  # number of API users per burst
        SLEEP_SECS = 1   # pause between bursts

        try:
            # ----------- شروع تراکنش -----------
            self.db.db.execute("BEGIN")

            # 1) بررسی کاربران فعال
            sql_active = (
                "SELECT s.user_id, f.uid FROM subscriptions s "
                "JOIN free_package_users f ON f.user_id = s.user_id "
                "WHERE s.plan_id = ? AND s.status = 'active'"
            )
            processed = 0
            for user_id, uid in [(r[0], r[1]) for r in self.db.db.execute(sql_active, (plan_id,)).fetchall()]:
                last_checked = self.db.db.execute("SELECT last_checked FROM free_package_users WHERE user_id=?", (user_id,)).fetchone()[0]
                if last_checked:
                    try:
                        last_dt = datetime.fromisoformat(str(last_checked))
                        if datetime.utcnow() - last_dt < timedelta(hours=24):
                            # کمتر از ۲۰ ساعت از بررسی قبل گذشته => صرفنظر
                            continue
                    except ValueError:
                        pass
                volume = svc.get_user_total_volume(uid)
                last_trade = svc.get_last_trade_time(uid) or datetime.min.replace(tzinfo=timezone.utc)
                # به‌روز‌رسانی last_checked
                self.db.db.execute("UPDATE free_package_users SET last_checked=? WHERE user_id=?", (datetime.utcnow().isoformat(sep=" ", timespec="seconds"), user_id))
                if volume < 500 or last_trade < cutoff:
                    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
                    self.db.db.execute(
                        "UPDATE subscriptions SET status='cancelled', end_date=?, updated_at=? WHERE user_id=? AND plan_id=? AND status='active'",
                        (now, now, user_id, plan_id),
                    )
                    kicked_users.append(user_id)

            # 2) فشرده‌سازی صف (حذف جایگاه‌های خالی)
            self._compact_waitlist()

            # 3) ارتقای نفرات صف بر اساس ظرفیت
            capacity = int(getattr(config, "FREE_PACKAGE_CAPACITY", 100))
            active_count = self.db.db.execute("SELECT COUNT(*) FROM subscriptions WHERE plan_id=? AND status='active'", (plan_id,)).fetchone()[0]
            slots = max(0, capacity - active_count)
            if slots:
                wait_rows = self.db.db.execute("SELECT user_id FROM free_package_waitlist ORDER BY position LIMIT ?", (slots,)).fetchall()
                for (wait_user_id,) in wait_rows:
                    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
                    self.db.db.execute(
                        "INSERT OR REPLACE INTO subscriptions (user_id, plan_id, start_date, amount_paid, payment_method, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                        (wait_user_id, plan_id, now, 0, "auto_promote", "active", now, now),
                    )
                    self.db.db.execute("DELETE FROM free_package_waitlist WHERE user_id=?", (wait_user_id,))
                    promoted_users.append(wait_user_id)

            self._compact_waitlist()
            self.db.db.execute("COMMIT")
            # ----------- پایان تراکنش -----------
        except Exception as exc:
            self.db.db.execute("ROLLBACK")
            self.logger.error("Error in validate_free_package_subscribers: %s", exc, exc_info=exc)
            return

        # 4) ارسال اعلان‌ها (خارج از تراکنش)
        for uid in kicked_users:
            try:
                await bot.send_message(uid, "⚠️ دسترسی پکیج رایگان شما به‌دلیل عدم فعالیت کافی در توبیت لغو شد. در صورت ادامه معاملات می‌توانید دوباره درخواست دهید.")
            except Forbidden:
                pass
            except Exception as e:
                self.logger.warning("Failed to notify kicked user %s: %s", uid, e)
        for uid in promoted_users:
            try:
                await bot.send_message(uid, "🎉 به شما تبریک می‌گوییم! پکیج رایگان شما فعال شد. لطفاً طبق شرایط در توبیت فعال بمانید.")
            except Forbidden:
                pass
            except Exception as e:
                self.logger.warning("Failed to notify promoted user %s: %s", uid, e)
        # گزارش روزانه به ادمین‌ها
        try:
            if kicked_users or promoted_users:
                report_lines = ["📊 گزارش روزانه پکیج رایگان:"]
                if kicked_users:
                    report_lines.append(f"• کاربران لغو شده ({len(kicked_users)}): " + ", ".join(map(str, kicked_users)))
                if promoted_users:
                    report_lines.append(f"• کاربران ارتقاءیافته ({len(promoted_users)}): " + ", ".join(map(str, promoted_users)))
                report_text = "\n".join(report_lines)
                admin_ids: list[int] = []
                if isinstance(self.admin_config, list):
                    for adm in self.admin_config:
                        if isinstance(adm, dict):
                            admin_ids.append(adm.get("chat_id") or adm.get("id"))
                        else:
                            admin_ids.append(adm)
                elif isinstance(self.admin_config, dict):
                    admin_ids = list(self.admin_config.keys())
                for adm_id in admin_ids:
                    if not adm_id:
                        continue
                    try:
                        await bot.send_message(adm_id, report_text)
                    except Forbidden:
                        pass
                    except Exception as e:
                        self.logger.warning("Failed to send free package report to admin %s: %s", adm_id, e)
        except Exception as e:
            self.logger.error("Error sending admin report: %s", e)

        # پایان منطق اصلی
        return

        

        plan_id = plan_id[0] if isinstance(plan_id, tuple) else plan_id["id"]
        # Fetch active subscribers with UID
        sql = (
            "SELECT s.user_id, f.uid FROM subscriptions s "
            "JOIN free_package_users f ON f.user_id = s.user_id "
            "WHERE s.plan_id = ? AND s.status = 'active'"
        )
        rows = self.db.db.execute(sql, (plan_id,)).fetchall()
        kicked_users = []
        svc = ToobitService()
        cutoff = datetime.utcnow() - timedelta(days=7)
        for row in rows:
            user_id = row[0] if isinstance(row, tuple) else row["user_id"]
            uid = row[1] if isinstance(row, tuple) else row["uid"]
            volume = svc.get_user_total_volume(uid)
            last_trade = svc.get_last_trade_time(uid) or datetime.min.replace(tzinfo=timezone.utc)
            if volume < 500 or last_trade < cutoff:
                # deactivate subscription
                now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
                self.db.db.execute(
                    "UPDATE subscriptions SET status='cancelled', end_date=?, updated_at=? WHERE user_id=? AND plan_id=? AND status='active'",
                    (now, now, user_id, plan_id),
                )
                kicked_users.append(user_id)
        if kicked_users:
            self.db.db.commit()
        # Promote from waitlist
        capacity = int(getattr(config, "FREE_PACKAGE_CAPACITY", 100))
        active_count = self.db.db.execute("SELECT COUNT(*) FROM subscriptions WHERE plan_id=? AND status='active'", (plan_id,)).fetchone()[0]
        slots = max(0, capacity - active_count)
        if slots:
            wait_rows = self.db.db.execute("SELECT user_id FROM free_package_waitlist ORDER BY position LIMIT ?", (slots,)).fetchall()
            for w in wait_rows:
                uid_user = w[0] if isinstance(w, tuple) else w["user_id"]
                now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
                self.db.db.execute(
                    "INSERT OR REPLACE INTO subscriptions (user_id, plan_id, start_date, amount_paid, payment_method, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (uid_user, plan_id, now, 0, "auto_promote", "active", now, now),
                )
                # remove from waitlist
                self.db.db.execute("DELETE FROM free_package_waitlist WHERE user_id=?", (uid_user,))
            self.db.db.commit()

    def _compact_waitlist(self):
        """Re-order positions in waitlist to be contiguous starting from 1."""
        rows = self.db.db.execute("SELECT id FROM free_package_waitlist ORDER BY position").fetchall()
        for idx, row in enumerate(rows, 1):
            self.db.db.execute("UPDATE free_package_waitlist SET position=? WHERE id=?", (idx, row[0]))
        self.db.db.commit()

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
            
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            from database.queries import DatabaseQueries
            keyboard = []
            if DatabaseQueries.get_setting('renew_free', '1') == '1':
                keyboard.append([InlineKeyboardButton("🎁 رایگان", callback_data="free_package_menu")])
            if DatabaseQueries.get_setting('renew_products', '1') == '1':
                keyboard.append([InlineKeyboardButton("🛒 محصولات", callback_data="products_menu")])
            if not keyboard:
                keyboard.append([InlineKeyboardButton("🛒 محصولات", callback_data="products_menu")])  # fallback
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await bot.send_message(chat_id=user_id, text=message, reply_markup=reply_markup)
                log_reminder_sent(user_id, days_left)
                self.logger.info(
                    f"Sent expiration reminder to user {user_id} (days left: {days_left})"
                )
            except Forbidden:
                self.logger.warning(f"Cannot send reminder to user {user_id} (bot blocked or user privacy).")
            except Exception as exc:
                self.logger.error(f"Error sending reminder to {user_id}: {exc}")

    async def stop(self):
        """Stop the bot"""
        self.logger.info("Stopping Manager Bot")
        if self.application.updater and self.application.updater.running:
            await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        self.logger.info("Manager Bot stopped")



    # --- Command Handlers ---
    @staff_only
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command for admin users and serves as the main menu."""
        user = update.effective_user
        admin_alias = get_alias_from_admin_list(user.id, self.admin_config) or user.first_name
        self.logger.info(f"Admin user {admin_alias} ({user.id}) accessed the main menu.")

        is_admin_flag = is_user_in_admin_list(user.id, self.admin_config)
        if is_admin_flag:
            keyboard = [
                [KeyboardButton(self.menu_handler.button_texts['users']), KeyboardButton(self.menu_handler.button_texts['products'])],
                [KeyboardButton(self.menu_handler.button_texts['tickets']), KeyboardButton(self.menu_handler.button_texts['payments'])],
                [KeyboardButton(self.menu_handler.button_texts['broadcast']), KeyboardButton(self.menu_handler.button_texts['stats'])],
                [KeyboardButton(self.menu_handler.button_texts['settings']), KeyboardButton(self.menu_handler.button_texts['back_to_main'])],
            ]
        else:
            keyboard = [
                [KeyboardButton(self.menu_handler.button_texts['tickets']), KeyboardButton(self.menu_handler.button_texts['payments'])],
                [KeyboardButton(self.menu_handler.button_texts['back_to_main'])],
            ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True, one_time_keyboard=False)

        await update.effective_message.reply_text(
            'پنل مدیریت در اختیار شماست. لطفا گزینه مورد نظر را انتخاب کنید:',
            reply_markup=reply_markup
        )
    
        return

    @staff_only
    async def view_tickets_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display open tickets to admins."""
        user = update.effective_user
        admin_alias = get_alias_from_admin_list(user.id, self.admin_config) or user.first_name
        self.logger.info(f"Admin {admin_alias} ({user.id}) requested to view tickets.")

        try:
            open_tickets = Database.get_open_tickets()
            from database.queries import DatabaseQueries  # Local import to avoid circular deps
            if not open_tickets:
                await update.message.reply_text("در حال حاضر هیچ تیکت بازی وجود ندارد.")
                return

            response_message = "📋 لیست تیکت‌های باز:\n\n"
            for ticket in open_tickets:
                ticket_id = ticket['id']
                user_id = ticket['user_id']
                subject = ticket['subject']
                created_at = ticket['created_at']
                # Try to get user's alias or name from MainBot if available
                # Fetch user info for nicer display (full name + username if available)
                try:
                    user_info = DatabaseQueries.get_user_by_telegram_id(user_id)
                    if user_info and not isinstance(user_info, dict):
                        user_info = dict(user_info)
                except Exception:
                    user_info = None
                if user_info:
                    full_name = user_info.get('full_name') or user_info.get('name') or ""
                    username = user_info.get('username') or ""
                    if username:
                        username = f"@{username}"
                    if full_name and username:
                        user_display = f"{full_name} ({username})"
                    else:
                        user_display = full_name or username or f"کاربر {user_id}"
                else:
                    user_display = f"کاربر {user_id}"
                if self.main_bot_app and hasattr(self.main_bot_app, 'user_data_cache') and user_id in self.main_bot_app.user_data_cache:
                    user_display = self.main_bot_app.user_data_cache[user_id].get('name', user_display)
                
                response_message += f"🎫 تیکت #{ticket_id}\n"
                response_message += f"👤 کاربر: {user_display}\n"
                response_message += f"🔹 موضوع: {subject}\n"
                response_message += f"📅 تاریخ: {created_at}\n"
                response_message += "───────────────────\n\n"
            
            keyboard = []
            for ticket in open_tickets:
                keyboard.append([InlineKeyboardButton(f"تیکت{ticket['id']} ({ticket['subject']})", callback_data=f"view_ticket_{ticket['id']}")])
            
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
        """Send newly-created ticket alert to manager admins و اعضای تیم پشتیبانی."""
        if not notification_text:
            return
        if not self.application or not self.application.bot:
            self.logger.error("send_new_ticket_notification called but bot application not initialized.")
            return

        # ---- جمع‌آوری دریافت‌کنندگان ----
        admin_ids: list[int] = []
        # 1) ادمین‌های اختصاص داده‌شده به ManagerBot هنگام ساخت شیء
        if isinstance(self.admin_config, dict):
            admin_ids = [int(k) for k in self.admin_config.keys()]
        elif isinstance(self.admin_config, list):
            try:
                admin_ids = [int(a.get("chat_id")) for a in self.admin_config if a.get("chat_id")]
            except Exception:
                admin_ids = [int(a) for a in self.admin_config if a]

        # 2) ادمین‌های تعریف شده در config (پشتیبانی از نسخه‌های قدیمی)
        if not admin_ids:
            admin_ids = getattr(config, "MANAGER_BOT_ADMIN_IDS", []) or []

        # 3) اعضای تیم پشتیبانی (ثابت در config و همچنین کاربران ثبت‌شده در DB)
        support_staff_ids: list[int] = []
        try:
            # From static config list
            support_staff_ids.extend(
                [int(staff.get("chat_id"))
                 for staff in getattr(config, "MAIN_BOT_SUPPORT_STAFF_LIST", [])
                 if staff.get("chat_id")]
            )
        except Exception as e:
            self.logger.error("Failed to extract support staff IDs from config: %s", e)

        # Retrieve dynamic support users stored in database
        try:
            from database.queries import DatabaseQueries
            db_rows = DatabaseQueries.get_all_support_users()
            for row in db_rows or []:
                try:
                    if isinstance(row, int):
                        support_staff_ids.append(row)
                    elif isinstance(row, (list, tuple)):
                        support_staff_ids.append(int(row[0]))
                    else:
                        # sqlite3.Row or dict-like
                        support_staff_ids.append(int(row["telegram_id"]))
                except (KeyError, IndexError, TypeError, ValueError):
                    continue
        except Exception as e:
            self.logger.error("Failed to fetch support users from DB: %s", e)

        recipient_ids: list[int] = list({*admin_ids, *support_staff_ids})
        self.logger.info(f"Preparing to send ticket notification to recipients: admins={admin_ids}, support_staff={support_staff_ids}")
        if not recipient_ids:
            self.logger.warning("No admin/support IDs configured – cannot deliver ticket notification.")
            return

        # ---- ارسال پیام ----
        sent_count = 0
        for chat_id in recipient_ids:
            try:
                await self.application.bot.send_message(chat_id=chat_id,
                                                          text=notification_text,
                                                          parse_mode=ParseMode.HTML)
                sent_count += 1
            except Exception as e:
                self.logger.error("Failed to send ticket notification to %s: %s", chat_id, e)

        self.logger.info("Ticket notification delivered to %s/%s recipients (admins & support).",
                         sent_count,
                         len(recipient_ids))

    
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
        # Register AltSeason admin conversation handler
        application.add_handler(self.altseason_admin_handler.get_conv_handler())

        # Register product management conversation handlers
        for handler in self.product_handler.get_product_conv_handlers():
            application.add_handler(handler)

        # Register static product management callback handlers (non-conversational)
        for handler in self.product_handler.get_static_product_handlers():
            application.add_handler(handler)

        # Register category management conversation handler
        application.add_handler(self.category_handler.get_conv_handler())

        # Register ticket management conversation handler
        application.add_handler(self.ticket_handler.get_ticket_conversation_handler())
        # Capture admin replies (ForceReply) for edited/manual ticket answers
        application.add_handler(MessageHandler(
            filters.ChatType.PRIVATE & filters.REPLY & filters.TEXT,
            self.ticket_handler.receive_edited_answer
        ))
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
        # Handler for text messages
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE & ~admin_button_filter,
            self.menu_handler.message_handler
        ), group=1)
        # Handler for non-text (photo, document, etc.) messages so that broadcast content can be any type
        application.add_handler(MessageHandler(
            ~filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE & ~admin_button_filter,
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
    # ---------------- Collect recipients ----------------
    admin_ids: list[int] = []
    # 1) Manager bot admins from passed admin_config
    if isinstance(self.admin_config, dict):
        admin_ids = [int(k) for k in self.admin_config.keys()]
    elif isinstance(self.admin_config, list):
        try:
            # When admin_config is a list of dicts e.g. [{"chat_id": 123, ...}]
            admin_ids = [int(a.get("chat_id")) for a in self.admin_config if a.get("chat_id")]
        except Exception:
            # Fallback: assume list of plain integers
            admin_ids = [int(a) for a in self.admin_config if a]

    # 2) Manager bot admins from config (legacy support)
    if not admin_ids:
        admin_ids = getattr(config, "MANAGER_BOT_ADMIN_IDS", []) or []

    # 3) Support staff defined for the main bot (not necessarily managers) – they should also receive ticket alerts.
    support_staff_ids: list[int] = []
    try:
        support_staff_ids = [int(staff.get("chat_id")) for staff in getattr(config, "MAIN_BOT_SUPPORT_STAFF_LIST", []) if staff.get("chat_id")]
    except Exception as e:
        self.logger.error(f"Failed to extract support staff IDs from config.MAIN_BOT_SUPPORT_STAFF_LIST: {e}")
        support_staff_ids = []

    # Union of admin and support IDs, preserving uniqueness
    recipient_ids: list[int] = list({*admin_ids, *support_staff_ids})

    if not recipient_ids:
        self.logger.warning("No admin or support IDs configured – cannot deliver ticket notification.")
        return
    sent_count = 0
    for adm in recipient_ids:
        try:
            await self.application.bot.send_message(chat_id=adm, text=notification_text, parse_mode=ParseMode.HTML)
            sent_count += 1
        except Exception as e:
            self.logger.error(f"Failed to send ticket notification to admin {adm}: {e}")
    self.logger.info(f"Ticket notification delivered to {sent_count}/{len(recipient_ids)} recipients (admins/support).")
    
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
    # Category management conversation
    application.add_handler(self.category_handler.get_conv_handler())
    for handler in self.product_handler.get_product_conv_handlers():
        application.add_handler(handler)
    for handler in self.product_handler.get_static_product_handlers():
        application.add_handler(handler)
    application.add_handler(self.ticket_handler.get_ticket_conversation_handler())
    application.add_handler(self.menu_handler.get_invite_link_conv_handler())
    application.add_handler(self.menu_handler.get_ban_unban_conv_handler())
    # Broadcast handler is now integrated into admin_menu_handlers routing
    # application.add_handler(get_broadcast_conv_handler(), group=-2)
    application.add_handler(get_video_upload_conv(), group=-1)

    # --- CallbackQuery Handlers for static menus ---
    # This handles callbacks from non-conversation inline keyboards, like the main settings menu.
    application.add_handler(CallbackQueryHandler(self.menu_handler.callback_query_handler), group=2)

    # --- Message Handlers for Admin Private Chat (Group 0) ---
    # This handler is specifically for the admin's main menu, which uses ReplyKeyboardMarkup.
    admin_button_filter = filters.Text(list(self.admin_buttons_map.keys()))
    application.add_handler(MessageHandler(
         admin_button_filter & filters.ChatType.PRIVATE,
         self._admin_reply_keyboard_handler
     ), group=2)

    # This is a general message handler for admins, which can be used for features like search.
    # It should not handle commands or the main menu buttons.
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE & ~admin_button_filter,
        self.menu_handler.message_handler
    ), group=2)

    # Generic UpdateHandler for logging (Group 100)
    application.add_handler(TypeHandler(Update, self.log_all_updates), group=100)