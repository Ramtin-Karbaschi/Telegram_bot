"""
Payment handlers for the Daraei Academy Telegram bot
"""

from services.crypto_payment_service import CryptoPaymentService
from services.zarinpal_service import ZarinpalPaymentService # Added for Zarinpal
from config import CRYPTO_WALLET_ADDRESS, CRYPTO_PAYMENT_TIMEOUT_MINUTES, RIAL_GATEWAY_URL, CRYPTO_GATEWAY_URL, PAYMENT_CONVERSATION_TIMEOUT # Added CRYPTO_WALLET_ADDRESS, CRYPTO_PAYMENT_TIMEOUT_MINUTES

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, LabeledPrice, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode # Added for message formatting
from telegram.error import BadRequest  # Handle message not modified
import config # Added for TELEGRAM_CHANNELS_INFO
import logging
from ..subscription.subscription_handlers import activate_or_extend_subscription
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, 
    MessageHandler, filters, CallbackQueryHandler
)
logger = logging.getLogger(__name__)

# --- Patch telegram CallbackQuery.answer to safely ignore "query is too old" / timeout errors ---
from telegram._callbackquery import CallbackQuery as _CallbackQueryOriginal
_original_answer = _CallbackQueryOriginal.answer

async def _safe_answer(self, *args, **kwargs):  # type: ignore[override]
    try:
        return await _original_answer(self, *args, **kwargs)
    except BadRequest as e:
        if any(tok in str(e).lower() for tok in (
            'query is too old',
            'response timeout expired',
            'query id is invalid'
        )):
            logger.warning(f"[safe_answer_patch] Ignored BadRequest while answering callback: {e}")
            return None
        raise

_CallbackQueryOriginal.answer = _safe_answer
# ----------------------------------------------------------------------

from datetime import datetime, timedelta
import uuid
import os
import math
# import config # Direct access to SUBSCRIPTION_PLANS removed
from database.queries import DatabaseQueries as Database
from utils.price_utils import get_usdt_to_irr_rate, convert_irr_to_usdt, convert_usdt_to_irr
from config import RIAL_GATEWAY_URL, CRYPTO_GATEWAY_URL # Assuming these are still needed from config
from utils.keyboards import (
    get_subscription_plans_keyboard, get_payment_methods_keyboard,
    get_back_to_plans_button, get_back_to_payment_methods_button,
    get_main_menu_keyboard, get_ask_discount_keyboard, get_back_to_ask_discount_keyboard
)
from utils.keyboards.categories_keyboard import get_categories_keyboard

from telegram.constants import ParseMode

async def back_to_main_menu_from_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to main menu from categories - show user profile instead."""
    query = update.callback_query
    user_id = update.effective_user.id
    if query:
        await query.answer()
        # Import and call view_active_subscription to show user profile/status
        from handlers.subscription.subscription_handlers import view_active_subscription
        await view_active_subscription(update, context)

# ---------------- Count-down timer helpers -----------------
from telegram.ext import Job

def _cancel_existing_payment_timer(context: ContextTypes.DEFAULT_TYPE):
    """Cancel any running payment timer job for the current chat/user."""
    job: Job | None = context.user_data.pop('payment_timer_job', None)
    if job:
        job.schedule_removal()

async def _payment_timer_callback(context: ContextTypes.DEFAULT_TYPE):
    """Update the payment message countdown each minute and refresh price on expiry."""
    job_data = context.job.data
    chat_id = job_data['chat_id']
    message_id = job_data['message_id']
    expiry: datetime = job_data['expiry']
    user_data = job_data['user_data']  # reference to same dict

    now = datetime.utcnow()
    remaining = expiry - now
    try:
        if remaining.total_seconds() <= 0:
            # Price expired – recalc price & reset timer
            selected_plan = user_data.get('selected_plan_details')
            final_price_rial = user_data.get('dynamic_irr_price')
            # Force refresh USDT rate
            new_rate = await get_usdt_to_irr_rate(force_refresh=True)
            # USDT price remains constant (product base price), no need to recalculate
            expiry = now + timedelta(minutes=CRYPTO_PAYMENT_TIMEOUT_MINUTES)
            job_data['expiry'] = expiry
            remaining = expiry - now
        # Format remaining mm:ss
        mins, secs = divmod(int(remaining.total_seconds()), 60)
        timer_str = f"{mins:02d}:{secs:02d}"
        usdt_display = user_data.get('live_usdt_price')
        usdt_str = f"{int(usdt_display)}" if usdt_display is not None else "N/A"
        text = (
            f"{user_data['payment_message_header']}\n\n"
            f"⏳ اعتبار قیمت: {timer_str} دقیقه\n"
            f"💵 مبلغ تتر: {usdt_str} USDT (شبکه) — کارمزد را جداگانه بپردازید"
        )
        context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=get_payment_methods_keyboard(),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.warning("Payment timer update failed: %s", e)


from utils.constants import (
    SUBSCRIPTION_PLANS_MESSAGE, PAYMENT_METHOD_MESSAGE,
    CRYPTO_PAYMENT_UNIQUE_AMOUNT_MESSAGE, # Changed from CRYPTO_PAYMENT_MESSAGE
    PAYMENT_SUCCESS_MESSAGE,
    PAYMENT_ERROR_MESSAGE # Changed from PAYMENT_FAILED_MESSAGE
)
from utils.constants.all_constants import (
    VERIFY_ZARINPAL_PAYMENT_CALLBACK, 
    TEXT_GENERAL_BACK_TO_MAIN_MENU, 
    CALLBACK_BACK_TO_MAIN_MENU
) # Added for Zarinpal
from utils.constants.all_constants import ZARINPAL_VERIFY_SUCCESS_STATUS, ZARINPAL_REQUEST_SUCCESS_STATUS # Added for Zarinpal status check
from utils.helpers import calculate_days_left, generate_qr_code
from handlers.subscription.subscription_handlers import activate_or_extend_subscription
from utils.user_actions import UserAction
from handlers.subscription.subscription_handlers import activate_or_extend_subscription

# Conversation states
SELECT_PLAN, ASK_DISCOUNT, VALIDATE_DISCOUNT, SELECT_PAYMENT_METHOD, VERIFY_PAYMENT, WAIT_FOR_TX_HASH = range(6)

async def back_to_main_menu_from_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت به منوی اصلی و پاک‌سازی context پرداخت"""
    from handlers.subscription.subscription_handlers import view_active_subscription
    query = update.callback_query
    user_id = update.effective_user.id
    Database.update_user_activity(user_id)
    context.user_data.clear()
    return await view_active_subscription(update, context)

async def safe_edit_message_text(message, **kwargs):
    """Edit message text safely, ignoring 'Message is not modified' errors."""
    try:
        await message.edit_text(**kwargs)
    except BadRequest as e:
        if 'Message is not modified' in str(e):
            pass  # Silently ignore
        else:
            raise

