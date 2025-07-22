"""AdminCategoryHandler: manage product category tree via Telegram inline keyboards."""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

import logging
from database.queries import DatabaseQueries
from utils.helpers import admin_only_decorator as admin_only, safe_edit_message_text

logger = logging.getLogger(__name__)

# Conversation states
NAVIGATE, ADD_NAME, RENAME_NAME, DELETE_CONFIRM = range(4)

class AdminCategoryHandler:
    def __init__(self, db_queries: DatabaseQueries | None = None, admin_config: list | dict | None = None):
        """Conversation handler for managing product categories.

        Parameters
        ----------
        db_queries: DatabaseQueries | None
            Optional custom DBQueries instance (mainly for testing).
        admin_config: list | dict | None
            The same admin users configuration structure that `admin_only_decorator` expects.
        """
        self.db = db_queries or DatabaseQueries()
        # Save admin configuration so that @admin_only decorator can validate permissions
        self.admin_config = admin_config

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------
    @admin_only
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show root categories."""
        return await self._show_children(update, context, parent_id=None)

    # ------------------------------------------------------------------
    # Navigation helpers
    # ------------------------------------------------------------------
    async def _show_children(self, update: Update, context: ContextTypes.DEFAULT_TYPE, parent_id: int | None):
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            sender = query
        else:
            sender = update
        cats = self.db.get_children_categories(parent_id)
        keyboard: list[list[InlineKeyboardButton]] = []
        for c in cats:
            keyboard.append([
                InlineKeyboardButton(f"📂 {c['name']}", callback_data=f"cat_{c['id']}")
            ])
        # management buttons
        if parent_id is not None:
            keyboard.append([
                InlineKeyboardButton("➕ افزودن زیر‌دسته", callback_data=f"add_{parent_id}"),
                InlineKeyboardButton("✏️ ویرایش", callback_data=f"ren_{parent_id}"),
                InlineKeyboardButton("🗑 حذف", callback_data=f"del_{parent_id}"),
            ])
            keyboard.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="back")])
        else:
            keyboard.append([InlineKeyboardButton("➕ افزودن دسته جدید", callback_data="add_root")])
        markup = InlineKeyboardMarkup(keyboard)
        text = "لطفاً دسته مورد نظر را انتخاب کنید یا عملیات مد نظر را انجام دهید."
        if update.callback_query:
            await safe_edit_message_text(query, text=text, reply_markup=markup)
        else:
            await sender.message.reply_text(text, reply_markup=markup)
        context.user_data["cat_parent"] = parent_id
        return NAVIGATE

    async def _navigate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data = query.data
        if data == "back":
            parent = context.user_data.get("cat_parent")
            if parent is None:
                # already root
                await self._show_children(update, context, None)
                return NAVIGATE
            # fetch grand-parent
            parent_row = self.db.get_category_by_id(parent)
            grand = parent_row["parent_id"] if parent_row else None
            return await self._show_children(update, context, grand)
        if data.startswith("cat_"):
            cat_id = int(data.split("_", 1)[1])
            return await self._show_children(update, context, parent_id=cat_id)
        if data.startswith("add_"):
            parent_id = None if data == "add_root" else int(data.split("_", 1)[1])
            context.user_data["cat_add_parent"] = parent_id
            await query.answer()
            await query.message.reply_text("نام دسته جدید را وارد کنید:")
            return ADD_NAME
        if data.startswith("ren_"):
            cat_id = int(data.split("_", 1)[1])
            context.user_data["cat_rename_id"] = cat_id
            await query.answer()
            await query.message.reply_text("نام جدید را وارد کنید:")
            return RENAME_NAME
        if data.startswith("del_"):
            cat_id = int(data.split("_", 1)[1])
            context.user_data["cat_delete_id"] = cat_id
            await query.answer()
            await query.message.reply_text("از حذف مطمئن هستید؟ (yes/no)")
            return DELETE_CONFIRM
        await query.answer()
        return NAVIGATE

    # ------------------------------------------------------------------
    # Add category
    # ------------------------------------------------------------------
    async def _add_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        name = update.message.text.strip()
        parent_id = context.user_data.get("cat_add_parent")
        new_id = self.db.create_category(name, parent_id)
        if new_id:
            await update.message.reply_text("✅ دسته افزوده شد.")
        else:
            await update.message.reply_text("❌ افزودن با خطا مواجه شد.")
        return await self._show_children(update, context, parent_id)

    # ------------------------------------------------------------------
    # Rename category
    # ------------------------------------------------------------------
    async def _rename(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        new_name = update.message.text.strip()
        cat_id = context.user_data.get("cat_rename_id")
        ok = self.db.update_category(cat_id, name=new_name)
        await update.message.reply_text("✅ بروزرسانی شد." if ok else "❌ خطا در بروزرسانی.")
        parent = self.db.get_category_by_id(cat_id)["parent_id"] if cat_id else None
        return await self._show_children(update, context, parent)

    # ------------------------------------------------------------------
    # Delete category
    # ------------------------------------------------------------------
    async def _delete_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip().lower()
        cat_id = context.user_data.get("cat_delete_id")
        parent = self.db.get_category_by_id(cat_id)["parent_id"] if cat_id else None
        if text == "yes" or text == "بله":
            ok = self.db.delete_category(cat_id)
            await update.message.reply_text("✅ حذف شد." if ok else "❌ امکان حذف نیست.")
        else:
            await update.message.reply_text("حذف لغو شد.")
        return await self._show_children(update, context, parent)

    # ------------------------------------------------------------------
    # Conversation handler factory
    # ------------------------------------------------------------------
    def get_conv_handler(self):
        return ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start, pattern="^manage_categories$"), CommandHandler("categories", self.start)],
            states={
                NAVIGATE: [CallbackQueryHandler(self._navigate)],
                ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._add_name)],
                RENAME_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._rename)],
                DELETE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._delete_confirm)],
            },
            fallbacks=[CommandHandler("cancel", self.start)],
            per_user=True,
            per_chat=True,
        )
