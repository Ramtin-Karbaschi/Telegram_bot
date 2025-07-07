from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.decorators import admin_only
from database.db_queries import DatabaseQueries
import logging

logger = logging.getLogger(__name__)

from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler

(ADD_NAME, ADD_PRICE, ADD_DURATION, ADD_DESCRIPTION, ADD_CONFIRMATION) = range(5)
(EDIT_NAME, EDIT_PRICE, EDIT_DURATION, EDIT_DESCRIPTION, EDIT_CONFIRMATION) = range(5, 10)

class AdminProductHandler:
    def __init__(self, admin_config=None):
        self.admin_config = admin_config
        self.db_queries = DatabaseQueries()

    async def _show_all_plans(self, query):
        """Displays a list of all plans with edit and delete buttons."""
        try:
            all_plans = self.db_queries.get_all_plans()
            if not all_plans:
                await query.edit_message_text("هیچ پلنی یافت نشد.")
                return

            keyboard = []
            for plan in all_plans:
                plan = dict(plan)
                plan_id = plan['id']
                plan_name = plan['name']
                # Create a button for each plan
                keyboard.append([InlineKeyboardButton(f"{plan_name}", callback_data=f"view_plan_{plan_id}")])

            keyboard.append([InlineKeyboardButton("➕ افزودن پلن جدید", callback_data="products_add")])
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("📜 *لیست پلن‌ها*:", parse_mode="Markdown", reply_markup=reply_markup)

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
        context.user_data['new_plan_price'] = float(update.message.text)
        await update.message.reply_text("مدت زمان پلن را به روز وارد کنید:")
        return ADD_DURATION

    async def get_plan_duration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['new_plan_duration'] = int(update.message.text)
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
        query = update.callback_query
        await query.answer()
        plan_data = context.user_data
        self.db_queries.add_plan(
            name=plan_data['new_plan_name'],
            price=plan_data['new_plan_price'],
            duration_days=plan_data['new_plan_duration'],
            description=plan_data['new_plan_description']
        )
        await query.edit_message_text("پلن با موفقیت اضافه شد.")
        # End conversation
        context.user_data.clear()
        # Show the updated list of plans
        await self._show_all_plans(query, is_new_message=False)
        return ConversationHandler.END

    async def _show_single_plan(self, query: Update.callback_query, plan_id: int):
        """Shows details for a single plan with action buttons."""
        try:
            plan = self.db_queries.get_plan_by_id(plan_id)
            if not plan:
                await query.edit_message_text("پلن مورد نظر یافت نشد.")
                return

            plan = dict(plan)
            status_text = "فعال 🟢" if plan['is_active'] else "غیرفعال 🔴"
            toggle_button_text = "🔴 غیرفعال کردن" if plan['is_active'] else "🟢 فعال کردن"

            text = (
                f"جزئیات پلن: {plan['name']}\n\n"
                f"شناسه: {plan['id']}\n"
                f"قیمت: {plan['price']} تومان\n"
                f"مدت: {plan['duration_days']} روز\n"
                f"وضعیت: {status_text}\n"
                f"توضیحات: {plan.get('description', 'ندارد')}"
            )

            keyboard = [
                [InlineKeyboardButton(toggle_button_text, callback_data=f"toggle_plan_{plan_id}")],
                [
                    InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_plan_{plan_id}"),
                    InlineKeyboardButton("✏️ ویرایش", callback_data=f"edit_plan_{plan_id}")
                ],
                [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="products_list")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error showing single plan {plan_id}: {e}")
            await query.edit_message_text("خطا در نمایش جزئیات پلن.")

    async def toggle_plan_status(self, query: Update.callback_query, plan_id: int):
        """Toggles the is_active status of a plan."""
        try:
            plan = self.db_queries.get_plan_by_id(plan_id)
            if not plan:
                await query.edit_message_text("پلن مورد نظر یافت نشد.")
                return

            new_status = not plan['is_active']
            self.db_queries.update_plan(plan_id, is_active=new_status)
            await query.answer(f"وضعیت پلن به {'فعال' if new_status else 'غیرفعال'} تغییر یافت.")
            # Refresh the view
            await self._show_single_plan(query, plan_id)
        except Exception as e:
            logger.error(f"Error toggling status for plan {plan_id}: {e}")
            await query.edit_message_text("خطا در تغییر وضعیت پلن.")

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
            context.user_data['edit_plan_price'] = float(update.message.text)
        await update.message.reply_text("لطفاً مدت زمان جدید را به روز وارد کنید (برای رد شدن، /skip را بزنید):")
        return EDIT_DURATION

    async def get_new_plan_duration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text != '/skip':
            context.user_data['edit_plan_duration'] = int(update.message.text)
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

    def get_handlers(self):
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