async def start_subscription_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for the subscription flow. Displays subscription plans."""
    query = update.callback_query
    user_id = update.effective_user.id

    # If called via CallbackQuery
    if query:
        await query.answer()

        # Detect optional category id from callback data (products_menu_<id>)
        category_id = None
        # Handle different entry points
        if query.data in ("start_subscription_flow", "products_menu"):
            # Always show top-level categories
            await safe_edit_message_text(
                query.message,
                text="📋 دسته‌بندی محصولات\n\nلطفاً یک دسته‌بندی را انتخاب کنید:",
                reply_markup=get_categories_keyboard(),
                parse_mode=ParseMode.HTML,
            )
            return SELECT_PLAN
        elif query.data == "back_to_plans":
            # Try to restore the last parent category from user_data
            parent_id = context.user_data.get('current_parent_category_id')
            if parent_id:
                from database.queries import DatabaseQueries as _DB
                parent_cat = _DB.get_category_by_id(parent_id)
                children = _DB.get_children_categories(parent_id)
                if children:
                    category_name = parent_cat.get('name', 'دسته‌بندی') if parent_cat else 'دسته‌بندی'
                    await safe_edit_message_text(
                        query.message,
                        text=f"📋 {category_name}\n\nلطفاً یک زیردسته را انتخاب کنید:",
                        reply_markup=get_categories_keyboard(parent_id=parent_id),
                        parse_mode=ParseMode.HTML,
                    )
                else:
                    keyboard = get_subscription_plans_keyboard(user_id, category_id=parent_id)
                    category_name = parent_cat.get('name', 'محصولات') if parent_cat else 'محصولات'
                    await safe_edit_message_text(
                        query.message,
                        text=f"🛍️ {category_name}\n\nلطفاً محصول مورد نظر خود را انتخاب کنید:",
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML,
                    )
                return SELECT_PLAN
            else:
                # Fallback to top-level categories
                await safe_edit_message_text(
                    query.message,
                    text="📋 دسته‌بندی محصولات\n\nلطفاً یک دسته‌بندی را انتخاب کنید:",
                    reply_markup=get_categories_keyboard(),
                    parse_mode=ParseMode.HTML,
                )
                return SELECT_PLAN

        # products_menu_<id>  -- extract numeric id safely
        if query.data.startswith("products_menu_"):
            possible_id = query.data.split("_")[-1]
            if possible_id.isdigit():
                category_id = int(possible_id)
        logger.info("Extracted category_id: %s from callback_data: '%s'", category_id, query.data)
        if category_id is None:
            # No valid category id found; ignore and exit handler gracefully
            return

        from database.queries import DatabaseQueries as _DB
        parent_cat = _DB.get_category_by_id(category_id)
        children = _DB.get_children_categories(category_id)
        if children:
            # Store current parent category for back navigation
            context.user_data['current_parent_category_id'] = category_id
            # Show sub-categories instead of plans
            category_name = parent_cat.get('name', 'دسته‌بندی') if parent_cat else 'دسته‌بندی'
            await safe_edit_message_text(
                query.message,
                text=f"📋 {category_name}\n\nلطفاً یک زیردسته را انتخاب کنید:",
                reply_markup=get_categories_keyboard(parent_id=category_id),
                parse_mode=ParseMode.HTML,
            )
        else:
            # Leaf: show plans
            # Store parent category id (if any) for back navigation
            context.user_data['current_parent_category_id'] = parent_cat.get('parent_id') if parent_cat else None
            keyboard = get_subscription_plans_keyboard(user_id, category_id=category_id)
            category_name = parent_cat.get('name', 'محصولات') if parent_cat else 'محصولات'
            await safe_edit_message_text(
                query.message,
                text=f"🛍️ {category_name}\n\nلطفاً محصول مورد نظر خود را انتخاب کنید:",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            return SELECT_PLAN
    # If called via Message (e.g. reply keyboard)
    elif update.message:
        # If triggered via a message (e.g. main menu button "🛒 محصولات")
        from database.queries import DatabaseQueries as _DB
        top_categories = _DB.get_children_categories(None)
        if len(top_categories) == 1:
            # Skip the redundant level when there is only one root category
            single_cat = top_categories[0]
            cat_id = single_cat['id']
            context.user_data['current_parent_category_id'] = cat_id
            children = _DB.get_children_categories(cat_id)
            if children:
                # Show sub-categories of that root
                cat_name = single_cat.get('name', 'دسته‌بندی')
                await update.message.reply_text(
                    text=f"📋 {cat_name}\n\nلطفاً یک زیردسته را انتخاب کنید:",
                    reply_markup=get_categories_keyboard(parent_id=cat_id),
                    parse_mode=ParseMode.HTML,
                )
            else:
                # Leaf: show plans of the root category
                keyboard = get_subscription_plans_keyboard(user_id, category_id=cat_id)
                cat_name = single_cat.get('name', 'محصولات')
                await update.message.reply_text(
                    text=f"🛍️ {cat_name}\n\nلطفاً محصول مورد نظر خود را انتخاب کنید:",
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
        else:
            # Default behaviour – show top-level categories when there are multiple choices
            await update.message.reply_text(
                text="📋 دسته‌بندی محصولات\n\nلطفاً یک دسته‌بندی را انتخاب کنید:",
                reply_markup=get_categories_keyboard(),
                parse_mode=ParseMode.HTML,
            )
    else:
        logger.error("start_subscription_flow called but neither callback_query nor message is present in update.")
        return ConversationHandler.END

    # Clear any previous plan selection from context to ensure a fresh start.
    context.user_data.pop('selected_plan_details', None)
    context.user_data.pop('live_usdt_price', None)
    return SELECT_PLAN

async def show_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the payment methods with the final price using new base currency system."""
    query = update.callback_query
    await query.answer()

    selected_plan = context.user_data.get('selected_plan_details')
    if not selected_plan:
        await query.edit_message_text("خطا: پلن انتخاب شده یافت نشد.")
        return ConversationHandler.END
    
    # Get current exchange rate
    usdt_rate = await get_usdt_to_irr_rate(force_refresh=True)
    if not usdt_rate:
        await query.edit_message_text("خطا در دریافت نرخ ارز. لطفاً دوباره تلاش کنید.")
        return SELECT_PAYMENT_METHOD
    
    # Get base currency and price from plan
    base_currency = selected_plan.get('base_currency', 'IRR')
    base_price = selected_plan.get('base_price')
    
    if base_price is None:
        # Fallback to legacy fields for backward compatibility
        if selected_plan.get('price_tether') is not None:
            base_currency = 'USDT'
            base_price = selected_plan['price_tether']
        elif selected_plan.get('price') is not None:
            base_currency = 'IRR'
            base_price = selected_plan['price']
        else:
            await query.edit_message_text("خطا: قیمت پلن تعریف نشده است.")
            return ConversationHandler.END
    
    # Calculate prices in both currencies
    if base_currency == 'USDT':
        usdt_price = math.ceil(float(base_price))
        irr_price = int(usdt_price * usdt_rate * 10)  # Convert to Rial (with 10x multiplier)
    else:  # base_currency == 'IRR'
        irr_price = int(float(base_price))
        usdt_price = math.ceil(irr_price / (usdt_rate * 10))  # Convert to USDT and round up
    
    # Store calculated prices with expiry time (30 minutes)
    from datetime import datetime, timedelta
    expiry_time = datetime.utcnow() + timedelta(minutes=30)
    context.user_data.update({
        'live_usdt_price': usdt_price,
        'live_irr_price': irr_price,
        'price_expiry': expiry_time.isoformat(),
        'base_currency': base_currency,
        'base_price': base_price
    })
    
    # Format prices for display
    plan_price_irr_formatted = f"{irr_price:,}"
    plan_price_usdt_formatted = f"{usdt_price}"
    
    # Create message with price expiry warning
    from utils.text_utils import buttonize_markdown
    plan_display_name = buttonize_markdown(selected_plan.get('name', 'N/A'))
    message_text = PAYMENT_METHOD_MESSAGE.format(
        plan_name=plan_display_name,
        plan_price=plan_price_irr_formatted,
        plan_tether=plan_price_usdt_formatted
    )
    message_text += "\n\n⚠️ قیمت‌ها تا ۳۰ دقیقه اعتبار دارند."
    
    await safe_edit_message_text(
        query.message,
        text=message_text,
        reply_markup=get_payment_methods_keyboard(),
        parse_mode=ParseMode.HTML
    )
    
    return SELECT_PAYMENT_METHOD

async def ask_discount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # """Asks the user if they have a discount code."""
    # query = update.callback_query
    # await query.answer()

    # selected_plan = context.user_data.get('selected_plan_details')
    # if not selected_plan:
    #     await query.edit_message_text("خطا: پلن انتخاب شده یافت نشد.")
    #     return ConversationHandler.END
    
    # # Calculate and store the live price for discount validation
    # # Get current exchange rate
    # usdt_rate = await get_usdt_to_irr_rate(force_refresh=True)
    ####################################
    """Temporarily bypass the discount question and directly show payment methods.
    This shortcut can be reverted by restoring original implementation."""
    # Simply delegate to show_payment_methods to keep rest of flow unchanged
    # Works for both initial callback and potential message scenarios.
    if update.callback_query:
        await show_payment_methods(update, context)
    else:
        # create a dummy CallbackQuery-like context by re-invoking the same handler via stored message id is complex,
        # so we skip; payment flow mainly uses callbacks.
        pass
    return SELECT_PAYMENT_METHOD
    ####################################
    if not usdt_rate:
        await query.edit_message_text("خطا در دریافت نرخ ارز. لطفاً دوباره تلاش کنید.")
        return SELECT_PLAN
    
    # Get base currency and price from plan
    base_currency = selected_plan.get('base_currency', 'IRR')
    base_price = selected_plan.get('base_price')
    
    if base_price is None:
        # Fallback to legacy fields for backward compatibility
        if selected_plan.get('price_tether') is not None:
            base_currency = 'USDT'
            base_price = selected_plan['price_tether']
        elif selected_plan.get('price') is not None:
            base_currency = 'IRR'
            base_price = selected_plan['price']
        else:
            await query.edit_message_text("خطا: قیمت پلن تعریف نشده است.")
            return ConversationHandler.END
    
    # Calculate prices in both currencies
    if base_currency == 'USDT':
        usdt_price = math.ceil(float(base_price))
        irr_price = int(usdt_price * usdt_rate * 10)  # Convert to Rial (with 10x multiplier)
    else:  # base_currency == 'IRR'
        irr_price = int(float(base_price))
        usdt_price = math.ceil(irr_price / (usdt_rate * 10))  # Convert to USDT and round up
    
    # Store calculated prices with expiry time (30 minutes)
    from datetime import datetime, timedelta
    expiry_time = datetime.utcnow() + timedelta(minutes=30)
    context.user_data.update({
        'live_usdt_price': usdt_price,
        'live_irr_price': irr_price,
        'price_expiry': expiry_time.isoformat(),
        'base_currency': base_currency,
        'base_price': base_price
    })
    
    from utils.text_utils import buttonize_markdown
    plan_display_name = buttonize_markdown(selected_plan['name'])
    message_text = f"شما پلن «{plan_display_name}» را انتخاب کرده‌اید. آیا کد تخفیف دارید؟"

    # Use safe_edit_message_text to prevent 'Message is not modified' errors if user triggers the same callback repeatedly
    await safe_edit_message_text(
        query.message,
        text=message_text,
        reply_markup=get_ask_discount_keyboard()
    )
    return ASK_DISCOUNT

