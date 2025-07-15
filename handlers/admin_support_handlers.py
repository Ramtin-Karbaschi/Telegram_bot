"""Handlers for managing support users (پشتیبان) by admins.

Only full admins (manager_bot_admin role) can add or remove support users.
Support users get limited access (ticket handling & payment verification).
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters

from utils.helpers import admin_only_decorator as admin_only
from database.queries import DatabaseQueries
import logging

logger = logging.getLogger(__name__)


ASK_NEW_SUPPORT_ID = range(1)

class SupportUserManager:
    """Provide commands for listing / adding / removing support users."""

    def __init__(self, admin_config=None):
        # Save admin list for permission checks used by @admin_only decorator
        from config import MANAGER_BOT_ADMINS_DICT
        if admin_config is None:
            # fallback to config constant: a dict {chat_id: alias}. Convert to list of ids for decorator.
            admin_config = list(MANAGER_BOT_ADMINS_DICT.keys())
        self.admin_config = admin_config

    # ---------- Public commands ----------

    @admin_only
    async def list_support_users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/support_users – show current list with inline remove buttons"""
        users = DatabaseQueries.get_all_support_users()
        if not users:
            await update.message.reply_text("👥 هیچ کاربر پشتیبانی تعریف نشده است.")
            return
        text = "👥 لیست کاربران پشتیبان:\n\n"
        keyboard = []
        for row in users:
            tg_id = row[0] if isinstance(row, (list, tuple)) else row.get("telegram_id")
            added_at = row[2] if isinstance(row, (list, tuple)) else row.get("added_at")
            text += f"• {tg_id} – {added_at}\n"
            keyboard.append([InlineKeyboardButton(f"❌ حذف {tg_id}", callback_data=f"remove_support_{tg_id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)

    @admin_only
    async def add_support_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/addsupport – ask admin for Telegram ID to add"""
        await update.message.reply_text("لطفاً آیدی عددی تلگرام کاربر پشتیبان را ارسال کنید:")
        return ASK_NEW_SUPPORT_ID

    async def _receive_support_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle numeric ID input and add support user"""
        try:
            tg_id_str = update.message.text.strip()
            tg_id = int(tg_id_str)
        except ValueError:
            await update.message.reply_text("فرمت آیدی نامعتبر است. دوباره تلاش کنید یا /cancel.")
            return ASK_NEW_SUPPORT_ID
        admin_id = update.effective_user.id
        if DatabaseQueries.add_support_user(tg_id, added_by=admin_id):
            await update.message.reply_text(f"✅ کاربر {tg_id} به عنوان پشتیبان ثبت شد.")
        else:
            await update.message.reply_text("❌ خطا در افزودن کاربر یا کاربر قبلاً وجود دارد.")
        return ConversationHandler.END

    @admin_only
    async def remove_support_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Inline button handler to remove support user"""
        query = update.callback_query
        await query.answer()
        tg_id = int(query.data.split("_")[-1])
        if DatabaseQueries.remove_support_user(tg_id):
            await query.edit_message_text(f"کاربر {tg_id} حذف شد.")
        else:
            await query.answer("خطا در حذف کاربر.", show_alert=True)

    # ---------- helper ----------
    def get_handlers(self):
        """Return list of handlers to register"""
        return [
            CommandHandler("support_users", self.list_support_users_command),
            CommandHandler("addsupport", self.add_support_command),
            CallbackQueryHandler(self.remove_support_callback, pattern=r"^remove_support_\d+$"),
            ConversationHandler(
                entry_points=[CommandHandler("addsupport", self.add_support_command)],
                states={
                    ASK_NEW_SUPPORT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._receive_support_id)],
                },
                fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
                per_user=True,
                per_chat=True,
            ),
        ]
