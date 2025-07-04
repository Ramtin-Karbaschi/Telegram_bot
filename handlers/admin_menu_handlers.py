"""Admin main menu handlers for Daraei Academy Telegram bot.
Provides a simple, localized admin panel with inline keyboards
so administrators can quickly access management features
(tickets, users, payments, broadcasts, settings)."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler, filters

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
        # Simple flag for maintenance mode toggle in misc settings
        self.maintenance_mode = False
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
        keyboard = [
            [InlineKeyboardButton("🎫 مدیریت تیکت‌ها", callback_data=self.TICKETS_MENU), InlineKeyboardButton("👥 مدیریت کاربران", callback_data=self.USERS_MENU)],
            [InlineKeyboardButton("💳 مدیریت پرداخت‌ها", callback_data=self.PAYMENTS_MENU), InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data=self.BROADCAST_MENU)],
            [InlineKeyboardButton("⚙️ تنظیمات", callback_data=self.SETTINGS_MENU)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("⚡️ *پنل مدیریت*\nیکی از گزینه‌های زیر را انتخاب کنید:", parse_mode="Markdown", reply_markup=reply_markup)

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
        elif data == self.BACK_MAIN:
            await self._back_to_main(query)
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
        # ----- Payments submenu actions -----
        elif data == "payments_recent":
            await self._show_recent_payments(query)
        elif data == "payments_stats":
            await self._show_payments_stats(query)
        # ----- Settings submenu actions -----
        elif data == "settings_admins":
            await self._show_admins_settings(query)
        elif data == "settings_misc":
            await self._settings_misc_submenu(query)
        elif data == "settings_toggle_maintenance":
            # Toggle the flag
            self.maintenance_mode = not self.maintenance_mode
            await query.answer("به‌روزرسانی شد")
            await self._settings_misc_submenu(query)
        # ----- Broadcast submenu actions -----
        elif data == "broadcast_send":
            # Initiate broadcast flow – ask admin to send the content
            await query.edit_message_text("✉️ لطفاً پیام مورد نظر خود را ارسال کنید. پس از ارسال، پیام به‌صورت خودکار برای تمامی کاربران فعال فوروارد خواهد شد.")
            # Flag the admin's user_data so the next incoming message will be treated as broadcast content
            context.user_data["awaiting_broadcast_content"] = True
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

    # ---------- Broadcast content handler ----------
    @admin_only
    async def broadcast_message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle dynamic admin inputs based on flow flags (broadcast, user search)."""
        message = update.effective_message
        # Debug log
        logger.debug("broadcast_message_handler triggered by user %s. Flags: broadcast=%s, search=%s", message.from_user.id if message else 'N/A', context.user_data.get("awaiting_broadcast_content"), context.user_data.get("awaiting_user_search_query"))

        # -------- Broadcast flow --------
        if context.user_data.get("awaiting_broadcast_content"):
            # Notify admin that sending is in progress
            await message.reply_text("⏳ در حال ارسال پیام به کاربران، لطفاً صبر کنید...")

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
            context.user_data.pop("awaiting_broadcast_content", None)
            return

        # -------- User search flow --------
        if context.user_data.get("awaiting_user_search_query"):
            term = message.text.strip()
            results = DatabaseQueries.search_users(term)
            if not results:
                await message.reply_text("❌ کاربری یافت نشد.")
            else:
                lines = ["🔎 *نتایج جستجو:*\n"]
                for r in results:
                    try:
                        user_id = r[0] if isinstance(r, (list, tuple)) else r.get('user_id')
                        full_name = r[1] if isinstance(r, (list, tuple)) else r.get('full_name', '')
                        username = r[2] if isinstance(r, (list, tuple)) else r.get('username', '')
                        line = f"• {full_name} ({'@'+username if username else '-'}) – {user_id}"
                    except Exception:
                        line = str(r)
                    lines.append(line)
                await message.reply_text("\n".join(lines), parse_mode="Markdown")
            context.user_data.pop("awaiting_user_search_query", None)
            return

        # If no flags matched, simply ignore the message so that other handlers may process it.
        logger.debug("broadcast_message_handler: No relevant flow flag set – ignoring message.")
        return

    # ---------- Payments helpers ----------
    async def _show_recent_payments(self, query):
        payments = DatabaseQueries.get_recent_payments(20)
        if not payments:
            await query.edit_message_text("📄 پرداختی یافت نشد.")
            return
        lines = ["💰 *۲۰ تراکنش اخیر:*\n"]
        for p in payments:
            try:
                payment_id = p[0] if isinstance(p, (list, tuple)) else p.get('id')
                user_id = p[1] if isinstance(p, (list, tuple)) else p.get('user_id')
                amount = p[2] if isinstance(p, (list, tuple)) else p.get('amount')
                status = p[5] if isinstance(p, (list, tuple)) else p.get('status')
                created_at = p[6] if isinstance(p, (list, tuple)) else p.get('created_at')
                lines.append(f"• #{payment_id} – {amount} ریال – {status} – {created_at} – UID:{user_id}")
            except Exception:
                lines.append(str(p))
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown")

    async def _show_payments_stats(self, query):
        plans = DatabaseQueries.get_active_plans()
        if not plans:
            await query.edit_message_text("📊 هیچ پلن فعالی یافت نشد.")
            return
        lines = ["📈 *آمار اشتراک‌های فعال:*\n"]
        for plan in plans:
            # Extract fields robustly for tuple/list, dict, or sqlite3.Row
            if isinstance(plan, (list, tuple)):
                plan_id, plan_name = plan[0], plan[1]
            else:
                # Try mapping access first
                try:
                    plan_id = plan["id"]
                    plan_name = plan["name"]
                except Exception:
                    plan_id = getattr(plan, "id", None)
                    plan_name = getattr(plan, "name", str(plan))
                    if plan_id is None and hasattr(plan, "get"):
                        plan_id = plan.get("id")
                        plan_name = plan.get("name", plan_name)

            count = DatabaseQueries.count_total_subs(plan_id)
            lines.append(f"• {plan_name}: {count} مشترک فعال")
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown")

    # ---------- Settings helpers ----------
    async def _settings_misc_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton(f"🛠 حالت تعمیرات: {'فعال' if self.maintenance_mode else 'غیرفعال'}", callback_data="settings_toggle_maintenance")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        status_text = "🛠 *حالت تعمیرات فعال است.*" if self.maintenance_mode else "✅ ربات در حالت عادی کار می‌کند."
        await query.edit_message_text(f"⚙️ *سایر تنظیمات*:\n{status_text}\nگزینه مورد نظر را انتخاب کنید:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_admins_settings(self, query):
        if not self.admin_config:
            await query.edit_message_text("🔐 پیکربندی مدیران یافت نشد.")
            return
        lines = ["🔐 *فهرست مدیران:*\n"]
        if isinstance(self.admin_config, list):
            for adm in self.admin_config:
                if isinstance(adm, dict):
                    lines.append(f"• {adm.get('alias','-')} – {adm.get('chat_id')}")
        elif isinstance(self.admin_config, dict):
            for uid, alias in self.admin_config.items():
                lines.append(f"• {alias} – {uid}")
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown")

    # ---------- Public helper ----------
    def get_handlers(self):
        """Return telegram.ext handlers to register in the dispatcher."""
        return [
            CommandHandler("admin", self.show_admin_menu),
            CallbackQueryHandler(self.admin_menu_callback, pattern=r"^admin_.*|^tickets_.*|^users_.*|^payments_.*|^broadcast_.*|^settings_.*"),
            # Handle incoming messages for broadcast flow (only processed when flag is set)
            MessageHandler(filters.ALL, self.broadcast_message_handler),
        ]