async def handle_free_content_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the logic for a one-time free content plan (e.g., sending videos).
    Checks eligibility, records the subscription, and sends the content.
    """
    query = update.callback_query
    user_id = update.effective_user.id
    telegram_id = update.effective_user.id

    if not query:
        logger.warning("handle_free_content_plan called without a query.")
        return ConversationHandler.END

    await query.answer()

    plan = context.user_data.get('selected_plan')
    if not plan:
        await query.message.edit_text("خطایی رخ داده است. لطفاً دوباره امتحان کنید.")
        return ConversationHandler.END

    plan_id = plan['id']
    from utils.text_utils import buttonize_markdown
    plan_name = buttonize_markdown(plan['name'])

    # 1. Check if the plan capacity is full (capacity stores remaining slots)
    if plan.get('capacity') is not None:
        # Safety check: ensure capacity is a number, not a list or other type
        if isinstance(plan['capacity'], (int, float)) and plan['capacity'] <= 0:
            await query.message.edit_text(
                "ظرفیت این پلن تکمیل شده است.",
                reply_markup=get_main_menu_keyboard()
            )
            return ConversationHandler.END

    # Use a placeholder for transaction_id and payment_table_id for free content
    transaction_id = f"free_{user_id}_{plan_id}_{datetime.now().timestamp()}"
    payment_table_id = None  # No payment record for free content

    success, message = await activate_or_extend_subscription(
        user_id=user_id,
        telegram_id=telegram_id,
        plan_id=plan_id,
        plan_name=plan_name,
        payment_amount=0,
        payment_method="free",
        transaction_id=transaction_id,
        context=context,
        payment_table_id=payment_table_id
    )

    if not success:
        logger.error(f"Failed to record free content access for user {user_id}, plan {plan_id}: {message}")
        await query.message.edit_text(f"خطا در فعال‌سازی پلن رایگان: {message}")
        return ConversationHandler.END

    # Send the educational videos
    video_folder_path = os.path.join(os.getcwd(), 'database', 'data', 'videos')
    if os.path.exists(video_folder_path) and os.path.isdir(video_folder_path):
        videos = sorted([v for v in os.listdir(video_folder_path) if v.lower().endswith(('.mp4', '.mov', '.avi'))])
        
        if not videos:
            await context.bot.send_message(
                chat_id=user_id,
                text="در حال حاضر ویدیوی آموزشی برای ارسال وجود ندارد. لطفاً بعداً دوباره تلاش کنید."
            )
        else:
            # Notify user that videos are about to be sent
            await context.bot.send_message(
                chat_id=user_id,
                text="ویدئو آموزشی به زودی برای شما ارسال می شود. لطفاً صبور باشید."
            )
            # Now send the videos.
            from database.queries import DatabaseQueries
            for video_file in videos:
                caption = os.path.splitext(video_file)[0]
                cached_file_id = DatabaseQueries.get_video_file_id(video_file)
                try:
                    if cached_file_id:
                        # Use cached file_id – instant send
                        message = await context.bot.send_video(
                            chat_id=user_id,
                            video=cached_file_id,
                            caption=caption
                        )
                    else:
                        # Upload from disk, then cache id for future use
                        video_path = os.path.join(video_folder_path, video_file)
                        with open(video_path, 'rb') as video:
                            message = await context.bot.send_video(
                                chat_id=user_id,
                                video=video,
                                caption=caption
                            )
                        # Cache the new file_id
                        if message and message.video and message.video.file_id:
                            DatabaseQueries.save_video_file_id(video_file, message.video.file_id)
                except Exception as e:
                    logger.error(f"Failed to send video {video_file} to user {user_id}: {e}")
                    # Do not send an error message to the user to avoid confusion.
    else:
        logger.warning(f"Video folder not found at {video_folder_path}")
        await context.bot.send_message(
            chat_id=user_id,
            text="ویدیوهای آموزشی یافت نشد. لطفاً با پشتیبانی تماس بگیرید."
        )

    # Show user account info after sending videos
    from handlers.core.core_handlers import handle_back_to_main
    await handle_back_to_main(update, context)

    # End conversation
    context.user_data.clear()
    return ConversationHandler.END

async def select_plan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user's plan selection and proceeds to payment method selection or content delivery."""
    query = update.callback_query
    user_id = update.effective_user.id
    logger.info(f"[select_plan_handler] User {user_id} triggered with data: {query.data}")
    await query.answer()

    # Check if user is registered before proceeding
    from utils.helpers import is_user_registered
    if not is_user_registered(user_id):
        logger.warning(f"[select_plan_handler] Unregistered user {user_id} tried to select a plan")
        await query.message.edit_text(
            "⚠️ برای خرید محصول یا استفاده از پکیج‌های رایگان، ابتدا باید ثبت‌نام کنید.\n\n"
            "لطفاً از منوی اصلی گزینه '📝 ثبت نام' را انتخاب کنید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 ثبت نام", callback_data="start_registration_flow")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main_menu")]
            ])
        )
        return ConversationHandler.END

    Database.update_user_activity(user_id)

    try:
        plan_id = int(query.data.split('_')[1])
    except (ValueError, IndexError):
        logger.error(f"[select_plan_handler] Invalid plan_id format from callback: {query.data} for user {user_id}")
        await query.message.edit_text("خطا: شناسه طرح نامعتبر است.")
        return SELECT_PLAN

    selected_plan = Database.get_plan_by_id(plan_id)
    if not selected_plan or not selected_plan['is_active']:
        logger.warning(f"[select_plan_handler] Plan not found or inactive: {plan_id}")
        await query.message.edit_text(
            "خطا: طرح انتخاب شده معتبر نیست یا دیگر فعال نمی‌باشد. لطفاً مجدداً یک طرح را انتخاب کنید.",
            reply_markup=get_subscription_plans_keyboard(user_id)
        )
        return SELECT_PLAN

    # Convert sqlite3.Row to a dictionary for easier and safer access
    plan_dict = dict(selected_plan)
    context.user_data['selected_plan'] = plan_dict

    # Check remaining capacity slots (capacity stores remaining slots).
    plan_capacity = plan_dict.get('capacity')
    if plan_capacity is not None:
        # Safety check: ensure capacity is a number, not a list or other type
        if isinstance(plan_capacity, (int, float)) and plan_capacity <= 0:
            logger.info(f"User {user_id} tried to select plan {plan_id} which is at full capacity.")
            await query.message.edit_text(
                text="ظرفیت این محصول تکمیل شده است.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]])
            )
            return ConversationHandler.END
    logger.info(f"[select_plan_handler] Selected plan: {plan_dict}")

    # Route based on plan_type first
    if plan_dict.get('plan_type') == 'one_time_content':
        logger.info(f"Plan {plan_id} is one_time_content. Routing to handle_free_content_plan.")
        return await handle_free_content_plan(update, context)

    # Determine if the plan is completely free using new base_price system
    base_price = plan_dict.get('base_price')
    if base_price is None:
        # Fallback to legacy fields for backward compatibility
        is_free_plan = (plan_dict.get('price') in (None, 0)) and (plan_dict.get('price_tether') in (None, 0))
    else:
        is_free_plan = base_price in (None, 0)
    if is_free_plan:
        # Prevent users from subscribing to free plan multiple times
        if Database.has_user_used_free_plan(user_id=user_id, plan_id=plan_id):
            await safe_edit_message_text(
                query.message,
                text="شما قبلاً از این طرح رایگان استفاده کرده‌اید و امکان فعال‌سازی مجدد آن وجود ندارد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]])
            )
            return ConversationHandler.END

        logger.info(f"Plan {plan_id} price is zero. Activating subscription without payment flow.")
        # Fetch user's DB id
        # We expect the primary key column in users table to be `user_id` (same as Telegram ID).
        # Ensure the user exists; `update_user_activity` at start usually inserts missing users via triggers/wrappers.
        user_row = Database.get_user_by_telegram_id(user_id)
        user_db_id = None
        if user_row:
            # sqlite3.Row can be accessed like a dict
            if 'user_id' in user_row.keys():
                user_db_id = user_row['user_id']
            elif 'id' in user_row.keys():  # fallback if schema differs
                user_db_id = user_row['id']
        # As a last resort, fall back to telegram_id itself (they are identical in our schema)
        if user_db_id is None:
            user_db_id = user_id


        success, err_msg = await activate_or_extend_subscription(
            user_id=user_db_id,
            telegram_id=user_id,
            plan_id=plan_id,
            plan_name=plan_dict['name'],
            payment_amount=0.0,
            payment_method='free',
            transaction_id='FREE',
            context=context,
            payment_table_id=0
        )
        if success:
            # Success message and links will be sent by send_channel_links_and_confirmation inside
            # activate_or_extend_subscription. No need to send another message here to avoid duplication.
            # Post-subscription flow (survey and video delivery) is already handled in activate_or_extend_subscription
            logger.debug("Free plan subscription activated; post-subscription flow handled in activate_or_extend_subscription.")
        else:
            await query.message.edit_text(
                text=f"❌ {err_msg}",
                reply_markup=get_main_menu_keyboard(user_id)
            )
        return ConversationHandler.END

    # Default to paid subscription flow
    logger.info(f"Plan {plan_id} requires payment. Proceeding to ask for discount.")
    context.user_data['selected_plan_details'] = plan_dict
    # No fixed IRR price; will compute dynamically later
    return await ask_discount_handler(update, context)
    


