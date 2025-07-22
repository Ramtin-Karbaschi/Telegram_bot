from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from utils.price_utils import get_usdt_to_irr_rate
from utils.helpers import admin_only_decorator as admin_only, safe_edit_message_text
from database.queries import DatabaseQueries
from services.video_service import video_service
from services.survey_service import survey_service
import logging
from typing import Any, Set
from datetime import datetime
import telegram  # Needed for telegram.error.BadRequest
import json
import config  # For TELEGRAM_CHANNELS_INFO

logger = logging.getLogger(__name__)

from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# Adding capacity states
# Conversation state definitions
# Add \u0026 Edit flows share a common FIELD_VALUE state for entering arbitrary field values
(
    ADD_NAME, ADD_CURRENCY, ADD_PRICE, ADD_DURATION, ADD_CAPACITY, ADD_DESCRIPTION, ADD_CONFIRMATION,
    EDIT_NAME, EDIT_PRICE, EDIT_DURATION, EDIT_CAPACITY, EDIT_DESCRIPTION, EDIT_CONFIRMATION,
    FIELD_VALUE,
) = range(14)

class AdminProductHandler:
    def __init__(self, db_queries=None, admin_config=None):
        """Initialize AdminProductHandler with database queries."""
        if db_queries is None:
            from database.queries import DatabaseQueries
            self.db_queries = DatabaseQueries()
        else:
            self.db_queries = db_queries
        self.admin_config = admin_config
        
        # Define field labels for plan editing
        self._PLAN_FIELD_LABELS = {
            # Required fields (marked with ⭐)
            'name': '⭐ نام پلن (ضروری)',
            'category_id': '⭐ دسته‌بندی (ضروری)',
            'description': '⭐ توضیحات (ضروری)',
            'base_currency': '⭐ ارز پایه (ضروری)',
            'base_price': '⭐ قیمت پایه (ضروری)',
            'duration_days': '⭐ مدت زمان/روز (ضروری)',
            
            # Optional fields (marked with 🔹)
            'capacity': '🔹 ظرفیت (اختیاری)',
            'expiration_date': '🔹 تاریخ انقضا (اختیاری)',
            'fixed_end_date': '🔹 تاریخ پایان ثابت (اختیاری)',
            'auto_delete_links': '🔹 حذف خودکار لینک‌ها (اختیاری)',
            'plan_type': '🔹 نوع پلن (اختیاری)',
            'videos': '🔹 ویدئوها (اختیاری)',
            'survey_type': '🔹 نظرسنجی (اختیاری)',
            'channels_json': '🔹 کانال‌های دسترسی (اختیاری)',
            
            # Legacy fields removed - use base_currency and base_price instead
        }
        
        # Required fields for validation
        self._REQUIRED_FIELDS = {'name', 'description', 'base_currency', 'base_price', 'duration_days', 'category_id'}
    
    async def _handle_fields_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle back button from the extra-fields menu.

        Behaviour depends on the current extra_mode:
        • add  -> abort extra-fields editing and go back to add confirmation screen (or cancel if no confirmation yet).
        • edit -> return to edit confirmation screen so admin can review changes.
        """
        query = update.callback_query
        await query.answer()

        # If returning from a nested picker (e.g., video selection), just show fields menu again
        if 'video_selection_mode' in context.user_data:
            # Exit video selection and show fields menu via helper to avoid duplication
            context.user_data.pop('video_selection_mode', None)
            context.user_data.pop('current_field_key', None)
            return await self._handle_back_to_fields(update, context)

        mode = context.user_data.get('extra_mode', 'add')

        if mode == 'add':
            # If add flow was started from confirmation step, we can re-show it; otherwise cancel.
            if 'new_plan_name' in context.user_data:
                # Recreate the confirmation step similar to _handle_fields_done (but without finishing)
                plan_data = context.user_data
                price_tether = plan_data.get('new_plan_price_tether') or plan_data.get('new_plan_price_usdt')
                irr_price = None
                if price_tether is not None:
                    usdt_rate = await get_usdt_to_irr_rate()
                    if usdt_rate:
                        irr_price = int(price_tether * usdt_rate * 10)

                if price_tether is None:
                    price_line = "قیمت: تعیین نشده"
                elif price_tether == 0:
                    price_line = "قیمت: رایگان"
                else:
                    price_line = f"قیمت: {price_tether:.5f} USDT"
                    if irr_price is not None:
                        price_line += f" (~{irr_price:,} ریال)"

                text = (
                    "🔖 *تایید اطلاعات پلن:*\n\n"
                    f"نام: {plan_data.get('new_plan_name', '—')}\n"
                    f"{price_line}\n"
                    f"مدت: {plan_data.get('new_plan_duration_days', '—')} روز\n"
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




    # -------------------- Category Selection Helpers --------------------
    async def _handle_unlimited_duration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle unlimited duration button press, setting duration_days to 0 and returning to fields menu."""
        query = update.callback_query
        await query.answer()

        # Determine mode (add or edit)
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'

        # Save unlimited duration as 0 days
        context.user_data[f"{prefix}duration_days"] = 0

        # Clear current field flags
        context.user_data.pop('current_field_key', None)
        context.user_data.pop('current_field', None)

        # Refresh fields menu
        text = self._generate_summary_text(context, mode) + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
        reply_markup = self._build_fields_keyboard(context, mode)
        try:
            await query.edit_message_text(text, reply_markup=reply_markup)
        except telegram.error.BadRequest as e:
            if "Message is not modified" not in str(e):
                raise
        return FIELD_VALUE

    async def _show_category_children(self, query, context, parent_id: int | None):
        """Display child categories for navigation and selection."""
        children = self.db_queries.get_children_categories(parent_id)
        keyboard = []
        
        if not children:
            # No categories found
            text = "❌ هیچ دسته‌بندی یافت نشد.\n\nلطفاً ابتدا از بخش مدیریت دسته‌بندی‌ها، دسته‌بندی ایجاد کنید."
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="fields_back")])
        else:
            text = "📂 **انتخاب دسته‌بندی محصول:**\n\n"
            if parent_id is None:
                text += "دسته‌بندی اصلی را انتخاب کنید:"
            else:
                text += "زیردسته مورد نظر را انتخاب کنید:"
            
            for cat in children:
                cat_id = cat.get('id')
                name = cat.get('name', '')
                # Determine if has children
                has_children = len(self.db_queries.get_children_categories(cat_id)) > 0
                if has_children:
                    # Row with two buttons: navigate 📂 and select ✅
                    keyboard.append([
                        InlineKeyboardButton(f"📂 {name}", callback_data=f"category_nav_{cat_id}"),
                        InlineKeyboardButton("✅", callback_data=f"category_select_{cat_id}")
                    ])
                else:
                    # Leaf: single select button with name
                    keyboard.append([InlineKeyboardButton(f"✅ {name}", callback_data=f"category_select_{cat_id}")])
            
            # Navigation buttons
            if parent_id is not None:
                # back button
                stack = context.user_data.get('category_nav_stack', [])
                parent_parent = stack[-1] if stack else None
                back_data = f"category_back_{parent_parent}" if parent_parent is not None else "category_back_root"
                keyboard.append([InlineKeyboardButton("🔙 بازگشت به بالا", callback_data=back_data)])
            else:
                keyboard.append([InlineKeyboardButton("🔙 بازگشت به فیلدها", callback_data="fields_back")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    async def _handle_category_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process category navigation and selection callbacks."""
        query = update.callback_query
        await query.answer()
        data = query.data
        if data.startswith('category_nav_'):
            cat_id = int(data.split('_')[-1])
            stack = context.user_data.get('category_nav_stack', [])
            stack.append(parent_id := cat_id)
            context.user_data['category_nav_stack'] = stack
            await self._show_category_children(query, context, parent_id=cat_id)
            return FIELD_VALUE
        if data.startswith('category_back_'):
            target = data.split('_')[-1]
            if target == 'root':
                context.user_data['category_nav_stack'] = []
                await self._show_category_children(query, context, parent_id=None)
            else:
                parent_id = int(target)
                stack = context.user_data.get('category_nav_stack', [])
                if stack:
                    stack.pop()
                context.user_data['category_nav_stack'] = stack
                await self._show_category_children(query, context, parent_id=parent_id)
            return FIELD_VALUE
        if data.startswith('category_select_'):
            cat_id = int(data.split('_')[-1])
            mode = context.user_data.get('extra_mode', 'add')
            prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
            context.user_data[f'{prefix}category_id'] = cat_id
            context.user_data.pop('category_nav_stack', None)
            context.user_data.pop('current_field', None)
            text = self._generate_summary_text(context, mode) + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
            reply_markup = self._build_fields_keyboard(context, mode)
            await query.edit_message_text(f"✅ دسته‌بندی انتخاب شد.\n\n" + text, reply_markup=reply_markup)
            return FIELD_VALUE
        return FIELD_VALUE

    async def _show_all_plans(self, query):
        """Displays a list of all plans grouped by categories."""
        try:
            # Fetch all plans, including inactive/private ones, for admin view
            all_plans = self.db_queries.get_all_plans()
            if not all_plans:
                await query.edit_message_text("هیچ پلنی یافت نشد.")
                return

            # Group plans by category
            categorized_plans = {}
            uncategorized_plans = []
            
            for plan in all_plans:
                plan = dict(plan)
                category_id = plan.get('category_id')
                if category_id:
                    if category_id not in categorized_plans:
                        categorized_plans[category_id] = []
                    categorized_plans[category_id].append(plan)
                else:
                    uncategorized_plans.append(plan)
            
            keyboard = []
            text = "📜 *مدیریت پلن‌ها*:\n\n"
            
            # Show categorized plans
            for category_id, plans in categorized_plans.items():
                try:
                    category = self.db_queries.get_category_by_id(category_id)
                    category_name = category.get('name', f'ID: {category_id}') if category else f'ID: {category_id}'
                    text += f"📁 **{category_name}** ({len(plans)} محصول)\n"
                    
                    for plan in plans:
                        plan_id = plan['id']
                        plan_name = plan['name']
                        status_emoji = "✅" if plan.get('is_active', False) else "❌"
                        visibility_emoji = "🌍" if plan.get('is_public', False) else "🔒"
                        
                        button_text = f"{status_emoji}{visibility_emoji} {plan_name}"
                        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_plan_{plan_id}")])
                    
                    text += "\n"
                except Exception as e:
                    logger.error(f"Error getting category {category_id}: {e}")
            
            # Show uncategorized plans
            if uncategorized_plans:
                text += f"📄 **بدون دسته‌بندی** ({len(uncategorized_plans)} محصول)\n"
                for plan in uncategorized_plans:
                    plan_id = plan['id']
                    plan_name = plan['name']
                    status_emoji = "✅" if plan.get('is_active', False) else "❌"
                    visibility_emoji = "🌍" if plan.get('is_public', False) else "🔒"
                    
                    button_text = f"{status_emoji}{visibility_emoji} {plan_name}"
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_plan_{plan_id}")])

            keyboard.append([InlineKeyboardButton("➕ افزودن پلن جدید", callback_data="products_add")])
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

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
        """Store plan name, then ask admin to pick price base currency."""
        context.user_data['new_plan_name'] = update.message.text.strip()
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🪙 تتر (USDT)", callback_data="currency_usdt")],
            [InlineKeyboardButton("﷼ ریال (IRR)", callback_data="currency_irr")]
        ])
        await update.message.reply_text("ارز پایه قیمت را انتخاب کنید:", reply_markup=keyboard)
        return ADD_CURRENCY

    async def get_plan_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Collect plan price according to previously selected base currency."""
        from utils.locale_utils import to_float
        base_currency = context.user_data.get('price_base')
        if base_currency is None:
            # Fallback – should not happen
            base_currency = 'USDT'
            context.user_data['price_base'] = 'USDT'
        try:
            price_val = to_float(update.message.text)
        except (ValueError, TypeError):
            await update.message.reply_text("❌ مقدار وارد شده معتبر نیست. لطفاً مبلغ را به عدد صحیح یا اعشاری وارد کنید.")
            return ADD_PRICE

        if base_currency == 'USDT':
            context.user_data['new_plan_price_tether'] = price_val
            context.user_data['new_plan_price'] = None
            context.user_data['new_plan_price_usdt'] = price_val  # legacy field
        else:
            context.user_data['new_plan_price'] = int(price_val)
            context.user_data['new_plan_price_tether'] = None
            context.user_data['new_plan_price_usdt'] = None

        await update.message.reply_text("مدت زمان پلن را به روز وارد کنید:")
        return ADD_DURATION

    async def get_plan_duration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from utils.locale_utils import to_int
        context.user_data['new_plan_duration_days'] = to_int(update.message.text)
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

        # ---------------------------- Currency selection callback ---------------------------- #
    async def handle_select_currency(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Callback when admin selects base currency."""
        query = update.callback_query
        await query.answer()
        currency = 'USDT' if query.data == 'currency_usdt' else 'IRR'
        context.user_data['price_base'] = currency
        await query.edit_message_text(f"ارز پایه «{currency}» انتخاب شد. حالا مبلغ را وارد کنید:")
        return ADD_PRICE

    # ---------------------------- Extra-field helper methods ---------------------------- #
    _PLAN_FIELD_LABELS: dict[str, str] = {
        "name": "نام پلن",
                "price": "قیمت ریالی (price)",
        "original_price_irr": "قیمت ریالی اصلی",
        "price_tether": "قیمت تتر (USDT)",
        "original_price_usdt": "قیمت تتر اصلی",
        "duration_days": "مدت (روز)",
        "capacity": "ظرفیت",
        "description": "توضیحات",
        "features": "ویژگی‌ها (JSON)",
        "plan_type": "نوع پلن",
        "expiration_date": "تاریخ انقضا (YYYY-MM-DD)",
        "fixed_end_date": "تاریخ پایان ثابت (YYYY-MM-DD)",
        "display_order": "ترتیب نمایش",
        "is_active": "فعال؟ (1/0)",
        "is_public": "عمومی؟ (1/0)",
        "channels_json": "کانال‌ها (پس از خرید)",
        "auto_delete_links": "حذف خودکار لینک‌ها؟ (1/0)",
    }

    # ---------------- Channel picker helpers ----------------
    def _build_channel_select_keyboard(self, channels: list[dict], selected_ids: Set[int]):
        """Build inline keyboard with custom prefix 'plch_'."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = []
        row = []
        for ch in channels:
            cid = ch.get("id")
            title = ch.get("title")
            if cid is None or title is None:
                continue
            selected = cid in selected_ids
            text = ("✅ " if selected else "☑️ ") + title
            row.append(InlineKeyboardButton(text, callback_data=f"plch_{cid}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        toggle_text = "انتخاب همه" if len(selected_ids) < len(channels) else "لغو همه"
        keyboard.append([
             InlineKeyboardButton(toggle_text, callback_data="plch_all"),
             InlineKeyboardButton("❌ هیچکدام", callback_data="plch_none"),
         ])
        keyboard.append([
             InlineKeyboardButton("✅ تأیید", callback_data="plch_done"),
         ])
        keyboard.append([
            InlineKeyboardButton("🔙 بازگشت", callback_data="fields_back"),
        ])
        return InlineKeyboardMarkup(keyboard)

    async def _plan_channel_picker_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callbacks from plan channel picker."""
        logger.info(f"CHANNEL_PICKER_CALLBACK: Received callback with data: {update.callback_query.data if update.callback_query else 'NO_QUERY'}")
        
        query = update.callback_query
        if not query:
            logger.error("CHANNEL_PICKER_CALLBACK: No callback query found")
            return FIELD_VALUE
        
        data = query.data
        logger.info(f"CHANNEL_PICKER_CALLBACK: Processing data: {data}")
        
        # Prevent duplicate processing
        if context.user_data.get('processing_plch_callback'):
            await query.answer("در حال پردازش...")
            return FIELD_VALUE
        
        context.user_data['processing_plch_callback'] = True
        
        try:
            # Ensure selected_ids set in user_data
            selected_ids: Set[int] = context.user_data.get("plch_selected_ids", set())
            # Parse channels once
            try:
                channels_info = (
                    json.loads(config.TELEGRAM_CHANNELS_INFO)
                    if isinstance(config.TELEGRAM_CHANNELS_INFO, str)
                    else config.TELEGRAM_CHANNELS_INFO
                )
            except Exception:
                channels_info = []

            logger.info(f"CHANNEL_PICKER_CALLBACK: channels_info loaded, count: {len(channels_info)}")
            logger.info(f"CHANNEL_PICKER_CALLBACK: selected_ids: {selected_ids}")

            if data.startswith("plch_") and data not in {"plch_done", "plch_all", "plch_none"}:
                try:
                    cid = int(data.replace("plch_", ""))
                    if cid in selected_ids:
                        selected_ids.remove(cid)
                    else:
                        selected_ids.add(cid)
                    logger.info(f"CHANNEL_PICKER_CALLBACK: Updated selected_ids: {selected_ids}")
                except ValueError:
                    logger.error(f"CHANNEL_PICKER_CALLBACK: Invalid channel ID: {data}")
                    pass
            elif data == "plch_none":
                # Clear all selections and immediately finalize (behaves like Done with empty set)
                selected_ids = set()
                logger.info("CHANNEL_PICKER_CALLBACK: None selected, cleared all selections")
                # Save empty selection into user_data
                mode = context.user_data.get("extra_mode", "add")
                prefix = "new_plan_" if mode == "add" else "edit_plan_"
                context.user_data[f"{prefix}channels_json"] = json.dumps([], ensure_ascii=False)
                context.user_data.pop("plch_selected_ids", None)
                # Return to fields menu
                await query.answer("✅ بدون کانال انتخاب شد.")
                await self._show_fields_menu(query, context, mode)
                return FIELD_VALUE
            elif data == "plch_all":

                if len(selected_ids) < len(channels_info):
                    selected_ids = {c["id"] for c in channels_info}
                else:
                    selected_ids = set()
                logger.info(f"CHANNEL_PICKER_CALLBACK: Select all toggled, selected_ids: {selected_ids}")
            elif data == "plch_done":
                logger.info(f"CHANNEL_PICKER_CALLBACK: Processing plch_done with {len(selected_ids)} selected channels")
                # Save selection into user_data as JSON string of channel dicts
                mode = context.user_data.get("extra_mode", "add")
                prefix = "new_plan_" if mode == "add" else "edit_plan_"
                selected_channels = [c for c in channels_info if c["id"] in selected_ids]
                context.user_data[f"{prefix}channels_json"] = json.dumps(selected_channels, ensure_ascii=False)
                # Cleanup temp
                context.user_data.pop("plch_selected_ids", None)
                
                logger.info(f"CHANNEL_PICKER_CALLBACK: Saved {len(selected_channels)} channels to user_data")
                
                # Show success message and return to fields menu
                success_msg = f"✅ {len(selected_channels)} کانال انتخاب شد."
                await query.answer(success_msg)
                
                logger.info(f"CHANNEL_PICKER_CALLBACK: Returning to fields menu for mode: {mode}")
                
                # Return to fields menu
                try:
                    await self._show_fields_menu(query, context, mode)
                    logger.info("CHANNEL_PICKER_CALLBACK: Successfully returned to fields menu")
                except telegram.error.BadRequest as e:
                    logger.error(f"CHANNEL_PICKER_CALLBACK: BadRequest error: {e}")
                    if "Message is not modified" in str(e):
                        # Message content is same, just answer the callback
                        pass
                    else:
                        # Fallback: send new message
                        text = self._generate_summary_text(context, mode) + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
                        reply_markup = self._build_fields_keyboard(context, mode)
                        await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=reply_markup)
                        logger.info("CHANNEL_PICKER_CALLBACK: Sent fallback message")
                except Exception as e:
                    logger.error(f"CHANNEL_PICKER_CALLBACK: Unexpected error: {e}")
                return FIELD_VALUE

            # Update set in user_data for non-done actions
            context.user_data["plch_selected_ids"] = selected_ids
            # Refresh keyboard
            keyboard = self._build_channel_select_keyboard(channels_info, selected_ids)
            try:
                await query.edit_message_reply_markup(reply_markup=keyboard)
                logger.info("CHANNEL_PICKER_CALLBACK: Updated keyboard successfully")
            except telegram.error.BadRequest as e:
                logger.error(f"CHANNEL_PICKER_CALLBACK: Error updating keyboard: {e}")
                if "Message is not modified" not in str(e):
                    raise
        
        finally:
            # Always cleanup processing flag
            context.user_data.pop('processing_plch_callback', None)
        
        return FIELD_VALUE

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
        logger.info(f"Showing fields menu in {mode} mode")
        required_labels = [self._PLAN_FIELD_LABELS[k] for k in self._REQUIRED_FIELDS]
        required_line = "🛑 فیلدهای ضروری: " + ", ".join(required_labels)
        text = (
            self._generate_summary_text(context, mode)
            + "\n\n" + required_line
            + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
        )
        reply_markup = self._build_fields_keyboard(context, mode)
        logger.info(f"Built keyboard with {len(reply_markup.inline_keyboard)} rows")
        await safe_edit_message_text(query, text, reply_markup=reply_markup)

    def _generate_summary_text(self, context: ContextTypes.DEFAULT_TYPE, mode: str) -> str:
        """Build a Persian summary of all currently filled fields for the admin."""
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        lines: list[str] = ["— وضعیت مقادیر فعلی —"]
        for field, label in self._PLAN_FIELD_LABELS.items():
            val = context.user_data.get(f"{prefix}{field}")
            emoji = "✅" if val is not None else "▫️"
            
            # Special handling for category_id to show category name
            if field == 'category_id' and val is not None:
                try:
                    category = self.db_queries.get_category_by_id(val)
                    show_val = category.get('name', f'ID: {val}') if category else f'ID: {val}'
                except:
                    show_val = f'ID: {val}'
            else:
                show_val = val if val is not None else "—"
            
            lines.append(f"{emoji} {label}: {show_val}")
        return "\n".join(lines)

    async def _prompt_for_field_value(self, query: Update.callback_query, field_key: str):
        label = self._PLAN_FIELD_LABELS.get(field_key, field_key)
        
        # Special handling for category_id field - should not reach here as it's handled in _handle_set_field
        if field_key == 'category_id':
            # This should not happen, but if it does, redirect to category selection
            context = query._context if hasattr(query, '_context') else None
            if context:
                context.user_data['category_nav_stack'] = []
                await self._show_category_children(query, context, parent_id=None)
            else:
                await query.edit_message_text("خطا در انتخاب دسته‌بندی. لطفاً دوباره تلاش کنید.")
            return
        
        # Special handling for base_currency field
        if field_key == 'base_currency':
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 ریال (IRR)", callback_data="base_currency_irr")],
                [InlineKeyboardButton("🪙 تتر (USDT)", callback_data="base_currency_usdt")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="fields_back")]
            ])
            await query.edit_message_text(f"ارز پایه را انتخاب کنید:", reply_markup=keyboard)
        else:
            # Add cancel button for text input fields
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ لغو", callback_data="cancel_field_input")]
            ])
            await query.edit_message_text(
                f"✏️ وارد کردن {label}:\n\n"
                f"مقدار جدید را وارد کنید:\n\n"
                f"دستورات:\n"
                f"• /skip - رد کردن این فیلد",
                reply_markup=keyboard
            )

    async def _handle_fields_done(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle completion of extra fields editing and return to confirmation screen."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        
        if mode == 'add':
            # Return to add confirmation screen
            plan_data = context.user_data
            base_currency = plan_data.get('new_plan_base_currency', 'IRR')
            base_price = plan_data.get('new_plan_base_price')
            price_display = "رایگان"
            irr_price = None

            if base_price is not None:
                if base_currency == 'USDT':
                    usdt_rate = await get_usdt_to_irr_rate()
                    if usdt_rate:
                        irr_price = int(base_price * usdt_rate * 10)
                    price_display = f"{base_price} USDT"
                    if irr_price:
                        price_display += f" ({irr_price:,} تومان)"
                else:
                    price_display = f"{int(base_price):,} تومان"
            
            text = (
                f"✅ اطلاعات پلن:\n\n"
                f"نام: {plan_data.get('new_plan_name', 'نامشخص')}\n"
                f"قیمت: {price_display}\n"
                f"مدت: {plan_data.get('new_plan_duration_days', 'نامشخص')} روز\n"
                f"ظرفیت: {plan_data.get('new_plan_capacity') or 'نامحدود'}\n"
                f"توضیحات: {plan_data.get('new_plan_description', 'ندارد')}\n\n"
                f"آیا از ثبت این پلن اطمینان دارید؟"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ تایید و ذخیره", callback_data="confirm_add_plan"),
                    InlineKeyboardButton("➕ فیلدهای بیشتر", callback_data="add_more_fields")
                ],
                [InlineKeyboardButton("❌ لغو", callback_data="cancel_add_plan")]
            ]
            
            await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ADD_CONFIRMATION
            
        elif mode == 'edit':
            # Return to edit confirmation screen
            plan_id = context.user_data['edit_plan_id']
            original_plan = dict(self.db_queries.get_plan_by_id(plan_id))
            
            updated_data = {
                'name': context.user_data.get('edit_plan_name', original_plan.get('name')),
                'base_currency': context.user_data.get('edit_plan_base_currency', original_plan.get('base_currency') or ('USDT' if original_plan.get('price_tether') is not None else 'IRR')),
                'base_price': context.user_data.get('edit_plan_base_price', original_plan.get('base_price') or original_plan.get('price_tether') or original_plan.get('price')),
                'duration_days': context.user_data.get('edit_plan_duration', original_plan.get('duration_days')),
                'capacity': context.user_data.get('edit_plan_capacity', original_plan.get('capacity')),
                'description': context.user_data.get('edit_plan_description', original_plan.get('description'))
            }
            
            # Build price display
            price_display = "رایگان"
            if updated_data['base_price'] is not None:
                if updated_data['base_currency'] == 'USDT':
                    usdt_rate = await get_usdt_to_irr_rate()
                    irr_price = None
                    if usdt_rate:
                        irr_price = int(updated_data['base_price'] * usdt_rate * 10)
                    price_display = f"{updated_data['base_price']} USDT"
                    if irr_price:
                        price_display += f" ({irr_price:,} تومان)"
                else:
                    price_display = f"{int(updated_data['base_price']):,} تومان"
            
            text = (
                f"آیا از اعمال تغییرات زیر اطمینان دارید؟\n\n"
                f"نام: {updated_data['name']}\n"
                f"قیمت: {price_display}\n"
                f"مدت: {updated_data['duration_days']} روز\n"
                f"ظرفیت: {updated_data.get('capacity', 'نامحدود')}\n"
                f"توضیحات: {updated_data['description']}"
            )
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ تایید و ذخیره", callback_data="confirm_edit_plan"),
                    InlineKeyboardButton("❌ لغو", callback_data="cancel_edit_plan")
                ]
            ]
            
            await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
            return EDIT_CONFIRMATION

    async def _handle_set_field(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle selection of a specific field to edit."""
        query = update.callback_query
        await query.answer()
        
        field_key = query.data.replace("set_field_", "")
        logger.info(f"User selected field: {field_key}")
        # Store under the unified key expected by value-input handlers
        context.user_data['current_field_key'] = field_key
        # Keep legacy key for backward-compatibility with any older handlers
        context.user_data['current_field'] = field_key
        
        # Special handling for category field
        if field_key == "category_id":
            # Begin category navigation from root
            context.user_data['category_nav_stack'] = []
            await self._show_category_children(query, context, parent_id=None)
            return FIELD_VALUE

        # Special handling for channels field
        if field_key == "channels_json":
            # Show channel picker
            channels_info = getattr(config, "TELEGRAM_CHANNELS_INFO", [])
            if not channels_info:
                await query.edit_message_text("هیچ کانالی در تنظیمات تعریف نشده است.")
                return FIELD_VALUE
            
            # Initialize selected channels from existing data
            mode = context.user_data.get("extra_mode", "add")
            prefix = "new_plan_" if mode == "add" else "edit_plan_"
            existing_json = context.user_data.get(f"{prefix}channels_json", "[]")
            
            try:
                existing_channels = json.loads(existing_json)
                selected_ids = {ch.get("id") for ch in existing_channels if ch.get("id")}
            except:
                selected_ids = set()
            
            context.user_data["plch_selected_ids"] = selected_ids
            keyboard = self._build_channel_select_keyboard(channels_info, selected_ids)
            
            await query.edit_message_text(
                "کانال‌هایی که پس از خرید این پلن، کاربر به آن‌ها دعوت شود را انتخاب کنید:",
                reply_markup=keyboard
            )
            return FIELD_VALUE
        
        # Special handling for survey_type field
        if field_key == "survey_type":
            # Show survey type options
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 نظرسنجی با Poll تلگرام", callback_data="survey_type_poll_based")],
                [InlineKeyboardButton("❌ بدون نظرسنجی", callback_data="survey_type_none")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="fields_back")]
            ])
            await query.edit_message_text(
                "📋 **انتخاب نوع نظرسنجی:**\n\n"
                "📊 **Poll تلگرام:** از قابلیت‌های آماده تلگرام استفاده کنید\n"
                "❌ **بدون نظرسنجی:** هیچ نظرسنجی نداشته باشید",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return FIELD_VALUE
        
        # For other fields, prompt for text input
        await self._prompt_for_field_value(query, field_key)
        return FIELD_VALUE

    async def _handle_field_value_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text input for field values."""
        # Check if we're in survey creation mode
        if context.user_data.get('survey_step') == 'question_text':
            return await self._handle_question_text_input(update, context)
        elif context.user_data.get('survey_step') == 'question_options':
            return await self._handle_question_options_input(update, context)
        
        field_key = context.user_data.get('current_field')
        if not field_key:
            await update.message.reply_text("خطا: فیلد مشخص نشده است.")
            return FIELD_VALUE
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        # Store the value
        context.user_data[f'{prefix}{field_key}'] = update.message.text
        
        # Clear current field
        context.user_data.pop('current_field', None)
        
        # Return to fields menu
        text = self._generate_summary_text(context, mode) + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
        reply_markup = self._build_fields_keyboard(context, mode)
        
        await update.message.reply_text(text, reply_markup=reply_markup)
        return FIELD_VALUE

    async def _handle_base_currency_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle base currency selection (IRR or USDT)."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        if query.data == 'base_currency_irr':
            context.user_data[f'{prefix}base_currency'] = 'IRR'
            currency_name = 'ریال'
        elif query.data == 'base_currency_usdt':
            context.user_data[f'{prefix}base_currency'] = 'USDT'
            currency_name = 'تتر'
        else:
            await query.edit_message_text("خطا در انتخاب ارز.")
            return FIELD_VALUE
        
        # Clear current field
        context.user_data.pop('current_field', None)
        
        # Return to fields menu with confirmation
        await query.edit_message_text(f"✅ ارز پایه «{currency_name}» انتخاب شد.")
        
        # Show fields menu after a brief delay
        import asyncio
        await asyncio.sleep(1)
        
        text = self._generate_summary_text(context, mode) + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
        reply_markup = self._build_fields_keyboard(context, mode)
        await query.edit_message_text(text, reply_markup=reply_markup)
        return FIELD_VALUE
    
    async def _handle_plan_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle plan type selection."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        if query.data == 'plan_type_subscription':
            context.user_data[f'{prefix}plan_type'] = 'subscription'
            type_name = 'اشتراک معمولی'
        elif query.data == 'plan_type_video_content':
            context.user_data[f'{prefix}plan_type'] = 'video_content'
            type_name = 'محتوای ویدئویی'
        elif query.data == 'plan_type_one_time_content':
            context.user_data[f'{prefix}plan_type'] = 'one_time_content'
            type_name = 'محتوای یکبار مصرف'
        else:
            await query.edit_message_text("خطا در انتخاب نوع پلن.")
            return FIELD_VALUE
        
        # Clear current field
        context.user_data.pop('current_field', None)
        
        # Return to fields menu with confirmation
        await query.edit_message_text(f"✅ نوع پلن «{type_name}» انتخاب شد.")
        
        # Show fields menu after a brief delay
        import asyncio
        await asyncio.sleep(1)
        
        text = self._generate_summary_text(context, mode) + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
        reply_markup = self._build_fields_keyboard(context, mode)
        await query.edit_message_text(text, reply_markup=reply_markup)
        return FIELD_VALUE
    
    async def _handle_video_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video management for plans."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        
        # First, sync videos from directory
        new_videos, total_videos = video_service.scan_and_sync_videos()
        
        if new_videos > 0:
            await query.edit_message_text(f"✅ {new_videos} ویدئوی جدید به دیتابیس اضافه شد.")
            import asyncio
            await asyncio.sleep(1)
        
        # Get all available videos
        available_videos = video_service.get_available_videos()
        
        if not available_videos:
            await query.edit_message_text(
                "❌ هیچ ویدئویی در دایرکتوری videos یافت نشد.\n\n"
                "لطفاً ویدئوهای آموزشی را در مسیر زیر قرار دهید:\n"
                f"`{video_service.videos_directory}`",
                parse_mode='Markdown'
            )
            return FIELD_VALUE
        
        # Show video selection interface
        context.user_data['video_selection_mode'] = mode
        await self._show_video_selection(query, context, available_videos)
        return FIELD_VALUE
    
    async def _show_video_selection(self, query, context, available_videos):
        """Show enhanced video selection interface with guidance."""
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        # Get currently selected videos with their details
        selected_video_data = context.user_data.get(f'{prefix}video_data', {})
        selected_videos = list(selected_video_data.keys())
        
        text = "🎥 **مدیریت ویدئوهای محصول**\n\n"
        text += f"📊 **تعداد انتخاب شده:** {len(selected_videos)}\n\n"
        
        if selected_videos:
            text += "🏆 **ویدئوهای انتخاب شده:**\n"
            for i, video_id in enumerate(selected_videos, 1):
                video_info = selected_video_data[video_id]
                video_name = video_info.get('display_name', f'ویدئو {video_id}')
                custom_caption = video_info.get('custom_caption', '')
                caption_preview = custom_caption[:30] + '...' if len(custom_caption) > 30 else custom_caption
                text += f"{i}. 🎥 {video_name}\n"
                if custom_caption:
                    text += f"   📝 کپشن: {caption_preview}\n"
                else:
                    text += f"   ⚠️ کپشن تعریف نشده\n"
            text += "\n"
        
        text += "📋 **ویدئوهای موجود:**\n"
        
        keyboard = []
        for video in available_videos:
            is_selected = video['id'] in selected_videos
            status = "✅" if is_selected else "▫️"
            button_text = f"{status} {video['display_name']}"
            callback_data = f"toggle_video_{video['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        # Add management buttons
        if selected_videos:
            keyboard.extend([
                [InlineKeyboardButton("📝 مدیریت کپشن‌ها", callback_data="manage_video_captions")],
                [InlineKeyboardButton("🔄 ترتیب ویدئوها", callback_data="reorder_videos")],
                [InlineKeyboardButton("✅ تأیید نهایی", callback_data="confirm_video_selection")]
            ])
        
        keyboard.extend([
            [InlineKeyboardButton("🔙 بازگشت به فیلدها", callback_data="back_to_fields")],
            [InlineKeyboardButton("❓ راهنمایی", callback_data="video_help")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_video_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle toggling video selection with enhanced data structure."""
        query = update.callback_query
        await query.answer()
        
        video_id = int(query.data.split('_')[2])
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        # Get video data structure
        video_data = context.user_data.get(f'{prefix}video_data', {})
        
        # Get video details from service
        available_videos = video_service.get_available_videos()
        video_info = next((v for v in available_videos if v['id'] == video_id), None)
        
        if not video_info:
            await query.answer("❌ ویدئو یافت نشد.", show_alert=True)
            return FIELD_VALUE
        
        if video_id in video_data:
            # Remove video
            del video_data[video_id]
            await query.answer(f"❌ {video_info['display_name']} حذف شد.")
        else:
            # Add video with default data
            video_data[video_id] = {
                'display_name': video_info['display_name'],
                'file_path': video_info['file_path'],
                'custom_caption': '',
                'order': len(video_data) + 1
            }
            await query.answer(f"✅ {video_info['display_name']} اضافه شد.")
        
        context.user_data[f'{prefix}video_data'] = video_data
        
        # Refresh the video selection interface
        await self._show_video_selection(query, context, 1)
        return FIELD_VALUE
    
    async def _handle_video_selection_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirm video selection with validation."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        video_data = context.user_data.get(f'{prefix}video_data', {})
        
        if not video_data:
            await query.answer("❌ هیچ ویدئوی انتخاب نشده است.", show_alert=True)
            return FIELD_VALUE
        
        # Check if all videos have captions
        videos_without_caption = []
        for video_id, video_info in video_data.items():
            if not video_info.get('custom_caption', '').strip():
                videos_without_caption.append(video_info['display_name'])
        
        if videos_without_caption:
            text = "⚠️ **هشدار**\n\n"
            text += "ویدئوهای زیر کپشن ندارند:\n"
            for name in videos_without_caption[:5]:  # Show max 5
                text += f"• {name}\n"
            if len(videos_without_caption) > 5:
                text += f"• و {len(videos_without_caption) - 5} ویدئو دیگر...\n"
            text += "\nآیا می‌خواهید بدون کپشن ادامه دهید؟"
            
            keyboard = [
                [InlineKeyboardButton("📝 افزودن کپشن‌ها", callback_data="manage_video_captions")],
                [InlineKeyboardButton("✅ ادامه بدون کپشن", callback_data="force_confirm_videos")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_video_selection")]
            ]
            
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return FIELD_VALUE
        
        # All videos have captions, proceed with confirmation
        await self._finalize_video_selection(query, context)
        return FIELD_VALUE
    
    async def _finalize_video_selection(self, query, context):
        """Finalize video selection and return to fields menu."""
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        video_data = context.user_data.get(f'{prefix}video_data', {})
        
        # Clear current field
        context.user_data.pop('current_field_key', None)
        
        # Show confirmation
        text = f"✅ **ویدئوها با موفقیت تنظیم شد!**\n\n"
        text += f"📊 **تعداد:** {len(video_data)} ویدئو\n"
        text += f"📝 **با کپشن:** {sum(1 for v in video_data.values() if v.get('custom_caption', '').strip())}\n\n"
        
        # Show brief summary
        for i, (video_id, video_info) in enumerate(video_data.items(), 1):
            text += f"{i}. {video_info['display_name']}\n"
            if video_info.get('custom_caption', '').strip():
                caption_preview = video_info['custom_caption'][:40] + '...' if len(video_info['custom_caption']) > 40 else video_info['custom_caption']
                text += f"   📝 {caption_preview}\n"
        
        keyboard = [[
            InlineKeyboardButton("🔙 بازگشت به فیلدها", callback_data="back_to_fields")
        ]]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        # Show fields menu after a brief delay
        import asyncio
        await asyncio.sleep(2)
        
        summary_text = self._generate_summary_text(context, mode) + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
        reply_markup = self._build_fields_keyboard(context, mode)
        await query.edit_message_text(summary_text, reply_markup=reply_markup)
    
    async def _handle_survey_management(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle survey management for plans."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        # Show survey options
        keyboard = [
            [InlineKeyboardButton("📋 ایجاد نظرسنجی پیش‌فرض", callback_data="create_default_survey")],
            [InlineKeyboardButton("📝 ایجاد نظرسنجی سفارشی", callback_data="create_custom_survey")],
            [InlineKeyboardButton("❌ بدون نظرسنجی", callback_data="no_survey")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_fields")]
        ]
        
        text = "📊 تنظیمات نظرسنجی\n\n"
        text += "برای محصولات ویدئویی، می‌توانید یک نظرسنجی پیش‌شرط تعریف کنید:\n\n"
        text += "🔹 نظرسنجی پیش‌فرض: شامل سوالات استاندارد\n"
        text += "🔹 نظرسنجی سفارشی: سوالات دلخواه شما\n"
        text += "🔹 بدون نظرسنجی: دسترسی مستقیم به ویدئوها"
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
        return FIELD_VALUE
    
    async def _handle_survey_option(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle survey option selection."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        if query.data == "create_default_survey":
            context.user_data[f'{prefix}survey_type'] = 'default'
            survey_text = "نظرسنجی پیش‌فرض"
        elif query.data == "create_custom_survey":
            context.user_data[f'{prefix}survey_type'] = 'custom'
            survey_text = "نظرسنجی سفارشی"
        elif query.data == "no_survey":
            context.user_data[f'{prefix}survey_type'] = 'none'
            survey_text = "بدون نظرسنجی"
        else:
            await query.edit_message_text("خطا در انتخاب نوع نظرسنجی.")
            return FIELD_VALUE
        
        # Clear current field
        context.user_data.pop('current_field', None)
        
        # Show confirmation
        await query.edit_message_text(f"✅ {survey_text} انتخاب شد.")
        
        # Show fields menu after a brief delay
        import asyncio
        await asyncio.sleep(1)
        
        text = self._generate_summary_text(context, mode) + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
        reply_markup = self._build_fields_keyboard(context, mode)
        await query.edit_message_text(text, reply_markup=reply_markup)
        return FIELD_VALUE
    
    async def _handle_back_to_fields(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle back to fields button."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        
        # Clear current field
        context.user_data.pop('current_field', None)
        
        # Return to fields menu
        text = self._generate_summary_text(context, mode) + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
        reply_markup = self._build_fields_keyboard(context, mode)
        try:
            await query.edit_message_text(text, reply_markup=reply_markup)
        except telegram.error.BadRequest as e:
            if "Message is not modified" in str(e):
                # Safe to ignore – nothing changed
                pass
            else:
                raise
        return FIELD_VALUE
    
    async def _handle_manage_video_captions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show video caption management interface."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        video_data = context.user_data.get(f'{prefix}video_data', {})
        
        if not video_data:
            await query.answer("❌ هیچ ویدئوی انتخاب نشده است.", show_alert=True)
            return FIELD_VALUE
        
        text = "📝 **مدیریت کپشن ویدئوها**\n\n"
        text += "ویدئوهای انتخاب شده:\n\n"
        
        keyboard = []
        for i, (video_id, video_info) in enumerate(video_data.items(), 1):
            video_name = video_info['display_name']
            has_caption = bool(video_info.get('custom_caption', '').strip())
            status = "✅" if has_caption else "❌"
            
            text += f"{i}. {status} {video_name}\n"
            if has_caption:
                caption_preview = video_info['custom_caption'][:50] + '...' if len(video_info['custom_caption']) > 50 else video_info['custom_caption']
                text += f"   📝 {caption_preview}\n"
            else:
                text += "   ⚠️ کپشن تعریف نشده\n"
            
            keyboard.append([InlineKeyboardButton(
                f"✏️ {video_name[:25]}{'...' if len(video_name) > 25 else ''}",
                callback_data=f"edit_caption_{video_id}"
            )])
        
        keyboard.extend([
            [InlineKeyboardButton("🔙 بازگشت به انتخاب ویدئو", callback_data="back_to_video_selection")],
            [InlineKeyboardButton("✅ تأیید و ادامه", callback_data="confirm_video_selection")]
        ])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return FIELD_VALUE
    
    async def _handle_video_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show video management help."""
        query = update.callback_query
        await query.answer()
        
        text = "❓ **راهنمای مدیریت ویدئو**\n\n"
        text += "🎯 **هدف:**\n"
        text += "برای هر محصول می‌توانید چندین ویدئو با کپشن‌های سفارشی تعریف کنید.\n\n"
        
        text += "📋 **مراحل:**\n"
        text += "1️⃣ **انتخاب ویدئوها:** روی ویدئوهای مورد نظر کلیک کنید\n"
        text += "2️⃣ **تعریف کپشن:** برای هر ویدئو توضیح مناسب بنویسید\n"
        text += "3️⃣ **تنظیم ترتیب:** ترتیب نمایش ویدئوها را مشخص کنید\n"
        text += "4️⃣ **تأیید نهایی:** تنظیمات را ذخیره کنید\n\n"
        
        text += "💡 **نکات مهم:**\n"
        text += "• هر ویدئو باید کپشن داشته باشد\n"
        text += "• کپشن باید توضیح مختصری از محتوا باشد\n"
        text += "• ترتیب ویدئوها مهم است (از آسان به سخت)\n"
        text += "• می‌توانید بعداً ویدئوها را ویرایش کنید"
        
        keyboard = [[
            InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_video_selection")
        ]]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return FIELD_VALUE
    
    async def _handle_force_confirm_videos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Force confirm videos without all captions."""
        query = update.callback_query
        await query.answer()
        
        await self._finalize_video_selection(query, context)
        return FIELD_VALUE
    
    async def _handle_back_to_video_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Return to video selection interface."""
        query = update.callback_query
        await query.answer()
        
        available_videos = video_service.get_available_videos()
        await self._show_video_selection(query, context, available_videos)
        return FIELD_VALUE
    
    async def _handle_edit_caption(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle editing caption for a specific video."""
        query = update.callback_query
        await query.answer()
        
        video_id = int(query.data.split('_')[2])
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        video_data = context.user_data.get(f'{prefix}video_data', {})
        
        if video_id not in video_data:
            await query.answer("❌ ویدئو یافت نشد.", show_alert=True)
            return FIELD_VALUE
        
        video_info = video_data[video_id]
        current_caption = video_info.get('custom_caption', '')
        
        # Set caption editing mode
        context.user_data['caption_editing_video_id'] = video_id
        context.user_data['caption_step'] = 'input'
        
        text = f"📝 **ویرایش کپشن ویدئو**\n\n"
        text += f"🎥 **ویدئو:** {video_info['display_name']}\n\n"
        
        if current_caption:
            text += f"📄 **کپشن فعلی:**\n{current_caption}\n\n"
        else:
            text += "📄 **کپشن فعلی:** تعریف نشده\n\n"
        
        text += "✏️ **کپشن جدید را وارد کنید:**\n\n"
        text += "💡 **راهنمایی:**\n"
        text += "• کپشن باید توضیح مختصری از محتوای ویدئو باشد\n"
        text += "• می‌توانید از ایموجی استفاده کنید\n"
        text += "• حداکثر 500 کاراکتر\n"
        text += "• برای پاک کردن کپشن، عبارت 'حذف' را وارد کنید"
        
        keyboard = [[
            InlineKeyboardButton("❌ لغو", callback_data="cancel_caption_edit")
        ]]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return FIELD_VALUE
    
    async def _handle_caption_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle caption text input."""
        if context.user_data.get('caption_step') != 'input':
            return await self._handle_field_value_input(update, context)
        
        video_id = context.user_data.get('caption_editing_video_id')
        if not video_id:
            await update.message.reply_text("❌ خطا در ویرایش کپشن.")
            return FIELD_VALUE
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        video_data = context.user_data.get(f'{prefix}video_data', {})
        
        if video_id not in video_data:
            await update.message.reply_text("❌ ویدئو یافت نشد.")
            return FIELD_VALUE
        
        caption_text = update.message.text.strip()
        
        # Handle deletion
        if caption_text.lower() in ['حذف', 'delete', 'remove']:
            video_data[video_id]['custom_caption'] = ''
            success_text = "🗑️ کپشن حذف شد."
        else:
            # Validate length
            if len(caption_text) > 500:
                await update.message.reply_text(
                    "❌ کپشن خیلی طولانی است. حداکثر 500 کاراکتر مجاز است.\n"
                    f"طول فعلی: {len(caption_text)} کاراکتر"
                )
                return FIELD_VALUE
            
            video_data[video_id]['custom_caption'] = caption_text
            success_text = "✅ کپشن با موفقیت ذخیره شد."
        
        # Clear editing state
        context.user_data.pop('caption_editing_video_id', None)
        context.user_data.pop('caption_step', None)
        
        # Update video data
        context.user_data[f'{prefix}video_data'] = video_data
        
        # Show success message and return to caption management
        await update.message.reply_text(success_text)
        
        # Return to caption management after 1 second
        import asyncio
        await asyncio.sleep(1)
        
        # Create mock query for returning to caption management
        class MockQuery:
            def __init__(self, chat_id):
                self.message = type('obj', (object,), {'chat_id': chat_id})()
            
            async def answer(self):
                pass
            
            async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
                await context.bot.send_message(
                    chat_id=self.message.chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
        
        mock_query = MockQuery(update.message.chat_id)
        mock_update = type('obj', (object,), {'callback_query': mock_query})()
        await self._handle_manage_video_captions(mock_update, context)
        
        return FIELD_VALUE
    
    async def _handle_cancel_caption_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle canceling caption edit."""
        query = update.callback_query
        await query.answer()
        
        # Clear editing state
        context.user_data.pop('caption_editing_video_id', None)
        context.user_data.pop('caption_step', None)
        
        # Return to caption management
        await self._handle_manage_video_captions(update, context)
        return FIELD_VALUE
    
    async def _handle_custom_survey_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle poll-based survey creation process."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        # Initialize poll collection
        context.user_data[f'{prefix}survey_polls'] = []
        context.user_data['survey_creation_mode'] = True
        
        # Show poll creation instructions
        await self._show_poll_creation_menu(query, context)
        return FIELD_VALUE
    
    async def _show_poll_creation_menu(self, query, context):
        """Show poll-based survey creation menu."""
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        collected_polls = context.user_data.get(f'{prefix}survey_polls', [])
        
        text = (
            "📊 **ساخت نظرسنجی با Poll تلگرام**\n\n"
            "🎯 **راهنما:**\n"
            "1️⃣ روی 'ساخت Poll جدید' کلیک کنید\n"
            "2️⃣ از منوی تلگرام Poll یا Quiz بسازید\n"
            "3️⃣ Poll را ارسال کنید تا ذخیره شود\n"
            "4️⃣ تکرار کنید تا همه سوالات آماده شود\n\n"
            f"📋 **Poll‌های جمع‌آوری شده:** {len(collected_polls)}\n"
        )
        
        if collected_polls:
            text += "\n🔸 **لیست Poll‌ها:**\n"
            for i, poll_data in enumerate(collected_polls, 1):
                poll_question = poll_data.get('question', 'سوال نامشخص')[:30]
                poll_type = '🧠 Quiz' if poll_data.get('type') == 'quiz' else '📊 Poll'
                text += f"{i}. {poll_type} {poll_question}...\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ ساخت Poll جدید", callback_data="create_new_poll")],
        ]
        
        if collected_polls:
            keyboard.extend([
                [InlineKeyboardButton("🗑️ حذف آخرین Poll", callback_data="remove_last_poll")],
                [InlineKeyboardButton("✅ تأیید و ذخیره نظرسنجی", callback_data="confirm_poll_survey")]
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_survey_options")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    
    async def _handle_create_new_poll(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle creating a new poll instruction."""
        query = update.callback_query
        await query.answer()
        
        # Set poll creation mode
        context.user_data['waiting_for_poll'] = True
        
        text = (
            "📊 **آماده سازی Poll جدید**\n\n"
            "🔄 **مراحل:**\n"
            "1️⃣ روی گیره 📎 کنار باکس متن کلیک کنید\n"
            "2️⃣ از منو '📊 Poll' یا '🧠 Quiz' انتخاب کنید\n"
            "3️⃣ سوال و گزینه‌ها را وارد کنید\n"
            "4️⃣ Poll را ارسال کنید\n\n"
            "⚠️ **نکته:** بعد از ارسال Poll، به صورت خودکار ذخیره می‌شود"
        )
        
        keyboard = [
            [InlineKeyboardButton("❌ لغو و بازگشت", callback_data="cancel_poll_creation")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        return FIELD_VALUE
    
    async def _handle_poll_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle received poll messages during survey creation."""
        if not context.user_data.get('waiting_for_poll') or not context.user_data.get('survey_creation_mode'):
            return  # Not in poll creation mode
        
        poll = update.message.poll
        if not poll:
            await update.message.reply_text("❌ لطفاً یک Poll یا Quiz ارسال کنید.")
            return
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        # Extract poll data
        poll_data = {
            'id': poll.id,
            'question': poll.question,
            'options': [opt.text for opt in poll.options],
            'type': 'quiz' if poll.type == 'quiz' else 'poll',
            'allows_multiple_answers': poll.allows_multiple_answers,
            'correct_option_id': poll.correct_option_id if poll.type == 'quiz' else None,
            'explanation': poll.explanation if poll.type == 'quiz' else None
        }
        
        # Add to collected polls
        if f'{prefix}survey_polls' not in context.user_data:
            context.user_data[f'{prefix}survey_polls'] = []
        context.user_data[f'{prefix}survey_polls'].append(poll_data)
        
        # Clear waiting flag
        context.user_data['waiting_for_poll'] = False
        
        # Show success and return to menu
        poll_type = '🧠 Quiz' if poll.type == 'quiz' else '📊 Poll'
        success_text = f"✅ {poll_type} با موفقیت اضافه شد!\n\nسوال: {poll.question[:50]}{'...' if len(poll.question) > 50 else ''}"
        await update.message.reply_text(success_text)
        
        # Return to poll creation menu
        import asyncio
        await asyncio.sleep(0.5)
        await self._send_poll_creation_menu(update, context)
        return FIELD_VALUE
    
    async def _send_poll_creation_menu(self, update, context):
        """Send poll creation menu as new message."""
        chat_id = update.effective_chat.id if hasattr(update, "effective_chat") else update.message.chat_id
        
        class DummyQuery:
            def __init__(self, bot, chat_id):
                self.bot = bot
                self.chat_id = chat_id
            async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
                await self.bot.send_message(chat_id=self.chat_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
        
        dummy_query = DummyQuery(context.bot, chat_id)
        await self._show_poll_creation_menu(dummy_query, context)
    
    async def _handle_remove_last_poll(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle removing the last poll from survey."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        collected_polls = context.user_data.get(f'{prefix}survey_polls', [])
        
        if collected_polls:
            removed_poll = collected_polls.pop()
            context.user_data[f'{prefix}survey_polls'] = collected_polls
            
            poll_question = removed_poll.get('question', 'سوال نامشخص')[:30]
            await query.answer(f"✅ Poll حذف شد: {poll_question}...", show_alert=True)
        
        await self._show_poll_creation_menu(query, context)
    
    async def _handle_confirm_poll_survey(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle confirming and saving the poll-based survey."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        collected_polls = context.user_data.get(f'{prefix}survey_polls', [])
        
        if not collected_polls:
            await query.answer("❌ لطفاً حداقل یک Poll اضافه کنید.", show_alert=True)
            return
        
        # Convert polls to survey format and save
        survey_questions = []
        for poll_data in collected_polls:
            question = {
                'text': poll_data['question'],
                'type': 'multiple_choice',
                'options': poll_data['options'],
                'required': True,
                'poll_type': poll_data['type'],
                'allows_multiple_answers': poll_data.get('allows_multiple_answers', False),
                'correct_option_id': poll_data.get('correct_option_id'),
                'explanation': poll_data.get('explanation')
            }
            survey_questions.append(question)
        
        # Save to user_data
        context.user_data[f'{prefix}survey_questions'] = survey_questions
        context.user_data[f'{prefix}survey_type'] = 'poll_based'
        
        # Cleanup
        context.user_data.pop(f'{prefix}survey_polls', None)
        context.user_data.pop('survey_creation_mode', None)
        context.user_data.pop('waiting_for_poll', None)
        
        # Show success and return to fields menu
        success_text = f"✅ نظرسنجی با {len(survey_questions)} سوال ذخیره شد!"
        await query.answer(success_text, show_alert=True)
        
        await self._show_fields_menu(query, context, mode)
        return FIELD_VALUE
    
    async def _handle_cancel_poll_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle canceling poll creation and return to poll menu."""
        query = update.callback_query
        await query.answer()
        
        # Clear waiting flag
        context.user_data.pop('waiting_for_poll', None)
        
        # Return to poll creation menu
        await self._show_poll_creation_menu(query, context)
        return FIELD_VALUE
    
    async def _handle_survey_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle survey type selection."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        if query.data == 'survey_type_poll_based':
            # Start poll-based survey creation
            return await self._handle_custom_survey_creation(update, context)
        elif query.data == 'survey_type_none':
            # No survey
            context.user_data[f'{prefix}survey_type'] = 'none'
            context.user_data.pop('current_field', None)
            
            await query.answer("✅ بدون نظرسنجی انتخاب شد.")
            
            # Return to fields menu
            await self._show_fields_menu(query, context, mode)
            return FIELD_VALUE
        
        return FIELD_VALUE
    
    async def _show_custom_survey_menu(self, query, context):
        """Show enhanced custom survey creation menu."""
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        survey_data = context.user_data.get(f'{prefix}custom_survey', {'questions': []})
        questions = survey_data.get('questions', [])
        
        text = f"📝 مدیریت نظرسنجی سفارشی\n\n"
        text += f"📊 تعداد سوالات: {len(questions)}\n\n"
        
        if questions:
            text += "📋 سوالات تعریف شده:\n"
            for i, q in enumerate(questions, 1):
                q_type = q.get('type', 'text')
                type_icon = {'text': '📝', 'multiple_choice': '🔘', 'rating': '⭐'}.get(q_type, '📝')
                text += f"{i}. {type_icon} {q['text'][:40]}{'...' if len(q['text']) > 40 else ''}\n"
                if q_type == 'multiple_choice' and q.get('options'):
                    text += f"   گزینه‌ها: {len(q['options'])} عدد\n"
            text += "\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ افزودن سوال متنی", callback_data="add_text_question")],
            [InlineKeyboardButton("🔘 افزودن سوال چندگزینه‌ای", callback_data="add_choice_question")],
            [InlineKeyboardButton("⭐ افزودن سوال امتیازی", callback_data="add_rating_question")]
        ]
        
        if questions:
            keyboard.extend([
                [InlineKeyboardButton("🗑️ حذف آخرین سوال", callback_data="remove_last_question")],
                [InlineKeyboardButton("✅ تأیید نظرسنجی", callback_data="confirm_custom_survey")]
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_survey_options")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
    
    async def _handle_add_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle adding a new question to custom survey."""
        query = update.callback_query
        await query.answer()
        
        question_type = query.data.replace('add_', '').replace('_question', '')
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        # Store current question type
        context.user_data[f'{prefix}current_question_type'] = question_type
        context.user_data['survey_step'] = 'question_text'
        
        type_names = {
            'text': 'متنی',
            'choice': 'چندگزینه‌ای',
            'rating': 'امتیازی (1-5 ستاره)'
        }
        
        text = f"❓ افزودن سوال {type_names.get(question_type, question_type)}\n\n"
        text += "لطفاً متن سوال را وارد کنید:"
        
        keyboard = [[InlineKeyboardButton("❌ لغو", callback_data="cancel_add_question")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
        return FIELD_VALUE
    
    async def _handle_question_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle question text input."""
        if context.user_data.get('survey_step') != 'question_text':
            return await self._handle_field_value_input(update, context)
        
        question_text = update.message.text.strip()
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        question_type = context.user_data.get(f'{prefix}current_question_type')
        
        # Store question text temporarily
        context.user_data[f'{prefix}current_question_text'] = question_text
        
        if question_type == 'choice':
            # Ask for options
            context.user_data['survey_step'] = 'question_options'
            text = f"🔘 سوال: {question_text}\n\n"
            text += "حالا گزینه‌های پاسخ را وارد کنید.\n"
            text += "هر گزینه را در یک خط جداگانه بنویسید:\n\n"
            text += "مثال:\nگزینه یک\nگزینه دو\nگزینه سه"
            
            await update.message.reply_text(text)
        else:
            # For text and rating questions, save directly
            await self._save_custom_question(update, context, question_text, question_type)
        
        return FIELD_VALUE
    
    async def _handle_question_options_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle question options input for multiple choice questions."""
        if context.user_data.get('survey_step') != 'question_options':
            return await self._handle_field_value_input(update, context)
        
        options_text = update.message.text.strip()
        options = [opt.strip() for opt in options_text.split('\n') if opt.strip()]
        
        if len(options) < 2:
            await update.message.reply_text("❌ لطفاً حداقل 2 گزینه وارد کنید.")
            return FIELD_VALUE
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        question_text = context.user_data.get(f'{prefix}current_question_text')
        
        await self._save_custom_question(update, context, question_text, 'multiple_choice', options)
        return FIELD_VALUE
    
    async def _save_custom_question(self, update, context, question_text, question_type, options=None):
        """Save a custom question to the survey."""
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        # Get or create survey data
        if f'{prefix}custom_survey' not in context.user_data:
            context.user_data[f'{prefix}custom_survey'] = {'questions': []}
        
        survey_data = context.user_data[f'{prefix}custom_survey']
        
        # Create question object
        question = {
            'text': question_text,
            'type': question_type,
            'options': options or [],
            'required': True,
            'order': len(survey_data['questions']) + 1
        }
        
        # Add question to survey
        survey_data['questions'].append(question)
        context.user_data[f'{prefix}custom_survey'] = survey_data
        
        # Clear temporary data
        context.user_data.pop(f'{prefix}current_question_type', None)
        context.user_data.pop(f'{prefix}current_question_text', None)
        context.user_data.pop('survey_step', None)
        
        # Show success message
        success_text = f"✅ سوال با موفقیت اضافه شد!\n\nسوال: {question_text}"
        
        if hasattr(update, 'message'):
            await update.message.reply_text(success_text)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=success_text)
        
                # Return to survey menu after short pause
        import asyncio
        await asyncio.sleep(0.5)
        await self._send_custom_survey_menu(update, context)

    async def _send_custom_survey_menu(self, update, context):
        """Send the custom survey menu as a fresh message (used after adding a question)."""
        # Re-use _show_custom_survey_menu logic by creating a lightweight dummy query that
        # simply sends a new message instead of editing one.
        chat_id = (
            update.effective_chat.id if hasattr(update, "effective_chat") else update.message.chat_id
        )
        class DummyQuery:
            def __init__(self, bot, chat_id):
                self.bot = bot
                self.chat_id = chat_id
            async def edit_message_text(self, text, reply_markup=None):
                await self.bot.send_message(chat_id=self.chat_id, text=text, reply_markup=reply_markup)
        dummy_query = DummyQuery(context.bot, chat_id)
        await self._show_custom_survey_menu(dummy_query, context)
    
    async def _send_custom_survey_menu(self, context):
        """(Deprecated) Wrapper kept for backward compatibility – delegates to the newer version."""
        # Try to retrieve last chat id from user_data fallback to admin_config
        chat_id = context.user_data.get('last_admin_chat_id')
        if not chat_id and hasattr(self, 'admin_config') and self.admin_config:
            chat_id = self.admin_config.get('ADMIN_CHAT_ID')
        if not chat_id:
            logger.warning("Could not determine chat_id for sending survey menu")
            return
        class DummyUpdate:
            def __init__(self, chat_id):
                self.effective_chat = type('obj', (), {'id': chat_id})
        dummy_update = DummyUpdate(chat_id)
        await self._send_custom_survey_menu(dummy_update, context)
        return
        """Send custom survey menu as new message."""
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        survey_data = context.user_data.get(f'{prefix}custom_survey', {'questions': []})
        questions = survey_data.get('questions', [])
        
        text = f"📝 ایجاد نظرسنجی سفارشی\n\n"
        text += f"📊 تعداد سوالات: {len(questions)}\n\n"
        
        if questions:
            text += "سوالات اضافه شده:\n"
            for i, q in enumerate(questions, 1):
                text += f"{i}. {q['text'][:50]}{'...' if len(q['text']) > 50 else ''}\n"
            text += "\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ افزودن سوال متنی", callback_data="add_text_question")],
            [InlineKeyboardButton("🔘 افزودن سوال چندگزینه‌ای", callback_data="add_choice_question")],
            [InlineKeyboardButton("⭐ افزودن سوال امتیازی", callback_data="add_rating_question")]
        ]
        
        if questions:
            keyboard.extend([
                [InlineKeyboardButton("🗑️ حذف آخرین سوال", callback_data="remove_last_question")],
                [InlineKeyboardButton("✅ تأیید نظرسنجی", callback_data="confirm_custom_survey")]
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_survey_options")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=context._chat_id,
            text=text,
            reply_markup=reply_markup
        )
    
    async def _handle_remove_last_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle removing the last question from custom survey."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        survey_data = context.user_data.get(f'{prefix}custom_survey', {'questions': []})
        questions = survey_data.get('questions', [])
        
        if questions:
            removed_question = questions.pop()
            context.user_data[f'{prefix}custom_survey'] = survey_data
            
            text = f"✅ سوال حذف شد: {removed_question['text'][:50]}{'...' if len(removed_question['text']) > 50 else ''}"
            await query.answer(text, show_alert=True)
        
        await self._show_custom_survey_menu(query, context)
        return FIELD_VALUE
    
    async def _handle_confirm_custom_survey(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle confirming custom survey creation."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        survey_data = context.user_data.get(f'{prefix}custom_survey', {'questions': []})
        questions = survey_data.get('questions', [])
        
        if not questions:
            await query.answer("❌ لطفاً حداقل یک سوال اضافه کنید.", show_alert=True)
            return FIELD_VALUE
        
        # Store survey type and data
        context.user_data[f'{prefix}survey_type'] = 'custom'
        context.user_data[f'{prefix}survey_data'] = survey_data
        
        # Show confirmation
        text = f"✅ نظرسنجی سفارشی با {len(questions)} سوال ایجاد شد!\n\n"
        text += "سوالات:\n"
        for i, q in enumerate(questions, 1):
            text += f"{i}. {q['text'][:50]}{'...' if len(q['text']) > 50 else ''}\n"
        
        keyboard = [[InlineKeyboardButton("🔙 بازگشت به فیلدها", callback_data="back_to_fields")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
        return FIELD_VALUE
    
    async def _handle_back_to_survey_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle back to survey options."""
        query = update.callback_query
        await query.answer()
        
        # Clear custom survey data if not confirmed
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        if f'{prefix}survey_type' not in context.user_data or context.user_data[f'{prefix}survey_type'] != 'custom':
            context.user_data.pop(f'{prefix}custom_survey', None)
        
        # Return to survey management
        await self._handle_survey_management(update, context)
        return FIELD_VALUE
    
    async def _handle_cancel_add_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle canceling question addition."""
        query = update.callback_query
        await query.answer()
        
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        # Clear temporary question data
        context.user_data.pop(f'{prefix}current_question_type', None)
        context.user_data.pop(f'{prefix}current_question_text', None)
        context.user_data.pop('survey_step', None)
        
        # Return to survey menu
        await self._show_custom_survey_menu(query, context)
        return FIELD_VALUE
    
    async def _update_survey_in_save_plan(self, plan_id, context):
        """Update save_plan method to handle custom surveys."""
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        
        survey_type = context.user_data.get(f'{prefix}survey_type', 'none')
        plan_type = context.user_data.get(f'{prefix}plan_type', 'subscription')
        plan_name = context.user_data.get(f'{prefix}name', 'نام پلن')
        
        if survey_type == 'custom' and plan_type in ['video_content', 'one_time_content']:
            survey_data = context.user_data.get(f'{prefix}survey_data', {})
            questions = survey_data.get('questions', [])
            
            if questions:
                # Create custom survey
                survey_service = SurveyService(self.db_queries)
                survey_id = survey_service.create_plan_survey(
                    plan_id, 
                    f"نظرسنجی {plan_name}", 
                    "نظرسنجی سفارشی"
                )
                
                if survey_id:
                    # Add custom questions
                    for question in questions:
                        question_id = survey_service.add_survey_question(
                            survey_id,
                            question['text'],
                            question['type'],
                            question.get('options', []),
                            question.get('required', True),
                            question.get('order', 1)
                        )
                        logger.info(f"Added custom question {question_id} to survey {survey_id}")
                    
                    logger.info(f"Created custom survey {survey_id} with {len(questions)} questions for plan {plan_id}")
                    return survey_id
                else:
                    logger.error(f"Failed to create custom survey for plan {plan_id}")
        
        return None

    # ---------------------------- Existing methods ---------------------------- #

    async def get_plan_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Collect description and show confirmation with USDT & IRR prices."""
        context.user_data['new_plan_description'] = update.message.text
        plan_data = context.user_data

        price_tether: float | None = plan_data.get('new_plan_price_tether') or plan_data.get('new_plan_price_usdt')
        price_irr: float | None = plan_data.get('new_plan_price')
        irr_price: int | None = None
        if price_tether is not None:
            usdt_rate = await get_usdt_to_irr_rate()
            if usdt_rate:
                irr_price = int(price_tether * usdt_rate * 10)  # toman→rial

        # ---------------- Compose price line for confirmation ----------------
        if price_tether is None and price_irr is not None:
            price_line = f"قیمت: {int(price_irr):,} ریال"
            # optionally show USDT eq.
            if irr_price is None:  # irr_price uses tether→irr path; if irr_price None, compute.
                irr_price = int(price_irr)
            price_line += " (مبنای ریال)"
        elif price_tether is None:
            price_line = "قیمت مشخص نشده"
        elif price_tether == 0:
            price_line = "قیمت: رایگان"
        else:
            price_line = f"قیمت: {price_tether} USDT"
            if irr_price is not None:
                price_line += f" (~{irr_price:,} ریال)"
        text = (
            f"آیا از افزودن پلن زیر اطمینان دارید؟\n\n"
            f"نام: {plan_data['new_plan_name']}\n"
            f"{price_line}\n"
            f"مدت: {plan_data.get('new_plan_duration_days')} روز\n"
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
            
            # Get base currency and price from new field system
            base_currency = plan_data.get('new_plan_base_currency', 'IRR')
            base_price = plan_data.get('new_plan_base_price')
            
            # Legacy price fields for backward compatibility
            price_tether = plan_data.get('new_plan_price_tether') or plan_data.get('new_plan_price_usdt')
            price_irr = plan_data.get('new_plan_price')
            
            # Use base_price if available, otherwise fall back to legacy
            if base_price is not None:
                if base_currency == 'USDT':
                    price_tether = float(base_price)
                    price_irr = None
                else:  # IRR
                    price_irr = float(base_price)
                    price_tether = None
            
            irr_price: int | None = None
            if price_tether is not None:
                usdt_rate = await get_usdt_to_irr_rate()
                if usdt_rate:
                    irr_price = int(price_tether * usdt_rate * 10)

            # Compose price line
            if price_tether is None and price_irr is not None:
                price_line = f"قیمت: {int(price_irr):,} ریال"
            elif price_tether is None and price_irr is None:
                price_line = "قیمت مشخص نشده"
            elif price_tether == 0:
                price_line = "قیمت: رایگان"
            else:
                price_line = f"قیمت: {price_tether} USDT"
                if irr_price is not None:
                    price_line += f" (~{irr_price:,} ریال)"
            text = (
                f"آیا از افزودن پلن زیر اطمینان دارید؟\n\n"
                f"نام: {plan_data.get('new_plan_name')}\n"
                f"{price_line}\n"
                f"مدت: {plan_data.get('new_plan_duration_days')} روز\n"
                f"ظرفیت: {plan_data.get('new_plan_capacity', 'نامحدود')}\n"
                f"توضیحات: {plan_data.get('new_plan_description')}"
            )
            keyboard = [[
                InlineKeyboardButton("✅ تایید و افزودن", callback_data="confirm_add_plan"),
                InlineKeyboardButton("⚙️ تنظیم سایر فیلدها", callback_data="add_more_fields"),
                InlineKeyboardButton("❌ لغو", callback_data="cancel_add_plan")
            ]]
            await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
            return ADD_CONFIRMATION
        else:
            # Build confirmation summary for edit flow
            plan_id = context.user_data.get('edit_plan_id')
            original_plan = dict(self.db_queries.get_plan_by_id(plan_id)) if plan_id else {}

            # Helper to fetch updated value or fallback to original
            def val(key, orig_key):
                return context.user_data.get(f'edit_plan_{key}', original_plan.get(orig_key))

            name = val('name', 'name')
            price_tether = context.user_data.get('edit_plan_price_usdt', original_plan.get('price_tether'))
            irr_price_line = ""
            if price_tether is not None:
                usdt_rate = await get_usdt_to_irr_rate()
                if usdt_rate:
                    irr_equiv = int(price_tether * usdt_rate * 10)
                    irr_price_line = f" (~{irr_equiv:,} ریال)"
            price_line = f"قیمت: {price_tether} USDT{irr_price_line}" if price_tether is not None else "قیمت: —"
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
            await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
            return EDIT_CONFIRMATION

    async def _handle_add_more_fields(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Callback from confirmation step to open extra-fields menu before saving."""
        query = update.callback_query
        await query.answer()
        logger.info("Opening extra fields menu in add mode")
        await self._show_fields_menu(query, context, mode="add")
        return FIELD_VALUE  # We stay in conversation until done

    async def _handle_set_field(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle selection of a specific plan field (add/edit flows)."""
        query = update.callback_query
        await query.answer()

        field_key = query.data.replace("set_field_", "")
        logger.info(f"[SET_FIELD] User chose field: {field_key}")

        # Store under both legacy and new keys so ALL downstream handlers work consistently
        context.user_data['current_field_key'] = field_key
        context.user_data['current_field'] = field_key

        # ---------------- Special FIELD UIs ----------------
        # 1) Category – hierarchical picker
        if field_key == "category_id":
            # Initialise navigation stack and open root categories
            context.user_data['category_nav_stack'] = []
            await self._show_category_children(query, context, parent_id=None)
            return FIELD_VALUE

        # 2) Videos – open video management UI
        if field_key == "videos":
            return await self._show_video_selection(query, context)

        # 3) Survey type – choose poll/none
        if field_key == "survey_type":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 نظرسنجی با Poll تلگرام", callback_data="survey_type_poll_based")],
                [InlineKeyboardButton("❌ بدون نظرسنجی", callback_data="survey_type_none")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="fields_back")],
            ])
            await query.edit_message_text(
                "📋 **انتخاب نوع نظرسنجی:**\n\n"
                "📊 **Poll تلگرام:** از قابلیت‌های آماده تلگرام استفاده کنید\n"
                "❌ **بدون نظرسنجی:** هیچ نظرسنجی نداشته باشید",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            return FIELD_VALUE

        # 4) Channel multi-select
        if field_key == "channels_json":
            selected_ids: Set[int] = context.user_data.get("plch_selected_ids", set())
            try:
                channels_info = (
                    json.loads(config.TELEGRAM_CHANNELS_INFO)
                    if isinstance(config.TELEGRAM_CHANNELS_INFO, str)
                    else config.TELEGRAM_CHANNELS_INFO
                )
            except Exception:
                channels_info = []
            keyboard = self._build_channel_select_keyboard(channels_info, selected_ids)
            await query.edit_message_text(
                "کانال‌های موردنظر را انتخاب و سپس دکمه تأیید را بزنید:",
                reply_markup=keyboard,
            )
            return FIELD_VALUE

        # ---------------- Default: prompt for value ----------------
        await self._prompt_for_field_value(query, field_key)
        return FIELD_VALUE
        # If admin chose videos, open video selection UI
        if field_key == "survey_type":
            # Show survey type options (Poll-based or none)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 نظرسنجی با Poll تلگرام", callback_data="survey_type_poll_based")],
                [InlineKeyboardButton("❌ بدون نظرسنجی", callback_data="survey_type_none")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="fields_back")]
            ])
            await query.edit_message_text(
                "📋 **انتخاب نوع نظرسنجی:**\n\n"
                "📊 **Poll تلگرام:** از قابلیت‌های آماده تلگرام استفاده کنید\n"
                "❌ **بدون نظرسنجی:** هیچ نظرسنجی نداشته باشید",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return FIELD_VALUE
        if field_key == "videos":
            return await self._show_video_selection(query, context)
        # Special handling for channel multi-select field
        if field_key == "channels_json":
            selected_ids: Set[int] = context.user_data.get("plch_selected_ids", set())
            # Parse TELEGRAM_CHANNELS_INFO
            try:
                channels_info = (
                    json.loads(config.TELEGRAM_CHANNELS_INFO)
                    if isinstance(config.TELEGRAM_CHANNELS_INFO, str)
                    else config.TELEGRAM_CHANNELS_INFO
                )
            except Exception:
                channels_info = []
            keyboard = self._build_channel_select_keyboard(channels_info, selected_ids)
            await query.edit_message_text(
                "کانال‌های موردنظر را انتخاب و سپس دکمه تأیید را بزنید:",
                reply_markup=keyboard,
            )
            return FIELD_VALUE

        await self._prompt_for_field_value(query, field_key)
        return FIELD_VALUE
    
    async def _prompt_for_field_value(self, query, field_key):
        """Prompt admin to enter value for a specific field with cancel button."""
        field_label = self._PLAN_FIELD_LABELS.get(field_key, field_key)
        
        # If the field is base_currency we present a choice keyboard instead of asking for text
        if field_key == 'base_currency':
            keyboard = [
                [InlineKeyboardButton("🪙 تتر (USDT)", callback_data="base_currency_USDT")],
                [InlineKeyboardButton("﷼ ریال (IRR)", callback_data="base_currency_IRR")],
                [InlineKeyboardButton("❌ لغو و بازگشت", callback_data="cancel_field_input")]
            ]
            await safe_edit_message_text(query, "ارز پایه را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))
            return  # wait for callback

        # Standard text input prompt with cancel button
        text = f"✏️ وارد کردن {field_label}:\n\n"

        # Add field-specific instructions
        if field_key in ['base_price', 'price_tether']:
            text += "مقدار عددی وارد کنید (مثال: 10.5)\n"
        elif field_key == 'duration_days':
            # Provide unlimited option through inline keyboard
            text += "مدت زمان پلن را به روز وارد کنید (مثال: 30)\n"
            keyboard = [
                [InlineKeyboardButton("♾ نامحدود", callback_data="duration_unlimited")],
                [InlineKeyboardButton("❌ لغو و بازگشت", callback_data="cancel_field_input")]
            ]
            await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
            return  # wait for unlimited or cancel callbacks
        elif field_key == 'capacity':
            text += "حداکثر تعداد کاربر را وارد کنید (مثال: 100)\n"
        elif field_key == 'expiration_date':
            text += "تاریخ را به فرمت YYYY-MM-DD وارد کنید (مثال: 2024-12-31)\n"

        text += "\nدستورات:\n"
        text += "• /skip - رد کردن این فیلد"

        keyboard = [
            [InlineKeyboardButton("❌ لغو و بازگشت", callback_data="cancel_field_input")]
        ]

        await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def _handle_base_currency_selection(self, update, context):
        """Save selected base currency and return to fields menu."""
        query = update.callback_query
        await query.answer()
        currency = query.data.split('_')[-1]  # USDT or IRR
        mode = context.user_data.get('extra_mode', 'add')
        prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
        context.user_data[f"{prefix}base_currency"] = currency
        # Clear current field selection
        context.user_data.pop('current_field_key', None)
        # Refresh menu
        summary_text = self._generate_summary_text(context, mode) + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
        await query.edit_message_text(f"✅ ارز پایه «{currency}» انتخاب شد.\n\n" + summary_text, reply_markup=self._build_fields_keyboard(context, mode))
        return FIELD_VALUE
    
    async def _handle_cancel_field_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle cancel button press during field input."""
        query = update.callback_query
        await query.answer()
        
        # Clear current field
        context.user_data.pop('current_field_key', None)
        
        # Return to fields menu
        mode = context.user_data.get('extra_mode', 'add')
        text = self._generate_summary_text(context, mode) + "\n\nستون مورد نظر را برای مقداردهی انتخاب کنید:"
        reply_markup = self._build_fields_keyboard(context, mode)
        
        await query.edit_message_text("❌ عملیات لغو شد.\n\n" + text, reply_markup=reply_markup)
        return FIELD_VALUE

    async def _handle_field_value_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receives value for previously selected field and stores it in user_data."""
        # Check if this is survey question input
        survey_step = context.user_data.get('survey_step')
        if survey_step == 'question_text':
            return await self._handle_question_text_input(update, context)
        elif survey_step == 'question_options':
            return await self._handle_question_options_input(update, context)
        
        field_key: str = context.user_data.get('current_field_key')
        if not field_key:
            await update.message.reply_text("خطا: فیلدی انتخاب نشده است.")
            return FIELD_VALUE
        val_text = update.message.text.strip()
        
        # Cancel is now handled by button, not command
        
        # Handle skip to clear value
        if val_text == '/skip':
            parsed_val = None
        else:
            parsed_val: Any = val_text
        try:
            if field_key in {"price", "original_price_irr", "price_tether", "original_price_usdt", "base_price"}:
                if val_text != '/skip':
                    parsed_val = float(val_text)
            elif field_key in {"duration_days", "capacity", "display_order"}:
                if val_text != '/skip':
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
                await update.message.reply_text("فرمت تاریخ اشتباه است. لطفاً تاریخ را به فرمت YYYY-MM-DD وارد کنید یا /skip برای رد کردن.")
            else:
                await update.message.reply_text("فرمت مقدار وارد شده اشتباه است. دوباره تلاش کنید یا /skip برای رد کردن.")
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

    async def confirm_add_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle confirm_add_plan callback - validates and saves the plan."""
        return await self.save_plan(update, context)

    async def save_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        plan_data = context.user_data
        name = plan_data.get('new_plan_name')
        duration_days = plan_data.get('new_plan_duration_days') or plan_data.get('new_plan_duration')
        # Basic validation
        if not name:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text("❌ لطفاً ابتدا نام پلن را وارد کنید.")
            return FIELD_VALUE
        if duration_days is None:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text("❌ لطفاً مدت (روز) را تعیین کنید.")
            return FIELD_VALUE
        
        # By default, plans are active and public
        is_active = True
        is_public = True
        
        # Special case for 'free_30d' plan to be private by default
        if name == 'free_30d':
            is_public = False

                # ---------------- New Price Handling ----------------
        # Get base currency and price from user data
        base_currency = plan_data.get('new_plan_base_currency', 'IRR')
        base_price = plan_data.get('new_plan_base_price')
        
        # Clean up numeric parsing
        def _parse_float(val: Any | None) -> float | None:
            if val is None:
                return None
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
        
        base_price = _parse_float(base_price)
        
        # Validation: base_price must be provided (unless it's a free plan)
        if base_price is None:
            await update.callback_query.answer()
            await update.callback_query.message.reply_text("❌ لطفاً قیمت پایه را وارد کنید.")
            return FIELD_VALUE
        
        # Validate base_currency
        if base_currency not in ['IRR', 'USDT']:
            base_currency = 'IRR'  # Default fallback
        
        # For backward compatibility, set legacy price fields based on base currency
        price_tether = base_price if base_currency == 'USDT' else None
        irr_price = base_price if base_currency == 'IRR' else None
        
        # Ensure at least one price field is set to avoid NULL constraint
        if irr_price is None and price_tether is not None:
            # Convert USDT to IRR for the required price field
            usdt_rate = await get_usdt_to_irr_rate()
            if usdt_rate:
                irr_price = int(price_tether * usdt_rate * 10)
            else:
                irr_price = 0  # Fallback if rate unavailable
        elif irr_price is None and price_tether is None:
            irr_price = 0  # Default fallback

                # Collect extra fields dynamically
        extra_kwargs = {}
        # Exclude keys that are already passed explicitly to add_plan to avoid duplicates
        explicit_fields = {
            'name', 'price', 'price_tether', 'original_price_irr', 'original_price_usdt',
            'duration', 'duration_days', 'capacity', 'description', 'is_active', 'is_public',
            'price_usdt', 'price_irr', 'base_currency', 'base_price',
            # Video and survey fields - handled separately
            'videos', 'video_data', 'selected_videos', 'survey_type', 'custom_survey'
        }
        for field in self._PLAN_FIELD_LABELS.keys():
            if field in explicit_fields:
                continue
            key = f"new_plan_{field}"
            if key in plan_data:
                extra_kwargs[field] = plan_data[key]

        plan_id = self.db_queries.add_plan(
            name=name,
            price=int(irr_price) if irr_price is not None else None,
            price_tether=price_tether if price_tether is not None else None,
            original_price_irr=None,
            original_price_usdt=None,
            duration_days=duration_days,
            capacity=plan_data.get('new_plan_capacity'),
            description=plan_data.get('new_plan_description'),
            is_active=is_active,
            is_public=is_public,
            base_currency=base_currency,
            base_price=base_price,
            **extra_kwargs
        )
        
        if plan_id:
            # Handle video assignments with new video_data structure
            video_data = plan_data.get('new_plan_video_data', {})
            if video_data:
                # Sort videos by order
                sorted_videos = sorted(video_data.items(), key=lambda x: x[1].get('order', 0))
                for video_id, video_info in sorted_videos:
                    video_service.add_video_to_plan(
                        plan_id, 
                        video_id, 
                        display_order=video_info.get('order', 0),
                        custom_caption=video_info.get('custom_caption', '')
                    )
                logger.info(f"Added {len(video_data)} videos with captions to plan {plan_id}")
            
            # Fallback to old selected_videos format for backward compatibility
            elif 'new_plan_selected_videos' in plan_data:
                selected_videos = plan_data.get('new_plan_selected_videos', [])
                if selected_videos:
                    for i, video_id in enumerate(selected_videos):
                        video_service.add_video_to_plan(plan_id, video_id, display_order=i)
                    logger.info(f"Added {len(selected_videos)} videos to plan {plan_id} (legacy format)")
            
            # Handle survey creation
            survey_type = plan_data.get('new_plan_survey_type', 'none')
            plan_type = plan_data.get('new_plan_plan_type', 'subscription')
            
            if survey_type == 'default' and plan_type in ['video_content', 'one_time_content']:
                survey_id = survey_service.create_default_survey_for_plan(plan_id, name)
                if survey_id:
                    logger.info(f"Created default survey {survey_id} for plan {plan_id}")
                else:
                    logger.error(f"Failed to create default survey for plan {plan_id}")
            elif survey_type == 'custom':
                # Handle custom surveys with questions
                survey_data = plan_data.get('new_plan_survey_data', {})
                questions = survey_data.get('questions', [])
                
                if questions:
                    # Create custom survey with questions
                    survey_id = survey_service.create_plan_survey(
                        plan_id, 
                        f"نظرسنجی {name}", 
                        "نظرسنجی سفارشی"
                    )
                    
                    if survey_id:
                        # Add custom questions
                        for question in questions:
                            question_id = survey_service.add_survey_question(
                                survey_id,
                                question['text'],
                                question['type'],
                                question.get('options', []),
                                question.get('required', True),
                                question.get('order', 1)
                            )
                            logger.info(f"Added custom question {question_id} to survey {survey_id}")
                        
                        logger.info(f"Created custom survey {survey_id} with {len(questions)} questions for plan {plan_id}")
                    else:
                        logger.error(f"Failed to create custom survey for plan {plan_id}")
                else:
                    # Create empty custom survey for later population
                    survey_id = survey_service.create_plan_survey(
                        plan_id, 
                        f"نظرسنجی {name}", 
                        "نظرسنجی سفارشی - لطفاً سوالات را اضافه کنید"
                    )
                    if survey_id:
                        logger.info(f"Created empty custom survey {survey_id} for plan {plan_id}")
                    else:
                        logger.error(f"Failed to create custom survey for plan {plan_id}")
            elif survey_type == 'poll_based':
                # Handle poll-based surveys
                survey_questions = plan_data.get('new_plan_survey_questions', [])
                
                if survey_questions:
                    # Use the upsert_plan_survey method to save poll-based survey
                    from database.queries import DatabaseQueries
                    success = DatabaseQueries.upsert_plan_survey(plan_id, survey_questions)
                    
                    if success:
                        logger.info(f"Created poll-based survey with {len(survey_questions)} questions for plan {plan_id}")
                    else:
                        logger.error(f"Failed to create poll-based survey for plan {plan_id}")
                else:
                    logger.warning(f"Poll-based survey type selected but no questions found for plan {plan_id}")
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

    # --- Video Selection & Paging --- #
    VIDEO_PAGE_SIZE = 8

    async def _show_video_selection(self, query, context: ContextTypes.DEFAULT_TYPE, page: int = 1):
        """Display paginated list of available videos for selection (read-only draft)."""
        await query.answer()
        videos, total = video_service.list_all_videos(page, self.VIDEO_PAGE_SIZE)
        total_pages = max(1, (total + self.VIDEO_PAGE_SIZE - 1) // self.VIDEO_PAGE_SIZE)
        if page > total_pages:
            page = total_pages
        # build keyboard
        keyboard = []
        # build text list
        text = f"🎬 **انتخاب ویدئوها** (صفحه {page}/{total_pages})\n\n"
        if not videos:
            text += "⚠️ هیچ ویدئویی موجود نیست. با دکمه ⬆️ آپلود کنید."
        else:
            prefix = 'new_plan_' if context.user_data.get('extra_mode','add')=='add' else 'edit_plan_'
            selected: dict = context.user_data.get(f"{prefix}video_data", {})
            for i, vid in enumerate(videos, 1):
                sel = '✅' if vid['id'] in selected else '▫️'
                text += f"{sel} {i}. {vid['display_name']}\n"
                keyboard.append([InlineKeyboardButton(f"{sel} {vid['display_name'][:25]}", callback_data=f"toggle_video_{vid['id']}_{page}")])
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"vidsel_page_{page-1}"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"vidsel_page_{page+1}"))
        if nav_row:
            keyboard.append(nav_row)
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="fields_back")])
        if videos and selected:
            keyboard.append([InlineKeyboardButton("✅ تأیید انتخاب", callback_data="confirm_video_selection")])
        keyboard.append([InlineKeyboardButton("➕ افزودن ویدئو جدید", callback_data="upload_new_video")])
        keyboard.append([InlineKeyboardButton("❌ هیچکدام", callback_data="clear_video_selection")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return FIELD_VALUE

    async def _handle_toggle_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        parts = query.data.split('_')
        video_id = int(parts[2])
        page = int(parts[3]) if len(parts)>3 else 1
        mode = context.user_data.get('extra_mode','add')
        prefix = 'new_plan_' if mode=='add' else 'edit_plan_'
        video_data: dict = context.user_data.get(f"{prefix}video_data", {})
        if video_id in video_data:
            video_data.pop(video_id)
        else:
            vid = video_service.get_video_by_id(video_id)
            if vid:
                video_data[video_id] = {'display_name': vid['display_name'], 'custom_caption':'', 'order': len(video_data)+1}
        context.user_data[f"{prefix}video_data"] = video_data
        return await self._show_video_selection(query, context, page)

    async def _handle_confirm_video_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        # After selection redirect to caption manager
        return await self._handle_manage_video_captions(update, context)

    async def _handle_video_page_nav(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle navigation callbacks vid sel page."""
        query = update.callback_query
        page = int(query.data.split('_')[-1])
        return await self._show_video_selection(query, context, page)

    async def _handle_clear_video_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clear all video selections and go back to field selection."""
        query = update.callback_query
        await query.answer()
        mode = context.user_data.get('extra_mode','add')
        prefix = 'new_plan_' if mode=='add' else 'edit_plan_'
        context.user_data[f"{prefix}video_data"] = {}
        # Go back to field selection
        return await self._show_field_selection(query, context)

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

        # New price handling logic
        base_currency = context.user_data.get('edit_plan_base_currency')
        base_price = context.user_data.get('edit_plan_base_price')
        
        update_kwargs = {
            'name': context.user_data.get('edit_plan_name'),
            'duration_days': context.user_data.get('edit_plan_duration'),
            'capacity': context.user_data.get('edit_plan_capacity'),
            'description': context.user_data.get('edit_plan_description'),
        }
        
        # Handle base currency and price updates
        if base_currency is not None:
            update_kwargs['base_currency'] = base_currency
        if base_price is not None:
            update_kwargs['base_price'] = float(base_price)
            # Update legacy price fields for backward compatibility
            if base_currency == 'USDT':
                update_kwargs['price_tether'] = float(base_price)
                update_kwargs['price'] = None  # Clear IRR price
            elif base_currency == 'IRR':
                update_kwargs['price'] = int(float(base_price))
                update_kwargs['price_tether'] = None  # Clear USDT price
        
        # Collect values for any additional fields that were set via the extra-fields menu
        # Exclude main fields to avoid conflicts
        main_fields = {
            'name', 'duration_days', 'capacity', 'description', 'base_currency', 'base_price',
            # Video and survey fields - handled separately
            'videos', 'video_data', 'selected_videos', 'survey_type', 'custom_survey'
        }
        for field in self._PLAN_FIELD_LABELS.keys():
            if field not in main_fields:
                val = context.user_data.get(f'edit_plan_{field}')
                if val is not None:
                    update_kwargs[field] = val
        # remove None entries
        update_kwargs = {k: v for k, v in update_kwargs.items() if v is not None}

        if update_kwargs:
            self.db_queries.update_plan(plan_id, **update_kwargs)
            
            # Handle video updates
            video_data = context.user_data.get('edit_plan_video_data')
            if video_data is not None:
                # Clear existing videos for this plan
                video_service.clear_plan_videos(plan_id)
                
                # Add updated videos
                if video_data:
                    sorted_videos = sorted(video_data.items(), key=lambda x: x[1].get('order', 0))
                    for video_id, video_info in sorted_videos:
                        video_service.add_video_to_plan(
                            plan_id, 
                            video_id, 
                            display_order=video_info.get('order', 0),
                            custom_caption=video_info.get('custom_caption', '')
                        )
                    logger.info(f"Updated {len(video_data)} videos for plan {plan_id}")
            
            # Handle survey updates
            survey_type = context.user_data.get('edit_plan_survey_type')
            if survey_type is not None:
                if survey_type == 'custom':
                    custom_survey = context.user_data.get('edit_plan_custom_survey')
                    if custom_survey and custom_survey.get('questions'):
                        survey_id = survey_service.create_custom_survey_for_plan(
                            plan_id, 
                            f"Custom Survey for {context.user_data.get('edit_plan_name', 'Plan')}",
                            custom_survey['questions']
                        )
                        if survey_id:
                            logger.info(f"Created custom survey {survey_id} for plan {plan_id}")
                elif survey_type == 'poll_based':
                    survey_questions = context.user_data.get('edit_plan_survey_questions', [])
                    if survey_questions:
                        success = DatabaseQueries.upsert_plan_survey(plan_id, survey_questions)
                        if success:
                            logger.info(f"Updated poll-based survey for plan {plan_id} with {len(survey_questions)} questions")
                        else:
                            logger.error(f"Failed to update poll-based survey for plan {plan_id}")
                elif survey_type == 'default':
                    plan_type = context.user_data.get('edit_plan_plan_type', 'subscription')
                    if plan_type in ['video_content', 'one_time_content']:
                        survey_id = survey_service.create_default_survey_for_plan(
                            plan_id, 
                            context.user_data.get('edit_plan_name', 'Plan')
                        )
                        if survey_id:
                            logger.info(f"Created default survey {survey_id} for plan {plan_id}")
            
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
                ADD_CURRENCY: [CallbackQueryHandler(self.handle_select_currency, pattern='^currency_')],
                ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plan_price)],
                ADD_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plan_duration)],
                ADD_CAPACITY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plan_capacity),
                    CommandHandler('skip', self.get_plan_capacity)
                ],
                ADD_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_plan_description)],
                ADD_CONFIRMATION: [
                     CallbackQueryHandler(self.confirm_add_plan, pattern='^confirm_add_plan$'),
                     CallbackQueryHandler(self._handle_add_more_fields, pattern='^add_more_fields$'),
                     CallbackQueryHandler(self.cancel_add_plan, pattern='^cancel_add_plan$')
                 ],
                 FIELD_VALUE: [
                     CallbackQueryHandler(self._handle_set_field, pattern='^set_field_'),
                 CallbackQueryHandler(self._handle_category_callback, pattern='^category_'),
                     CallbackQueryHandler(self._handle_fields_done, pattern='^fields_done$'),
                     CallbackQueryHandler(self._handle_fields_back, pattern='^fields_back$'),
                      CallbackQueryHandler(self._plan_channel_picker_callback, pattern='^plch.*'),
                      CallbackQueryHandler(self._handle_base_currency_selection, pattern='^base_currency_'),
                      CallbackQueryHandler(self._handle_plan_type_selection, pattern='^plan_type_'),
                       CallbackQueryHandler(self._handle_unlimited_duration, pattern='^duration_unlimited$'),
                      CallbackQueryHandler(self._handle_video_management, pattern='^manage_videos$'),
                      CallbackQueryHandler(self._handle_video_toggle, pattern='^toggle_video_'),
                      CallbackQueryHandler(self._handle_confirm_video_selection, pattern='^confirm_video_selection$'),
                       CallbackQueryHandler(self._handle_clear_video_selection, pattern='^clear_video_selection$'),
                      CallbackQueryHandler(self._handle_survey_management, pattern='^manage_survey$'),
                      CallbackQueryHandler(self._handle_survey_option, pattern='^(create_default_survey|create_custom_survey|no_survey)$'),
                      CallbackQueryHandler(self._handle_back_to_fields, pattern='^back_to_fields$'),
                      CallbackQueryHandler(self._handle_add_question, pattern='^add_(text|choice|rating)_question$'),
                      CallbackQueryHandler(self._handle_remove_last_question, pattern='^remove_last_question$'),
                      CallbackQueryHandler(self._handle_confirm_custom_survey, pattern='^confirm_custom_survey$'),
                      CallbackQueryHandler(self._handle_back_to_survey_options, pattern='^back_to_survey_options$'),
                      CallbackQueryHandler(self._handle_cancel_add_question, pattern='^cancel_add_question$'),
                      CallbackQueryHandler(self._handle_cancel_field_input, pattern='^cancel_field_input$'),
                      CallbackQueryHandler(self._handle_manage_video_captions, pattern='^manage_video_captions$'),
                      CallbackQueryHandler(self._handle_edit_caption, pattern='^edit_caption_'),
                      CallbackQueryHandler(self._handle_cancel_caption_edit, pattern='^cancel_caption_edit$'),
                      CallbackQueryHandler(self._handle_video_help, pattern='^video_help$'),
                      CallbackQueryHandler(self._handle_force_confirm_videos, pattern='^force_confirm_videos$'),
                      CallbackQueryHandler(self._handle_back_to_video_selection, pattern='^back_to_video_selection$'),
                     MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_caption_input),
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
                 CallbackQueryHandler(self._handle_category_callback, pattern='^category_'),
                     CallbackQueryHandler(self._handle_fields_done, pattern='^fields_done$'),
                     CallbackQueryHandler(self._handle_fields_back, pattern='^fields_back$'),
                      CallbackQueryHandler(self._plan_channel_picker_callback, pattern='^plch.*'),
                      CallbackQueryHandler(self._handle_base_currency_selection, pattern='^base_currency_'),
                      CallbackQueryHandler(self._handle_plan_type_selection, pattern='^plan_type_'),
                       CallbackQueryHandler(self._handle_unlimited_duration, pattern='^duration_unlimited$'),
                      CallbackQueryHandler(self._handle_video_management, pattern='^manage_videos$'),
                      CallbackQueryHandler(self._handle_video_toggle, pattern='^toggle_video_'),
                      CallbackQueryHandler(self._handle_confirm_video_selection, pattern='^confirm_video_selection$'),
                       CallbackQueryHandler(self._handle_clear_video_selection, pattern='^clear_video_selection$'),
                      CallbackQueryHandler(self._handle_survey_management, pattern='^manage_survey$'),
                      CallbackQueryHandler(self._handle_survey_option, pattern='^(create_default_survey|create_custom_survey|no_survey)$'),
                      CallbackQueryHandler(self._handle_back_to_fields, pattern='^back_to_fields$'),
                      CallbackQueryHandler(self._handle_add_question, pattern='^add_(text|choice|rating)_question$'),
                      CallbackQueryHandler(self._handle_remove_last_question, pattern='^remove_last_question$'),
                      CallbackQueryHandler(self._handle_confirm_custom_survey, pattern='^confirm_custom_survey$'),
                      CallbackQueryHandler(self._handle_back_to_survey_options, pattern='^back_to_survey_options$'),
                      CallbackQueryHandler(self._handle_cancel_add_question, pattern='^cancel_add_question$'),
                      CallbackQueryHandler(self._handle_cancel_field_input, pattern='^cancel_field_input$'),
                      CallbackQueryHandler(self._handle_manage_video_captions, pattern='^manage_video_captions$'),
                      CallbackQueryHandler(self._handle_edit_caption, pattern='^edit_caption_'),
                      CallbackQueryHandler(self._handle_cancel_caption_edit, pattern='^cancel_caption_edit$'),
                      CallbackQueryHandler(self._handle_video_help, pattern='^video_help$'),
                      CallbackQueryHandler(self._handle_force_confirm_videos, pattern='^force_confirm_videos$'),
                      CallbackQueryHandler(self._handle_back_to_video_selection, pattern='^back_to_video_selection$'),
                     MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_caption_input),
                      MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_field_value_input)
                 ],
                 EDIT_CONFIRMATION: [
                      CallbackQueryHandler(self.update_plan, pattern='^confirm_edit_plan$'),
                      CallbackQueryHandler(self._handle_fields_back, pattern='^fields_back$'),
                     CallbackQueryHandler(self.cancel_edit_plan, pattern='^cancel_edit_plan$')
                 ]
            },
            fallbacks=[CallbackQueryHandler(self.cancel_edit_plan, pattern='^cancel_edit_plan$')],
            per_user=True,
            per_chat=True,
        )

        return [add_plan_handler, edit_plan_handler]


