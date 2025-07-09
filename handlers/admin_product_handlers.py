from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.helpers import admin_only_decorator as admin_only
from database.queries import DatabaseQueries
import logging

logger = logging.getLogger(__name__)

from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler

(ADD_NAME, ADD_PRICE, ADD_DURATION, ADD_DESCRIPTION, ADD_CONFIRMATION) = range(5)
(EDIT_NAME, EDIT_PRICE, EDIT_DURATION, EDIT_DESCRIPTION, EDIT_CONFIRMATION) = range(5, 10)

class AdminProductHandler:
    def __init__(self, db_queries: DatabaseQueries, admin_config=None):
        """Handler for managing product plans.

        Parameters
        ----------
        db_queries : DatabaseQueries
            An already-initialized DatabaseQueries instance bound to the shared
            database connection. This avoids creating multiple connections and
            matches new constructor signature of DatabaseQueries.
        admin_config : optional
            Optional admin configuration dict if additional settings are
            required.
        """
        self.db_queries = db_queries
        self.admin_config = admin_config

    async def _show_all_plans(self, query):
        """Displays a list of all plans with their status to admins."""
        try:
            # Fetch all plans, including inactive/private ones, for admin view
            all_plans = self.db_queries.get_all_plans()
            if not all_plans:
                await query.edit_message_text("هیچ پلنی یافت نشد.")
                return

            keyboard = []
            for plan in all_plans:
                plan = dict(plan)
                plan_id = plan['id']
                plan_name = plan['name']
                status_emoji = "✅" if plan.get('is_active', False) else "❌"
                visibility_emoji = "🌍" if plan.get('is_public', False) else "🔒"
                
                button_text = f"{plan_name} [{status_emoji} فعال, {visibility_emoji} عمومی]"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_plan_{plan_id}")])

            keyboard.append([InlineKeyboardButton("➕ افزودن پلن جدید", callback_data="products_add")])
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("📜 *مدیریت پلن‌ها*:", parse_mode="Markdown", reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error showing all plans: {e}")
            await query.edit_message_text("خطا در نمایش لیست پلن‌ها.")

    async def add_plan_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Starts the conversation to add a new plan."""
        await update.callback_query.message.reply_text("لطفاً نام پلن جدید را وارد کنید:")
        return ADD_NAME

    async def get_plan_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['new_plan_name'] = update.message.text
        await update.message.reply_text("لطفاً قیمت پلن را به تومان وارد کنید:")
        return ADD_PRICE

    async def get_plan_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from utils.locale_utils import to_float
        context.user_data['new_plan_price'] = to_float(update.message.text)
        await update.message.reply_text("مدت زمان پلن را به روز وارد کنید:")
        return ADD_DURATION

    async def get_plan_duration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from utils.locale_utils import to_int
        context.user_data['new_plan_duration'] = to_int(update.message.text)
        await update.message.reply_text("توضیحات پلن را وارد کنید (اختیاری):")
        return ADD_DESCRIPTION

    async def get_plan_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['new_plan_description'] = update.message.text
        # Show confirmation
        plan_data = context.user_data
        text = (
            f"آیا از افزودن پلن زیر اطمینان دارید؟\n\n"
            f"نام: {plan_data['new_plan_name']}\n"
            f"قیمت: {plan_data['new_plan_price']} تومان\n"
            f"مدت: {plan_data['new_plan_duration']} روز\n"
            f"توضیحات: {plan_data['new_plan_description']}"
        )
        keyboard = [[InlineKeyboardButton("✅ تایید و افزودن", callback_data="confirm_add_plan"), InlineKeyboardButton("❌ لغو", callback_data="cancel_add_plan")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return ADD_CONFIRMATION

    async def save_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        plan_data = context.user_data
        name = plan_data['new_plan_name']
        
        # By default, plans are active and public
        is_active = True
        is_public = True
        
        # Special case for 'free_30d' plan to be private by default
        if name == 'free_30d':
            is_public = False

        plan_id = self.db_queries.add_plan(
            name=name,
            price=plan_data['new_plan_price'],
            duration_days=plan_data['new_plan_duration'],
            description=plan_data['new_plan_description'],
            is_active=is_active,
            is_public=is_public
        )
        query = update.callback_query
        await query.answer("پلن با موفقیت افزوده شد.")
        await self._show_all_plans(query)
        context.user_data.clear()
        return ConversationHandler.END

    async def handle_show_all_plans(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await self._show_all_plans(query)

    async def handle_view_single_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        plan_id = int(query.data.split('_')[-1])
        await query.answer()
        await self._show_single_plan(query, plan_id)

    async def _show_single_plan(self, query: Update.callback_query, plan_id: int):
        """Shows details for a single plan with enhanced action buttons."""
        try:
            plan = self.db_queries.get_plan_by_id(plan_id)
            if not plan:
                await query.edit_message_text("پلن مورد نظر یافت نشد.")
                return

            plan = dict(plan)
            is_active = plan.get('is_active', False)
            is_public = plan.get('is_public', False)

            status_text = "فعال" if is_active else "غیرفعال"
            public_text = "عمومی" if is_public else "خصوصی (فقط ادمین)"

            text = (
                f"*جزئیات پلن: {plan['name']}*\n\n"
                f"*قیمت:* {plan['price']} تومان\n"
                f"*مدت:* {plan['duration_days']} روز\n"
                f"*توضیحات:* {plan.get('description', 'ندارد')}\n"
                f"*وضعیت:* {status_text}\n"
                f"*نمایش:* {public_text}"
            )

            toggle_active_text = " غیرفعال کردن" if is_active else "✅ فعال کردن"
            toggle_public_text = "🔒 خصوصی کردن" if is_public else "🌍 عمومی کردن"

            keyboard = [
                [InlineKeyboardButton(f"✏️ ویرایش", callback_data=f"edit_plan_{plan_id}"),
                 InlineKeyboardButton(f"🗑 حذف", callback_data=f"delete_plan_confirm_{plan_id}")],
                [InlineKeyboardButton(toggle_active_text, callback_data=f"toggle_plan_active_{plan_id}")],
                [InlineKeyboardButton(toggle_public_text, callback_data=f"toggle_plan_public_{plan_id}")],
                [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="products_show_all")]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error showing single plan {plan_id}: {e}")
            await query.edit_message_text("خطا در نمایش جزئیات پلن.")

    async def handle_toggle_plan_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        plan_id = int(query.data.split('_')[-1])
        await self.toggle_plan_status(query, plan_id)

    async def toggle_plan_status(self, query: Update.callback_query, plan_id: int):
        """Toggles the is_active status of a plan."""
        try:
            success = self.db_queries.set_plan_activation(plan_id)
            if not success:
                await query.answer("خطا: پلن یافت نشد یا وضعیت تغییر نکرد.", show_alert=True)
                return

            await query.answer("وضعیت فعال‌سازی پلن با موفقیت تغییر کرد.")
            await self._show_single_plan(query, plan_id) # Refresh the view
        except Exception as e:
            logger.error(f"Error toggling plan status for {plan_id}: {e}")
            await query.edit_message_text("خطا در تغییر وضعیت پلن.")

    async def handle_toggle_plan_visibility(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        plan_id = int(query.data.split('_')[-1])
        await self.toggle_plan_visibility(query, plan_id)

    async def toggle_plan_visibility(self, query: Update.callback_query, plan_id: int):
        """Toggles the is_public status of a plan."""
        try:
            success = self.db_queries.set_plan_visibility(plan_id)
            if not success:
                await query.answer("خطا: پلن یافت نشد یا وضعیت تغییر نکرد.", show_alert=True)
                return

            await query.answer("وضعیت نمایش پلن با موفقیت تغییر کرد.")
            await self._show_single_plan(query, plan_id) # Refresh the view
        except Exception as e:
            logger.error(f"Error toggling plan visibility for {plan_id}: {e}")
            await query.edit_message_text("خطا در تغییر وضعیت نمایش پلن.")

    async def delete_plan_confirmation(self, query: Update.callback_query, plan_id: int):
        """Asks for confirmation before deleting a plan."""
        keyboard = [
            [InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"confirm_delete_plan_{plan_id}")],
            [InlineKeyboardButton("❌ خیر، بازگشت", callback_data=f"view_plan_{plan_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("⚠️ آیا از حذف این پلن اطمینان دارید؟ این عمل غیرقابل بازگشت است.", reply_markup=reply_markup)

    # --- Edit Plan Conversation --- #

    async def edit_plan_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        plan_id = int(query.data.split("_")[2])
        context.user_data['edit_plan_id'] = plan_id
        await query.message.reply_text("لطفاً نام جدید پلن را وارد کنید (برای رد شدن، /skip را بزنید):")
        return EDIT_NAME

    async def get_new_plan_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text != '/skip':
            context.user_data['edit_plan_name'] = update.message.text
        await update.message.reply_text("لطفاً قیمت جدید را وارد کنید (برای رد شدن، /skip را بزنید):")
        return EDIT_PRICE

    async def get_new_plan_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text != '/skip':
            from utils.locale_utils import to_float
            context.user_data['edit_plan_price'] = to_float(update.message.text)
        await update.message.reply_text("لطفاً مدت زمان جدید را به روز وارد کنید (برای رد شدن، /skip را بزنید):")
        return EDIT_DURATION

    async def get_new_plan_duration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text != '/skip':
            from utils.locale_utils import to_int
            context.user_data['edit_plan_duration'] = to_int(update.message.text)
        await update.message.reply_text("لطفاً توضیحات جدید را وارد کنید (برای رد شدن، /skip را بزنید):")
        return EDIT_DESCRIPTION

    async def get_new_plan_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text != '/skip':
            context.user_data['edit_plan_description'] = update.message.text
        
        # Show confirmation
        plan_id = context.user_data['edit_plan_id']
        original_plan = dict(self.db_queries.get_plan_by_id(plan_id))
        
        updated_data = {
            'name': context.user_data.get('edit_plan_name', original_plan['name']),
            'price': context.user_data.get('edit_plan_price', original_plan['price']),
            'duration_days': context.user_data.get('edit_plan_duration', original_plan['duration_days']),
            'description': context.user_data.get('edit_plan_description', original_plan['description'])
        }

        text = (
            f"آیا از اعمال تغییرات زیر اطمینان دارید؟\n\n"
            f"نام: {updated_data['name']}\n"
            f"قیمت: {updated_data['price']} تومان\n"
            f"مدت: {updated_data['duration_days']} روز\n"
            f"توضیحات: {updated_data['description']}"
        )
        keyboard = [[InlineKeyboardButton("✅ تایید و ذخیره", callback_data="confirm_edit_plan"), InlineKeyboardButton("❌ لغو", callback_data="cancel_edit_plan")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return EDIT_CONFIRMATION

    async def update_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        plan_id = context.user_data['edit_plan_id']
        update_kwargs = {
            'name': context.user_data.get('edit_plan_name'),
            'price': context.user_data.get('edit_plan_price'),
            'duration_days': context.user_data.get('edit_plan_duration'),
            'description': context.user_data.get('edit_plan_description'),
        }
        # Filter out None values
        update_kwargs = {k: v for k, v in update_kwargs.items() if v is not None}

        if update_kwargs:
            self.db_queries.update_plan(plan_id, **update_kwargs)
            await query.edit_message_text("پلن با موفقیت ویرایش شد.")
        else:
            await query.edit_message_text("هیچ تغییری اعمال نشد.")

        context.user_data.clear()
        await self._show_single_plan(query, plan_id)
        return ConversationHandler.END

    async def cancel_edit_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        plan_id = context.user_data.get('edit_plan_id')
        await query.edit_message_text("عملیات ویرایش لغو شد.")
        context.user_data.clear()
        if plan_id:
            await self._show_single_plan(query, plan_id)
        return ConversationHandler.END

    async def delete_plan(self, query: Update.callback_query, plan_id: int):
        """Deletes a plan after confirmation."""
        try:
            self.db_queries.delete_plan(plan_id)
            await query.answer("پلن با موفقیت حذف شد.")
            # Go back to the list
            await self._show_all_plans(query)
        except Exception as e:
            logger.error(f"Error deleting plan {plan_id}: {e}")
            await query.edit_message_text("خطا در حذف پلن.")

    async def cancel_add_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.edit_message_text("عملیات افزودن پلن لغو شد.")
        context.user_data.clear()
        return ConversationHandler.END

    def get_static_product_handlers(self):
        return [
            CallbackQueryHandler(self.handle_show_all_plans, pattern='^products_show_all$'),
            CallbackQueryHandler(self.handle_view_single_plan, pattern='^view_plan_'),
            CallbackQueryHandler(self.handle_toggle_plan_status, pattern='^toggle_plan_active_'),
            CallbackQueryHandler(self.handle_toggle_plan_visibility, pattern='^toggle_plan_public_'),
            CallbackQueryHandler(self.delete_plan_confirmation, pattern='^delete_plan_confirm_'),
            CallbackQueryHandler(self.delete_plan, pattern='^delete_plan_execute_')
        ]

    def get_product_conv_handlers(self):
        add_plan_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.add_plan_start, pattern='^products_add$')],
            states={
                ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plan_name)],
                ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plan_price)],
                ADD_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plan_duration)],
                ADD_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plan_description)],
                ADD_CONFIRMATION: [
                    CallbackQueryHandler(self.save_plan, pattern='^confirm_add_plan$'),
                    CallbackQueryHandler(self.cancel_add_plan, pattern='^cancel_add_plan$')
                ]
            },
            fallbacks=[CallbackQueryHandler(self.cancel_add_plan, pattern='^cancel_add_plan$')],
            per_user=True,
            per_chat=True,
        )

        edit_plan_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.edit_plan_start, pattern='^edit_plan_')],
            states={
                EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_new_plan_name)],
                EDIT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_new_plan_price)],
                EDIT_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_new_plan_duration)],
                EDIT_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_new_plan_description)],
                EDIT_CONFIRMATION: [
                    CallbackQueryHandler(self.update_plan, pattern='^confirm_edit_plan$'),
                    CallbackQueryHandler(self.cancel_edit_plan, pattern='^cancel_edit_plan$')
                ]
            },
            fallbacks=[CallbackQueryHandler(self.cancel_edit_plan, pattern='^cancel_edit_plan$')],
            per_user=True,
            per_chat=True,
        )

        return [add_plan_handler, edit_plan_handler]