async def select_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment method selection"""
    query = update.callback_query
    telegram_id = update.effective_user.id

    Database.update_user_activity(telegram_id) # Ensures user exists in DB

    user_record = Database.get_user_details(telegram_id)
    if not user_record:
        logger.error(f"Critical: User with telegram_id {telegram_id} not found in database after update_user_activity.")
        await query.message.edit_text("خطای سیستمی: اطلاعات کاربری شما یافت نشد. لطفاً با پشتیبانی تماس بگیرید.")
        return ConversationHandler.END
    user_db_id = user_record['user_id']
    context.user_data['user_db_id'] = user_db_id # Ensure user_db_id is in context for subsequent logs

    selected_plan_details_for_log = context.user_data.get('selected_plan_details')
    logger.info(f"User {telegram_id} (DB ID: {user_db_id}): Entered select_payment_method with callback_data: {query.data}. Plan selected: {selected_plan_details_for_log is not None}")

    payment_method = query.data.split('_')[1]
    context.user_data['payment_method'] = payment_method
    logger.info(f"User {telegram_id}: Determined payment_method: {payment_method}. Plan details: ID {selected_plan_details_for_log['id'] if selected_plan_details_for_log else 'N/A'}, Name: {selected_plan_details_for_log['name'] if selected_plan_details_for_log else 'N/A'}")
    await query.answer()

    selected_plan = context.user_data.get('selected_plan_details')
    if not selected_plan:
        logger.warning(f"No selected_plan_details in context for telegram_id {telegram_id} in select_payment_method.")
        await query.message.edit_text("خطا: اطلاعات طرح یافت نشد. لطفاً از ابتدا شروع کنید.", reply_markup=get_subscription_plans_keyboard(telegram_id))
        return SELECT_PLAN

    # Check if price has expired (30 minutes)
    from datetime import datetime
    price_expiry = context.user_data.get('price_expiry')
    if price_expiry:
        expiry_time = datetime.fromisoformat(price_expiry)
        if datetime.utcnow() > expiry_time:
            await query.edit_message_text(
                "⚠️ قیمت محاسبه شده منقضی شده است. لطفاً دوباره پلن را انتخاب کنید.",
                reply_markup=get_subscription_plans_keyboard(telegram_id)
            )
            return SELECT_PLAN
    
    # Retrieve the final price (potentially discounted) from user_data
    price_irr = context.user_data.get('final_price')
    if price_irr is None:
        # Try cached live IRR
        price_irr = context.user_data.get('live_irr_price')
    # If still None, but تتر پایه موجود است، محاسبه از روی نرخ لحظه‌ای
    if price_irr is None:
        usdt_base_price = selected_plan.get('price_tether') or selected_plan.get('original_price_usdt')
        if usdt_base_price:
            rate = get_usdt_to_irr_rate()
            if rate:
                price_irr = int(usdt_base_price * rate)
                context.user_data['dynamic_irr_price'] = price_irr
                context.user_data['live_irr_price'] = price_irr
    
    if price_irr is None:
        await query.edit_message_text(
            "خطا در محاسبه قیمت. لطفاً دوباره پلن را انتخاب کنید.",
            reply_markup=get_subscription_plans_keyboard(telegram_id)
        )
        return SELECT_PLAN
    
    # Ensure price_irr is numeric
    try:
        price_irr = int(price_irr) if price_irr is not None else None
    except (ValueError, TypeError):
        price_irr = None

    if price_irr is None:
        logger.error(f"User {telegram_id}: Could not determine numeric IRR price for selected plan.")
        await query.message.edit_text("خطای سیستمی: قیمت پلن انتخابی مشخص نشد. لطفاً دوباره تلاش کنید.")
        return SELECT_PLAN

    plan_id = selected_plan['id']
    # Fetch full plan with price_tether from DB
    db_plan = Database.get_plan(plan_id)
    if db_plan is not None:
        selected_plan = dict(db_plan)
        context.user_data['selected_plan_details'] = selected_plan
    from utils.text_utils import buttonize_markdown
    plan_name = buttonize_markdown(selected_plan['name'])

    # --- Handle free plans or plans discounted to zero ---
    if price_irr is None or price_irr <= 0:
        # Prevent duplicate activation of free plan (including plans discounted to zero)
        if Database.has_user_used_free_plan(user_id=telegram_id, plan_id=plan_id):
            await query.message.edit_text(
                "شما قبلاً از این طرح رایگان استفاده کرده‌اید و امکان فعال‌سازی مجدد آن وجود ندارد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]])
            )
            return ConversationHandler.END

        logger.info(f"Plan {plan_id} has zero price ({price_irr}). Activating for user {telegram_id} without payment.")
        success, msg = await activate_or_extend_subscription(
            user_id=user_db_id,
            telegram_id=telegram_id,
            plan_id=plan_id,
            plan_name=plan_name,
            payment_amount=0,
            payment_method='free_plan',
            transaction_id=f"FREE-{uuid.uuid4().hex[:6]}",
            context=context,
            payment_table_id=None
        )
        if success:
            await query.message.edit_text(f"✅ پلن «{plan_name}» به صورت رایگان برای شما فعال شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))
        else:
            await query.message.edit_text(f"❌ {msg}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))
        UserAction.log_user_action(telegram_id, 'free_plan_activated', {'plan_id': plan_id})
        return ConversationHandler.END

    if payment_method == 'rial':
        transaction_id = str(uuid.uuid4())[:8].upper()
        context.user_data['transaction_id'] = transaction_id
        
        # Use the potentially discounted price
        plan_price_irr = price_irr

        # Create a detailed description for the payment record in the database
        db_description = f"خرید محصولات {plan_name} (Plan ID: {plan_id}) توسط کاربر ID: {user_db_id}"

        payment_db_id = Database.add_payment(
            user_id=user_db_id,
            plan_id=plan_id,  # Associate payment with the plan
            amount=plan_price_irr,  # Amount for the plan in IRR
            payment_method='zarinpal', # Payment gateway used
            description=db_description, # Detailed description for the payment
            status='pending', # Initially pending
            transaction_id=None # Will be updated later with Zarinpal's authority/ref_id
        )

        if not payment_db_id:
            logger.error(f"Failed to create initial Zarinpal payment record for user {telegram_id}, plan {plan_id}.")
            await query.message.edit_text(PAYMENT_ERROR_MESSAGE, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))
            UserAction.log_user_action(telegram_id, 'zarinpal_payment_db_creation_failed', {'plan_id': plan_id})
            return ConversationHandler.END

        # Prepare for Zarinpal request
        description = f"خرید محصولات {plan_name} برای کاربر {telegram_id}"
        # Zarinpal amount should be integer
        amount_for_zarinpal = int(plan_price_irr) 

        logger.info(f"Requesting Zarinpal payment for user {telegram_id}, plan {plan_id}, amount {amount_for_zarinpal} IRR.")
        bot_username = (await context.bot.get_me()).username
        # The callback_url will be dynamically constructed inside the service
        zarinpal_request = ZarinpalPaymentService.create_payment_request(
            amount=amount_for_zarinpal,
            description=description,
            callback_url=f"https://t.me/{bot_username}" # Base URL for deep linking
        )
        logger.info(f"User {telegram_id} (DB ID: {user_db_id}): Zarinpal request result: {zarinpal_request}")

        if zarinpal_request and zarinpal_request.get('status') == ZARINPAL_REQUEST_SUCCESS_STATUS:
            authority = zarinpal_request.get('authority')
            payment_url = zarinpal_request.get('payment_url')

            # Set 30-minute expiry for this payment link
            expires_at_dt = datetime.now() + timedelta(minutes=30)
            Database.update_payment_expires_at(payment_db_id, expires_at_dt)

            # Immediately update the database with the authority code
            Database.update_payment_transaction_id(payment_db_id, str(authority), status='pending_verification')

            context.user_data['zarinpal_authority'] = authority
            context.user_data['rial_amount_for_zarinpal'] = amount_for_zarinpal
            context.user_data['selected_plan_id'] = plan_id
            context.user_data['payment_db_id_zarinpal'] = payment_db_id
            context.user_data['selected_plan_name'] = plan_name
            
            # Create the deep link for user's manual return
            callback_deeplink = f"https://t.me/{bot_username}?start=zarinpal_verify_{authority}"

            message_text = (
                f"برای تکمیل خرید محصولات «{plan_name}» به مبلغ {amount_for_zarinpal:,} ریال، لطفاً از طریق لینک زیر پرداخت خود را انجام دهید.\n\n"
                f"⚠️ <b>مهم:</b> پس از تکمیل پرداخت در سایت زرین‌پال، <b>روی دکمه زیر کلیک کنید</b> تا اشتراک شما فعال شود.\n\n"
                f"این لینک پرداخت تا ۳۰ دقیقه معتبر است و پس از آن منقضی می‌شود."
            )
            await query.message.edit_text(
                text=message_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("ورود به درگاه پرداخت زرین‌پال", url=payment_url)],
                    [InlineKeyboardButton("✅ پرداخت را انجام دادم، تایید کن", url=callback_deeplink)],
                    [get_back_to_payment_methods_button()]
                ]),
                parse_mode=ParseMode.HTML
            )
            logger.info(f"User {telegram_id} (DB ID: {user_db_id}): Payment method keyboard shown with callback_data: {query.data}. Returning VERIFY_PAYMENT.")
            return VERIFY_PAYMENT
        
        else: # ERROR or other statuses
            Database.update_payment_status(payment_db_id, 'failed', error_message=f"zarinpal_req_err_{zarinpal_request.get('status')}")
            logger.error(f"Zarinpal payment request failed for user {telegram_id}. Response: {zarinpal_request}")
            await query.message.edit_text(
                f"متاسفانه در ایجاد لینک پرداخت مشکلی پیش آمد.\nخطا: {zarinpal_request.get('message')} (کد: {zarinpal_request.get('status')})\nلطفاً دقایقی دیگر مجدداً تلاش کنید یا روش پرداخت دیگری را انتخاب نمایید.",
                reply_markup=InlineKeyboardMarkup([
                    [get_back_to_payment_methods_button()],
                    [InlineKeyboardButton(TEXT_GENERAL_BACK_TO_MAIN_MENU, callback_data=CALLBACK_BACK_TO_MAIN_MENU)]
                ])
            )
            UserAction.log_user_action(telegram_id, 'zarinpal_request_failed', {'plan_id': plan_id, 'error_code': zarinpal_request.get('status'), 'error_message': zarinpal_request.get('message')})
            # Do not end conversation, let user go back or choose another method
            return SELECT_PAYMENT_METHOD

    elif payment_method == 'crypto':
        import math
        # Determine live USDT price (base price possibly discounted)
        live_calculated_usdt_price = math.ceil(
            context.user_data.get('live_usdt_price') or (
                selected_plan.get('price_tether') or selected_plan.get('original_price_usdt')
            )
        )
        # Cache for later verification steps
        context.user_data['live_usdt_price'] = live_calculated_usdt_price

        if live_calculated_usdt_price is None or live_calculated_usdt_price <= 0:
            logger.warning(
                f"Plan {plan_id} has invalid live_calculated_usdt_price {live_calculated_usdt_price} for crypto payment. telegram_id: {telegram_id}"
            )
            await query.message.edit_text(
                "خطا: قیمت محاسبه شده تتر برای طرح نامعتبر است یا یافت نشد. لطفاً مجدداً تلاش کنید.",
                reply_markup=get_payment_methods_keyboard(),
            )
            return SELECT_PAYMENT_METHOD

        # Ensure we also have an up-to-date IRR equivalent (for DB گزارش‌ها و سقف تراکنش‌ها)
        rial_amount = context.user_data.get('dynamic_irr_price')
        if rial_amount is None or rial_amount <= 0:
            # Compute on-the-fly from current market rate
            usdt_rate_toman = await get_usdt_to_irr_rate()  # returns IRR per 1 USDT
            if usdt_rate_toman:
                rial_amount = int(live_calculated_usdt_price * usdt_rate_toman)
                context.user_data['dynamic_irr_price'] = rial_amount
            else:
                # If rate fetch failed, still proceed without Rial amount
                rial_amount = 0

        expires_at = datetime.now() + timedelta(minutes=CRYPTO_PAYMENT_TIMEOUT_MINUTES)

        # Step 1: Create a preliminary crypto payment request entry to get an ID.
        rial_plan_price_irr = context.user_data.get('dynamic_irr_price') # Get RIAL price of the plan
        payment_timeout_minutes = config.CRYPTO_PAYMENT_TIMEOUT_MINUTES
        expires_at_dt = datetime.now() + timedelta(minutes=payment_timeout_minutes)

        crypto_payment_request_db_id = Database.create_crypto_payment_request(
            user_id=user_db_id,
            rial_amount=rial_plan_price_irr,  # Dynamic IRR amount of the plan
            usdt_amount_requested=live_calculated_usdt_price, # This is the base USDT price for the plan
            wallet_address=config.CRYPTO_WALLET_ADDRESS,
            expires_at=expires_at_dt
        )
        logger.info(f"User {telegram_id} (DB ID: {user_db_id}): Crypto payment_request_db_id: {crypto_payment_request_db_id}. Result from Database.create_crypto_payment_request.")

        if not crypto_payment_request_db_id:
            UserAction.log_user_action(
                telegram_id=telegram_id, 
                action_type='crypto_placeholder_creation_failed',
                details={'plan_id': plan_id, 'rial_amount': rial_amount, 'user_db_id': user_db_id})
            logger.error(f"Failed to create placeholder crypto payment request for user_db_id {user_db_id}, plan {plan_id}.")
            await query.message.edit_text(PAYMENT_ERROR_MESSAGE, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))
            return ConversationHandler.END  # Or SELECT_PAYMENT_METHOD

        # مبلغ USDT برابر با قیمت پایهٔ پلن (بدون آفست)
        usdt_amount_requested = live_calculated_usdt_price
        context.user_data['usdt_amount_requested'] = usdt_amount_requested


        # Step 3: Update the crypto payment request record with the calculated USDT amount.
        # This requires a method like: Database.update_crypto_payment_request_with_amount(request_id, usdt_amount)
        update_success = Database.update_crypto_payment_request_with_amount(
            payment_request_id=crypto_payment_request_db_id,
            usdt_amount=usdt_amount_requested
        )

        if not update_success:
            UserAction.log_user_action(
                telegram_id=telegram_id, 
                action_type='crypto_usdt_amount_update_failed',
                details={'payment_request_id': crypto_payment_request_db_id, 'usdt_amount': usdt_amount_requested, 'user_db_id': user_db_id}
            )
            logger.error(f"Failed to update crypto payment request {crypto_payment_request_db_id} with USDT amount {usdt_amount_requested}. telegram_id: {telegram_id}")
            await query.message.edit_text("خطای سیستمی هنگام ثبت مبلغ تتر. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))
            return ConversationHandler.END # Or SELECT_PAYMENT_METHOD

        if not crypto_payment_request_db_id:
            UserAction.log_user_action(
                telegram_id=telegram_id,
                user_db_id=user_db_id,
                action_type='crypto_payment_request_creation_failed_db',
                details={
                    'plan_id': plan_id,
                    'rial_amount': rial_amount,
                    'usdt_amount_requested': usdt_amount_requested
                }
            )
            logger.error(f"Failed to create crypto_payment_request in DB for user_db_id {user_db_id}, telegram_id {telegram_id}, plan_id {plan_id}")
            await query.message.edit_text("خطا: امکان ایجاد درخواست پرداخت کریپتو وجود ندارد. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=get_payment_methods_keyboard())
            return SELECT_PAYMENT_METHOD

        context.user_data['crypto_payment_id'] = crypto_payment_request_db_id
        context.user_data['usdt_amount_requested'] = usdt_amount_requested

        # The log for calculate_unique_usdt_amount call is now part of the try-except block below where it's actually called

        payment_info_text = CRYPTO_PAYMENT_UNIQUE_AMOUNT_MESSAGE.format(
            wallet_address=CRYPTO_WALLET_ADDRESS,
            usdt_amount=f"{usdt_amount_requested}",
            timeout_minutes=CRYPTO_PAYMENT_TIMEOUT_MINUTES
        )



        keyboard_buttons = [
            [InlineKeyboardButton("📷 نمایش QR کد", callback_data=f"show_qr_code_{crypto_payment_request_db_id}")],
            [InlineKeyboardButton("🔗 ارسال Tx Hash", callback_data="payment_send_tx")]
        ]
        # Always use the standard 'back to payment methods' button
        keyboard_buttons.append([get_back_to_payment_methods_button()]) 

        keyboard = InlineKeyboardMarkup(keyboard_buttons)

        await query.message.edit_text(
            text=payment_info_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

        UserAction.log_user_action(
            telegram_id=telegram_id,
            user_db_id=user_db_id,
            action_type='crypto_payment_info_displayed',
            details={
                'crypto_payment_request_id': crypto_payment_request_db_id,
                'plan_id': plan_id,
                'usdt_amount_requested': usdt_amount_requested,
                'wallet_address': CRYPTO_WALLET_ADDRESS
            }
        )
        return VERIFY_PAYMENT

    logger.error(f"Unknown payment_method '{payment_method}' encountered for telegram_id {telegram_id}, plan_id {plan_id}.")
    await query.message.edit_text(
        "خطایی در انتخاب روش پرداخت رخ داد. لطفاً مجدداً یک طرح را انتخاب کنید.",
        reply_markup=get_subscription_plans_keyboard(telegram_id)
    )
    return SELECT_PLAN




async def verify_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify payment status and activate/extend subscription."""
    query = update.callback_query
    telegram_id = update.effective_user.id # Renamed from user_id for clarity
    user_db_id = None # Will be populated after fetching payment record

    Database.update_user_activity(telegram_id) # Uses telegram_id

    user_db_id = context.user_data.get('user_db_id')
    selected_plan_details = context.user_data.get('selected_plan_details')
    payment_id = context.user_data.get('payment_id')
    logger.info(f"User {telegram_id} (DB ID: {user_db_id}): Entered verify_payment_status with callback_data: {query.data}. Plan selected: {selected_plan_details is not None}")
    payment_method = context.user_data.get('payment_method')

    UserAction.log_user_action(
        telegram_id=telegram_id,
        action_type='rial_payment_verification_initiated',
        details={
            'payment_id_context': payment_id,
            'selected_plan_id_context': selected_plan_details.get('id') if selected_plan_details else None,
            'payment_method_context': payment_method
        }
    )

    if not payment_id or not selected_plan_details or not payment_method:
        UserAction.log_user_action(
            telegram_id=telegram_id,
            action_type='rial_payment_missing_context_data',
            details={
                'has_payment_id': bool(payment_id),
                'has_selected_plan_details': bool(selected_plan_details),
                'has_payment_method': bool(payment_method)
            }
        )
        await query.message.edit_text(
            "خطایی در بازیابی اطلاعات پرداخت، طرح یا روش پرداخت رخ داد. لطفاً دوباره تلاش کنید.",
            reply_markup=get_subscription_plans_keyboard(telegram_id) # Use telegram_id
        )
        logger.error(f"Error: Missing payment_id, selected_plan_details, or payment_method in verify_payment_status for user {telegram_id}")
        return SELECT_PLAN

    # Fetch payment record to get user_db_id and verify payment
    db_payment = Database.get_payment_by_id(payment_id)
    if not db_payment:
        UserAction.log_user_action(
            telegram_id=telegram_id,
            action_type='rial_payment_record_not_found_db',
            details={'payment_id': payment_id}
        )
        logger.error(f"Error: Payment record with ID {payment_id} not found in database for user {telegram_id}.")
        await query.message.edit_text(
            "اطلاعات پرداخت شما در سیستم یافت نشد. لطفاً با پشتیبانی تماس بگیرید.",
            reply_markup=get_main_menu_keyboard(user_id=telegram_id) # Use telegram_id
        )
        return ConversationHandler.END
    
    user_db_id = db_payment.get('user_id')

    UserAction.log_user_action(
        telegram_id=telegram_id,
        user_db_id=user_db_id,
        action_type='rial_payment_gateway_check_initiated',
        details={'payment_db_id': payment_id, 'payment_method': payment_method}
    )
    # Simulate payment verification 
    payment_successful = True # TODO: Replace with actual payment gateway verification logic for Rial
    gateway_transaction_id = context.user_data.get('transaction_id')

    if payment_successful:
        UserAction.log_user_action(
            telegram_id=telegram_id,
            user_db_id=user_db_id,
            action_type='rial_payment_gateway_succeeded',
            details={
                'payment_db_id': payment_id,
                'gateway_transaction_id': gateway_transaction_id,
                'payment_method': payment_method
            }
        )
        
        if not Database.update_payment_status(payment_id, "completed", gateway_transaction_id):
            UserAction.log_user_action(
                telegram_id=telegram_id,
                user_db_id=user_db_id,
                action_type='rial_payment_db_status_update_failed',
                details={
                    'payment_db_id': payment_id,
                    'target_status': 'completed',
                    'gateway_transaction_id': gateway_transaction_id
                }
            )
            await query.message.edit_text(
                "خطا در به‌روزرسانی وضعیت پرداخت. لطفاً با پشتیبانی تماس بگیرید.",
                reply_markup=get_main_menu_keyboard(user_id=telegram_id)
            )
            logger.error(f"Error: Failed to update payment status for payment_id {payment_id} for user {telegram_id}")
            for key in ['selected_plan_details', 'payment_id', 'transaction_id', 'payment_method']:
                context.user_data.pop(key, None)
            return ConversationHandler.END

        UserAction.log_user_action(
            telegram_id=telegram_id,
            user_db_id=user_db_id,
            action_type='rial_payment_db_status_update_succeeded',
            details={
                'payment_db_id': payment_id,
                'new_status': 'completed',
                'gateway_transaction_id': gateway_transaction_id
            }
        )

        plan_id = selected_plan_details['id']
        plan_duration_days = selected_plan_details['days']
        plan_name = selected_plan_details['name']

        if payment_method == 'rial':
            amount_paid = selected_plan_details.get('price')
        elif payment_method == 'crypto': 
            amount_paid = selected_plan_details.get('price_tether') 
        else:
            UserAction.log_user_action(
                telegram_id=telegram_id,
                user_db_id=user_db_id,
                action_type='rial_payment_unknown_method_error',
                details={'payment_db_id': payment_id, 'payment_method': payment_method}
            )
            logger.error(f"Error: Unknown payment_method '{payment_method}' for user {telegram_id}, payment_id {payment_id}")
            await query.message.edit_text("خطای داخلی: روش پرداخت ناشناخته است.", reply_markup=get_main_menu_keyboard(user_id=telegram_id))
            return ConversationHandler.END
        
        if amount_paid is None:
            UserAction.log_user_action(
                telegram_id=telegram_id,
                user_db_id=user_db_id,
                action_type='rial_payment_amount_not_found_error',
                details={'payment_db_id': payment_id, 'plan_id': plan_id, 'payment_method': payment_method}
            )
            logger.error(f"Error: Amount for plan_id {plan_id} with payment_method '{payment_method}' is None for user {telegram_id}")
            await query.message.edit_text("خطای داخلی: مبلغ طرح یافت نشد.", reply_markup=get_main_menu_keyboard(user_id=telegram_id))
            return ConversationHandler.END

        UserAction.log_user_action(
            telegram_id=telegram_id,
            user_db_id=user_db_id,
            action_type='rial_subscription_activation_initiated',
            details={
                'payment_db_id': payment_id,
                'plan_id': plan_id,
                'amount_paid': float(amount_paid),
                'payment_method': payment_method
            }
        )
        activation_success, _ = await activate_or_extend_subscription(
            user_id=user_db_id if user_db_id else telegram_id,
            telegram_id=telegram_id,
            plan_id=plan_id,
            plan_name=plan_name,
            payment_amount=float(amount_paid),
            payment_method=payment_method,
            transaction_id=gateway_transaction_id,
            context=context,
            payment_table_id=payment_id
        )

        if activation_success:
            # Increment discount usage if a discount was applied
            if 'discount_id' in context.user_data:
                discount_id = context.user_data.get('discount_id')
                logger.info(f"[verify_payment_status] Incrementing usage for discount ID {discount_id}.")
                Database.increment_discount_usage(discount_id)

            UserAction.log_user_action(
                telegram_id=telegram_id,
                user_db_id=user_db_id,
                action_type='rial_subscription_activation_succeeded',
                details={
                    'payment_db_id': payment_id,
                    'subscription_record_id': subscription_record_id,
                    'plan_id': plan_id
                }
            )
            updated_subscription = Database.get_subscription(subscription_record_id)
            if not updated_subscription:
                updated_subscription = Database.get_user_active_subscription(user_db_id if user_db_id else telegram_id)

            display_end_date = "نامشخص"
            if updated_subscription and updated_subscription.get('end_date'):
                try:
                    end_date_dt = datetime.strptime(updated_subscription['end_date'], "%Y-%m-%d %H:%M:%S")
                    display_end_date = end_date_dt.strftime("%Y-%m-%d")
                except ValueError:
                    logger.warning(f"Error parsing end_date from updated_subscription: {updated_subscription.get('end_date')}")

            # -------------------------------------------------------------------
            # Send unique one-time invite links for the configured channels/groups
            # -------------------------------------------------------------------
            try:
                from utils.invite_link_manager import InviteLinkManager
                links = await InviteLinkManager.ensure_one_time_links(context.bot, telegram_id)
                if links:
                    for link in links:
                        await context.bot.send_message(
                            chat_id=telegram_id,
                            text=f"لینک ورود شما به کانال/گروه:\n{link}"
                        )
                    logger.info("Sent %d invite links to user %s after subscription activation", len(links), telegram_id)
            except Exception as send_link_err:
                logger.error("Failed to generate or send invite links to user %s: %s", telegram_id, send_link_err)

        else:
            UserAction.log_user_action(
                telegram_id=telegram_id,
                user_db_id=user_db_id,
                action_type='rial_subscription_activation_failed',
                details={'payment_db_id': payment_id, 'plan_id': plan_id}
            )
            await query.message.edit_text(
                "خطا در فعال‌سازی اشتراک. لطفاً با پشتیبانی تماس بگیرید.",
                reply_markup=get_main_menu_keyboard(user_id=telegram_id)
            )
            logger.error(f"Error: add_subscription returned None for user {telegram_id}, payment_id {payment_id}")

        for key in ['selected_plan_details', 'payment_id', 'transaction_id', 'payment_method']:
            context.user_data.pop(key, None)
        return ConversationHandler.END
    else: # payment_successful is False
        UserAction.log_user_action(
            telegram_id=telegram_id,
            user_db_id=user_db_id,
            action_type='rial_payment_gateway_failed',
            details={
                'payment_db_id': payment_id,
                'gateway_transaction_id': gateway_transaction_id,
                'payment_method': payment_method
            }
        )
        if not Database.update_payment_status(payment_id, "failed", gateway_transaction_id):
             logger.warning(f"Warning: Failed to update payment status to 'failed' for payment_id {payment_id} for user {telegram_id}")
             UserAction.log_user_action(
                telegram_id=telegram_id,
                user_db_id=user_db_id,
                action_type='rial_payment_db_status_update_to_failed_failed',
                details={'payment_db_id': payment_id}
            )
        
        await query.message.edit_text(
            PAYMENT_ERROR_MESSAGE,
            reply_markup=get_payment_methods_keyboard()
        )
        context.user_data.pop('payment_id', None)
        context.user_data.pop('transaction_id', None)
        return SELECT_PAYMENT_METHOD

