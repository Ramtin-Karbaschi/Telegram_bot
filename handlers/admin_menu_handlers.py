"""Admin main menu handlers for Daraei Academy Telegram bot.
Provides a simple, localized admin panel with inline keyboards
so administrators can quickly access management features
(tickets, users, payments, broadcasts, settings)."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler

from utils.helpers import admin_only_decorator as admin_only
from handlers.admin_ticket_handlers import AdminTicketHandler
from database.queries import DatabaseQueries

logger = logging.getLogger(__name__)


class AdminMenuHandler:
    """Show an interactive admin panel and dispatch to feature modules."""

    def __init__(self, admin_config=None):
        # Save admin configuration for permission checks used by @admin_only decorator
        self.admin_config = admin_config
        # Re-use ticket handler to show lists inside this menu
        self.ticket_handler = AdminTicketHandler()
    """Show an interactive admin panel and dispatch to feature modules."""

    # Callback data constants
    TICKETS_MENU = "admin_tickets_menu"
    USERS_MENU = "admin_users_menu"
    PAYMENTS_MENU = "admin_payments_menu"
    BROADCAST_MENU = "admin_broadcast_menu"
    SETTINGS_MENU = "admin_settings_menu"
    BACK_MAIN = "admin_back_main"

    @admin_only
    async def show_admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Entry command `/admin` – show main panel."""
        keyboard = [
            [InlineKeyboardButton("🎫 مدیریت تیکت‌ها", callback_data=self.TICKETS_MENU), InlineKeyboardButton("👥 مدیریت کاربران", callback_data=self.USERS_MENU)],
            [InlineKeyboardButton("💳 مدیریت پرداخت‌ها", callback_data=self.PAYMENTS_MENU), InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data=self.BROADCAST_MENU)],
            [InlineKeyboardButton("⚙️ تنظیمات", callback_data=self.SETTINGS_MENU)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("⚡️ *پنل مدیریت*\nیکی از گزینه‌های زیر را انتخاب کنید:", parse_mode="Markdown", reply_markup=reply_markup)

    async def _back_to_main(self, query):
        """Return to main admin panel (used internally)."""
        await query.edit_message_text("⚡️ *پنل مدیریت*\nیکی از گزینه‌های زیر را انتخاب کنید:", parse_mode="Markdown")
        # Re-use show_admin_menu keyboard
        await self.show_admin_menu(query, None)  # type: ignore[arg-type]

    # ---------- Menu callbacks ----------
    @admin_only
    async def admin_menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        logger.debug("Admin menu callback: %s", data)

        if data == self.TICKETS_MENU:
            await self._tickets_submenu(query)
        elif data == self.USERS_MENU:
            await self._users_submenu(query)
        elif data == self.PAYMENTS_MENU:
            await self._payments_submenu(query)
        elif data == self.BROADCAST_MENU:
            await self._broadcast_submenu(query)
        elif data == self.SETTINGS_MENU:
            await self._settings_submenu(query)
        # ----- Ticket submenu actions -----
        elif data == "tickets_open":
            await self.ticket_handler._show_tickets_inline(query)
        elif data == "tickets_all":
            await self.ticket_handler._show_all_tickets_inline(query)
        # ----- Users submenu actions -----
        elif data == "users_active":
            await self._show_active_users(query)
        elif data == "users_search":
            await query.answer("جستجو هنوز پیاده‌سازی نشده است.")
            await self._users_submenu(query)
        elif data == self.BACK_MAIN:
            # Just recreate the main menu
            await self.show_admin_menu(query, context)  # type: ignore[arg-type]
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
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("🎫 *مدیریت تیکت‌ها*\nگزینه مورد نظر را انتخاب کنید:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _users_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("🔎 جستجوی کاربر", callback_data="users_search"), InlineKeyboardButton("📋 لیست کاربران فعال", callback_data="users_active")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("👥 *مدیریت کاربران*:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _payments_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("💰 تراکنش‌های اخیر", callback_data="payments_recent"), InlineKeyboardButton("📈 آمار اشتراک‌ها", callback_data="payments_stats")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("💳 *مدیریت پرداخت‌ها*:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _broadcast_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("✉️ ارسال پیام", callback_data="broadcast_send")],
            [InlineKeyboardButton("🗑 لغو", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("📢 *ارسال پیام همگانی*:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _settings_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("🔐 تنظیم مدیران", callback_data="settings_admins"), InlineKeyboardButton("⚙️ سایر تنظیمات", callback_data="settings_misc")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("⚙️ *تنظیمات*:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    # ---------- Public helper ----------
    def get_handlers(self):
        """Return telegram.ext handlers to register in the dispatcher."""
        return [
            CommandHandler("admin", self.show_admin_menu),
            CallbackQueryHandler(self.admin_menu_callback, pattern=r"^admin_.*|^tickets_.*|^users_.*|^payments_.*|^broadcast_.*|^settings_.*"),
        ]
