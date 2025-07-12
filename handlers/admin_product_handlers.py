from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.price_utils import get_usdt_to_irr_rate
from utils.helpers import admin_only_decorator as admin_only
from database.queries import DatabaseQueries
import logging
from typing import Any
import telegram  # Needed for telegram.error.BadRequest

logger = logging.getLogger(__name__)

from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# Adding capacity states
# Conversation state definitions
# Add \u0026 Edit flows share a common FIELD_VALUE state for entering arbitrary field values
(
    ADD_NAME, ADD_PRICE, ADD_DURATION, ADD_CAPACITY, ADD_DESCRIPTION, ADD_CONFIRMATION,
    EDIT_NAME, EDIT_PRICE, EDIT_DURATION, EDIT_CAPACITY, EDIT_DESCRIPTION, EDIT_CONFIRMATION,
    FIELD_VALUE,
) = range(13)

class AdminProductHandler:
    async def _handle_fields_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle back button from the extra-fields menu.

        Behaviour depends on the current extra_mode:
        • add  -> abort extra-fields editing and go back to add confirmation screen (or cancel if no confirmation yet).
        • edit -> return to edit confirmation screen so admin can review changes.
        """
        query = update.callback_query
        await query.answer()
        mode = context.user_data.get('extra_mode', 'add')

        if mode == 'add':
            # If add flow was started from confirmation step, we can re-show it; otherwise cancel.
            if 'new_plan_name' in context.user_data:
                # Recreate the confirmation step similar to _handle_fields_done (but without finishing)
                plan_data = context.user_data
                usdt_price = plan_data.get('new_plan_price_usdt')
                irr_price = None
                if usdt_price is not None:
                    usdt_rate = await get_usdt_to_irr_rate()
                    if usdt_rate:
                        irr_price = int(usdt_price * usdt_rate * 10)

                price_line = f"قیمت: {usdt_price} USDT" if usdt_price is not None else "قیمت: تعیین نشده"
                if irr_price is not None:
                    price_line += f"  (~{irr_price:,} ریال)"

                text = (
                    "🔖 *تایید اطلاعات پلن:*\n\n"
                    f"نام: {plan_data.get('new_plan_name', '—')}\n"
                    f"{price_line}\n"
                    f"مدت: {plan_data.get('new_plan_duration', '—')} روز\n"
                    f"ظرفیت: {plan_data.get('new_plan_capacity', 'نامحدود')}\n"
                    f"توضیحات: {plan_data.get('new_plan_description', '—')}"
                )
                keyboard = [[
                    InlineKeyboardButton("✅ تایید و افزودن", callback_data="confirm_add_plan"),
                    InlineKeyboardButton("⚙️ تنظیم سایر فیلدها", callback_data="add_more_fields"),
                    InlineKeyboardButton("❌ لغو", callback_data="cancel_add_plan")
                ]]
                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                return ADD_CONFIRMATION
            else:
                # No data yet – treat as cancel
                await self.cancel_add_plan(update, context)
                return ConversationHandler.END
        else:
            # edit mode – show edit confirmation similar to _handle_fields_done
            await self._handle_fields_done(update, context)
            return EDIT_CONFIRMATION


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
        """Starts adding a new plan by opening the selective field menu instead of a linear prompt."""
        query = update.callback_query
        # Clear any previous temp data and mark mode
        context.user_data.clear()
        context.user_data['extra_mode'] = 'add'
        # Show interactive field-selection menu
        await self._show_fields_menu(query, context, mode="add")
        return FIELD_VALUE

    async def get_plan_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['new_plan_name'] = update.message.text
        await update.message.reply_text("لطفاً قیمت پلن را به تتر (USDT) وارد کنید:")
        return ADD_PRICE

    async def get_plan_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Collects the plan price in USDT and validates the numeric input."""
        from utils.locale_utils import to_float
        try:
            context.user_data['new_plan_price_usdt'] = to_float(update.message.text)
        except (ValueError, TypeError):
            await update.message.reply_text("❌ مقدار وارد شده معتبر نیست. لطفاً مبلغ را به عدد (مثلاً 10.5) وارد کنید یا /skip بزنید.")
            return ADD_PRICE

        await update.message.reply_text("مدت زمان پلن را به روز وارد کنید:")
        return ADD_DURATION

    async def get_plan_duration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from utils.locale_utils import to_int
        context.user_data['new_plan_duration'] = to_int(update.message.text)
        await update.message.reply_text("ظرفیت فروش (تعداد مجاز) را وارد کنید:")
        return ADD_CAPACITY

    async def _parse_capacity_input(self, text: str):
        """Helper to interpret capacity input; returns int or None (for unlimited)."""
        text = text.strip().lower()
        if text in {'نامحدود', 'unlimited', '-', '', '∞'}:
            return None
        try:
            from utils.locale_utils import to_int
            val = to_int(text)
            if val == 0:
                return None
            return val
        except Exception:
            return None

    async def get_plan_capacity(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Allow admin to send /skip or words indicating unlimited
        if update.message.text == '/skip':
            capacity_val = None
        else:
            capacity_val = await self._parse_capacity_input(update.message.text)
        context.user_data['new_plan_capacity'] = capacity_val
        await update.message.reply_text("توضیحات پلن را وارد کنید (اختیاری):")
        return ADD_DESCRIPTION

    # ---------------------------- Extra-field helper methods ---------------------------- #
    _PLAN_FIELD_LABELS: dict[str, str] = {
        "price": "قیمت ریالی (price)",
        "original_price_irr": "قیمت ریالی اصلی",
        "price_tether": "قیمت تتر (USDT)",
        "original_price_usdt": "قیمت تتر اصلی",
        "duration_days": "مدت (روز)",
        "capacity": "ظرفیت",
        "features": "ویژگی‌ها (JSON)",
        "plan_type": "نوع پلن",
        "expiration_date": "تاریخ انقضا (YYYY-MM-DD)",
        "fixed_end_date": "تاریخ پایان ثابت (YYYY-MM-DD)",
        "display_order": "ترتیب نمایش",
        "is_active": "فعال؟ (1/0)",
        "is_public": "عمومی؟ (1/0)",
    }

    def _build_fields_keyboard(self, context: ContextTypes.DEFAULT_TYPE, mode: str) -> InlineKeyboardMarkup:
        """Return an inline keyboard with <=3 buttons per row for all editable plan columns.
        Each button shows a tick if that field already has a value in the current user_data.
        """
        buttons: list[list[InlineKeyboardButton]] = []
        row: list[InlineKeyboardButton] = []
        for idx, (field, label) in enumerate(self._PLAN_FIELD_LABELS.items(), start=1):
            prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
            value_exists = context.user_data.get(f"{prefix}{field}") is not None
            label_with_tick = ("✅ " if value_exists else "▫️ ") + label
            row.append(InlineKeyboardButton(label_with_tick, callback_data=f"set_field_{field}"))
            if idx % 3 == 0:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        # control buttons
        buttons.append([
            InlineKeyboardButton("✅ اتمام", callback_data="fields_done"),
            InlineKeyboardButton("🔙 بازگشت", callback_data="fields_back")
        ])
        return InlineKeyboardMarkup(buttons)


    async def _show_fields_menu(self, query, context: ContextTypes.DEFAULT_TYPE, mode: str):
        """Show the menu for selecting which additional field to set (add/edit)."""
        context.user_data['extra_mode'] = mode  # 'add' or 'edit'
        text = (
            self._generate_summary_text(context, mode)
            + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
        )
        reply_markup = self._build_fields_keyboard(context, mode)
        try:
            await query.edit_message_text(text, reply_markup=reply_markup)
        except telegram.error.BadRequest as e:
            # Ignore harmless error when content is identical to current message
            if "Message is not modified" not in str(e):
                raise

    def _generate_summary_text(self, context: ContextTypes.DEFAULT_TYPE, mode: str) -> str:
        """Build a Persian summary of all currently filled fields for the admin."""
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        lines: list[str] = ["— وضعیت مقادیر فعلی —"]
        for field, label in self._PLAN_FIELD_LABELS.items():
            val = context.user_data.get(f"{prefix}{field}")
            emoji = "✅" if val is not None else "▫️"
            show_val = val if val is not None else "—"
            lines.append(f"{emoji} {label}: {show_val}")
        return "\n".join(lines)

    async def _prompt_for_field_value(self, query: Update.callback_query, field_key: str):
        label = self._PLAN_FIELD_LABELS.get(field_key, field_key)
        await query.edit_message_text(f"مقدار جدید برای «{label}» را وارد کنید:")

    # ---------------------------- Existing methods ---------------------------- #

    async def get_plan_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Collect description and show confirmation with USDT & IRR prices."""
        context.user_data['new_plan_description'] = update.message.text
        plan_data = context.user_data

        usdt_price: float | None = plan_data.get('new_plan_price_usdt')
        irr_price: int | None = None
        if usdt_price is not None:
            usdt_rate = await get_usdt_to_irr_rate()
            if usdt_rate:
                irr_price = int(usdt_price * usdt_rate * 10)  # toman→rial

        price_line = f"قیمت: {usdt_price} USDT" if usdt_price is not None else "قیمت مشخص نشده"
        if irr_price is not None:
            price_line += f" (~{irr_price:,} ریال)"
        text = (
            f"آیا از افزودن پلن زیر اطمینان دارید؟\n\n"
            f"نام: {plan_data['new_plan_name']}\n"
            f"{price_line}\n"
            f"مدت: {plan_data['new_plan_duration']} روز\n"
            f"ظرفیت: {plan_data.get('new_plan_capacity', 'نامحدود')}\n"
            f"توضیحات: {plan_data['new_plan_description']}"
        )
        keyboard = [[
        InlineKeyboardButton("✅ تایید و افزودن", callback_data="confirm_add_plan"),
        InlineKeyboardButton("⚙️ تنظیم سایر فیلدها", callback_data="add_more_fields"),
        InlineKeyboardButton("❌ لغو", callback_data="cancel_add_plan")
    ]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return ADD_CONFIRMATION

    async def _handle_fields_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """User finished editing extra fields; show confirmation again."""
        query = update.callback_query
        await query.answer()
        mode = context.user_data.get('extra_mode')
        if mode == 'add':
            # regenerate confirmation similar to get_plan_description but using existing data
            plan_data = context.user_data
            usdt_price = plan_data.get('new_plan_price_usdt')
            irr_price = None
            if usdt_price is not None:
                usdt_rate = await get_usdt_to_irr_rate()
                if usdt_rate:
                    irr_price = int(usdt_price * usdt_rate * 10)
            price_line = f"قیمت: {usdt_price} USDT" if usdt_price is not None else "قیمت مشخص نشده"
            if irr_price is not None:
                price_line += f" (~{irr_price:,} ریال)"
            text = (
                f"آیا از افزودن پلن زیر اطمینان دارید؟\n\n"
                f"نام: {plan_data.get('new_plan_name')}\n"
                f"{price_line}\n"
                f"مدت: {plan_data.get('new_plan_duration')} روز\n"
                f"ظرفیت: {plan_data.get('new_plan_capacity', 'نامحدود')}\n"
                f"توضیحات: {plan_data.get('new_plan_description')}"
            )
            keyboard = [[
                InlineKeyboardButton("✅ تایید و افزودن", callback_data="confirm_add_plan"),
                InlineKeyboardButton("⚙️ تنظیم سایر فیلدها", callback_data="add_more_fields"),
                InlineKeyboardButton("❌ لغو", callback_data="cancel_add_plan")
            ]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ADD_CONFIRMATION
        else:
            # Build confirmation summary for edit flow
            plan_id = context.user_data.get('edit_plan_id')
            original_plan = dict(self.db_queries.get_plan_by_id(plan_id)) if plan_id else {}

            # Helper to fetch updated value or fallback to original
            def val(key, orig_key):
                return context.user_data.get(f'edit_plan_{key}', original_plan.get(orig_key))

            name = val('name', 'name')
            usdt_price = context.user_data.get('edit_plan_price_usdt', original_plan.get('price_tether'))
            irr_price_line = ""
            if usdt_price is not None:
                usdt_rate = await get_usdt_to_irr_rate()
                if usdt_rate:
                    irr_equiv = int(usdt_price * usdt_rate * 10)
                    irr_price_line = f" (~{irr_equiv:,} ریال)"
            price_line = f"قیمت: {usdt_price} USDT{irr_price_line}" if usdt_price is not None else "قیمت: —"
            duration = val('duration', 'duration_days')
            capacity = val('capacity', 'capacity') or 'نامحدود'
            description = val('description', 'description')

            text = (
                "📝 لطفاً تغییرات زیر را تایید کنید:\n\n"
                f"نام: {name}\n"
                f"{price_line}\n"
                f"مدت: {duration} روز\n"
                f"ظرفیت: {capacity}\n"
                f"توضیحات: {description}"
            )
            keyboard = [[
                InlineKeyboardButton("✅ تایید و ذخیره", callback_data="confirm_edit_plan"),
                InlineKeyboardButton("⚙️ ویرایش مجدد فیلدها", callback_data="fields_back"),
                InlineKeyboardButton("❌ لغو", callback_data="cancel_edit_plan")
            ]]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
            return EDIT_CONFIRMATION

    async def _handle_add_more_fields(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Callback from confirmation step to open extra-fields menu before saving."""
        query = update.callback_query
        await query.answer()
        await self._show_fields_menu(query, context, mode="add")
        return FIELD_VALUE  # We stay in conversation until done

    async def _handle_set_field(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Admin selected a specific field to set."""
        query = update.callback_query
        await query.answer()
        field_key = query.data.replace("set_field_", "")
        context.user_data['current_field_key'] = field_key
        await self._prompt_for_field_value(query, field_key)
        return FIELD_VALUE

    async def _handle_field_value_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receives value for previously selected field and stores it in user_data."""
        field_key: str = context.user_data.get('current_field_key')
        if not field_key:
            await update.message.reply_text("خطا: فیلدی انتخاب نشده است.")
            return FIELD_VALUE
        val_text = update.message.text.strip()
        # Handle skip to clear value
        if val_text == '/skip':
            parsed_val = None
        else:
            parsed_val: Any = val_text
        try:
            if field_key in {"price", "original_price_irr", "price_tether", "original_price_usdt"}:
                parsed_val = float(val_text)
            elif field_key in {"duration_days", "capacity", "display_order"}:
                from utils.locale_utils import to_int
                parsed_val = to_int(val_text)
            elif field_key in {"is_active", "is_public"}:
                parsed_val = 1 if val_text in {"1", "true", "True", "yes", "Yes"} else 0
            elif field_key in {"expiration_date", "fixed_end_date"}:
                try:
                    datetime.strptime(parsed_val, "%Y-%m-%d")
                except ValueError:
                    raise ValueError("invalid_date_format")
            # else keep string (e.g., json, dates)
        except ValueError as e:
            if str(e) == "invalid_date_format":
                await update.message.reply_text("فرمت تاریخ اشتباه است. لطفاً تاریخ را به فرمت YYYY-MM-DD وارد کنید یا /skip بزنید.")
            else:
                await update.message.reply_text("فرمت مقدار وارد شده اشتباه است. دوباره تلاش کنید (YYYY-MM-DD برای تاریخ یا /skip).")
            return FIELD_VALUE
        # store value
        mode = context.user_data.get('extra_mode')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        context.user_data[f"{prefix}{field_key}"] = parsed_val
        context.user_data.pop('current_field_key', None)
        # Refresh menu so admin can continue or finish
        summary_text = self._generate_summary_text(context, mode) + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
        await update.message.reply_text(summary_text, reply_markup=self._build_fields_keyboard(context, mode))
        return FIELD_VALUE

    async def save_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        plan_data = context.user_data
        name = plan_data['new_plan_name']
        
        # By default, plans are active and public
        is_active = True
        is_public = True
        
        # Special case for 'free_30d' plan to be private by default
        if name == 'free_30d':
            is_public = False

        # Compute IRR equivalent for storage (legacy compatibility)
        usdt_price: float | None = plan_data.get('new_plan_price_usdt')
        irr_price: int | None = None
        if usdt_price is not None:
            usdt_rate = await get_usdt_to_irr_rate()
            if usdt_rate:
                irr_price = int(usdt_price * usdt_rate * 10)

                # Collect extra fields dynamically
        extra_kwargs = {}
        for field in self._PLAN_FIELD_LABELS.keys():
            key = f"new_plan_{field}"
            if key in plan_data:
                extra_kwargs[field] = plan_data[key]

        plan_id = self.db_queries.add_plan(
            name=name,
            price_tether=plan_data.get('new_plan_price_usdt'),
            original_price_irr=irr_price,
            original_price_usdt=plan_data.get('new_plan_price_usdt'),
            duration_days=plan_data['new_plan_duration'],
            capacity=plan_data.get('new_plan_capacity'),
            description=plan_data['new_plan_description'],
            is_active=is_active,
            is_public=is_public,
        **extra_kwargs
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

            # Prepare price display (USDT + IRR)
            usdt_val = plan.get('price_tether') or plan.get('original_price_usdt')
            irr_val = plan.get('price') or plan.get('original_price_irr')
            price_display = f"{usdt_val} USDT" if usdt_val is not None else "—"
            if irr_val is not None:
                price_display += f" (~{irr_val:,} ریال)"

            text = (
                f"*جزئیات پلن: {plan['name']}*\n\n"
                f"*قیمت:* {price_display}\n"
                f"*مدت:* {plan['duration_days']} روز\n"
                f"*ظرفیت:* {plan.get('capacity', 'نامحدود')}\n"
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
                [InlineKeyboardButton("✏️ ویرایش ظرفیت", callback_data=f"edit_plan_{plan_id}")],
                [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="products_show_all")]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

        except Exception as e:
            logger.error(f"Error showing single plan {plan_id}: {e}")
            await query.edit_message_text("خطا در نمایش جزئیات پلن.")

    async def handle_toggle_plan_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        data_parts = query.data.split('_')
        plan_id = int(data_parts[-1])
        if 'confirm' in data_parts:
            # second step -> execute
            await self.toggle_plan_status(query, plan_id)
            return
        # First click – ask for confirmation
        keyboard = [
            [InlineKeyboardButton("✅ بله، تغییر وضعیت", callback_data=f"toggle_plan_active_confirm_{plan_id}")],
            [InlineKeyboardButton("❌ خیر", callback_data=f"view_plan_{plan_id}")]
        ]
        await query.edit_message_text("آیا از تغییر وضعیت فعال/غیرفعال این پلن اطمینان دارید؟", reply_markup=InlineKeyboardMarkup(keyboard))

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
        parts = query.data.split('_')
        plan_id = int(parts[-1])
        if 'confirm' in parts:
            await self.toggle_plan_visibility(query, plan_id)
            return
        keyboard = [
            [InlineKeyboardButton("✅ بله، تغییر نمایش", callback_data=f"toggle_plan_public_confirm_{plan_id}")],
            [InlineKeyboardButton("❌ خیر", callback_data=f"view_plan_{plan_id}")]
        ]
        await query.edit_message_text("آیا از تغییر وضعیت نمایش این پلن اطمینان دارید؟", reply_markup=InlineKeyboardMarkup(keyboard))

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
        """Entry point for editing a plan – presents field selection menu for selective editing."""
        query = update.callback_query
        plan_id = int(query.data.split("_")[2])

        # Clear any previous temp data then set base identifiers
        context.user_data.clear()
        context.user_data['edit_plan_id'] = plan_id

        # Fetch plan once for optimistic lock & initial values
        original_plan = self.db_queries.get_plan_by_id(plan_id)
        if original_plan is None:
            await query.answer("پلن یافت نشد.", show_alert=True)
            return ConversationHandler.END
        # Ensure we have a plain dict so .get works everywhere
        original_plan = dict(original_plan)

        # Save timestamp for optimistic locking later
        if 'updated_at' in original_plan:
            context.user_data['edit_original_updated_at'] = str(original_plan['updated_at'])

        # Pre-fill current values so they appear checked in the menu & summary
        context.user_data.update({
            'edit_plan_name': original_plan.get('name'),
            'edit_plan_price_usdt': original_plan.get('price_tether'),
            'edit_plan_duration': original_plan.get('duration_days'),
            'edit_plan_capacity': original_plan.get('capacity'),
            'edit_plan_description': original_plan.get('description'),
        })

        # Show interactive menu for field selection
        await self._show_fields_menu(query, context, mode="edit")
        return FIELD_VALUE


    async def get_new_plan_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text != '/skip':
            context.user_data['edit_plan_name'] = update.message.text
        await update.message.reply_text("لطفاً قیمت جدید را وارد کنید (برای رد شدن، /skip را بزنید):")
        return EDIT_PRICE

    async def get_new_plan_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Updates the USDT price for an existing plan with validation."""
        if update.message.text != '/skip':
            from utils.locale_utils import to_float
            try:
                context.user_data['edit_plan_price_usdt'] = to_float(update.message.text)
            except (ValueError, TypeError):
                await update.message.reply_text("❌ مقدار وارد شده معتبر نیست. لطفاً مبلغ را به عدد (مثلاً 9.99) وارد کنید یا /skip بزنید.")
                return EDIT_PRICE

        await update.message.reply_text("لطفاً مدت زمان جدید را به روز وارد کنید (برای رد شدن، /skip را بزنید):")
        return EDIT_DURATION

    async def get_new_plan_duration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text != '/skip':
            from utils.locale_utils import to_int
            context.user_data['edit_plan_duration'] = to_int(update.message.text)
        await update.message.reply_text("لطفاً ظرفیت فروش جدید را وارد کنید (برای رد شدن، /skip را بزنید):")
        return EDIT_CAPACITY

    async def get_new_plan_capacity(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text != '/skip':
            context.user_data['edit_plan_capacity'] = await self._parse_capacity_input(update.message.text)
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
            'capacity': context.user_data.get('edit_plan_capacity', original_plan.get('capacity')),
            'description': context.user_data.get('edit_plan_description', original_plan['description'])
        }

        text = (
            f"آیا از اعمال تغییرات زیر اطمینان دارید؟\n\n"
            f"نام: {updated_data['name']}\n"
            f"قیمت: {updated_data['price']} تومان\n"
            f"مدت: {updated_data['duration_days']} روز\n"
            f"ظرفیت: {updated_data.get('capacity', 'نامحدود')}\n"
            f"توضیحات: {updated_data['description']}"
        )
        keyboard = [[InlineKeyboardButton("✅ تایید و ذخیره", callback_data="confirm_edit_plan"), InlineKeyboardButton("❌ لغو", callback_data="cancel_edit_plan")]]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return EDIT_CONFIRMATION

    async def update_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        plan_id = context.user_data['edit_plan_id']
        # Optimistic lock – abort if another admin changed the plan
        db_plan = self.db_queries.get_plan_by_id(plan_id)
        stored_ts = context.user_data.get('edit_original_updated_at')
        if db_plan and 'updated_at' in db_plan and stored_ts is not None and str(db_plan['updated_at']) != stored_ts:
            await query.edit_message_text("❌ این پلن توسط ادمین دیگری تغییر کرده است. لطفاً مجدداً بارگذاری کنید.")
            context.user_data.clear()
            return ConversationHandler.END

        update_kwargs = {
            'name': context.user_data.get('edit_plan_name'),
            'price': None,  # will derive again
            'price_tether': context.user_data.get('edit_plan_price_usdt'),
            'duration_days': context.user_data.get('edit_plan_duration'),
            'capacity': context.user_data.get('edit_plan_capacity'),
            'description': context.user_data.get('edit_plan_description'),
        }
        # Collect values for any additional fields that were set via the extra-fields menu
        for field in self._PLAN_FIELD_LABELS.keys():
            val = context.user_data.get(f'edit_plan_{field}')
            if val is not None:
                update_kwargs[field] = val
        # Filter out None values
        # compute IRR price if tether provided
        if update_kwargs.get('price_tether') is not None:
            usdt_rate = await get_usdt_to_irr_rate()
            if usdt_rate:
                irr_price_val = int(update_kwargs['price_tether'] * usdt_rate * 10)
                update_kwargs['price'] = irr_price_val
                update_kwargs['original_price_irr'] = irr_price_val
                update_kwargs['original_price_usdt'] = update_kwargs['price_tether']
        # remove None entries
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
                ADD_CAPACITY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plan_capacity),
                    CommandHandler('skip', self.get_plan_capacity)
                ],
                ADD_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plan_description)],
                ADD_CONFIRMATION: [
                     CallbackQueryHandler(self.save_plan, pattern='^confirm_add_plan$'),
                     CallbackQueryHandler(self._handle_add_more_fields, pattern='^add_more_fields$'),
                     CallbackQueryHandler(self.cancel_add_plan, pattern='^cancel_add_plan$')
                 ],
                 FIELD_VALUE: [
                     CallbackQueryHandler(self._handle_set_field, pattern='^set_field_'),
                     CallbackQueryHandler(self._handle_fields_done, pattern='^fields_done$'),
                     CallbackQueryHandler(self._handle_fields_back, pattern='^fields_back$'),
                     MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_field_value_input)
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
                EDIT_CAPACITY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_new_plan_capacity),
                    CommandHandler('skip', self.get_new_plan_capacity)
                 ],
                 EDIT_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_new_plan_description)],
                 FIELD_VALUE: [
                     CallbackQueryHandler(self._handle_set_field, pattern='^set_field_'),
                     CallbackQueryHandler(self._handle_fields_done, pattern='^fields_done$'),
                     CallbackQueryHandler(self._handle_fields_back, pattern='^fields_back$'),
                     MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_field_value_input)
                 ],
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