async def show_qr_code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Show QR Code' button press for crypto payments."""
    query = update.callback_query
    telegram_id = update.effective_user.id
    # Extract crypto_payment_request_db_id from callback_data, which acts as our transaction identifier here
    crypto_payment_request_db_id = query.data.split('_')[-1]

    # Retrieve wallet address and amount from context or database if necessary
    # For this example, we assume wallet address is fixed and amount is in context
    wallet_address = CRYPTO_WALLET_ADDRESS
    # Retrieve payment details using crypto_payment_request_db_id
    # This might involve a database lookup if not all info is in context.user_data
    # For now, let's assume usdt_amount_requested was stored with a key related to this ID or is generally available.
    # A more robust way would be to fetch from DB: payment_record = Database.get_payment_by_id(crypto_payment_request_db_id)
    # and then use payment_record['amount']
    usdt_amount = context.user_data.get('usdt_amount_requested') # Assuming it's the one from the current flow

    if not wallet_address:
        await query.answer("خطا: آدرس کیف پول برای تولید QR کد یافت نشد.", show_alert=True)
        logger.error(f"QR Code: Wallet address not found for user {telegram_id}, payment_request_id {crypto_payment_request_db_id}")
        return
    
    # Construct the data for QR code (e.g., bitcoin:address?amount=0.001)
    # For USDT (TRC20), it's usually just the address, but some wallets support amount.
    # We'll just use the address for simplicity here.
    qr_data = wallet_address
    if usdt_amount: # Optionally add amount if your QR scanner/wallet supports it for TRC20
        # This is a common format, but might vary. For TRC20, often just address is used.
        # qr_data = f"tron:{wallet_address}?amount={usdt_amount}" # Example if amount is supported
        pass # Keeping it simple with just address for now

    try:
        qr_image_bytes = generate_qr_code(qr_data)
        await query.answer() # Acknowledge the callback
        await context.bot.send_photo(
            chat_id=telegram_id,
            photo=qr_image_bytes,
            caption=f"آدرس کیف پول (TRC20):\n`{wallet_address}`\n\nمبلغ: `{usdt_amount}` USDT (بدون کارمزد)\nلطفاً کارمزد شبکه را جداگانه پرداخت کنید.\n\nاسکن کنید:"
        )
        UserAction.log_user_action(telegram_id, action_type='qr_code_displayed', details={'crypto_payment_request_id': crypto_payment_request_db_id})
    except Exception as e:
        logger.error(f"Error generating or sending QR code for user {telegram_id}, payment_request_id {crypto_payment_request_db_id}: {e}")
        await query.answer("خطا در تولید یا ارسال QR کد.", show_alert=True)

