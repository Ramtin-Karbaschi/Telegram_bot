"""Admin main menu handlers for Daraei Academy Telegram bot.
Provides a simple, localized admin panel with inline keyboards
so administrators can quickly access management features
(tickets, users, payments, broadcasts, settings)."""

import logging
from typing import Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ConversationHandler

from utils.helpers import admin_only_decorator as admin_only
from utils.helpers import staff_only_decorator as staff_only
from utils.helpers import is_user_in_admin_list
from utils.invite_link_manager import InviteLinkManager
from database.free_plan_helper import ensure_free_plan
from utils.db_backup import export_database, export_database_excel

from .admin_product_handlers import AdminProductHandler
from .admin_support_handlers import SupportUserManager


from database.queries import DatabaseQueries

logger = logging.getLogger(__name__)

# States for Ban/Unban Conversation
AWAIT_USER_ID_FOR_BAN, AWAIT_BAN_CHOICE = range(2)

class AdminMenuHandler:
    """Show an interactive admin panel and dispatch to feature modules."""

    def __init__(self, db_queries: DatabaseQueries, invite_link_manager=None, admin_config=None, main_bot_app=None):
        # Store shared DatabaseQueries instance
        self.db_queries = db_queries

        # Store invite link manager class or instance
        self.invite_link_manager = invite_link_manager

        # Save admin configuration for permission checks used by @admin_only decorator
        self.admin_config = admin_config
        
        # Store main bot application for sending broadcast messages
        self.main_bot_app = main_bot_app

        # Re-use ticket handler to show lists inside this menu (no DB object required here)
        from .admin_ticket_handlers import AdminTicketHandler
        self.ticket_handler = AdminTicketHandler()

        # Product handler needs DB access as well as optional admin config
        self.product_handler = AdminProductHandler(self.db_queries, admin_config=self.admin_config)
        # Support user manager
        self.support_manager = SupportUserManager(admin_config=self.admin_config)
        
        # Export subscribers helper
        from .admin.export_subs_admin_handler import ExportSubsAdminHandler
        self.export_handler = ExportSubsAdminHandler(db_queries)

        # Simple flag for maintenance mode toggle in misc settings
        self.maintenance_mode = False
        self.search_flag = None
        self.broadcast_flag = None

        self.button_texts = {
            'users': '👥 مدیریت کاربران',
            'products': '📦 مدیریت محصولات',
            'tickets': '🎫 مدیریت تیکت‌ها',
            'payments': '💳 مدیریت پرداخت‌ها',
            'broadcast': '📢 ارسال پیام همگانی',
            'stats': '📊 آمار کلی',
            'settings': '⚙️ تنظیمات',
            'export_subs': '📤 خروجی مشترکین',
            'back_to_main': '🔙 بازگشت به منوی اصلی',
        }

        self.admin_buttons_map = {
            self.button_texts['users']: self._users_submenu,
            self.button_texts['products']: self._products_submenu,
            self.button_texts['tickets']: self._tickets_submenu,
            self.button_texts['payments']: self._payments_submenu,
            self.button_texts['broadcast']: self._broadcast_submenu,
            self.button_texts['stats']: self._show_stats_handler,
            self.button_texts['settings']: self._settings_submenu,
            self.button_texts['export_subs']: self._export_subs_entry,
            self.button_texts['back_to_main']: self.show_admin_menu,
        }

    @staff_only
    async def route_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Routes admin commands from ReplyKeyboardMarkup clicks."""
        from utils.locale_utils import fa_to_en_digits  # localized digit support
        command_text = fa_to_en_digits(update.message.text)
        user_id = update.effective_user.id if update.effective_user else None
        is_admin_flag = user_id is not None and is_user_in_admin_list(user_id, self.admin_config)
        support_allowed_labels = {self.button_texts['tickets'], self.button_texts['payments'], self.button_texts['back_to_main']}
        if not is_admin_flag and command_text not in support_allowed_labels:
            await update.message.reply_text("دسترسی محدود است.")
            return
        function_to_call = self.admin_buttons_map.get(command_text)

        if not function_to_call:
            return

        # Handlers like _users_submenu expect a 'query' object.
        # Handlers like show_admin_menu expect 'update' and 'context'.
        # We create a dummy query object to bridge this gap.
        class DummyQuery:
            def __init__(self, message):
                self.message = message

            async def answer(self):
                pass  # No-op

            async def edit_message_text(self, *args, **kwargs):
                # For reply keyboards, we send a new message instead of editing.
                await self.message.reply_text(*args, **kwargs)

        # Check the function signature to decide how to call it.
        import inspect
        sig = inspect.signature(function_to_call)
        if len(sig.parameters) > 1: # Assumes (self, update, context)
            await function_to_call(update, context)
        else: # Assumes (self, query)
            await function_to_call(DummyQuery(update.message))

    async def _export_subs_entry(self, query):
        """Entry point: delegate to ExportSubsAdminHandler.entry"""
        # ExportSubsAdminHandler expects an object with .callback_query attribute like Update.
        from types import SimpleNamespace
        dummy_update = SimpleNamespace(callback_query=query)
        await self.export_handler.entry(dummy_update, None)

    async def _show_stats_handler(self, query):
        """
        Handles showing stats, designed to be called from a reply keyboard.
        It uses query.message.reply_text instead of query.edit_message_text.
        """
        stats = DatabaseQueries.get_subscription_stats()
        message_text = ""
        if stats:
            stats = dict(stats)  # Ensure it's a dict
            message_text = (
                f"📊 *آمار اشتراک‌ها:*\n\n"
                f"کل کاربران: {stats.get('total_users', 'N/A')}\n"
                f"کاربران فعال: {stats.get('active_subscribers', 'N/A')}\n"
                f"درآمد کل (تتر): {stats.get('total_revenue_usdt', 0):.2f} USDT\n"
                f"درآمد کل (ریال): {int(stats.get('total_revenue_irr', 0)):,} ریال"
            )
        else:
            message_text = "آماری برای نمایش وجود ندارد."

        # DummyQuery has `message` attribute from the original update
        if hasattr(query, 'message') and query.message:
            await query.message.reply_text(message_text, parse_mode="Markdown")
        else:
            # Fallback, though it shouldn't be needed
            logger.warning("Could not send stats reply, query object lacks 'message'.")
    """Show an interactive admin panel and dispatch to feature modules."""

    # Callback data constants
    TICKETS_MENU = "admin_tickets_menu"
    USERS_MENU = "admin_users_menu"
    FREE20_CALLBACK = "users_free20"
    CREATE_INVITE_LINK = "users_create_invite_link"
    PAYMENTS_MENU = "admin_payments_menu"
    BROADCAST_MENU = "admin_broadcast_menu"
    EXPORT_SUBS_MENU = "admin_export_subs"
    BROADCAST_ACTIVE = "broadcast_active"
    BROADCAST_ALL = "broadcast_all"
    BROADCAST_WITH_LINK = "broadcast_with_link"
    BROADCAST_WL_ACTIVE = "broadcast_wl_active"
    BROADCAST_WL_ALL = "broadcast_wl_all"
    BROADCAST_CANCEL = "broadcast_cancel"
    SETTINGS_MENU = "admin_settings_menu"
    PRODUCTS_MENU = "admin_products_menu"
    BACKUP_CALLBACK = "settings_backup_json"
    BACKUP_XLSX_CALLBACK = "settings_backup_xlsx"
    SUPPORT_MENU = "settings_support_users"
    SUPPORT_ADD = "settings_support_add"
    SUPPORT_LIST = "settings_support_list"
    BACK_MAIN = "admin_back_main"
    TICKETS_HISTORY = "tickets_history_input"
    MAIN_MENU_CALLBACK = BACK_MAIN
    BAN_UNBAN_USER = "users_ban_unban"
    EXTEND_SUB_CALLBACK = "users_extend_subscription"
    EXTEND_SUB_ALL_CALLBACK = "users_extend_all_subscription"
    CHECK_SUB_STATUS = "users_check_subscription"

    # Conversation states
    (GET_INVITE_LINK_USER_ID,) = range(100, 101)
    (AWAIT_BROADCAST_MESSAGE, AWAIT_BROADCAST_CONFIRMATION) = range(101, 103)
    (AWAIT_FREE20_USER_ID,) = range(103, 104)
    (AWAIT_USER_ID_FOR_BAN, AWAIT_BAN_CHOICE) = range(104, 106)
    (AWAIT_EXTEND_USER_ID, AWAIT_EXTEND_DAYS) = range(106, 108)
    (AWAIT_CHECK_USER_ID,) = range(108, 109)
    (AWAIT_EXTEND_ALL_DAYS,) = range(109, 110)

    @staff_only
    async def show_admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Entry command `/admin` – show main panel."""
        user_id = update.effective_user.id if update.effective_user else None
        is_admin = user_id is not None and is_user_in_admin_list(user_id, self.admin_config)
        if is_admin:
            keyboard = [
                [InlineKeyboardButton("🎫 مدیریت تیکت‌ها", callback_data=self.TICKETS_MENU), InlineKeyboardButton("👥 مدیریت کاربران", callback_data=self.USERS_MENU)],
                [InlineKeyboardButton("💳 مدیریت پرداخت‌ها", callback_data=self.PAYMENTS_MENU), InlineKeyboardButton("📦 مدیریت محصولات", callback_data=self.PRODUCTS_MENU)],
                [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data=self.BROADCAST_MENU), InlineKeyboardButton("📤 خروجی مشترکین", callback_data=self.EXPORT_SUBS_MENU)],
                [InlineKeyboardButton("⚙️ تنظیمات", callback_data=self.SETTINGS_MENU)],
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("🎫 مدیریت تیکت‌ها", callback_data=self.TICKETS_MENU), InlineKeyboardButton("💳 مدیریت پرداخت‌ها", callback_data=self.PAYMENTS_MENU)],
            ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Check if we are editing a message (from a callback) or sending a new one
        if update.callback_query:
            await update.callback_query.edit_message_text("⚡️ *پنل مدیریت*\nیکی از گزینه‌های زیر را انتخاب کنید:", parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await update.message.reply_text("⚡️ *پنل مدیریت*\nیکی از گزینه‌های زیر را انتخاب کنید:", parse_mode="Markdown", reply_markup=reply_markup)

    # ---------- Menu callbacks ----------
    @staff_only
    async def admin_menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = query.from_user.id
        is_admin_flag = is_user_in_admin_list(user_id, self.admin_config)
        support_allowed_callbacks = {
            self.TICKETS_MENU, self.PAYMENTS_MENU,
            "tickets_open", "tickets_all",
            "payments_recent", "payments_stats",
            self.TICKETS_HISTORY,
            self.BACK_MAIN
        }
        if not is_admin_flag and data not in support_allowed_callbacks:
            await query.answer("دسترسی محدود است.", show_alert=True)
            return

        logger.debug("Admin menu callback: %s", data)

        if data == self.TICKETS_MENU:
            await self._tickets_submenu(query)
        elif data == self.TICKETS_HISTORY:
            await query.edit_message_text("🔎 لطفاً شمارهٔ موبایل (مثلاً +98912...) کاربر را ارسال کنید:")
            context.user_data["awaiting_ticket_history_user"] = True
        elif data == self.USERS_MENU:
            await self._users_submenu(query)
        elif data == self.PAYMENTS_MENU:
            await self._payments_submenu(query)
        elif data == self.EXPORT_SUBS_MENU:
            await self.export_handler.entry(update, context)
        elif data.startswith("exp_prod_"):
            await self.export_handler.handle_product(update, context)
        elif data == self.BROADCAST_MENU:
            await self._broadcast_submenu(query)
        elif data == self.BROADCAST_WITH_LINK:
            await self._broadcast_wl_choose_audience(query)
        elif data == self.BROADCAST_WL_ACTIVE:
            await self._broadcast_wl_ask_content(query, context, target="active")
        elif data == self.BROADCAST_WL_ALL:
            await self._broadcast_wl_ask_content(query, context, target="all")
        elif data.startswith("chpick_"):
            await self._broadcast_wl_picker_callback(query, context)
        elif data == self.BROADCAST_CANCEL:
            await self._broadcast_wl_cancel(query, context)
        elif data == "users_list_active":
            await self._show_active_users(query)
        elif data == self.SETTINGS_MENU:
            await self._settings_submenu(query)
        elif data == self.PRODUCTS_MENU:
            await self._products_submenu(query)
        # ----- Product submenu actions -----
        elif data == "products_list":
            await self.product_handler._show_all_plans(query)
        elif data == "products_show_all":
            await self.product_handler._show_all_plans(query)
        elif data.startswith("view_plan_"):
            plan_id = int(data.split("_")[2])
            await self.product_handler._show_single_plan(query, plan_id)
        elif data.startswith("toggle_plan_active_"):
            plan_id = int(data.rsplit("_", 1)[1])
            await self.product_handler.toggle_plan_status(query, plan_id)
        elif data.startswith("toggle_plan_public_"):
            plan_id = int(data.rsplit("_", 1)[1])
            await self.product_handler.toggle_plan_visibility(query, plan_id)
        elif data.startswith("delete_plan_confirm_"):
            # confirmation button already includes 'confirm'
            plan_id = int(data.rsplit("_", 1)[1])
            await self.product_handler.delete_plan_confirmation(query, plan_id)
        elif data.startswith("delete_plan_"):
            # initial delete request from single-plan view
            plan_id = int(data.rsplit("_", 1)[1])
            await self.product_handler.delete_plan_confirmation(query, plan_id)
        elif data.startswith("confirm_delete_plan_"):
            plan_id = int(data.rsplit("_", 1)[1])
            await self.product_handler.delete_plan(query, plan_id)
        elif data == self.BACK_MAIN:
            await self.show_admin_menu(update, context)
        # ----- Ticket submenu actions -----
        elif data == "tickets_open":
            await self.ticket_handler._show_tickets_inline(query)
        elif data == "tickets_all":
            await self.ticket_handler._show_all_tickets_inline(query)
        # ----- Users submenu actions -----
        elif data == "users_active":
            await self._show_active_users(query)
        elif data == "users_search":
            # Ask admin for search term
            await query.edit_message_text("🔎 لطفاً نام کاربری، نام یا آیدی عددی کاربر را ارسال کنید:")
            context.user_data["awaiting_user_search_query"] = True
        elif data == self.FREE20_CALLBACK:
            # Start free 20-day activation flow
            await query.edit_message_text("🎁 لطفاً نام کاربری (بدون @) یا آیدی عددی کاربر را ارسال کنید:")
            context.user_data["awaiting_free20_user"] = True
        elif data == self.BAN_UNBAN_USER:
            await self.ban_unban_start(update, context)
        # ----- Payments submenu actions -----
        elif data == "payments_recent":
                await self._show_recent_payments_inline(query)
        elif data.startswith("payment_info_"):
            pid = data.split("_", 2)[2]
            await self._show_payment_details(query, pid)
        elif data == "payments_search":
            await query.edit_message_text("🔎 لطفاً شناسه پرداخت یا هش تراکنش را ارسال کنید:")
            context.user_data["awaiting_payment_search"] = True
            await self._show_recent_payments(query)
        elif data == "payments_stats":
            await self._show_payments_stats(query)
        # ----- Discounts submenu actions -----
        elif data == "discounts_menu":
            await self._discounts_submenu(query)
        elif data == "discounts_add":
            # Start inline create discount flow
            context.user_data["discount_flow"] = {"mode":"create","state":"await_code","data":{}}
            await query.edit_message_text("🆕 لطفاً کد تخفیف را ارسال کنید (حروف و اعداد لاتین).")
        elif data == "discounts_list":
            await self._list_discounts(query)
        elif data.startswith("view_discount_"):
            did = int(data.split("_")[2])
            await self._show_single_discount(query, did)
        elif data.startswith("edit_discount_") or data.startswith("discounts_edit_"):
            # Support both 'edit_discount_' and legacy 'discounts_edit_' prefixes
            did = int(data.split("_")[-1])
            context.user_data["discount_flow"] = {"mode":"edit","discount_id":did,"state":"await_value","data":{}}
            await query.edit_message_text(
                "✏️ مقدار و نوع جدید را ارسال کنید به فرم 'percentage 10' یا 'fixed 50000':\n\nیا دکمه ⏭️ بدون تغییر را بزنید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏭️ بدون تغییر", callback_data="discount_edit_skip")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data=f"view_discount_{did}")]
                ])
            )
        elif data.startswith("toggle_discount_"):
            did = int(data.split("_")[2])

            await self._toggle_discount_status(query, did)
        elif data.startswith("delete_discount_"):
            did = int(data.split("_")[2])
            await self._delete_discount_confirmation(query, did)
        elif data.startswith("planpick_") or data in ("planpick_all", "planpick_done"):
            try:
                # Extract plan ID if it exists and is numeric
                if data.startswith("planpick_") and not data in ("planpick_all", "planpick_done"):
                    parts = data.split("_")
                    if len(parts) > 1 and not parts[1].isdigit() and parts[1] not in ["all", "done"]:
                        logger.warning(f"Invalid planpick callback data: {data}")
                        await query.answer("❌ شناسه پلن نامعتبر است.", show_alert=True)
                        return
                await self._handle_plan_select_callback(query, context)
            except Exception as e:
                logger.error(f"Error in planpick callback: {e}", exc_info=True)
                await query.answer("❌ خطا در پردازش درخواست", show_alert=True)
        elif data.startswith("confirm_delete_discount_"):
            did = int(data.split("_")[3])
            await self._delete_discount(query, did)
            await self._list_discounts(query)
        # ----- Settings submenu actions -----
        elif data == "settings_admins":
            await self._show_admins_settings(query)
        elif data == self.BACKUP_CALLBACK:
            # generate and send JSON backup
            bio = export_database()
            if bio:
                bio.seek(0)
                await context.bot.send_document(chat_id=query.from_user.id, document=bio, filename="db_backup.json")
                await query.answer("📤 بکاپ JSON ارسال شد")
            else:
                await query.answer("❌ خطا در تهیه بکاپ JSON", show_alert=True)
        elif data == self.BACKUP_XLSX_CALLBACK:
            bio = export_database_excel()
            if bio:
                bio.seek(0)
                await context.bot.send_document(chat_id=query.from_user.id, document=bio, filename="db_backup.xlsx")
                await query.answer("📤 بکاپ اکسل ارسال شد")
            else:
                await query.answer("❌ خطا در تهیه بکاپ اکسل", show_alert=True)
        elif data == self.SUPPORT_MENU:
            await self._settings_support_submenu(query)
        elif data == self.SUPPORT_ADD:
             # Begin inline flow to add support user
             await query.edit_message_text("➕ لطفاً آیدی عددی تلگرام کاربر پشتیبان را ارسال کنید:")
             context.user_data["awaiting_support_user_id"] = True
        elif data == self.SUPPORT_LIST:
            await self._show_support_users(query)
        elif data == "settings_misc":
            await self._settings_misc_submenu(query)
        elif data == "settings_toggle_maintenance":
            # Toggle the flag
            self.maintenance_mode = not self.maintenance_mode
            await query.answer("به‌روزرسانی شد")
            await self._settings_misc_submenu(query)
        # ----- Broadcast submenu actions -----
        elif data in (self.BROADCAST_ACTIVE, self.BROADCAST_ALL):
            # Set broadcast target and ask for content
            target_label = "کاربران فعال" if data == self.BROADCAST_ACTIVE else "تمامی کاربران ثبت‌نام‌شده"
            context.user_data["broadcast_target"] = "active" if data == self.BROADCAST_ACTIVE else "all"
            await query.edit_message_text(f"✉️ لطفاً پیام مورد نظر خود را ارسال کنید. پس از ارسال، پیام به‌صورت خودکار برای {target_label} فوروارد خواهد شد.")
            context.user_data["awaiting_broadcast_content"] = True
        elif data == self.BACK_MAIN:
            # Just recreate the main admin menu correctly
            await self.show_admin_menu(update, context)
        else:
            await query.answer("دستور ناشناخته!", show_alert=True)

    # ---------- Helper for users ----------
    async def _show_active_users(self, query):
        """Show list of active users (simple version)."""
        try:
            users = DatabaseQueries.get_all_active_subscribers()
            if not users:
                await query.edit_message_text("📋 هیچ کاربر فعالی یافت نشد.")
                return
            message_lines = ["📋 *لیست کاربران فعال:*\n"]
            for u in users[:30]:
                # Depending on the returned row type (sqlite3.Row or tuple/dict), access safely
                try:
                    user_id = u['user_id'] if isinstance(u, dict) else u[0]
                    full_name = u.get('full_name') if isinstance(u, dict) else (u[1] if len(u) > 1 else "")
                except Exception:
                    user_id = u[0] if isinstance(u, (list, tuple)) else getattr(u, 'user_id', 'N/A')
                    full_name = getattr(u, 'full_name', '')
                line = f"• {full_name} – {user_id}"
                message_lines.append(line)
            await query.edit_message_text("\n".join(message_lines), parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error showing active users: {e}")
            await query.edit_message_text("❌ خطا در نمایش کاربران فعال.")

    # ---------- Sub-menus ----------
    async def _tickets_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("🟢 تیکت‌های منتظر پاسخ", callback_data="tickets_open"), InlineKeyboardButton("📜 همهٔ تیکت‌ها", callback_data="tickets_all")],
            [InlineKeyboardButton("🔎 تاریخچهٔ تیکت کاربر", callback_data=self.TICKETS_HISTORY), InlineKeyboardButton("📄 خروجی تیکت‌ها", callback_data="export_all_tickets")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("🎫 *مدیریت تیکت‌ها*\nگزینه مورد نظر را انتخاب کنید:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _users_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("🔗 لینک دعوت", callback_data=self.CREATE_INVITE_LINK), InlineKeyboardButton("➕ افزایش اشتراک", callback_data=self.EXTEND_SUB_CALLBACK)],
            [InlineKeyboardButton("➕ افزایش همگانی", callback_data=self.EXTEND_SUB_ALL_CALLBACK)],
            [InlineKeyboardButton("📆 مشاهده اعتبار", callback_data=self.CHECK_SUB_STATUS), InlineKeyboardButton("📋 کاربران فعال", callback_data="users_list_active")],
            [InlineKeyboardButton("🔎 جستجوی کاربر", callback_data="users_search"), InlineKeyboardButton("🛑 مسدود/آزاد کردن", callback_data=self.BAN_UNBAN_USER)],
            [InlineKeyboardButton("🎁 فعال‌سازی ۲۰ روزه رایگان", callback_data=self.FREE20_CALLBACK)],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("👥 *مدیریت کاربران*:\nچه کاری می‌خواهید انجام دهید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _payments_submenu(self, query):
        keyboard = [
             [InlineKeyboardButton("💰 تراکنش‌های اخیر", callback_data="payments_recent"), InlineKeyboardButton("🔍 جستجوی پرداخت", callback_data="payments_search")],
             [InlineKeyboardButton("📤 خروجی مشترکین", callback_data=self.EXPORT_SUBS_MENU), InlineKeyboardButton("📈 آمار اشتراک‌ها", callback_data="payments_stats")],
             [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
         ]
        await query.edit_message_text("💳 *مدیریت پرداخت‌ها*:\nچه کاری می‌خواهید انجام دهید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _broadcast_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("✉️ ارسال پیام همگانی", callback_data="broadcast_send")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("📢 *ارسال پیام همگانی*:\nمی‌خواهید یک پیام برای همه کاربران ارسال کنید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _products_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("➕ محصول جدید", callback_data="products_add"), InlineKeyboardButton("📜 محصولات", callback_data="products_list")],
            [InlineKeyboardButton("📂 مدیریت دسته‌بندی‌ها", callback_data="manage_categories")],
            [InlineKeyboardButton("آلت‌سیزن", callback_data="altseason_admin")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("📦 *مدیریت محصولات*:\nچه کاری می‌خواهید انجام دهید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _discounts_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("➕ کد تخفیف جدید", callback_data="discounts_add"), InlineKeyboardButton("📜 کدهای تخفیف", callback_data="discounts_list")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("💸 *مدیریت کدهای تخفیف*:\nچه کاری می‌خواهید انجام دهید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _list_discounts(self, query):
        """Lists all discount codes with simple view."""
        discounts = DatabaseQueries.get_all_discounts()
        if not discounts:
            # query may be CallbackQuery or DummyQuery; fall back to reply_text if needed
            if hasattr(query, "edit_message_text"):
                await query.edit_message_text("هیچ کد تخفیفی یافت نشد.")
            else:
                await query.message.reply_text("هیچ کد تخفیفی یافت نشد.")
            return
        text = "📜 *لیست کدهای تخفیف*:\n"
        keyboard = []
        row = []
        for d in discounts:
            # Convert sqlite3.Row to dict properly
            if hasattr(d, 'keys'):
                d_dict = {key: d[key] for key in d.keys()}
            else:
                d_dict = dict(d)
            
            status = "🟢 فعال" if d_dict.get("is_active") else "🔴 غیرفعال"
            text += f"\n• {d_dict.get('code')} ({status})"
            # add button
            row.append(InlineKeyboardButton(d_dict.get('code'), callback_data=f"view_discount_{d_dict.get('id')}") )
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="discounts_menu")])
        if hasattr(query, "edit_message_text"):
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_single_discount(self, query, discount_id: int):
        d = DatabaseQueries.get_discount_by_id(discount_id) if hasattr(DatabaseQueries, 'get_discount_by_id') else None
        if not d:
            await query.edit_message_text("کد تخفیف یافت نشد.")
            return
        
        # Convert sqlite3.Row to dict properly
        if hasattr(d, 'keys'):
            d_dict = {key: d[key] for key in d.keys()}
        else:
            d_dict = dict(d)
            
        status_text = "فعال 🟢" if d_dict.get("is_active") else "غیرفعال 🔴"
        toggle_text = "🔴 غیرفعال کردن" if d_dict.get("is_active") else "🟢 فعال کردن"
        text = (
            f"جزئیات کد تخفیف {d_dict['code']}\n\n"
            f"شناسه: {d_dict['id']}\n"
            f"نوع: {d_dict['type']}\n"
            f"مقدار: {d_dict['value']}\n"
            f"وضعیت: {status_text}\n"
            f"تاریخ شروع: {d_dict.get('start_date','-')}\n"
            f"تاریخ پایان: {d_dict.get('end_date','-')}\n"
            f"حداکثر استفاده: {d_dict.get('max_uses','-')}\n"
            f"تعداد استفاده: {d_dict.get('uses_count','0')}"
        )
        keyboard = [
            [InlineKeyboardButton(toggle_text, callback_data=f"toggle_discount_{discount_id}")],
            [InlineKeyboardButton("✏️ ویرایش", callback_data=f"edit_discount_{discount_id}")],
            [InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_discount_{discount_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="discounts_list")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    # --------------------------------------
    # New helper methods for plan selection
    # --------------------------------------
    def _build_plan_select_keyboard(self, selected_ids: set[int], plans):
        """Return an inline keyboard for multi-selecting plans."""
        keyboard = []
        row = []
        for p in plans:
            # Handle different data types (tuple/list vs sqlite3.Row)
            if isinstance(p, (list, tuple)):
                pid = p[0]
                pname = p[1]
            else:
                # Convert sqlite3.Row to dict properly
                if hasattr(p, 'keys'):
                    p_dict = {key: p[key] for key in p.keys()}
                else:
                    p_dict = dict(p)
                pid = p_dict.get("id")
                pname = p_dict.get("name")
            selected = pid in selected_ids
            button_text = ("✅ " if selected else "☑️ ") + str(pname)
            row.append(InlineKeyboardButton(button_text, callback_data=f"planpick_{pid}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        # Control buttons
        toggle_all_text = "انتخاب همه" if len(selected_ids) < len(plans) else "لغو همه"
        keyboard.append([
            InlineKeyboardButton(toggle_all_text, callback_data="planpick_all"),
            InlineKeyboardButton("✅ تأیید", callback_data="planpick_done"),
        ])
        keyboard.append([InlineKeyboardButton("❌ انصراف", callback_data="discounts_menu")])
        return keyboard

    async def _handle_plan_select_callback(self, query, context):
        """Handle toggle/confirm actions during plan multi-select."""
        df = context.user_data.get("discount_flow")
        if not df or df.get("state") != "await_plan_inline":
            return  # Not in this flow
        data = query.data
        selected: set = df["data"].get("selected_plan_ids", set())
        plans = DatabaseQueries.get_active_plans()

        if data == "planpick_done":
            # Proceed to create discount
            plan_ids = list(selected)
            ddata = df["data"]
            new_id = DatabaseQueries.create_discount(ddata["code"], ddata["type"], ddata["value"])
            if new_id:
                if plan_ids:
                    DatabaseQueries.link_discount_to_plans(new_id, plan_ids)
                await query.edit_message_text("✅ کد تخفیف ایجاد شد.")
            else:
                await query.edit_message_text("❌ خطا در ایجاد کد تخفیف. شاید کد تکراری باشد.")
            # Clean up and show submenu
            context.user_data.pop("discount_flow", None)
            await self._discounts_submenu(query)
            return
        elif data == "planpick_all":
            if len(selected) < len(plans):
                selected = {p[0] if isinstance(p, (list, tuple)) else p.get("id") for p in plans}
            else:
                selected = set()
        elif data.startswith("planpick_"):
            try:
                # Extract the part after planpick_
                parts = data.split("_", 1)
                if len(parts) < 2 or not parts[1].isdigit():
                    logger.warning(f"Invalid planpick callback data: {data}")
                    await query.answer("❌ شناسه پلن نامعتبر است.", show_alert=True)
                    return
                    
                pid = int(parts[1])
                if pid in selected:
                    selected.remove(pid)
                else:
                    selected.add(pid)
            except (ValueError, IndexError) as e:
                logger.error(f"Error processing planpick callback: {e}", exc_info=True)
                await query.answer("❌ خطا در پردازش درخواست", show_alert=True)
                return
        else:
            return  # Unknown callback

        # Save and refresh keyboard
        df["data"]["selected_plan_ids"] = selected
        keyboard = self._build_plan_select_keyboard(selected, plans)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    async def _toggle_discount_status(self, query, discount_id: int):
        d = DatabaseQueries.get_discount_by_id_code_or_id(discount_id) if hasattr(DatabaseQueries, 'get_discount_by_id_code_or_id') else None
        # fallback
        if d is None:
            # attempt by custom query
            pass
        d = DatabaseQueries.get_discount_by_id(discount_id) if hasattr(DatabaseQueries, 'get_discount_by_id') else None
        if not d:
            await query.answer("خطا", show_alert=True)
            return
        
        # Convert sqlite3.Row to dict properly
        if hasattr(d, 'keys'):
            d_dict = {key: d[key] for key in d.keys()}
        else:
            d_dict = dict(d)
            
        new_status = 0 if d_dict['is_active'] else 1
        DatabaseQueries.toggle_discount_status(discount_id, new_status)
        await self._show_single_discount(query, discount_id)

    async def _delete_discount_confirmation(self, query, discount_id: int):
        keyboard = [[InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"confirm_delete_discount_{discount_id}"), InlineKeyboardButton("❌ انصراف", callback_data=f"view_discount_{discount_id}")]]
        await query.edit_message_text("آیا از حذف این کد تخفیف اطمینان دارید؟", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _delete_discount(self, query, discount_id: int):
        if DatabaseQueries.delete_discount(discount_id):
            await query.answer("حذف شد")
            await self._list_discounts(query)
        else:
            await query.answer("خطا در حذف", show_alert=True)

    async def _settings_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("🔐 مدیران", callback_data="settings_admins"), InlineKeyboardButton("👥 مدیریت پشتیبان‌ها", callback_data=self.SUPPORT_MENU)],
            [InlineKeyboardButton("🔘 دکمه‌های تمدید", callback_data="settings_renew_buttons"), InlineKeyboardButton("💸 مدیریت کدهای تخفیف", callback_data="discounts_menu")],
            [InlineKeyboardButton("💾 بکاپ JSON دیتابیس", callback_data=self.BACKUP_CALLBACK), InlineKeyboardButton("📊 بکاپ Excel دیتابیس", callback_data=self.BACKUP_XLSX_CALLBACK)],
            [InlineKeyboardButton("⚙️ سایر تنظیمات", callback_data="settings_misc")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("⚙️ *تنظیمات ربات*:\nکدام بخش را می‌خواهید مدیریت کنید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _settings_renew_buttons_submenu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show dynamic submenu listing all active plans & root categories to toggle renew button visibility."""
        query = update.callback_query
        await query.answer()

        visibility = DatabaseQueries.get_renew_visibility()
        selected_plans = visibility["plans"]
        selected_cats = visibility["categories"]

        # Fetch active plans and full category tree (nested)
        plans = DatabaseQueries.get_active_plans()
        category_tree = DatabaseQueries.get_category_tree() or []

        keyboard: list[list[InlineKeyboardButton]] = []

        # ------------------------------------------------------------
        # Special categories (Free plans and Products)
        # ------------------------------------------------------------
        free_enabled = 0 in selected_cats
        prod_enabled = -1 in selected_cats
        free_text = ("✅ " if free_enabled else "❌ ") + "🎁 رایگان"
        prod_text = ("✅ " if prod_enabled else "❌ ") + "🛒 محصولات"
        keyboard.append([InlineKeyboardButton(free_text, callback_data="toggle_renew_cat_0")])
        keyboard.append([InlineKeyboardButton(prod_text, callback_data="toggle_renew_cat_-1")])

        # ------------------------------------------------------------
        # Helper to flatten category tree with indentation
        # ------------------------------------------------------------
        def _flatten(tree: list[dict], level: int = 0):
            flat: list[tuple[int, str]] = []
            prefix = "  " * level  # two spaces per hierarchy level for indentation
            for node in tree:
                cid = node.get("id")
                cname = node.get("name", "-")
                flat.append((cid, f"{prefix}{cname}"))
                children = node.get("children")
                if children:
                    flat.extend(_flatten(children, level + 1))
            return flat

        categories_flat = _flatten(category_tree)

        # Divider before categories
        if categories_flat:
            keyboard.append([InlineKeyboardButton("──────────", callback_data="noop")])

        # Category toggle buttons (in hierarchical order)
        for cid, cname in categories_flat:
            enabled = cid in selected_cats
            text = ("✅ " if enabled else "❌ ") + f"{cname}"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"toggle_renew_cat_{cid}")])

        # Divider before plans
        if plans:
            keyboard.append([InlineKeyboardButton("──────────", callback_data="noop")])

        # Plans
        for plan in plans:
            pid = plan["id"] if isinstance(plan, dict) else plan[0]
            pname = plan["name"] if isinstance(plan, dict) else plan[1]
            enabled = pid in selected_plans
            text = ("✅ " if enabled else "❌ ") + f"{pname}"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"toggle_renew_plan_{pid}")])

        # Back button
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=self.SETTINGS_MENU)])

        await query.edit_message_text(
            "🔘 تنظیم نمایش دکمه‌های تمدید برای هر طرح و دسته‌بندی:\nبا لمس هر مورد، وضعیت آن تغییر خواهد کرد.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _settings_renew_toggle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        await query.answer()

        visibility = DatabaseQueries.get_renew_visibility()

        if data.startswith("toggle_renew_plan_"):
            pid = int(data.split("_")[-1])
            if pid in visibility["plans"]:
                visibility["plans"].remove(pid)
            else:
                visibility["plans"].add(pid)
            DatabaseQueries.set_renew_visibility(visibility)
        elif data.startswith("toggle_renew_cat_"):
            cid = int(data.split("_")[-1])
            if cid in visibility["categories"]:
                visibility["categories"].remove(cid)
            else:
                visibility["categories"].add(cid)
            DatabaseQueries.set_renew_visibility(visibility)
        else:
            # legacy free/products toggles – treat as special categories
            if data.endswith("_free"):
                special = 0
            else:
                special = -1
            if special in visibility["categories"]:
                visibility["categories"].remove(special)
            else:
                visibility["categories"].add(special)
            DatabaseQueries.set_renew_visibility(visibility)

        # Refresh submenu
        await self._settings_renew_buttons_submenu(update, context)

    async def _toggle_renew_button(self, query, key):
        """Toggle db setting and refresh the renew buttons submenu."""
        current = DatabaseQueries.get_setting(key, '1')
        new_val = '0' if current == '1' else '1'
        DatabaseQueries.set_setting(key, new_val)
        # Rebuild the submenu keyboard after toggle
        free_enabled = DatabaseQueries.get_setting('renew_free', '1') == '1'
        prod_enabled = DatabaseQueries.get_setting('renew_products', '1') == '1'
        free_text = ('✅' if free_enabled else '❌') + " 🎁 رایگان"
        prod_text = ('✅' if prod_enabled else '❌') + " 🛒 محصولات"
        keyboard = [
            [InlineKeyboardButton(free_text, callback_data="toggle_renew_free")],
            [InlineKeyboardButton(prod_text, callback_data="toggle_renew_products")],
            [InlineKeyboardButton("✔️ ذخیره و بازگشت", callback_data=self.SETTINGS_MENU)]
        ]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    async def _settings_misc_submenu(self, query):
        """Show miscellaneous settings such as maintenance toggle."""
        maintenance_status = "ON" if self.maintenance_mode else "OFF"
        keyboard = [
            [InlineKeyboardButton(f"🚧 حالت نگه‌داری: {maintenance_status}", callback_data="settings_toggle_maintenance")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.SETTINGS_MENU)],
        ]
        await query.edit_message_text(
            "⚙️ *سایر تنظیمات*:\nبرای تغییر حالت نگه‌داری دکمه زیر را فشار دهید.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _broadcast_submenu(self, query):
        """Display broadcast options (active users vs all users)."""
        keyboard = [
            [InlineKeyboardButton("🟢 کاربران فعال", callback_data=self.BROADCAST_ACTIVE)],
            [InlineKeyboardButton("👥 تمامی اعضا", callback_data=self.BROADCAST_ALL)],
            [InlineKeyboardButton("🔗 پیام با دکمهٔ لینک کانال", callback_data="broadcast_with_link")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text(
            "📢 *ارسال پیام همگانی*:\nیکی از گزینه‌های زیر را انتخاب کنید:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # ---------- Broadcast with link flow helpers ----------
    async def _broadcast_wl_choose_audience(self, query):
        """Ask admin to choose target audience for broadcast with link."""
        keyboard = [
            [InlineKeyboardButton("🟢 کاربران فعال", callback_data=self.BROADCAST_WL_ACTIVE)],
            [InlineKeyboardButton("👥 تمامی اعضا", callback_data=self.BROADCAST_WL_ALL)],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BROADCAST_MENU)],
        ]
        await query.edit_message_text("📢 *پیام با دکمه کانال*\nلطفاً مخاطبین را انتخاب کنید:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _broadcast_wl_ask_content(self, query, context, target: str):
        """Prompt admin to send message content."""
        context.user_data["bw_target"] = target  # 'active' or 'all'
        context.user_data["bw_awaiting_content"] = True
        await query.edit_message_text("✏️ محتوای پیام (متن یا عکس) را ارسال کنید.")

    async def _broadcast_wl_show_channel_picker(self, message, context):
        """After receiving content, ask admin to pick channels."""
        from utils.broadcast_helpers import build_channel_select_keyboard
        from config import TELEGRAM_CHANNELS_INFO

        context.user_data["bw_selected_ids"] = set()
        keyboard = build_channel_select_keyboard(TELEGRAM_CHANNELS_INFO, set())
        await message.reply_text("🔗 لینک‌های کانال/گروه موردنظر را انتخاب کنید، سپس تأیید را بزنید:", reply_markup=keyboard)
        
        # For media messages, we need to download and re-upload via main bot since file_ids are bot-specific
        if message.text and not message.effective_attachment:
            # Plain text message - store content directly
            context.user_data["bw_draft"] = {
                "type": "text",
                "data": {
                    "text": message.text_html or message.text,
                    **({"parse_mode": "HTML"} if message.text_html else {}),
                }
            }
            logger.info("Stored text message for broadcast")
        elif message.photo or message.video or message.document:
            # For media, we'll download and re-upload via main bot during broadcast
            # Store the original message reference and let main bot handle the file transfer
            if self.main_bot_app:
                try:
                    # Send the media to main bot first so it gets its own file_id
                    from io import BytesIO
                    from telegram import InputFile

                    if message.photo:
                        # Download photo bytes
                        photo_file = await message.photo[-1].get_file()
                        bio = BytesIO()
                        await photo_file.download_to_memory(out=bio)
                        bio.seek(0)
                        input_file = InputFile(bio, filename="photo.jpg")
                        sent = await self.main_bot_app.bot.send_photo(
                            chat_id=message.from_user.id,
                            photo=input_file,
                            caption="[BROADCAST_DRAFT] ",
                            disable_notification=True,
                            parse_mode="HTML"
                        )
                        # remove temp message
                        try:
                            await self.main_bot_app.bot.delete_message(chat_id=sent.chat_id, message_id=sent.message_id)
                        except Exception:
                            pass
                        context.user_data["bw_draft"] = {
                            "type": "photo",
                            "data": {
                                "photo": sent.photo[-1].file_id,
                                "caption": message.caption_html or message.caption or "",
                                **({"parse_mode": "HTML"} if message.caption_html else {}),
                            }
                        }
                    elif message.video:
                        # Download video bytes
                        video_file = await message.video.get_file()
                        bio = BytesIO()
                        await video_file.download_to_memory(out=bio)
                        bio.seek(0)
                        input_file = InputFile(bio, filename=message.video.file_name or "video.mp4")
                        sent = await self.main_bot_app.bot.send_video(
                            chat_id=message.from_user.id,
                            video=input_file,
                            caption="[BROADCAST_DRAFT] ",
                            disable_notification=True,
                            parse_mode="HTML"
                        )
                        try:
                            await self.main_bot_app.bot.delete_message(chat_id=sent.chat_id, message_id=sent.message_id)
                        except Exception:
                            pass
                        context.user_data["bw_draft"] = {
                            "type": "video",
                            "data": {
                                "video": sent.video.file_id,
                                "caption": message.caption_html or message.caption or "",
                                **({"parse_mode": "HTML"} if message.caption_html else {}),
                            }
                        }
                    elif message.document:
                        # Download document bytes
                        doc_file = await message.document.get_file()
                        bio = BytesIO()
                        await doc_file.download_to_memory(out=bio)
                        bio.seek(0)
                        input_file = InputFile(bio, filename=message.document.file_name or "document")
                        sent = await self.main_bot_app.bot.send_document(
                            chat_id=message.from_user.id,
                            document=input_file,
                            caption="[BROADCAST_DRAFT] ",
                            disable_notification=True,
                            parse_mode="HTML"
                        )
                        try:
                            await self.main_bot_app.bot.delete_message(chat_id=sent.chat_id, message_id=sent.message_id)
                        except Exception:
                            pass
                        context.user_data["bw_draft"] = {
                            "type": "document",
                            "data": {
                                "document": sent.document.file_id,
                                "caption": message.caption_html or message.caption or "",
                                **({"parse_mode": "HTML"} if message.caption_html else {}),
                            }
                        }
                    logger.info(f"Successfully transferred media to main bot for broadcast")
                except Exception as e:
                    logger.error(f"Failed to transfer media to main bot: {e}")
                    await message.reply_text("❌ خطا در آماده‌سازی فایل برای ارسال")
                    return
            else:
                await message.reply_text("❌ ربات اصلی در دسترس نیست")
                return
        else:
            await message.reply_text("❌ نوع پیام پشتیبانی نمی‌شود")
            return

    async def _broadcast_wl_picker_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle toggle/select-all/confirm for channel picker keyboard."""
        query = update.callback_query
        if not query:
            return  # Should never happen, but guard just in case
        # Acknowledge callback to remove loading spinner
        try:
            await query.answer()
        except Exception:
            pass
        # Handle selection toggles and final confirmation for channel picker
        data = query.data
        from utils.broadcast_helpers import build_channel_select_keyboard
        from config import TELEGRAM_CHANNELS_INFO

        selected_ids: set[int] = context.user_data.get("bw_selected_ids", set())
        if data == "chpick_all":
            if len(selected_ids) < len(TELEGRAM_CHANNELS_INFO):
                selected_ids = {c['id'] for c in TELEGRAM_CHANNELS_INFO}
            else:
                selected_ids = set()
        elif data.startswith("chpick_done"):
            # Proceed to send broadcast
            await self._broadcast_wl_send(query, context, selected_ids)
            # clear bw_* keys afterwards
            for k in ["bw_selected_ids", "bw_target", "bw_draft"]:
                context.user_data.pop(k, None)
            return
        elif data.startswith("chpick_"):
            cid = int(data.split("_")[1])
            if cid in selected_ids:
                selected_ids.remove(cid)
            else:
                selected_ids.add(cid)
        logger.info("Picker update after click: %s", selected_ids)
        # Save back
        context.user_data["bw_selected_ids"] = selected_ids
        keyboard = build_channel_select_keyboard(TELEGRAM_CHANNELS_INFO, selected_ids)
        await query.message.edit_reply_markup(reply_markup=keyboard)

    async def _broadcast_wl_cancel(self, query, context):
        """Cancel the broadcast-with-link flow and clean flags."""
        for k in ["bw_selected_ids", "bw_target", "bw_draft", "bw_awaiting_content"]:
            context.user_data.pop(k, None)
        await self._broadcast_submenu(query)

    async def _broadcast_wl_send(self, query, context, selected_ids: set[int]):
        """Copy message to users and attach link buttons."""
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        from config import TELEGRAM_CHANNELS_INFO
        draft = context.user_data.get("bw_draft")
        if not draft:
            await query.answer("پیش‌نویس یافت نشد", show_alert=True)
            return
        target = context.user_data.get("bw_target", "active")
        # Build buttons
        buttons = None
        if selected_ids:
            rows = []
            for cid in selected_ids:
                ch = next((c for c in TELEGRAM_CHANNELS_INFO if c['id']==cid), None)
                if ch:
                    rows.append([InlineKeyboardButton(ch['title'], url=ch['link'])])
            buttons = InlineKeyboardMarkup(rows)
        # Determine audience list
        if target == "active":
            users_rows = DatabaseQueries.get_all_active_subscribers()
        else:
            users_rows = DatabaseQueries.get_all_registered_users()
        user_ids = [row['user_id'] if isinstance(row, dict) else row[0] for row in users_rows]
        success = 0
        total = len(user_ids)
        
        # Use main bot for sending broadcast messages to users
        bot_to_use = self.main_bot_app.bot if self.main_bot_app else context.bot
        
        draft_type = draft.get("type")
        draft_data = draft.get("data", {})
        for uid in user_ids:
            try:
                if draft_type == "text":
                    sent = await bot_to_use.send_message(chat_id=uid, **draft_data)
                elif draft_type == "photo":
                    sent = await bot_to_use.send_photo(chat_id=uid, **draft_data)
                elif draft_type == "video":
                    sent = await bot_to_use.send_video(chat_id=uid, **draft_data)
                elif draft_type == "document":
                    sent = await bot_to_use.send_document(chat_id=uid, **draft_data)
                elif draft_type == "copy":
                    sent = await bot_to_use.copy_message(chat_id=uid, from_chat_id=draft_data['chat_id'], message_id=draft_data['message_id'])
                else:
                    logger.warning("Unknown draft_type %s", draft_type)
                    continue
                if buttons:
                    await bot_to_use.edit_message_reply_markup(chat_id=uid, message_id=sent.message_id, reply_markup=buttons)
                success += 1
            except Exception as e:
                logger.warning("Broadcast send to %s failed: %s", uid, e)
        await query.edit_message_text(f"✅ ارسال به پایان رسید. موفق: {success}/{total}")

    @admin_only
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle dynamic admin inputs based on flow flags (broadcast, user search)."""
        # Short-circuit if admin is replying to a ticket (set by AdminTicketHandler.manual_answer_callback or edit_answer_callback)
        if context.user_data.get("editing_ticket_id") is not None:
            from .admin_ticket_handlers import AdminTicketHandler  # Local import to avoid circular deps
            ticket_handler = getattr(self, "_ticket_delegate", None)
            if ticket_handler is None:
                ticket_handler = AdminTicketHandler()
                setattr(self, "_ticket_delegate", ticket_handler)
            await ticket_handler.receive_edited_answer(update, context)
            return

        logger.info("Admin message_handler triggered with text: %s | bw_content=%s | search_flag=%s", update.effective_message.text if update.effective_message else "<no message>", context.user_data.get("bw_awaiting_content"), context.user_data.get("awaiting_user_search_query"))
        message = update.effective_message
        # -------- Broadcast-with-link content flow --------
        if context.user_data.get("bw_awaiting_content"):
            # Accept a single message (text/photo/document) as content.
            context.user_data.pop("bw_awaiting_content", None)
            await self._broadcast_wl_show_channel_picker(message, context)
            return

        # -------- Ticket history flow --------
        if context.user_data.get("awaiting_ticket_history_user"):
            text = message.text.strip()
            digits = "".join(ch for ch in text if ch.isdigit())
            if not digits:
                await message.reply_text("❌ لطفاً شمارهٔ موبایل معتبر وارد کنید.")
                return
            # اگر طول ارقام حداقل 8 باشد فرض می‌کنیم شماره موبایل است
            target_id = None
            if len(digits) >= 8:
                user_row = DatabaseQueries.get_user_by_phone(digits)
                if not user_row:
                    await message.reply_text("❌ کاربری با این شماره پیدا نشد.")
                    return
                target_id = user_row.get('user_id')
            else:
                # فرض بر این است که آیدی تلگرام است
                target_id = int(digits)
            context.user_data.pop("awaiting_ticket_history_user", None)
            # Lazy init ticket delegate
            ticket_handler = getattr(self, "_ticket_delegate_history", None)
            if ticket_handler is None:
                from .admin_ticket_handlers import AdminTicketHandler
                ticket_handler = AdminTicketHandler()
                setattr(self, "_ticket_delegate_history", ticket_handler)
            await ticket_handler.show_ticket_history_for_user(update, context, target_id)
            return

        # -------- Add-support flow --------
        if context.user_data.get("awaiting_support_user_id"):
            text = message.text.strip()
            if not text.isdigit():
                await message.reply_text("❌ آیدی باید یک عدد باشد. دوباره تلاش کنید یا /cancel را بزنید.")
                return
            tg_id = int(text)
            admin_id = update.effective_user.id
            if DatabaseQueries.add_support_user(tg_id, added_by=admin_id):
                await message.reply_text(f"✅ کاربر {tg_id} به عنوان پشتیبان ثبت شد.")
            else:
                await message.reply_text("❌ خطا در افزودن کاربر یا کاربر قبلاً پشتیبان است.")
            # Reset flag and show submenu again
            context.user_data.pop("awaiting_support_user_id", None)
            class DummyQuery:
                def __init__(self, message):
                    self.message = message
                async def edit_message_text(self,*args,**kwargs):
                    await self.message.reply_text(*args,**kwargs)
            await self._settings_support_submenu(DummyQuery(message))
            return

        # -------- Discount create/edit flow --------
        if context.user_data.get("discount_flow"):
            df = context.user_data["discount_flow"]
            mode = df.get("mode")
            state = df.get("state")
            text = message.text.strip()
            if mode == "create":
                if state == "await_code":
                    df["data"]["code"] = text
                    df["state"] = "await_value_type"
                    await message.reply_text("لطفاً نوع و مقدار را ارسال کنید به فرم 'percentage 10' یا 'fixed 50000':")
                    return
                elif state == "await_value_type":
                    parts = text.split()
                    if len(parts)!=2 or parts[0] not in ("percentage","fixed") or not parts[1].replace('.', '', 1).isdigit():
                        await message.reply_text("❌ فرمت نامعتبر است. دوباره امتحان کنید.")
                        return
                    df["data"]["type"] = "percentage" if parts[0]=="percentage" else "fixed_amount"
                    df["data"]["value"] = float(parts[1])
                    # ask plan id or 0
                    active_plans = DatabaseQueries.get_active_plans()
                    if not active_plans:
                        await message.reply_text("❌ هیچ پلن فعالی برای انتخاب وجود ندارد.")
                        # Cancel flow
                        context.user_data.pop("discount_flow", None)
                        return
                    df["state"] = "await_plan_inline"
                    df["data"]["selected_plan_ids"] = set()
                    keyboard = self._build_plan_select_keyboard(set(), active_plans)
                    await message.reply_text("لطفاً پلن‌های مورد نظر را انتخاب کنید و سپس دکمه تأیید را بزنید:", reply_markup=InlineKeyboardMarkup(keyboard))
                    return
                elif state == "await_plan":
                    plan_input = text.replace(' ','')
                    if plan_input=="0":
                        plan_ids = []
                    else:
                        ids=[pid for pid in plan_input.split(',') if pid.isdigit()]
                        if not ids:
                            await message.reply_text("❌ ورودی نامعتبر. دوباره تلاش کنید.")
                            return
                        plan_ids=[int(i) for i in ids]
                    data=df["data"]
                    new_id=DatabaseQueries.create_discount(data["code"],data["type"],data["value"])
                    if new_id:
                        if plan_ids:
                            DatabaseQueries.link_discount_to_plans(new_id,plan_ids)
                        await message.reply_text("✅ کد تخفیف ایجاد شد.")
                    else:
                        await message.reply_text("❌ خطا در ایجاد کد تخفیف. شاید کد تکراری باشد.")
                    context.user_data.pop("discount_flow",None)
                    # back to discounts submenu
                    class DummyQuery:
                        def __init__(self,m):
                            self.message=m
                        async def edit_message_text(self,*args,**kwargs):
                            await self.message.reply_text(*args,**kwargs)
                    await self._discounts_submenu(DummyQuery(message))
                    return
            elif mode=="edit":
                did=df.get("discount_id")
                parts=text.split()
                if len(parts)!=2 or parts[0] not in ("percentage","fixed") or not parts[1].replace('.', '', 1).isdigit():
                    await message.reply_text("❌ فرمت نامعتبر است. دوباره تلاش کنید.")
                    return
                new_type="percentage" if parts[0]=="percentage" else "fixed_amount"
                new_value=float(parts[1])
                ok=DatabaseQueries.update_discount(did, type=new_type, value=new_value)
                await message.reply_text("✅ به‌روزرسانی شد." if ok else "❌ خطا در به‌روزرسانی.")
                context.user_data.pop("discount_flow",None)
                class DummyQuery:
                    def __init__(self,m):
                        self.message=m
                    async def edit_message_text(self,*args,**kwargs):
                        await self.message.reply_text(*args,**kwargs)
                await self._show_single_discount(DummyQuery(message), did)
                return

        # -------- Broadcast flow --------
        if context.user_data.get("awaiting_broadcast_content"):
            # Determine target users
            target = context.user_data.get("broadcast_target", "active")
            await message.reply_text("⏳ در حال ارسال پیام به کاربران، لطفاً صبر کنید...")

            if target == "all":
                users = DatabaseQueries.get_all_registered_users()
            else:
                users = DatabaseQueries.get_all_active_subscribers()
            total = len(users)
            success = 0
            for u in users:
                try:
                    # Robustly extract user_id from different row structures
                    user_id = None
                    if isinstance(u, (list, tuple)):
                        user_id = u[0]
                    else:
                        # Try mapping style access first (works for sqlite3.Row and dict)
                        try:
                            user_id = u["user_id"]
                        except Exception:
                            user_id = u.get("user_id") if hasattr(u, "get") else None

                    # Fallback to using the raw value if still None
                    if user_id is None:
                        user_id = u

                    # Ensure user_id is an int or str representing int
                    try:
                        user_id = int(user_id)
                    except Exception:
                        logger.debug("Could not convert user_id %s to int; using as-is", user_id)

                    await context.bot.copy_message(chat_id=user_id, from_chat_id=message.chat_id, message_id=message.message_id)
                    success += 1
                except Exception as e:
                    logger.warning("Failed to send broadcast to %s: %s", user_id, e)
                    continue

            await message.reply_text(f"✅ ارسال پیام به پایان رسید. موفق: {success}/{total}")
            # Reset flags
            context.user_data.pop("awaiting_broadcast_content", None)
            context.user_data.pop("broadcast_target", None)
            return

        # --- User Search Flow ---
        elif context.user_data.get("awaiting_user_search_query"):
            search_query = update.message.text
            context.user_data["awaiting_user_search_query"] = False # Reset flag

            # Simple search logic
            users = DatabaseQueries.search_users(search_query)
            if not users:
                await update.message.reply_text(f"❌ کاربری با مشخصات `{search_query}` یافت نشد.", parse_mode="Markdown")
                return

            lines = [f"🔎 نتایج جستجو برای `{search_query}`:"]
            for user in users:
                lines.append(f"• نام: {user.full_name}, آیدی: `{user.user_id}`, یوزرنیم: @{user.username}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

        # --- Free 30-Day Activation Flow ---
        elif context.user_data.get("awaiting_free20_user"):
            term = update.message.text.strip().lstrip("@")
            context.user_data.pop("awaiting_free20_user", None)  # Reset flag

            user_rows = DatabaseQueries.search_users(term)
            if not user_rows:
                await update.message.reply_text("❌ کاربری یافت نشد.")
                return

            # Pick the first match
            target_user_id = user_rows[0]['user_id']

            # Ensure free plan exists in the database
            plan_id = ensure_free_plan()
            if not plan_id:
                await update.message.reply_text("❌ خطا در یافتن یا ایجاد پلن رایگان در دیتابیس.")
                return

            # Add the subscription
            sub_id = DatabaseQueries.add_subscription(
                user_id=target_user_id,
                plan_id=plan_id,
                payment_id=None,  # No payment for a free plan
                plan_duration_days=20,
                amount_paid=0,
                payment_method="manual_free",
            )

            if not sub_id:
                await update.message.reply_text("❌ خطا در فعال‌سازی اشتراک رایگان برای کاربر.")
                return

            # Notify admin
            await update.message.reply_text(f"✅ اشتراک ۲۰ روزه رایگان برای کاربر `{target_user_id}` با موفقیت فعال شد. در حال ایجاد و ارسال لینک دعوت...", parse_mode="Markdown")

            # Generate and send invite links
            links = await self.invite_link_manager.ensure_one_time_links(context.bot, target_user_id)
            if not links:
                await update.message.reply_text("❌ خطا در ایجاد لینک‌های دعوت. اشتراک فعال شد اما لینک ارسال نشد.")
                return

            link_message = "🎁 سلام! اشتراک ۲۰ روزه رایگان شما فعال شد.\n\nمی‌توانید از طریق لینک‌های زیر به کانال‌ها و گروه‌های ما بپیوندید:\n"
            for channel_name, link in links.items():
                link_message += f"\n🔗 {channel_name}: {link}\n"
            link_message += "\nاین لینک‌ها یکبار مصرف هستند و فقط برای شما کار می‌کنند."

            try:
                await context.bot.send_message(chat_id=target_user_id, text=link_message)

                # Confirm to admin
                await update.message.reply_text(f"✅ لینک‌های دعوت با موفقیت برای کاربر `{target_user_id}` ارسال شد.", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send invite links to user {target_user_id}: {e}", exc_info=True)
                await update.message.reply_text(f"❌ خطا در ارسال لینک‌های دعوت به کاربر `{target_user_id}`. لطفاً به صورت دستی ارسال کنید.", parse_mode="Markdown")

        # If no flags matched, simply ignore the message so that other handlers may process it.
        logger.debug("broadcast_message_handler: No relevant flow flag set – ignoring message.")
        return

    # ---------- Payments helpers ----------
    async def _show_recent_payments_inline(self, query):
        """Show recent payments with inline buttons for quick details."""
        payments = DatabaseQueries.get_recent_payments(20)
        if not payments:
            await query.edit_message_text("📄 پرداختی یافت نشد.")
            return
        keyboard = []
        for p in payments:
            pid = p[0] if isinstance(p, (list, tuple)) else p.get('id')
            amount = p[2] if isinstance(p, (list, tuple)) else p.get('amount_rial')
            status = p[6] if isinstance(p, (list, tuple)) else p.get('status')
            created_at = p[7] if isinstance(p, (list, tuple)) else p.get('created_at')
            text = f"#{pid} | {amount:,} | {status} | {str(created_at)[:10]}"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"payment_info_{pid}")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=self.PAYMENTS_MENU)])
        await query.edit_message_text("💰 *۲۰ تراکنش اخیر:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_payment_details(self, query, payment_id: str):
        """Display details and history of a single payment."""
        db = DatabaseQueries()
        rec = db.get_payment(payment_id) or db.get_crypto_payment_by_payment_id(payment_id)
        if not rec:
            await query.edit_message_text("❌ پرداختی با این شناسه یافت نشد.")
            return
        # Build message
        lines = [f"🧾 *جزئیات پرداخت* #{payment_id}"]
        for k, v in dict(rec).items():
            lines.append(f"• {k}: {v}")
        history = db.get_payment_status_history(payment_id)
        if history:
            lines.append("\n📜 *تاریخچه وضعیت:*")
            for h in history:
                lines.append(f"→ {h['changed_at']} | {h['old_status']} ➜ {h['new_status']} | {h['note'] or ''}")
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="payments_recent")]]
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    async def _show_recent_payments(self, query):
        payments = DatabaseQueries.get_recent_payments(20)
        if not payments:
            await query.edit_message_text("📄 پرداختی یافت نشد.")
            return
        from telegram.helpers import escape_markdown
        lines = [escape_markdown("💰 ۲۰ تراکنش اخیر:", version=2) + "\n"]
        for p in payments:
            try:
                payment_id = p[0] if isinstance(p, (list, tuple)) else p.get('id')
                user_id = p[1] if isinstance(p, (list, tuple)) else p.get('user_id')
                amount = p[2] if isinstance(p, (list, tuple)) else p.get('amount')
                status = p[5] if isinstance(p, (list, tuple)) else p.get('status')
                created_at = p[6] if isinstance(p, (list, tuple)) else p.get('created_at')
                escaped_status = escape_markdown(str(status), version=2)
                lines.append(escape_markdown(f"• #{payment_id} – {amount} ریال – {escaped_status} – {created_at} – UID:{user_id}", version=2))
            except Exception:
                lines.append(str(p))
        await query.edit_message_text("\n".join(lines), parse_mode="MarkdownV2")

    async def _show_payments_stats(self, query):
        """Show per-plan sales & subscription stats for admins."""
        from telegram.helpers import escape_markdown

        stats = DatabaseQueries.get_sales_stats_per_plan()
        if not stats:
            await query.edit_message_text("📊 هیچ آماری برای نمایش وجود ندارد.")
            return

        header = escape_markdown("📈 آمار فروش/اشتراک هر پلن:", version=2)
        lines = [header + "\n"]
        for rec in stats:
            pid   = rec.get("plan_id")
            name  = rec.get("plan_name")
            active = rec.get("active_subscriptions", 0)
            total  = rec.get("total_subscriptions", 0)
            rev_r = rec.get("total_revenue_rial", 0) or 0
            rev_u = rec.get("total_revenue_usdt", 0) or 0
            name_md = escape_markdown(str(name), version=2)
            rev_u_md = escape_markdown(str(rev_u), version=2).replace('.', '\.').replace('-', '\-')
            lines.append(f"• {name_md}: {active}/{total} فعال \| درآمد: {rev_u_md} USDT – {int(rev_r):,} ریال")

        await query.edit_message_text("\n".join(lines), parse_mode="MarkdownV2")
    async def _show_admins_settings(self, query):
        """Display list of configured admins. Use safe HTML formatting to avoid Markdown errors."""
        import html as _html
        if not self.admin_config:
            await query.edit_message_text("🔐 پیکربندی مدیران یافت نشد.")
            return
        lines = ["<b>🔐 فهرست مدیران:</b>"]
        if isinstance(self.admin_config, list):
            for adm in self.admin_config:
                if isinstance(adm, dict):
                    alias = _html.escape(str(adm.get('alias', '-')))
                    cid = _html.escape(str(adm.get('chat_id', '-')))
                    lines.append(f"• {alias} – {cid}")
        elif isinstance(self.admin_config, dict):
            for uid, alias in self.admin_config.items():
                alias_h = _html.escape(str(alias))
                uid_h = _html.escape(str(uid))
                lines.append(f"• {alias_h} – {uid_h}")
        await query.edit_message_text("\n".join(lines), parse_mode="HTML")

    # ---------- Public helper ----------
    # ---------- Invite Link Conversation Handlers ----------

    @admin_only
    async def start_invite_link_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Asks the admin for the user_id to create an invite link for."""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "🔗 لطفاً آیدی عددی کاربری که می‌خواهید برای او لینک دعوت بسازید را ارسال کنید.\n\n"
            "برای لغو /cancel را بزنید."
        )
        return self.GET_INVITE_LINK_USER_ID

    @admin_only
    async def create_and_send_invite_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receives user_id, creates links, sends them, and confirms."""
        admin_user = update.effective_user
        target_user_id_str = update.message.text

        if not target_user_id_str.isdigit():
            await update.message.reply_text("❌ آیدی کاربر باید یک عدد باشد. لطفاً دوباره تلاش کنید یا /cancel را بزنید.")
            return self.GET_INVITE_LINK_USER_ID

        target_user_id = int(target_user_id_str)

        await update.message.reply_text(f"⏳ در حال ایجاد لینک برای کاربر `{target_user_id}`...", parse_mode="Markdown")

        try:
            # We need to use the new method name from the manager
            links = await InviteLinkManager.ensure_one_time_links(context.bot, target_user_id)

            if not links:
                await admin_user.send_message(
                    f"❌ متاسفانه ایجاد لینک برای کاربر `{target_user_id}` با خطا مواجه شد. "
                    f"ممکن است ربات دسترسی لازم در کانال‌ها را نداشته باشد. لطفاً لاگ‌ها را بررسی کنید.",
                    parse_mode="Markdown"
                )
                return ConversationHandler.END

            # Send links to the target user
            link_message = "سلام! لینک‌های دعوت شما برای عضویت در کانال‌ها آماده شد:\n\n" + "\n".join(links)
            try:
                await context.bot.send_message(chat_id=target_user_id, text=link_message)

                # Confirm to admin
                await admin_user.send_message(
                    f"✅ لینک‌های دعوت با موفقیت برای کاربر `{target_user_id}` ارسال شد.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to send invite links to user {target_user_id}: {e}", exc_info=True)
                await admin_user.send_message(
                    f"⚠️ لینک‌ها ایجاد شدند اما در ارسال به کاربر `{target_user_id}` خطا رخ داد: {e}\n\n"
                    "لینک‌ها:\n" + "\n".join(links),
                    parse_mode="Markdown"
                )

        except Exception as e:
            logger.error(f"Error in ensure_one_time_links for user {target_user_id}: {e}", exc_info=True)
            await admin_user.send_message(f"❌ یک خطای پیش‌بینی نشده در ایجاد لینک رخ داد: {e}")

        return ConversationHandler.END

    async def cancel_invite_link_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancels the invite link creation conversation."""
        await update.message.reply_text("عملیات ایجاد لینک دعوت لغو شد.")
        # To improve UX, we could show the main menu again, but this is sufficient.
        return ConversationHandler.END

    # --- Ban/Unban User Handlers ---
    async def ban_unban_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            text="لطفاً شناسه کاربری (User ID) کاربر مورد نظر را برای مسدود/آزاد کردن ارسال کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("لغو عملیات", callback_data='cancel_ban_unban')]])
        )
        return AWAIT_USER_ID_FOR_BAN

    async def ban_unban_receive_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id_str = update.message.text
        if not user_id_str.isdigit():
            await update.message.reply_text("شناسه کاربری نامعتبر است. لطفاً یک عدد ارسال کنید.")
            return AWAIT_USER_ID_FOR_BAN

        user_id = int(user_id_str)
        user = DatabaseQueries.get_user_by_telegram_id(user_id)

        if not user:
            await update.message.reply_text(
                f"کاربری با شناسه {user_id} یافت نشد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("لغو عملیات", callback_data='cancel_ban_unban')]])
            )
            return AWAIT_USER_ID_FOR_BAN

        status = DatabaseQueries.get_user_status(user_id)
        status_text = "مسدود 🛑" if status == 'banned' else "فعال ✅"

        keyboard = [
            [InlineKeyboardButton("مسدود کردن کاربر", callback_data=f'ban_user_{user_id}')],
            [InlineKeyboardButton("آزاد کردن کاربر", callback_data=f'unban_user_{user_id}')],
            [InlineKeyboardButton("لغو عملیات", callback_data='cancel_ban_unban')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"کاربر: {user['full_name'] or user_id}\nوضعیت فعلی: {status_text}\n\nلطفاً اقدام مورد نظر را انتخاب کنید:",
            reply_markup=reply_markup
        )
        return AWAIT_BAN_CHOICE

    async def ban_unban_set_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        action, _, user_id_str = query.data.partition('_user_')
        user_id = int(user_id_str)
        new_status = 'banned' if action == 'ban' else 'active'
        
        if DatabaseQueries.set_user_status(user_id, new_status):
            status_text = "مسدود شد" if new_status == 'banned' else "آزاد شد"
            await query.edit_message_text(f"کاربر با شناسه {user_id} با موفقیت {status_text}.")
        else:
            await query.edit_message_text("خطایی در به‌روزرسانی وضعیت کاربر رخ داد.")

        # Return to the main users menu
        await self._users_submenu(query)
        return ConversationHandler.END

    async def ban_unban_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("عملیات مسدود/آزاد کردن لغو شد.")
        await self._users_submenu(query)
        return ConversationHandler.END

    # --- Ban/Unban User Handlers ---
    async def ban_unban_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            text="لطفاً شناسه کاربری (User ID) کاربر مورد نظر را برای مسدود/آزاد کردن ارسال کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("لغو عملیات", callback_data='cancel_ban_unban')]])
        )
        return self.AWAIT_USER_ID_FOR_BAN

    async def ban_unban_receive_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id_str = update.message.text
        if not user_id_str.isdigit():
            await update.message.reply_text("شناسه کاربری نامعتبر است. لطفاً یک عدد ارسال کنید.")
            return self.AWAIT_USER_ID_FOR_BAN

        user_id = int(user_id_str)
        user = DatabaseQueries.get_user_by_telegram_id(user_id)

        if not user:
            await update.message.reply_text(
                f"کاربری با شناسه {user_id} یافت نشد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("لغو عملیات", callback_data='cancel_ban_unban')]])
            )
            return self.AWAIT_USER_ID_FOR_BAN

        status = DatabaseQueries.get_user_status(user_id)
        status_text = "مسدود 🛑" if status == 'banned' else "فعال ✅"

        keyboard = [
            [InlineKeyboardButton("مسدود کردن کاربر", callback_data=f'ban_user_{user_id}')],
            [InlineKeyboardButton("آزاد کردن کاربر", callback_data=f'unban_user_{user_id}')],
            [InlineKeyboardButton("لغو عملیات", callback_data='cancel_ban_unban')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"کاربر: {user['full_name'] or user_id}\nوضعیت فعلی: {status_text}\n\nلطفاً اقدام مورد نظر را انتخاب کنید:",
            reply_markup=reply_markup
        )
        return self.AWAIT_BAN_CHOICE

    async def ban_unban_set_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        action, _, user_id_str = query.data.partition('_user_')
        user_id = int(user_id_str)
        new_status = 'banned' if action == 'ban' else 'active'
        
        if DatabaseQueries.set_user_status(user_id, new_status):
            status_text = "مسدود شد" if new_status == 'banned' else "آزاد شد"
            await query.edit_message_text(f"کاربر با شناسه {user_id} با موفقیت {status_text}.")
        else:
            await query.edit_message_text("خطایی در به‌روزرسانی وضعیت کاربر رخ داد.")

        # Return to the main users menu
        await self._users_submenu(query)
        return ConversationHandler.END

    async def ban_unban_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("عملیات مسدود/آزاد کردن لغو شد.")
        await self._users_submenu(query)
        return ConversationHandler.END

    async def _settings_support_submenu(self, query):
        """Support users management submenu"""
        keyboard = [
            [InlineKeyboardButton("➕ افزودن پشتیبان", callback_data=self.SUPPORT_ADD)],
            [InlineKeyboardButton("📋 فهرست پشتیبان‌ها", callback_data=self.SUPPORT_LIST)],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.SETTINGS_MENU)],
        ]
        await query.edit_message_text("👥 *مدیریت پشتیبان‌ها*:\nگزینه مورد نظر را انتخاب کنید.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_support_users(self, query):
        rows = DatabaseQueries.get_all_support_users()
        if not rows:
            await query.edit_message_text("👥 هیچ کاربر پشتیبانی تعریف نشده است.")
            return
        lines = ["👥 *فهرست پشتیبان‌ها:*\n"]
        keyboard = []
        for row in rows:
            if isinstance(row, (list, tuple)):
                tg_id = row[0]
                added_at = row[2] if len(row) > 2 else None
            else:
                tg_id = row["telegram_id"] if "telegram_id" in row.keys() else row[0]
                added_at = row["added_at"] if "added_at" in row.keys() else (row[2] if len(row) > 2 else None)
            lines.append(f"• {tg_id} – {added_at}")
            keyboard.append([InlineKeyboardButton(f"❌ حذف {tg_id}", callback_data=f"remove_support_{tg_id}")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=self.SUPPORT_MENU)])
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    # ---- Extend Subscription Duration (Single User) Flow ----
    @staff_only
    async def start_extend_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Entry point: ask admin for target user identifier (username or Telegram ID)."""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "لطفاً شناسه عددی یا نام کاربری (بدون @) کاربر مورد نظر را ارسال کنید:\n\nبرای لغو /cancel را بزنید.",
            parse_mode="Markdown",
        )
        return self.AWAIT_EXTEND_USER_ID

    async def receive_extend_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        identifier = (update.message.text or "").strip()
        user_id = None
        # Convert Persian digits to English if helper exists
        try:
            from utils.locale_utils import fa_to_en_digits
            identifier = fa_to_en_digits(identifier)
        except Exception:
            pass

        if identifier.isdigit():
            user_id = int(identifier)
        else:
            # strip leading @ if present
            if identifier.startswith("@"):
                identifier = identifier[1:]
            # Search user by username
            results = DatabaseQueries.search_users(identifier)
            if results:
                # Take first match
                row = results[0]
                user_id = row["user_id"] if isinstance(row, dict) else row[0]
        if not user_id:
            await update.message.reply_text("کاربر یافت نشد. دوباره تلاش کنید یا /cancel را بزنید.")
            return self.AWAIT_EXTEND_USER_ID

        context.user_data["extend_target_user_id"] = user_id
        await update.message.reply_text("تعداد روزهایی که می‌خواهید به اشتراک کاربر اضافه شود را وارد کنید:")
        return self.AWAIT_EXTEND_DAYS

    async def receive_extend_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        days_str = (update.message.text or "").strip()
        try:
            days = int(days_str)
        except ValueError:
            await update.message.reply_text("لطفاً یک عدد معتبر وارد کنید.")
            return self.AWAIT_EXTEND_DAYS
        if days <= 0:
            await update.message.reply_text("تعداد روز باید بیشتر از ۰ باشد.")
            return self.AWAIT_EXTEND_DAYS

        user_id = context.user_data.get("extend_target_user_id")
        if not user_id:
            await update.message.reply_text("خطا: شناسه کاربر در حافظه یافت نشد. لطفاً از ابتدا دوباره تلاش کنید.")
            return ConversationHandler.END

        success = DatabaseQueries.extend_subscription_duration(user_id, days)
        if success:
            await update.message.reply_text(f"✅ اشتراک کاربر {user_id} به‌مدت {days} روز تمدید شد.")
            # Notify the user in the main bot (if we have access to bot instance)
            if self.main_bot_app:
                try:
                    # Check if main_bot_app has 'application' attribute (for Application object)
                    if hasattr(self.main_bot_app, "application") and hasattr(self.main_bot_app.application, "bot"):
                        await self.main_bot_app.application.bot.send_message(
                            chat_id=user_id,
                            text=f"اشتراک شما به‌مدت {days} روز تمدید شد. از همراهی شما سپاسگزاریم!"
                        )
                    # Check if main_bot_app has direct 'bot' attribute
                    elif hasattr(self.main_bot_app, "bot"):
                        await self.main_bot_app.bot.send_message(
                            chat_id=user_id,
                            text=f"اشتراک شما به‌مدت {days} روز تمدید شد. از همراهی شما سپاسگزاریم!"
                        )
                    else:
                        logger.warning("main_bot_app does not have expected bot attribute structure")
                except Exception as e:
                    logger.warning("Failed to notify user %s about extension: %s", user_id, e)
        else:
            await update.message.reply_text("❌ تمدید اشتراک ناموفق بود. کاربر ممکن است اشتراک فعالی نداشته باشد.")
        # After completion, show users submenu again
        class _DummyQuery:
            def __init__(self, message):
                self.message = message
            async def edit_message_text(self, *args, **kwargs):
                await self.message.reply_text(*args, **kwargs)
        await self._users_submenu(_DummyQuery(update.message))
        return ConversationHandler.END

    async def cancel_extend_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("عملیات لغو شد.")
        await self._users_submenu(update)
        return ConversationHandler.END

    # ---- Extend Subscription Duration for All Users (Bulk) ----
    @staff_only
    async def start_extend_subscription_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "🔔 لطفاً تعداد روزهایی که می‌خواهید به تمام کاربران فعال اضافه شود را وارد کنید:\n\nبرای لغو /cancel را بزنید.",
            parse_mode="Markdown",
        )
        return self.AWAIT_EXTEND_ALL_DAYS

    async def receive_extend_all_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        days_str = (update.message.text or "").strip()
        try:
            days = int(days_str)
        except ValueError:
            await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید.")
            return self.AWAIT_EXTEND_ALL_DAYS
        if days <= 0:
            await update.message.reply_text("❌ تعداد روز باید بیشتر از ۰ باشد.")
            return self.AWAIT_EXTEND_ALL_DAYS

        updated = DatabaseQueries.extend_subscription_duration_all(days)
        await update.message.reply_text(f"✅ اشتراک {updated} کاربر به‌مدت {days} روز تمدید شد.")

        # Notify each active subscriber
        if self.main_bot_app:
            try:
                users = DatabaseQueries.get_all_active_subscribers()
                bot_instance = None
                
                # Determine the correct bot instance
                if hasattr(self.main_bot_app, "application") and hasattr(self.main_bot_app.application, "bot"):
                    bot_instance = self.main_bot_app.application.bot
                elif hasattr(self.main_bot_app, "bot"):
                    bot_instance = self.main_bot_app.bot
                
                if bot_instance:
                    for row in users:
                        # Handle sqlite3.Row objects properly
                        if hasattr(row, 'keys'):  # sqlite3.Row
                            uid = row[0] if len(row) > 0 else None
                        elif isinstance(row, (list, tuple)):
                            uid = row[0]
                        elif isinstance(row, dict):
                            uid = row.get("user_id")
                        else:
                            uid = None
                        
                        if not uid:
                            continue
                        try:
                            await bot_instance.send_message(
                                chat_id=uid,
                                text=f"اشتراک شما به‌مدت {days} روز تمدید شد. از همراهی شما سپاسگزاریم!"
                            )
                        except Exception:
                            pass  # Ignore failures for individual users
                else:
                    logger.warning("Could not find bot instance in main_bot_app")
            except Exception as e:
                logger.warning("Failed to broadcast extension notification: %s", e)

        class _DummyQuery:
            def __init__(self, message):
                self.message = message
            async def edit_message_text(self, *args, **kwargs):
                await self.message.reply_text(*args, **kwargs)

        await self._users_submenu(_DummyQuery(update.message))
        return ConversationHandler.END

    async def cancel_extend_subscription_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("عملیات لغو شد.")
        await self._users_submenu(update)
        return ConversationHandler.END

    # ---- Check Subscription Status Flow ----
    @staff_only
    async def start_check_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("لطفاً شناسه عددی یا نام کاربری کاربر را وارد کنید:")
        return self.AWAIT_CHECK_USER_ID

    async def receive_check_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        identifier = (update.message.text or "").strip()
        try:
            from utils.locale_utils import fa_to_en_digits
            identifier = fa_to_en_digits(identifier)
        except Exception:
            pass
        user_id = None
        if identifier.isdigit():
            user_id = int(identifier)
        else:
            if identifier.startswith("@"):
                identifier = identifier[1:]
            results = DatabaseQueries.search_users(identifier)
            if results:
                # Take first match
                row = results[0]
                user_id = row["user_id"] if isinstance(row, dict) else row[0]
        if not user_id:
            await update.message.reply_text("کاربر یافت نشد. دوباره تلاش کنید یا /cancel.")
            return self.AWAIT_CHECK_USER_ID

        sub_row = DatabaseQueries.get_user_active_subscription(user_id)
        if not sub_row:
            await update.message.reply_text("این کاربر اشتراک فعالی ندارد.")
            await self._users_submenu(update)
            return ConversationHandler.END

        end_date_str = sub_row["end_date"] if isinstance(sub_row, dict) else sub_row[5]  # assuming column order
        try:
            from datetime import datetime
            end_dt = datetime.fromisoformat(end_date_str)
        except Exception:
            from datetime import datetime
            try:
                end_dt = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                end_dt = None
        if end_dt:
            from zoneinfo import ZoneInfo
            iran_tz = ZoneInfo("Asia/Tehran")
            # ensure both datetimes Tehran tz
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=iran_tz)
            else:
                end_dt = end_dt.astimezone(iran_tz)
            now = datetime.now(tz=iran_tz)
            delta = end_dt - now
            if delta.total_seconds() <= 0:
                # Possibly incorrect record; attempt to find a future subscription
                other_active = DatabaseQueries.get_user_active_subscriptions(user_id) if hasattr(DatabaseQueries, 'get_user_active_subscriptions') else None
                if other_active:
                    # Expect list of rows sorted by end_date DESC; pick first with future end_date
                    for row in other_active:
                        end_str = row['end_date'] if isinstance(row, dict) else row[5]
                        try:
                            alt_dt = datetime.fromisoformat(end_str)
                        except Exception:
                            try:
                                alt_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                            except Exception:
                                continue
                        if alt_dt.tzinfo is None:
                            alt_dt = alt_dt.replace(tzinfo=iran_tz)
                        else:
                            alt_dt = alt_dt.astimezone(iran_tz)
                        if alt_dt > now:
                            end_dt = alt_dt
                            delta = end_dt - now
                            break
                if delta.total_seconds() <= 0:
                    msg = "اشتراک کاربر منقضی شده است."
                else:
                    # fallthrough to human_rem below
                    pass
            if delta.total_seconds() > 0:
                days = delta.days
                hours = delta.seconds // 3600
                minutes = (delta.seconds % 3600) // 60
                human_rem = f"{days} روز"
                if hours or minutes:
                    human_rem += f" و {hours} ساعت و {minutes} دقیقه"
                msg = (
                    f"اعتبار اشتراک کاربر تا تاریخ {end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                    f"(حدود {human_rem} باقی مانده)"
                )
        else:
            msg = f"تاریخ پایان اشتراک: {end_date_str}"
        await update.message.reply_text(msg)

        # Wrap message in a lightweight DummyQuery so _users_submenu works
        class _DummyQuery:
            def __init__(self, message):
                self.message = message
            async def edit_message_text(self, *args, **kwargs):
                await self.message.reply_text(*args, **kwargs)
        await self._users_submenu(_DummyQuery(update.message))
        return ConversationHandler.END

    def get_handlers(self):
        """Return telegram.ext handlers to register in the dispatcher."""
        handlers = [
            CommandHandler("admin", self.show_admin_menu),
        ]

        # Conversation handler for creating invite links
        invite_link_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_invite_link_creation, pattern=f"^{self.CREATE_INVITE_LINK}$")],
            states={
                self.GET_INVITE_LINK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.create_and_send_invite_link)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_invite_link_creation)],
            per_user=True,
            per_chat=True,
        )
        handlers.append(invite_link_conv_handler)

        # Conversation handler for extending subscription duration
        extend_sub_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_extend_subscription, pattern=f'^{self.EXTEND_SUB_CALLBACK}$')],
            states={
                self.AWAIT_EXTEND_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_extend_user_id)],
                self.AWAIT_EXTEND_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_extend_days)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel_extend_subscription)],
            per_user=True,
            per_chat=True,
        )
        handlers.append(extend_sub_conv_handler)

        # Conversation handler for checking subscription status
        check_sub_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_check_subscription, pattern=f'^{self.CHECK_SUB_STATUS}$')],
            states={
                self.AWAIT_CHECK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_check_user_id)],
            },
            fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)],
            per_user=True,
            per_chat=True,
        )
        handlers.append(check_sub_conv_handler)

        ban_unban_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.ban_unban_start, pattern=f'^{self.BAN_UNBAN_USER}$')],
            states={
                AWAIT_USER_ID_FOR_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.ban_unban_receive_user_id)],
                AWAIT_BAN_CHOICE: [CallbackQueryHandler(self.ban_unban_set_status, pattern=r'^(ban|unban)_user_')]
            },
            fallbacks=[
                CallbackQueryHandler(self.ban_unban_cancel, pattern='^cancel_ban_unban$'),
                CommandHandler('cancel', self.ban_unban_cancel)
                ],
            map_to_parent={
                ConversationHandler.END: self.MAIN_MENU_CALLBACK
            }
        )
        ban_unban_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.ban_unban_start, pattern=f'^{self.BAN_UNBAN_USER}$')],
            states={
                self.AWAIT_USER_ID_FOR_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.ban_unban_receive_user_id)],
                self.AWAIT_BAN_CHOICE: [CallbackQueryHandler(self.ban_unban_set_status, pattern=r'^(ban|unban)_user_')]
            },
            fallbacks=[
                CallbackQueryHandler(self.ban_unban_cancel, pattern='^cancel_ban_unban$'),
                CommandHandler('cancel', self.ban_unban_cancel)
                ],
            # Since this is a nested conversation, we don't map to parent, but end it.
            # The parent handler will catch the back-to-menu callbacks.
        )
        handlers.append(ban_unban_handler)

        # Channel multi-select picker for broadcast with link
        handlers.append(CallbackQueryHandler(self._broadcast_wl_picker_callback, pattern=r"^(chpick_.*|chpick_all|chpick_done)$"))

        # ---- Renew buttons settings handlers ----
        handlers.append(CallbackQueryHandler(self._settings_renew_buttons_submenu, pattern='^settings_renew_buttons$'))
        handlers.append(CallbackQueryHandler(self._settings_renew_toggle_callback, pattern=r'^toggle_renew_(free|products)$'))
        handlers.append(CallbackQueryHandler(self._settings_renew_toggle_callback, pattern=r'^toggle_renew_(cat|plan)_-?\d+$'))

        # Conversation handler for extend all subscriptions
        extend_all_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_extend_subscription_all, pattern=f'^{self.EXTEND_SUB_ALL_CALLBACK}$')],
            states={
                self.AWAIT_EXTEND_ALL_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_extend_all_days)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel_extend_subscription_all)],
        )
        handlers.append(extend_all_conv_handler)

        # ---- Support user management handlers ----
        handlers.extend(self.support_manager.get_handlers())

        # ---- Export subscribers handlers ----
        handlers.append(CallbackQueryHandler(self.export_handler.entry, pattern=f'^{self.EXPORT_SUBS_MENU}$'))
        handlers.append(CallbackQueryHandler(self.export_handler.handle_product, pattern=r'^exp_prod_\d+$'))

        # This is the main handler for all other admin menu callbacks
        # Note: The invite link and ban/unban callbacks are handled by their respective ConversationHandlers.
        handlers.append(CallbackQueryHandler(self.admin_menu_callback, pattern="^(admin_|users_|tickets_|payments_|broadcast_|settings_|products_|discounts_|view_discount_|toggle_discount_|delete_discount_|confirm_delete_discount_|view_plan_|toggle_plan_|delete_plan_|confirm_delete_plan_|planpick_)"))

        return handlers
