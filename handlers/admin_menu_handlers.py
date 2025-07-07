"""Admin main menu handlers for Daraei Academy Telegram bot.
Provides a simple, localized admin panel with inline keyboards
so administrators can quickly access management features
(tickets, users, payments, broadcasts, settings)."""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler, filters, ConversationHandler

from utils.helpers import admin_only_decorator as admin_only
from utils.invite_link_manager import InviteLinkManager
from database.free_plan_helper import ensure_free_plan
from utils.db_backup import export_database
from .admin_ticket_handlers import AdminTicketHandler
from .admin_product_handlers import AdminProductHandler
from ..utils.invite_link_manager import InviteLinkManager
from ..database.free_plan_helper import ensure_free_plan
from ..database.queries import DatabaseQueries

logger = logging.getLogger(__name__)

# States for Ban/Unban Conversation
AWAIT_USER_ID_FOR_BAN, AWAIT_BAN_CHOICE = range(2)

class AdminMenuHandler:
    """Show an interactive admin panel and dispatch to feature modules."""

    def __init__(self, admin_config=None):
        # Save admin configuration for permission checks used by @admin_only decorator
        self.admin_config = admin_config
        # Re-use ticket handler to show lists inside this menu
        self.ticket_handler = AdminTicketHandler()
        self.product_handler = AdminProductHandler() # Create an instance
        # Simple flag for maintenance mode toggle in misc settings
        self.maintenance_mode = False
    """Show an interactive admin panel and dispatch to feature modules."""

    # Callback data constants
    TICKETS_MENU = "admin_tickets_menu"
    USERS_MENU = "admin_users_menu"
    FREE30_CALLBACK = "users_free30"
    CREATE_INVITE_LINK = "users_create_invite_link"
    PAYMENTS_MENU = "admin_payments_menu"
    BROADCAST_MENU = "admin_broadcast_menu"
    SETTINGS_MENU = "admin_settings_menu"
    PRODUCTS_MENU = "admin_products_menu"
    BACKUP_CALLBACK = "settings_backup"
    BACK_MAIN = "admin_back_main"
    BAN_UNBAN_USER = "users_ban_unban"

    # Conversation states
    (GET_INVITE_LINK_USER_ID,) = range(100, 101)
    (AWAIT_BROADCAST_MESSAGE, AWAIT_BROADCAST_CONFIRMATION) = range(101, 103)
    (AWAIT_FREE30_USER_ID,) = range(103, 104)
    (AWAIT_USER_ID_FOR_BAN, AWAIT_BAN_CHOICE) = range(104, 106)

    @admin_only
    async def show_admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Entry command `/admin` – show main panel."""
        keyboard = [
            [InlineKeyboardButton("🎫 مدیریت تیکت‌ها", callback_data=self.TICKETS_MENU), InlineKeyboardButton("👥 مدیریت کاربران", callback_data=self.USERS_MENU)],
            [InlineKeyboardButton("💳 مدیریت پرداخت‌ها", callback_data=self.PAYMENTS_MENU), InlineKeyboardButton("📦 مدیریت محصولات", callback_data=self.PRODUCTS_MENU)],
            [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data=self.BROADCAST_MENU), InlineKeyboardButton("⚙️ تنظیمات", callback_data=self.SETTINGS_MENU)],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Check if we are editing a message (from a callback) or sending a new one
        if update.callback_query:
            await update.callback_query.edit_message_text("⚡️ *پنل مدیریت*\nیکی از گزینه‌های زیر را انتخاب کنید:", parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await update.message.reply_text("⚡️ *پنل مدیریت*\nیکی از گزینه‌های زیر را انتخاب کنید:", parse_mode="Markdown", reply_markup=reply_markup)

    async def _back_to_main(self, query):
        """Return to main admin panel (used internally)."""
        # This now simply calls the main menu function with the query's message
        await self.show_admin_menu(query, None) # type: ignore

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
        elif data == self.PRODUCTS_MENU:
            await self._products_submenu(query)
        # ----- Product submenu actions -----
        elif data == "products_list":
            await self.product_handler._show_all_plans(query)
        elif data.startswith("view_plan_"):
            plan_id = int(data.split("_")[2])
            await self.product_handler._show_single_plan(query, plan_id)
        elif data.startswith("toggle_plan_"):
            plan_id = int(data.split("_")[2])
            await self.product_handler.toggle_plan_status(query, plan_id)
        elif data.startswith("delete_plan_"):
            plan_id = int(data.split("_")[2])
            await self.product_handler.delete_plan_confirmation(query, plan_id)
        elif data.startswith("confirm_delete_plan_"):
            plan_id = int(data.split("_")[3])
            await self.product_handler.delete_plan(query, plan_id)
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
        elif data == self.FREE30_CALLBACK:
            # Start free 30-day activation flow
            await query.edit_message_text("🎁 لطفاً نام کاربری (بدون @) یا آیدی عددی کاربر را ارسال کنید:")
            context.user_data["awaiting_free30_user"] = True
        elif data == self.BAN_UNBAN_USER:
            await self.ban_unban_start(update, context)
        # ----- Payments submenu actions -----
        elif data == "payments_recent":
            await self._show_recent_payments(query)
        elif data == "payments_stats":
            await self._show_payments_stats(query)
        # ----- Discounts submenu actions -----
        elif data == "discounts_menu":
            await self._discounts_submenu(query)
        elif data == "discounts_add":
            # instruct admin to use /create_discount command (handled by conversation)
            await query.edit_message_text("لطفاً دستور /create_discount را ارسال کنید تا فرایند ساخت کد تخفیف آغاز شود.")
        elif data == "discounts_list":
            await self._list_discounts(query)
        elif data.startswith("view_discount_"):
            did = int(data.split("_")[2])
            await self._show_single_discount(query, did)
        elif data.startswith("toggle_discount_"):
            did = int(data.split("_")[2])
            await self._toggle_discount_status(query, did)
        elif data.startswith("delete_discount_"):
            did = int(data.split("_")[2])
            await self._delete_discount_confirmation(query, did)
        elif data.startswith("confirm_delete_discount_"):
            did = int(data.split("_")[3])
            await self._delete_discount(query, did)
            await self._list_discounts(query)
        # ----- Settings submenu actions -----
        elif data == "settings_admins":
            await self._show_admins_settings(query)
        elif data == self.BACKUP_CALLBACK:
            # generate and send db backup JSON
            bio = export_database()
            if bio:
                bio.seek(0)
                await context.bot.send_document(chat_id=query.from_user.id, document=bio, filename="db_backup.json")
                await query.answer("📤 بکاپ ارسال شد")
            else:
                await query.answer("❌ خطا در تهیه بکاپ", show_alert=True)
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
            [InlineKeyboardButton("🔗 ایجاد لینک دعوت", callback_data=self.CREATE_INVITE_LINK)],
            [InlineKeyboardButton("🎁 فعال‌سازی ۳۰ روزه رایگان", callback_data=self.FREE30_CALLBACK)],
            [InlineKeyboardButton("📋 لیست کاربران فعال", callback_data="users_list_active")],
            [InlineKeyboardButton("🔎 جستجوی کاربر", callback_data="users_search"), InlineKeyboardButton("🛑 مسدود/آزاد کردن", callback_data=self.BAN_UNBAN_USER)],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("👥 *مدیریت کاربران*:\nچه کاری می‌خواهید انجام دهید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _payments_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("💰 تراکنش‌های اخیر", callback_data="payments_recent"), InlineKeyboardButton("📈 آمار اشتراک‌ها", callback_data="payments_stats")],
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
            [InlineKeyboardButton("➕ افزودن محصول جدید", callback_data="products_add")],
            [InlineKeyboardButton("📜 مشاهده و ویرایش محصولات", callback_data="products_list")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("📦 *مدیریت محصولات*:\nچه کاری می‌خواهید انجام دهید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _discounts_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("➕ ایجاد کد تخفیف", callback_data="discounts_add")],
            [InlineKeyboardButton("📜 لیست کدهای تخفیف", callback_data="discounts_list")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("💸 *مدیریت کدهای تخفیف*:\nچه کاری می‌خواهید انجام دهید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _list_discounts(self, query):
        """Lists all discount codes with simple view."""
        discounts = DatabaseQueries.get_all_discounts()
        if not discounts:
            await query.edit_message_text("هیچ کد تخفیفی یافت نشد.")
            return
        text = "📜 *لیست کدهای تخفیف*:\n"
        keyboard = []
        row = []
        for d in discounts:
            d = dict(d)
            status = "🟢 فعال" if d.get("is_active") else "🔴 غیرفعال"
            text += f"\n• {d.get('code')} ({status})"
            # add button
            row.append(InlineKeyboardButton(d.get('code'), callback_data=f"view_discount_{d.get('id')}") )
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="discounts_menu")])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_single_discount(self, query, discount_id: int):
        d = DatabaseQueries.get_discount_by_id(discount_id) if hasattr(DatabaseQueries, 'get_discount_by_id') else None
        if not d:
            await query.edit_message_text("کد تخفیف یافت نشد.")
            return
        d = dict(d)
        status_text = "فعال 🟢" if d.get("is_active") else "غیرفعال 🔴"
        toggle_text = "🔴 غیرفعال کردن" if d.get("is_active") else "🟢 فعال کردن"
        text = (
            f"جزئیات کد تخفیف {d['code']}\n\n"
            f"شناسه: {d['id']}\n"
            f"نوع: {d['type']}\n"
            f"مقدار: {d['value']}\n"
            f"وضعیت: {status_text}\n"
            f"تاریخ شروع: {d.get('start_date','-')}\n"
            f"تاریخ پایان: {d.get('end_date','-')}\n"
            f"حداکثر استفاده: {d.get('max_uses','-')}\n"
            f"تعداد استفاده: {d.get('uses_count','0')}"
        )
        keyboard = [
            [InlineKeyboardButton(toggle_text, callback_data=f"toggle_discount_{discount_id}")],
            [InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_discount_{discount_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="discounts_list")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

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
        new_status = 0 if d['is_active'] else 1
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
            [InlineKeyboardButton("🔐 تنظیم مدیران", callback_data="settings_admins"), InlineKeyboardButton("⚙️ سایر تنظیمات", callback_data="settings_misc")],
            [InlineKeyboardButton("💸 مدیریت کدهای تخفیف", callback_data="discounts_menu")],
            [InlineKeyboardButton("💾 بکاپ JSON دیتابیس", callback_data=self.BACKUP_CALLBACK)],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("⚙️ *تنظیمات ربات*:\nکدام بخش را می‌خواهید مدیریت کنید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

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

    # ---------- Broadcast content handler ----------
    @admin_only
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        elif context.user_data.get("awaiting_free30_user"):
            term = update.message.text.strip().lstrip("@")
            context.user_data.pop("awaiting_free30_user", None)  # Reset flag

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
                plan_duration_days=30,
                amount_paid=0,
                payment_method="manual_free",
            )

            if not sub_id:
                await update.message.reply_text("❌ خطا در فعال‌سازی اشتراک رایگان برای کاربر.")
                return

            # Notify admin
            await update.message.reply_text(f"✅ اشتراک ۳۰ روزه رایگان برای کاربر `{target_user_id}` با موفقیت فعال شد. در حال ایجاد و ارسال لینک دعوت...", parse_mode="Markdown")

            # Generate and send invite links
            links = await self.invite_link_manager.ensure_one_time_links(target_user_id)
            if not links:
                await update.message.reply_text("❌ خطا در ایجاد لینک‌های دعوت. اشتراک فعال شد اما لینک ارسال نشد.")
                return

            link_message = "🎁 سلام! اشتراک ۳۰ روزه رایگان شما فعال شد.\n\nمی‌توانید از طریق لینک‌های زیر به کانال‌ها و گروه‌های ما بپیوندید:\n"
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

    def get_handlers(self):
        """Return telegram.ext handlers to register in the dispatcher."""
        handlers = [
            CommandHandler("admin", self.show_admin_menu),
            # Handle incoming messages for various flows (only processed when a flag is set)
            MessageHandler(filters.TEXT & (~filters.COMMAND), self.message_handler),
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

        # This is the main handler for all other admin menu callbacks
        # Note: The invite link and ban/unban callbacks are handled by their respective ConversationHandlers.
        handlers.append(CallbackQueryHandler(self.admin_menu_callback, pattern="^(admin_|users_|tickets_|payments_|broadcast_|settings_|products_|view_plan_|toggle_plan_|delete_plan_|confirm_delete_plan_)"))

        return handlers