async def payment_verify_zarinpal_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Payment Done, Verify' button for Zarinpal payments."""
    query = update.callback_query
    await query.answer("در حال بررسی وضعیت پرداخت...")
    telegram_id = update.effective_user.id
    user_db_id = context.user_data.get('user_db_id')

    if not user_db_id:
        user_record = Database.get_user_by_telegram_id(telegram_id)
        if user_record:
            user_db_id = user_record['id']
            context.user_data['user_db_id'] = user_db_id
        else:
            logger.error(f"User DB ID not found for telegram_id {telegram_id} in payment_verify_zarinpal_handler.")
            await query.message.edit_text("خطا: اطلاعات کاربری شما یافت نشد. لطفاً مجدداً تلاش کنید یا با پشتیبانی تماس بگیرید.")
            return ConversationHandler.END

    zarinpal_authority = context.user_data.get('zarinpal_authority')
    rial_amount = context.user_data.get('rial_amount_for_zarinpal')
    plan_id = context.user_data.get('selected_plan_id')
    payment_db_id = context.user_data.get('payment_db_id_zarinpal')
    selected_plan_name = context.user_data.get('selected_plan_name', 'طرح شما')

    if not all([zarinpal_authority, rial_amount, plan_id, payment_db_id]):
        logger.error(f"Missing Zarinpal payment data in context for user {telegram_id}: authority={zarinpal_authority}, amount={rial_amount}, plan_id={plan_id}, payment_db_id={payment_db_id}")
        await query.message.edit_text(
            "خطا: اطلاعات پرداخت شما ناقص است. لطفاً مراحل پرداخت را از ابتدا طی کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]])
        )
        UserAction.log_user_action(telegram_id, 'zarinpal_verification_failed', {'reason': 'missing_context_data'})
        return ConversationHandler.END

    try:
        logger.info(f"Verifying Zarinpal payment for user {telegram_id}, authority {zarinpal_authority}, amount {rial_amount}")
        verification_result = ZarinpalPaymentService.verify_payment(amount=rial_amount, authority=zarinpal_authority)
        
        current_payment_record = Database.get_payment_by_id(payment_db_id)
        # Check expiration before contacting gateway
        expires_at_str = current_payment_record.get('expires_at') if current_payment_record else None
        if expires_at_str:
            try:
                expires_at_dt = datetime.fromisoformat(expires_at_str)
            except ValueError:
                expires_at_dt = None
            if expires_at_dt and datetime.now() > expires_at_dt:
                # Expired – update status and notify user
                Database.update_payment_status(payment_db_id, 'expired', error_message='link_expired')
                await query.message.edit_text(
                    text="❌ این لینک پرداخت منقضی شده است. لطفاً دوباره اقدام به پرداخت کنید.",
                    reply_markup=get_payment_methods_keyboard()
                )
                UserAction.log_user_action(telegram_id, 'zarinpal_link_expired', {'payment_db_id': payment_db_id})
                return ConversationHandler.END
        if not current_payment_record or current_payment_record['user_id'] != user_db_id:
            logger.error(f"Zarinpal verification: Payment record {payment_db_id} not found or mismatch for user {user_db_id}.")
            await query.message.edit_text("خطا: رکورد پرداخت شما یافت نشد. با پشتیبانی تماس بگیرید.")
            return ConversationHandler.END
        
        if current_payment_record['status'] == 'completed':
            logger.info(f"Zarinpal payment {payment_db_id} for authority {zarinpal_authority} already marked as completed for user {telegram_id}.")
            await query.message.edit_text(
                "پرداخت شما قبلاً با موفقیت تایید و اشتراک شما فعال شده است.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]])
            )
            return ConversationHandler.END

        if verification_result and verification_result.get('status') == ZARINPAL_VERIFY_SUCCESS_STATUS:
            ref_id = verification_result.get('ref_id')
            logger.info(f"Zarinpal payment successful for user {telegram_id}, authority {zarinpal_authority}, ref_id {ref_id}.")
            Database.update_payment_status(payment_db_id, 'completed', transaction_id=str(ref_id))
            activation_details = await activate_or_extend_subscription(
                user_id=user_db_id,
                telegram_id=telegram_id,
                plan_id=plan_id,
                plan_name=selected_plan_name,
                payment_amount=float(rial_amount),
                payment_method='zarinpal',
                transaction_id=str(ref_id),
                context=context,
                payment_table_id=payment_db_id
            )
            success_message = PAYMENT_SUCCESS_MESSAGE.format(
                plan_name=selected_plan_name,
                expiry_date=activation_details.get('new_expiry_date_jalali', 'N/A')
            )
            await query.message.edit_text(success_message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))
            UserAction.log_user_action(telegram_id, 'zarinpal_payment_verified', {'payment_db_id': payment_db_id, 'plan_id': plan_id, 'amount': rial_amount, 'zarinpal_authority': zarinpal_authority, 'zarinpal_ref_id': ref_id, 'subscription_details': activation_details})
            for key in ['zarinpal_authority', 'rial_amount_for_zarinpal', 'selected_plan_id', 'payment_db_id_zarinpal', 'selected_plan_name']:
                context.user_data.pop(key, None)
            return ConversationHandler.END
        elif verification_result and verification_result.get('status') == 101: # Already verified by Zarinpal
            ref_id = verification_result.get('ref_id')
            logger.warning(f"Zarinpal payment for authority {zarinpal_authority} (user {telegram_id}) already verified by Zarinpal (status 101). Ref ID: {ref_id}. Checking our DB status.")
            if current_payment_record['status'] != 'completed':
                logger.info(f"Processing Zarinpal status 101 as success for payment_db_id {payment_db_id} (user {telegram_id}) as it's not completed in our DB.")
                Database.update_payment_status(payment_db_id, 'completed', transaction_id=str(ref_id))
                activation_details = await activate_or_extend_subscription(
                    user_id=user_db_id,
                    telegram_id=telegram_id,
                    plan_id=plan_id,
                    plan_name=selected_plan_name,
                    payment_amount=float(rial_amount),
                    payment_method='zarinpal',
                    transaction_id=str(ref_id),
                    context=context,
                    payment_table_id=payment_db_id
                )
                success_message = PAYMENT_SUCCESS_MESSAGE.format(plan_name=selected_plan_name, expiry_date=activation_details.get('new_expiry_date_jalali', 'N/A'))
                await query.message.edit_text(success_message, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))
                UserAction.log_user_action(telegram_id, 'zarinpal_payment_verified_status_101', {'payment_db_id': payment_db_id, 'zarinpal_ref_id': ref_id, 'subscription_details': activation_details})
                for key in ['zarinpal_authority', 'rial_amount_for_zarinpal', 'selected_plan_id', 'payment_db_id_zarinpal', 'selected_plan_name']:
                    context.user_data.pop(key, None)
                return ConversationHandler.END
            else:
                await query.message.edit_text("این پرداخت قبلاً تایید شده است.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))
                return ConversationHandler.END
        else:
            error_code = verification_result.get('status', 'N/A')
            error_message_zarinpal = verification_result.get('error_message', 'خطای نامشخص از زرین‌پال')
            logger.error(f"Zarinpal payment verification failed for user {telegram_id}, authority {zarinpal_authority}. Status: {error_code}, Message: {error_message_zarinpal}")
            Database.update_payment_status(payment_db_id, 'failed', error_code=str(error_code))
            await query.message.edit_text(
                f"متاسفانه تایید پرداخت شما با مشکل مواجه شد (کد خطا: {error_code}).\n{error_message_zarinpal}\n"
                "لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("تلاش مجدد برای بررسی", callback_data=VERIFY_ZARINPAL_PAYMENT_CALLBACK)],
                    [get_back_to_payment_methods_button()],
                    [InlineKeyboardButton(TEXT_GENERAL_BACK_TO_MAIN_MENU, callback_data=CALLBACK_BACK_TO_MAIN_MENU)]
                ])
            )
            UserAction.log_user_action(telegram_id, 'zarinpal_verification_failed', {'payment_db_id': payment_db_id, 'zarinpal_authority': zarinpal_authority, 'error_code': error_code, 'error_message': error_message_zarinpal})
            return VERIFY_PAYMENT
    except Exception as e:
        logger.exception(f"Exception in payment_verify_zarinpal_handler for user {telegram_id}, authority {zarinpal_authority}: {e}")
        await query.message.edit_text("خطایی در هنگام بررسی پرداخت رخ داد. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))
        UserAction.log_user_action(telegram_id, 'zarinpal_verification_exception', {'zarinpal_authority': zarinpal_authority, 'error': str(e)})
        if payment_db_id:
            Database.update_payment_status(payment_db_id, 'error', error_code='handler_exception')
        return ConversationHandler.END

async def back_to_payment_methods_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت به انتخاب روش پرداخت و پاک‌سازی context مرحله تأیید پرداخت"""
    query = update.callback_query
    user_id = update.effective_user.id
    Database.update_user_activity(user_id)
    # پاک‌سازی context مرحله تأیید پرداخت
    for key in ['payment_info', 'payment_db_id']:
        context.user_data.pop(key, None)
    selected_plan = context.user_data.get('selected_plan_details')
    if not selected_plan:
        await query.message.edit_text(
            "خطا: اطلاعات طرح انتخاب شده یافت نشد. لطفاً مجدداً طرح را انتخاب کنید.",
            reply_markup=get_subscription_plans_keyboard()
        )
        return SELECT_PLAN

    # Always refresh plan from DB to ensure all fields (like price_tether) are present
    plan_id = selected_plan.get('id')
    db_plan = Database.get_plan(plan_id)
    if db_plan:
        selected_plan = dict(db_plan)
        context.user_data['selected_plan_details'] = selected_plan

    await query.answer()

    # Check if price has expired (30 minutes)
    from datetime import datetime
    price_expiry = context.user_data.get('price_expiry')
    if price_expiry:
        expiry_time = datetime.fromisoformat(price_expiry)
        if datetime.utcnow() > expiry_time:
            await query.edit_message_text(
                "⚠️ قیمت محاسبه شده منقضی شده است. لطفاً دوباره پلن را انتخاب کنید.",
                reply_markup=get_subscription_plans_keyboard(user_id)
            )
            return SELECT_PLAN
    
    # Use the stored live prices
    live_irr_price = context.user_data.get('live_irr_price')
    live_usdt_price = context.user_data.get('live_usdt_price')
    
    if live_irr_price is None or live_usdt_price is None:
        await query.edit_message_text(
            "خطا در محاسبه قیمت. لطفاً دوباره پلن را انتخاب کنید.",
            reply_markup=get_subscription_plans_keyboard(user_id)
        )
        return SELECT_PLAN
    
    plan_price_irr_formatted = f"{int(live_irr_price):,}"
    plan_price_usdt_formatted = f"{live_usdt_price}"
    from utils.text_utils import buttonize_markdown
    plan_display_name = buttonize_markdown(selected_plan.get('name', 'N/A'))
    message_text = PAYMENT_METHOD_MESSAGE.format(
        plan_name=plan_display_name,
        plan_price=plan_price_irr_formatted,
        plan_tether=plan_price_usdt_formatted
    )
    await query.message.edit_text(
        text=message_text,
        reply_markup=get_payment_methods_keyboard()
    )
    return SELECT_PAYMENT_METHOD


async def cancel_subscription_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the payment conversation, cleaning up user_data."""
    user_id = update.effective_user.id
    logger.info(f"User {user_id} cancelled the subscription/payment flow.")
    
    # Clean up user_data related to the payment flow
    for key in ['selected_plan_details', 'live_usdt_price', 'payment_method', 'payment_info', 'payment_db_id', 'zarinpal_authority']:
        context.user_data.pop(key, None)

    cancel_message = "فرایند خرید محصولات لغو شد. برای شروع مجدد، از منوی اصلی اقدام کنید."
    
    query = update.callback_query
    if query:
        await query.answer()
        # Using edit_message_text to provide feedback and remove the inline keyboard.
        await query.edit_message_text(text=cancel_message, reply_markup=None)
    else:
        # If cancelled via /cancel command
        await update.message.reply_text(text=cancel_message, reply_markup=get_main_menu_keyboard(user_id))

    return ConversationHandler.END


async def prompt_for_discount_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompts the user to enter their discount code."""
    query = update.callback_query
    await query.answer()

    await safe_edit_message_text(
        query.message,
        text="لطفاً کد تخفیف خود را وارد کنید:",
        reply_markup=get_back_to_ask_discount_keyboard()
    )
    return VALIDATE_DISCOUNT

async def validate_discount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validates the discount code entered by the user."""
    user_id = update.effective_user.id
    discount_code = update.message.text.strip()

    discount = Database.get_discount_by_code(discount_code)
    selected_plan = context.user_data.get('selected_plan_details')
    
    # Check if price has expired (30 minutes)
    from datetime import datetime
    price_expiry = context.user_data.get('price_expiry')
    if price_expiry:
        expiry_time = datetime.fromisoformat(price_expiry)
        if datetime.utcnow() > expiry_time:
            await update.message.reply_text(
                "⚠️ قیمت محاسبه شده منقضی شده است. لطفاً دوباره پلن را انتخاب کنید.",
                reply_markup=get_subscription_plans_keyboard(user_id)
            )
            return ConversationHandler.END
    
    # Get the current calculated IRR price
    final_price = context.user_data.get('live_irr_price')
    if final_price is None:
        await update.message.reply_text(
            "خطا در محاسبه قیمت. لطفاً دوباره پلن را انتخاب کنید.",
            reply_markup=get_subscription_plans_keyboard(user_id)
        )
        return ConversationHandler.END

    error_message = None
    if not discount:
        error_message = "کد تخفیف وارد شده معتبر نیست."
    else:
        # Convert sqlite3.Row to dict properly
        if hasattr(discount, 'keys'):
            discount_dict = {key: discount[key] for key in discount.keys()}
        else:
            discount_dict = dict(discount)
            
        if not discount_dict['is_active']:
            error_message = "این کد تخفیف دیگر فعال نیست."
        elif discount_dict['start_date'] and datetime.strptime(discount_dict['start_date'], '%Y-%m-%d') > datetime.now():
            error_message = "زمان استفاده از این کد تخفیف هنوز شروع نشده است."
        elif discount_dict['end_date'] and datetime.strptime(discount_dict['end_date'], '%Y-%m-%d') < datetime.now():
            error_message = "زمان استفاده از این کد تخفیف به پایان رسیده است."
        elif discount_dict['max_uses'] is not None and discount_dict['uses_count'] >= discount_dict['max_uses']:
            error_message = "ظرفیت استفاده از این کد تخفیف به اتمام رسیده است."
        else:
            # Check if discount is applicable to the selected plan
            applicable_plans = Database.get_plans_for_discount(discount_dict['id'])
            # Convert plan Row objects to dicts for comparison
            plan_ids = []
            for p in applicable_plans:
                if hasattr(p, 'keys'):
                    p_dict = {key: p[key] for key in p.keys()}
                else:
                    p_dict = dict(p)
                plan_ids.append(p_dict['id'])
            
            if not any(pid == selected_plan['id'] for pid in plan_ids):
                error_message = "این کد تخفیف برای پلن انتخابی شما معتبر نیست."

    if error_message:
        await update.message.reply_text(
            error_message + "\nلطفاً یک کد تخفیف معتبر وارد کنید یا با دکمهٔ «بازگشت» به مرحلهٔ قبل بروید.",
            reply_markup=get_back_to_ask_discount_keyboard()
        )
        return VALIDATE_DISCOUNT

    # Apply discount (use discount_dict from above)
    if discount_dict['type'] == 'percentage':
        final_price -= final_price * (discount_dict['value'] / 100)
    elif discount_dict['type'] == 'fixed_amount':
        final_price -= discount_dict['value']
    
    final_price = int(max(0, final_price)) # Ensure price doesn't go below zero and is an integer
    context.user_data['final_price'] = final_price
    context.user_data['discount_id'] = discount_dict['id']

    # If price is zero after discount, activate subscription directly
    if final_price == 0:
        plan_id = context.user_data['selected_plan']['id']
        
        # Create a placeholder payment record for this free activation
        payment_id = Database.create_payment(
            user_id=user_id,
            plan_id=plan_id,
            amount=0,
            payment_method='discount_100',
            status='completed',
            description=f"Activated with 100% discount code id: {discount_dict['id']}"
        )

        success, message = await activate_or_extend_subscription(
            user_id=user_id,
            telegram_id=user_id,
            plan_id=plan_id,
            plan_name=selected_plan.get('name', 'N/A'),
            payment_amount=0,
            payment_method='discount_100',
            transaction_id=f"discount_{discount_dict['id']}",
            context=context,
            payment_table_id=payment_id
        )
        
        if success:
            # Increment discount usage count
            Database.increment_discount_usage(discount_dict['id'])
            logger.info(f"User {user_id} activated plan {plan_id} for free using discount code ID {discount_dict['id']}.")
            # پیام لینک‌ها در activate_or_extend_subscription ارسال شده است؛ ارسال دوباره لازم نیست.
            context.user_data.clear()
            return ConversationHandler.END
        else:
            await update.message.reply_text(f"خطایی در فعال‌سازی اشتراک رخ داد: {message}")
            return ConversationHandler.END

    # If price is not zero, proceed to payment
    if final_price is not None:
        await update.message.reply_text(f"تخفیف با موفقیت اعمال شد. قیمت جدید (تقریبی): {final_price:,} ریال")
    else:
        await update.message.reply_text("تخفیف با موفقیت اعمال شد. قیمت جدید محاسبه نشد.")

    keyboard = get_payment_methods_keyboard()
    await update.message.reply_text(
        'لطفاً روش پرداخت خود را انتخاب کنید:',
        reply_markup=keyboard
    )
    return SELECT_PAYMENT_METHOD



# ================= Crypto Transaction Verification =================
async def ask_for_tx_hash_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to send Tx Hash after clicking the button."""
    query = update.callback_query
    await query.answer()
    telegram_id = update.effective_user.id

    help_text = (
        "✅ پرداخت را در کیف‌پول خود انجام دهید، سپس کد «TxID / Transaction Hash» "
        "تراکنش USDT (شبکه TRON) را ارسال کنید.\n\n"
        "• معمولاً به‌صورت رشته‌ای ۶۴ کاراکتری شامل حروف و ارقام است.\n"
        "• فقط خود کد را بدون توضیح اضافی بفرستید.\n"
        "• مثال: <code>ab12cd34ef56...</code>\n\n"
        "در صورتی که مبلغ پرداختی کمتر از قیمت پلن باشد، تراکنش مردود می‌شود؛ مبلغ مساوی یا بیشتر قابل قبول است."
    )

    # علامت‌گذاری حالت انتظار برای دریافت TxHash تا UnknownHandler دخالت نکند
    context.user_data['awaiting_tx_hash'] = True

    await query.message.edit_text(
        help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [get_back_to_payment_methods_button()]
        ])
    )
    return WAIT_FOR_TX_HASH

async def receive_tx_hash_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive Tx Hash from user, verify via TronGrid, handle success/failure."""
    telegram_id = update.effective_user.id
    tx_hash = update.message.text.strip()
    crypto_payment_id = context.user_data.get('crypto_payment_id')
    if not crypto_payment_id:
        await update.message.reply_text("پرداختی برای بررسی یافت نشد.")
        return ConversationHandler.END

    payment_record = Database.get_payment_by_id(crypto_payment_id)
    if not payment_record:
        await update.message.reply_text("اطلاعات پرداخت در پایگاه‌داده یافت نشد.")
        return ConversationHandler.END

    min_amount = payment_record['usdt_amount_requested']
    wallet_address = payment_record['wallet_address'] or config.CRYPTO_WALLET_ADDRESS

    verified, amount = CryptoPaymentService.verify_payment_by_hash(tx_hash, min_amount, wallet_address)
    if verified:
        # موفق
        Database.update_crypto_payment_on_success(payment_record['payment_id'], tx_hash, amount)
        # TODO: Activate subscription (reuse activate_or_extend_subscription)
        await update.message.reply_text(
            f"✅ تراکنش با مبلغ {amount:.2f} USDT تأیید شد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]])
        )
        return ConversationHandler.END
    else:
        from utils.keyboards import get_back_to_payment_methods_button
        await update.message.reply_text(
            "❌ تراکنش نامعتبر بود یا مبلغ کافی نیست. دوباره بررسی و کد صحیح را ارسال کنید.",
            reply_markup=InlineKeyboardMarkup([[get_back_to_payment_methods_button()]])
        )
        return WAIT_FOR_TX_HASH
async def payment_verify_crypto_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Verifies USDT (TRC20) payment via TronGrid when user presses the corresponding button."""
    query = update.callback_query
    await query.answer()
    telegram_id = update.effective_user.id

    crypto_payment_id = context.user_data.get('crypto_payment_id')
    if not crypto_payment_id:
        await query.message.reply_text("خطا: پرداختی برای بررسی یافت نشد.")
        return VERIFY_PAYMENT

    payment_record = Database.get_payment_by_id(crypto_payment_id)
    if not payment_record:
        await query.message.reply_text("خطا: اطلاعات پرداخت در پایگاه‌داده یافت نشد.")
        return VERIFY_PAYMENT

    expected_usdt = payment_record['usdt_amount_requested']
    wallet_address = payment_record['wallet_address'] or config.CRYPTO_WALLET_ADDRESS
    created_at_str = payment_record['created_at']
    created_at = datetime.fromisoformat(created_at_str) if isinstance(created_at_str, str) else created_at_str

    verified, tx_hash = CryptoPaymentService.verify_payment(expected_usdt, created_at, wallet_address)
    if verified:
        # Update DB status
        Database.update_crypto_payment_on_success(payment_record['payment_id'], tx_hash, expected_usdt)
        # TODO: Activate the purchased plan here, similar to Rial flow
        await query.message.edit_text(
            text=f"✅ تراکنش شما تأیید شد.\nشناسه تراکنش:\n<code>{tx_hash}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]])
        )
        return ConversationHandler.END
    else:
        await query.message.reply_text("هنوز تراکنشی با مبلغ مورد نظر یافت نشده است. چند دقیقه دیگر دوباره امتحان کنید.")
        return VERIFY_PAYMENT

payment_conversation = ConversationHandler(
    entry_points=[
        # Main menu buttons
        CallbackQueryHandler(start_subscription_flow, pattern='^start_subscription_flow$'),
        CallbackQueryHandler(start_subscription_flow, pattern='^products_menu(?:_\\d+)?$'),
        CallbackQueryHandler(start_subscription_flow, pattern='^back_to_plans$'),
        # Direct plan buttons (e.g., from reminder messages)
        CallbackQueryHandler(select_plan_handler, pattern='^plan_\\d+$'),
        # Text menu buttons
        MessageHandler(filters.Regex(r"^(🎫 عضویت رایگان|🛒 (?:محصولات|VIP))$"), start_subscription_flow),
    ],
    states={
        SELECT_PLAN: [
            CallbackQueryHandler(select_plan_handler, pattern='^plan_'),
        ],
        ASK_DISCOUNT: [
            CallbackQueryHandler(prompt_for_discount_code, pattern='^have_discount_code$'),
            CallbackQueryHandler(show_payment_methods, pattern='^skip_discount_code$'),
            CallbackQueryHandler(start_subscription_flow, pattern='^back_to_plans$'),
        ],
        VALIDATE_DISCOUNT: [
            CallbackQueryHandler(ask_discount_handler, pattern='^back_to_ask_discount$'),
            MessageHandler(filters.TEXT & ~filters.COMMAND, validate_discount_handler)
        ],
        SELECT_PAYMENT_METHOD: [
            CallbackQueryHandler(select_payment_method, pattern='^payment_(rial|crypto)$'),
            CallbackQueryHandler(start_subscription_flow, pattern='^back_to_plans$'),
            MessageHandler(filters.Regex(r"^(🎫 عضویت رایگان|🛒 (?:محصولات|VIP))$"), start_subscription_flow),
        ],
        VERIFY_PAYMENT: [
            CallbackQueryHandler(verify_payment_status, pattern='^payment_verify$'),
            CallbackQueryHandler(ask_for_tx_hash_handler, pattern='^payment_send_tx$'),
            CallbackQueryHandler(payment_verify_zarinpal_handler, pattern=f'^{VERIFY_ZARINPAL_PAYMENT_CALLBACK}$'),
            CallbackQueryHandler(back_to_payment_methods_handler, pattern='^back_to_payment_methods$'),
            CallbackQueryHandler(start_subscription_flow, pattern='^back_to_plans$'),
            MessageHandler(filters.Regex(r"^(🎫 عضویت رایگان|🛒 (?:محصولات|VIP))$"), start_subscription_flow),
        ],
        WAIT_FOR_TX_HASH: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_tx_hash_handler),
            CallbackQueryHandler(back_to_payment_methods_handler, pattern='^back_to_payment_methods$'),
            CallbackQueryHandler(start_subscription_flow, pattern='^back_to_plans$'),
        ],
    },
    fallbacks=[
        CommandHandler('cancel', cancel_subscription_flow),
        CallbackQueryHandler(cancel_subscription_flow, pattern='^cancel_payment_flow$'),
        CallbackQueryHandler(back_to_main_menu_from_payment_handler, pattern='^back_to_main_menu$'),
    ],
    conversation_timeout=config.PAYMENT_CONVERSATION_TIMEOUT,
    name="payment_flow_conversation",
    persistent=True,
    per_user=True,
    per_chat=True,
    allow_reentry=True
)
