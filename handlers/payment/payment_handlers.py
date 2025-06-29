"""
Payment handlers for the Daraei Academy Telegram bot
"""

from services.crypto_payment_service import CryptoPaymentService
from services.zarinpal_service import ZarinpalPaymentService # Added for Zarinpal
from config import CRYPTO_WALLET_ADDRESS, CRYPTO_PAYMENT_TIMEOUT_MINUTES, RIAL_GATEWAY_URL, CRYPTO_GATEWAY_URL, PAYMENT_CONVERSATION_TIMEOUT # Added CRYPTO_WALLET_ADDRESS, CRYPTO_PAYMENT_TIMEOUT_MINUTES

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, ReplyKeyboardMarkup, KeyboardButton
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

from datetime import datetime, timedelta
import uuid
# import config # Direct access to SUBSCRIPTION_PLANS removed
from database.queries import DatabaseQueries as Database
from utils.price_utils import get_usdt_to_irr_rate, convert_irr_to_usdt
from config import RIAL_GATEWAY_URL, CRYPTO_GATEWAY_URL # Assuming these are still needed from config
from utils.keyboards import (
    get_subscription_plans_keyboard, get_payment_methods_keyboard,
    get_back_to_plans_button, get_back_to_payment_methods_button,
    get_main_menu_keyboard
)

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
SELECT_PLAN = 0
SELECT_PAYMENT_METHOD = 1
PROCESS_PAYMENT = 2
VERIFY_PAYMENT = 3

async def back_to_main_menu_from_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت به منو اصلی و پاک‌سازی context پرداخت"""
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
        await safe_edit_message_text(
            query.message,
            text=SUBSCRIPTION_PLANS_MESSAGE,
            reply_markup=get_subscription_plans_keyboard(user_id),
            parse_mode=ParseMode.HTML
        )
    # If called via Message (e.g. reply keyboard)
    elif update.message:
        await update.message.reply_text(
            text=SUBSCRIPTION_PLANS_MESSAGE,
            reply_markup=get_subscription_plans_keyboard(user_id),
            parse_mode=ParseMode.HTML
        )
    else:
        logger.error("start_subscription_flow called but neither callback_query nor message is present in update.")
        return ConversationHandler.END

    # Clear any previous plan selection from context to ensure a fresh start.
    context.user_data.pop('selected_plan_details', None)
    context.user_data.pop('live_usdt_price', None)
    return SELECT_PLAN

async def select_plan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the user's plan selection and proceeds to payment method selection."""
    query = update.callback_query
    user_id = update.effective_user.id
    logger.info(f"[select_plan_handler] User {user_id} triggered with data: {query.data}")
    await query.answer()

    Database.update_user_activity(user_id)

    # The ConversationHandler's pattern ensures query.data starts with 'plan_'
    callback_data = query.data.split('_')
    try:
        numeric_plan_id = int(callback_data[1])
    except (ValueError, IndexError):
        logger.error(f"[select_plan_handler] Invalid plan_id format from callback: {query.data} for user {user_id}")
        await query.message.edit_text("خطا: شناسه طرح نامعتبر است.")
        return SELECT_PLAN

    selected_plan = Database.get_plan_by_id(numeric_plan_id)
    logger.info(f"[select_plan_handler] Selected plan: {selected_plan}")

    # Handle free plans immediately
    # sqlite3.Row objects are accessed by index or key, not with .get()
    # Treat plans with a price of 0 or NULL as free plans
    if selected_plan and float(selected_plan['price'] or 0) == 0:
        logger.info(f"[select_plan_handler] Detected free plan: {selected_plan['name']}. Processing... ")
        plan_id = selected_plan['id']

        # 1. Check if user has already used this free plan
        if Database.has_user_used_free_plan(user_id, plan_id):
            logger.warning(f"User {user_id} has already used free plan {plan_id}.")
            keyboard = [[InlineKeyboardButton("بازگشت به پروفایل کاربری", callback_data='back_to_main_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                text="شما قبلاً از این طرح رایگان استفاده کرده‌اید و امکان دریافت مجدد آن وجود ندارد.",
                reply_markup=reply_markup
            )
            return ConversationHandler.END

        # 2. Check for plan capacity
        # The 'capacity' column must exist in the 'plans' table for this to work.
        capacity = selected_plan['capacity'] if 'capacity' in selected_plan.keys() and selected_plan['capacity'] is not None else None
        if capacity is not None:
            logger.info(f"Checking total capacity for plan {plan_id}. Capacity: {capacity}")
            subscription_count = Database.count_total_subscriptions_for_plan(plan_id)
            logger.info(f"Total subscriptions ever created for plan {plan_id}: {subscription_count}")

            if subscription_count >= capacity:
                logger.warning(f"Free plan {plan_id} has reached its capacity. Deactivating plan.")
                # Deactivate the plan for future users
                Database.deactivate_plan(plan_id)
                keyboard = [[InlineKeyboardButton("بازگشت به پروفایل کاربری", callback_data='back_to_main_menu')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    text="ظرفیت این طرح رایگان تکمیل شده است و دیگر در دسترس نیست.",
                    reply_markup=reply_markup
                )
                return ConversationHandler.END

        # 3. If all checks pass, activate the subscription
        logger.info(f"Activating free subscription for user {user_id} and plan {plan_id}.")
        telegram_id = query.from_user.id
        transaction_id = f"FREE_PLAN_{user_id}_{plan_id}"
        payment_id = None  # No payment record for free plans
        amount = 0
        payment_method = 'free'
        plan_name = selected_plan['name']

        success, error_message = await activate_or_extend_subscription(
            user_id=user_id,
            telegram_id=telegram_id,
            plan_id=plan_id,
            plan_name=plan_name,
            payment_amount=amount,
            payment_method=payment_method,
            transaction_id=transaction_id,
            context=context,
            payment_table_id=payment_id
        )

        if success:
            await query.edit_message_text("✅ اشتراک رایگان شما با موفقیت فعال شد!")
        else:
            await query.edit_message_text(
                f"مشکلی در فعال‌سازی اشتراک رایگان شما پیش آمد. {error_message if error_message else 'لطفاً با پشتیبانی تماس بگیرید.'}"
            )
        
        return ConversationHandler.END
    if not selected_plan or not selected_plan['is_active']:
        logger.warning(f"[select_plan_handler] Plan not found or inactive: {numeric_plan_id}")
        await query.message.edit_text(
            "خطا: طرح انتخاب شده معتبر نیست یا دیگر فعال نمی‌باشد. لطفاً مجدداً یک طرح را انتخاب کنید.",
            reply_markup=get_subscription_plans_keyboard(user_id)
        )
        return SELECT_PLAN

    context.user_data['selected_plan_details'] = dict(selected_plan)
    plan_price_irr_formatted = f"{int(selected_plan['price']):,}" if selected_plan['price'] is not None else "N/A"
    usdt_rate = await get_usdt_to_irr_rate()
    if usdt_rate and selected_plan['price'] is not None:
        converted_usdt_price = convert_irr_to_usdt(float(selected_plan['price']), usdt_rate)
        plan_price_usdt_formatted = f"{converted_usdt_price}" if converted_usdt_price is not None else "N/A"
        if converted_usdt_price is not None:
            context.user_data['live_usdt_price'] = converted_usdt_price
    else:
        plan_price_usdt_formatted = "N/A"
        logger.warning(f"[select_plan_handler] Could not calculate USDT price for plan {numeric_plan_id}. USDT rate: {usdt_rate}")

    message_text = PAYMENT_METHOD_MESSAGE.format(
        plan_name=selected_plan['name'],
        plan_price=plan_price_irr_formatted,
        plan_tether=plan_price_usdt_formatted
    )
    logger.info(f"[select_plan_handler] Sending payment methods keyboard for user {user_id}.")
    keyboard = get_payment_methods_keyboard()
    for row in keyboard.inline_keyboard:
        for btn in row:
            logger.info(f"[select_plan_handler] Button text: {btn.text}, callback_data: {btn.callback_data}")
    await query.message.edit_text(
        text=message_text,
        reply_markup=keyboard
    )
    logger.info(f"[select_plan_handler] Returning SELECT_PAYMENT_METHOD for user {user_id}.")
    return SELECT_PAYMENT_METHOD
    


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

    plan_id = selected_plan['id']
    # Fetch full plan with price_tether from DB
    db_plan = Database.get_plan(plan_id)
    if db_plan is not None:
        selected_plan = dict(db_plan)
        context.user_data['selected_plan_details'] = selected_plan
    plan_name = selected_plan['name']

    if payment_method == 'rial':
        transaction_id = str(uuid.uuid4())[:8].upper()
        context.user_data['transaction_id'] = transaction_id
        plan_price_irr = selected_plan['price']

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
            await query.message.edit_text(PAYMENT_ERROR_MESSAGE, reply_markup=get_main_menu_keyboard(telegram_id))
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
                f"⛔ لطفا پیش از ورود به درگاه پرداخت، فیلترشکن خود را قطع کنید.\n"
                f"⚠️ <b>مهم:</b> پس از تکمیل پرداخت در سایت زرین‌پال، <b>روی دکمه زیر کلیک کنید</b> تا اشتراک شما فعال شود."
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
        rial_amount = selected_plan.get('price')
        # price_tether = selected_plan.get('price_tether') # Using live calculated price now
        live_calculated_usdt_price = context.user_data.get('live_usdt_price')

        if live_calculated_usdt_price is None or live_calculated_usdt_price <= 0:
            logger.warning(f"Plan {plan_id} has invalid live_calculated_usdt_price {live_calculated_usdt_price} for crypto payment. telegram_id: {telegram_id}")
            await query.message.edit_text("خطا: قیمت محاسبه شده تتر برای طرح نامعتبر است یا یافت نشد. لطفاً مجدداً تلاش کنید.", reply_markup=get_payment_methods_keyboard())
            return SELECT_PAYMENT_METHOD
        if rial_amount is None or rial_amount <= 0:
            logger.warning(f"Plan {plan_id} has invalid rial_amount {rial_amount} for crypto payment. telegram_id: {telegram_id}")
            await query.message.edit_text("خطا: قیمت ریالی طرح برای محاسبه معادل تتر مشخص نشده است.", reply_markup=get_payment_methods_keyboard())
            return SELECT_PAYMENT_METHOD

        expires_at = datetime.now() + timedelta(minutes=CRYPTO_PAYMENT_TIMEOUT_MINUTES)

        # Step 1: Create a preliminary crypto payment request entry to get an ID.
        rial_plan_price = selected_plan.get('price') # Get RIAL price of the plan
        payment_timeout_minutes = config.CRYPTO_PAYMENT_TIMEOUT_MINUTES
        expires_at_dt = datetime.now() + timedelta(minutes=payment_timeout_minutes)

        crypto_payment_request_db_id = Database.create_crypto_payment_request(
            user_id=user_db_id,
            rial_amount=rial_plan_price, # Pass the RIAL amount of the plan
            usdt_amount_requested=live_calculated_usdt_price, # This is the base USDT price for the plan
            wallet_address=config.CRYPTO_WALLET_ADDRESS,
            expires_at=expires_at_dt
        )
        logger.info(f"User {telegram_id} (DB ID: {user_db_id}): Crypto payment_request_db_id: {crypto_payment_request_db_id}. Result from Database.create_crypto_payment_request.")

        if not crypto_payment_request_db_id:
            UserAction.log_user_action(
                telegram_id=telegram_id, 
                action_type='crypto_placeholder_creation_failed',
                details={'plan_id': plan_id, 'rial_amount': rial_amount, 'user_db_id': user_db_id}
            )
            logger.error(f"Failed to create placeholder crypto payment request for user_db_id {user_db_id}, plan {plan_id}.")
            await query.message.edit_text(PAYMENT_ERROR_MESSAGE, reply_markup=get_main_menu_keyboard(telegram_id))
            return ConversationHandler.END # Or SELECT_PAYMENT_METHOD

        logger.info(f"User {telegram_id} (DB ID: {user_db_id}): About to call Database.create_crypto_payment_request for plan {selected_plan['id']}, price_tether: {selected_plan['price_tether']}")

        try:
            # Step 2: Calculate the unique USDT amount using the obtained ID.
            logger.info(f"User {telegram_id} (DB ID: {user_db_id}): Crypto payment_request_db_id: {crypto_payment_request_db_id}. About to call CryptoPaymentService.get_final_usdt_payment_amount with base_usdt_amount_rounded_to_3_decimals: {live_calculated_usdt_price}")
            usdt_amount_requested = CryptoPaymentService.get_final_usdt_payment_amount(
                base_usdt_amount_rounded_to_3_decimals=live_calculated_usdt_price # live_calculated_usdt_price is the USDT amount for the plan, already rounded to 3 decimals
            )
            # The following log line can be adjusted if needed, as 'unique_amount' might be misleading now.
            # Perhaps change 'unique_amount' to 'final_amount' or 'requested_amount'.
            logger.info(f"User {telegram_id} (DB ID: {user_db_id}): Crypto final_usdt_amount_data: {{'final_amount': {usdt_amount_requested}, 'id': {crypto_payment_request_db_id}}}")
            context.user_data['usdt_amount_requested'] = usdt_amount_requested

        except Exception as e:
            logger.exception(f"Error calculating USDT amount for rial_amount {rial_amount}, payment_id {crypto_payment_request_db_id}. telegram_id: {telegram_id}")
            # Consider updating DB record status to 'calculation_exception'
            await query.message.edit_text("خطا در سیستم تبدیل ارز. لطفاً لحظاتی دیگر تلاش کنید یا با پشتیبانی تماس بگیرید.", reply_markup=get_payment_methods_keyboard())
            return SELECT_PAYMENT_METHOD

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
            await query.message.edit_text("خطای سیستمی هنگام ثبت مبلغ تتر. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=get_main_menu_keyboard(telegram_id))
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
            usdt_amount=f"{usdt_amount_requested:.3f}",
            timeout_minutes=CRYPTO_PAYMENT_TIMEOUT_MINUTES
        )



        keyboard_buttons = [
            [InlineKeyboardButton("📷 نمایش QR کد", callback_data=f"show_qr_code_{crypto_payment_request_db_id}")],
            [InlineKeyboardButton("تراکنش را انجام دادم، بررسی شود", callback_data="payment_verify_crypto")]
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

async def show_qr_code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'show_qr_code' callback to display the USDT wallet QR code."""
    query = update.callback_query
    await query.answer()  # Acknowledge the callback

    # crypto_payment_request_db_id = query.data.split('show_qr_code_')[-1] # If ID is needed for logging or other purposes
    # logger.info(f"User {query.from_user.id} requested QR code for payment request ID: {crypto_payment_request_db_id}")

    wallet_address = config.CRYPTO_WALLET_ADDRESS
    if not wallet_address:
        logger.error("CRYPTO_WALLET_ADDRESS is not set in config.")
        # It's better to reply to the message or edit it, rather than sending a new one if it's an error related to a button press
        await query.edit_message_text("خطا: آدرس کیف پول برای نمایش QR کد تنظیم نشده است.")
        return

    try:
        # Generate QR code
        qr_img = qrcode.make(wallet_address)
        
        # Save QR code to a BytesIO object
        img_byte_arr = io.BytesIO()
        qr_img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0) # Go to the beginning of the BytesIO buffer

        usdt_amount_requested = context.user_data.get('usdt_amount_requested', 'N/A')
        usdt_amount_formatted = f"{usdt_amount_requested:.3f}" if isinstance(usdt_amount_requested, (float, int)) else usdt_amount_requested

        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=InputFile(img_byte_arr, filename='usdt_wallet_qr.png'),
            caption=f"اسکن کنید:\nآدرس کیف پول تتر (TRC20):\n{wallet_address}\n\nمبلغ دقیق برای واریز: {usdt_amount_formatted} USDT",
            parse_mode=ParseMode.MARKDOWN,
            reply_to_message_id=query.message.message_id # Reply to the message with the button
        )

        # Modify the keyboard of the original message
        current_markup = query.message.reply_markup
        if current_markup:
            new_buttons = []
            for row in current_markup.inline_keyboard:
                new_row = []
                for button in row:
                    if button.callback_data == query.data: # Matched the button that was pressed
                        new_row.append(InlineKeyboardButton("✔ QR نمایش داده شد", callback_data="qr_code_shown_noop"))
                    else:
                        new_row.append(button)
                if new_row:
                    new_buttons.append(new_row)
            
            if new_buttons:
                try:
                    await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_buttons))
                except Exception as e_edit:
                    logger.error(f"Error editing message reply markup after showing QR: {e_edit}")
            # If new_buttons is empty (e.g., only QR button existed and was replaced by nothing), 
            # it might be better to remove the markup entirely or ensure at least one button remains.
            # For now, if new_buttons is empty, it will effectively remove the keyboard if it only had the QR button.

    except Exception as e:
        logger.exception(f"Error generating or sending QR code for wallet {wallet_address}: {e}")
        # Replying to the original message or editing it is better than sending a new message for an error
        await query.message.reply_text("خطا در تولید یا ارسال QR کد. لطفاً دوباره تلاش کنید.")

    # This handler does not change the conversation state, so it returns None implicitly
    return


async def verify_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify payment status and activate/extend subscription."""
    query = update.callback_query
    telegram_id = update.effective_user.id # Renamed from user_id for clarity
    user_db_id = None # Will be populated after fetching payment record

    Database.update_user_activity(telegram_id) # Uses telegram_id

    user_db_id = context.user_data.get('user_db_id')
    selected_plan_details = context.user_data.get('selected_plan_details')
    logger.info(f"User {telegram_id} (DB ID: {user_db_id}): Entered select_payment_method with callback_data: {query.data}. Plan selected: {selected_plan_details is not None}")
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
            
            base_success_message = PAYMENT_SUCCESS_MESSAGE.format(
                plan_name=plan_name,
                end_date=display_end_date
            )
            channel_links_parts = []
            if hasattr(config, 'TELEGRAM_CHANNELS_INFO') and config.TELEGRAM_CHANNELS_INFO:
                channel_links_parts.append("\n\nلینک کانال‌ها و گروه‌های اختصاصی شما:")
                for channel_info in config.TELEGRAM_CHANNELS_INFO:
                    title = channel_info.get('title', 'کانال')
                    link = channel_info.get('link')
                    if link:
                        channel_links_parts.append(f"- [{title}]({link})")
            full_success_message = base_success_message + "\n".join(channel_links_parts)

            await query.message.edit_text(
                full_success_message,
                reply_markup=get_main_menu_keyboard(user_id=telegram_id),
                parse_mode=ParseMode.MARKDOWN
            )
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
            caption=f"آدرس کیف پول (TRC20):\n`{wallet_address}`\n\nمبلغ: `{usdt_amount:.6f}` USDT (در صورت نمایش در QR)\n\nاسکن کنید:"
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
            reply_markup=get_main_menu_keyboard(telegram_id)
        )
        UserAction.log_user_action(telegram_id, 'zarinpal_verification_failed', {'reason': 'missing_context_data'})
        return ConversationHandler.END

    try:
        logger.info(f"Verifying Zarinpal payment for user {telegram_id}, authority {zarinpal_authority}, amount {rial_amount}")
        verification_result = ZarinpalPaymentService.verify_payment(amount=rial_amount, authority=zarinpal_authority)
        
        current_payment_record = Database.get_payment_by_id(payment_db_id)
        if not current_payment_record or current_payment_record['user_id'] != user_db_id:
            logger.error(f"Zarinpal verification: Payment record {payment_db_id} not found or mismatch for user {user_db_id}.")
            await query.message.edit_text("خطا: رکورد پرداخت شما یافت نشد. با پشتیبانی تماس بگیرید.")
            return ConversationHandler.END
        
        if current_payment_record['status'] == 'completed':
            logger.info(f"Zarinpal payment {payment_db_id} for authority {zarinpal_authority} already marked as completed for user {telegram_id}.")
            await query.message.edit_text(
                "پرداخت شما قبلاً با موفقیت تایید و اشتراک شما فعال شده است.",
                reply_markup=get_main_menu_keyboard(telegram_id)
            )
            return ConversationHandler.END

        if verification_result and verification_result.get('status') == ZARINPAL_VERIFY_SUCCESS_STATUS:
            ref_id = verification_result.get('ref_id')
            logger.info(f"Zarinpal payment successful for user {telegram_id}, authority {zarinpal_authority}, ref_id {ref_id}.")
            Database.update_payment_status(payment_db_id, 'completed', transaction_id=str(ref_id))
            activation_details = await activate_or_extend_subscription(user_db_id, plan_id, payment_db_id, 'zarinpal', telegram_id, context)
            success_message = PAYMENT_SUCCESS_MESSAGE.format(
                plan_name=selected_plan_name,
                expiry_date=activation_details.get('new_expiry_date_jalali', 'N/A')
            )
            await query.message.edit_text(success_message, reply_markup=get_main_menu_keyboard(telegram_id))
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
                activation_details = await activate_or_extend_subscription(user_db_id, plan_id, payment_db_id, 'zarinpal', telegram_id, context)
                success_message = PAYMENT_SUCCESS_MESSAGE.format(plan_name=selected_plan_name, expiry_date=activation_details.get('new_expiry_date_jalali', 'N/A'))
                await query.message.edit_text(success_message, reply_markup=get_main_menu_keyboard(telegram_id))
                UserAction.log_user_action(telegram_id, 'zarinpal_payment_verified_status_101', {'payment_db_id': payment_db_id, 'zarinpal_ref_id': ref_id, 'subscription_details': activation_details})
                for key in ['zarinpal_authority', 'rial_amount_for_zarinpal', 'selected_plan_id', 'payment_db_id_zarinpal', 'selected_plan_name']:
                    context.user_data.pop(key, None)
                return ConversationHandler.END
            else:
                await query.message.edit_text("این پرداخت قبلاً تایید شده است.", reply_markup=get_main_menu_keyboard(telegram_id))
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
        await query.message.edit_text("خطایی در هنگام بررسی پرداخت رخ داد. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=get_main_menu_keyboard(telegram_id))
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
    plan_price_irr_formatted = f"{int(selected_plan['price']):,}" if selected_plan.get('price') is not None else "N/A"

    # Recalculate live USDT price
    live_usdt_price = None
    rial_price = selected_plan.get('price')
    if rial_price:
        usdt_rate = await get_usdt_to_irr_rate() # Fetches live rate from Nobitex/Coingecko
        if usdt_rate:
            live_usdt_price = convert_irr_to_usdt(rial_price, usdt_rate)
            context.user_data['live_usdt_price'] = live_usdt_price # Store for crypto payment step
        else:
            logger.warning(f"User {update.effective_user.id}: Could not fetch USDT rate in back_to_payment_methods_handler.")
    else:
        logger.warning(f"User {update.effective_user.id}: Rial price missing for plan {selected_plan.get('id')} in back_to_payment_methods_handler.")

    plan_price_usdt_formatted = f"{live_usdt_price:.3f}" if live_usdt_price is not None else "N/A"
    message_text = PAYMENT_METHOD_MESSAGE.format(
        plan_name=selected_plan.get('name', 'N/A'),
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

    cancel_message = "فرایند خرید محصولات لغو شد. برای شروع مجدد، از منو اصلی اقدام کنید."
    
    query = update.callback_query
    if query:
        await query.answer()
        # Using edit_message_text to provide feedback and remove the inline keyboard.
        await query.edit_message_text(text=cancel_message, reply_markup=None)
    else:
        # If cancelled via /cancel command
        await update.message.reply_text(text=cancel_message, reply_markup=get_main_menu_keyboard(user_id))

    return ConversationHandler.END


payment_conversation = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_subscription_flow, pattern='^start_subscription_flow$'),
        MessageHandler(filters.Regex(r"^(🎫 خرید محصولات)$"), start_subscription_flow),
    ],
    states={
        SELECT_PLAN: [
            CallbackQueryHandler(select_plan_handler, pattern='^plan_'),
            MessageHandler(filters.Regex(r"^(🎫 خرید محصولات)$"), start_subscription_flow),
        ],
        SELECT_PAYMENT_METHOD: [
            CallbackQueryHandler(select_payment_method, pattern='^payment_(rial|crypto)$'),
            CallbackQueryHandler(start_subscription_flow, pattern='^back_to_plans$'),
            MessageHandler(filters.Regex(r"^(🎫 خرید محصولات)$"), start_subscription_flow),
        ],
        VERIFY_PAYMENT: [
            CallbackQueryHandler(verify_payment_status, pattern='^payment_verify$'),
            CallbackQueryHandler(payment_verify_zarinpal_handler, pattern=f'^{VERIFY_ZARINPAL_PAYMENT_CALLBACK}$'),
            CallbackQueryHandler(back_to_payment_methods_handler, pattern='^back_to_payment_methods$'),
            MessageHandler(filters.Regex(r"^(🎫 خرید محصولات)$"), start_subscription_flow),
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
