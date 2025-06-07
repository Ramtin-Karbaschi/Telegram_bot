"""
Payment handlers for the Daraei Academy Telegram bot
"""

from services.crypto_payment_service import CryptoPaymentService
from config import CRYPTO_WALLET_ADDRESS, CRYPTO_PAYMENT_TIMEOUT_MINUTES, RIAL_GATEWAY_URL, CRYPTO_GATEWAY_URL # Added CRYPTO_WALLET_ADDRESS, CRYPTO_PAYMENT_TIMEOUT_MINUTES

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode # Added for message formatting
import config # Added for TELEGRAM_CHANNELS_INFO
import logging
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, 
    MessageHandler, filters, CallbackQueryHandler
)
logger = logging.getLogger(__name__)

from datetime import datetime, timedelta
import uuid
# import config # Direct access to SUBSCRIPTION_PLANS removed
from database.queries import DatabaseQueries as Database
from config import RIAL_GATEWAY_URL, CRYPTO_GATEWAY_URL # Assuming these are still needed from config
from utils.keyboards import (
    get_subscription_plans_keyboard, get_payment_methods_keyboard,
    get_back_to_plans_button, get_back_to_payment_methods_button,
    get_main_menu_keyboard
)
from utils.constants import (
    SUBSCRIPTION_PLANS_MESSAGE, PAYMENT_METHOD_MESSAGE,
    RIAL_PAYMENT_MESSAGE, CRYPTO_PAYMENT_UNIQUE_AMOUNT_MESSAGE, # Changed from CRYPTO_PAYMENT_MESSAGE
    PAYMENT_VERIFICATION_MESSAGE, PAYMENT_SUCCESS_MESSAGE,
    PAYMENT_ERROR_MESSAGE # Changed from PAYMENT_FAILED_MESSAGE
)
from utils.helpers import calculate_days_left
from handlers.subscription.subscription_handlers import activate_or_extend_subscription
from utils.user_actions import UserAction

# Conversation states
SELECT_PLAN = 0
SELECT_PAYMENT_METHOD = 1
PROCESS_PAYMENT = 2
VERIFY_PAYMENT = 3

async def select_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles plan selection, can be an entry point from /subscribe or a callback query."""
    """Handle subscription plan selection"""
    user = update.effective_user
    user_id = user.id
    
    # Update user activity
    Database.update_user_activity(user_id)
    
    # Check if it's a callback query
    if update.callback_query:
        query = update.callback_query
        callback_data = query.data.split('_')
        
        # Plan ID is directly from the callback data (e.g. "plan_1")
        # The format is "plan_X" where X is the numeric ID from the database
        if len(callback_data) > 1 and callback_data[0] == 'plan':
            try:
                numeric_plan_id = int(callback_data[1])
            except ValueError:
                await query.message.edit_text("خطا: شناسه طرح نامعتبر است (فرمت اشتباه).")
                # Log this error for admin
                print(f"Error: Invalid plan_id format from callback: {query.data} for user {user_id}")
                # Consider sending a message to admin here
                return SELECT_PLAN # Or end conversation
        else:
            await query.message.edit_text("خطا: طرح نامعتبر است (داده‌های ناقص).")
            print(f"Error: Invalid callback data structure: {query.data} for user {user_id}")
            return SELECT_PLAN # Or end conversation

        selected_plan = Database.get_plan_by_id(numeric_plan_id)

        if not selected_plan or not selected_plan['is_active']:
            await query.message.edit_text("خطا: طرح انتخاب شده معتبر نیست یا دیگر فعال نمی‌باشد. لطفاً مجدداً یک طرح را انتخاب کنید.")
            # Reshow plans
            await query.message.reply_text(
                SUBSCRIPTION_PLANS_MESSAGE,
                reply_markup=get_subscription_plans_keyboard(user_id) # Pass user_id if needed by keyboard
            )
            # It might be better to end the current message and send a new one
            # await query.delete_message() # If you want to remove the old message
            return SELECT_PLAN
        
        # Store plan details in user data
        context.user_data['selected_plan_details'] = dict(selected_plan) # Ensure it's a mutable dict
        
        # Answer callback query
        await query.answer()
        
        plan_price_irr_formatted = f"{int(selected_plan['price']):,}" if selected_plan['price'] is not None else "N/A"
        try:
            price_tether_val = selected_plan['price_tether']
            plan_price_usdt_formatted = f"{price_tether_val}" if price_tether_val is not None else "N/A"
        except IndexError:
            plan_price_usdt_formatted = "N/A"  # Default if 'price_tether' key doesn't exist

        message_text = PAYMENT_METHOD_MESSAGE.format(
            plan_name=selected_plan['name'],
            plan_price=plan_price_irr_formatted,
            plan_tether=plan_price_usdt_formatted
        )
        await query.message.edit_text(
            text=message_text,
            reply_markup=get_payment_methods_keyboard()
        )
        
        return SELECT_PAYMENT_METHOD
    
    # If called by a command (update.message is not None) or if it's a callback that needs to show plans again.
    # This part is crucial: select_plan can be an entry point.
    # If update.message exists, it's likely from a CommandHandler.
    # If update.callback_query exists, it's from a CallbackQueryHandler.

    # The initial display of plans when entering the conversation:
    if update.message: # Typically from CommandHandler or first message
        await update.message.reply_text(
            SUBSCRIPTION_PLANS_MESSAGE,
            reply_markup=get_subscription_plans_keyboard(user_id) # Pass user_id if needed
        )
    elif update.callback_query and not context.user_data.get('selected_plan_details'):
        # This case might occur if 'start_subscription_flow' callback directly calls this
        # without a plan_id, or if we are re-showing plans after an error.
        await update.callback_query.message.reply_text(
            SUBSCRIPTION_PLANS_MESSAGE,
            reply_markup=get_subscription_plans_keyboard(user_id)
        )
        await update.callback_query.answer() # Answer the callback if it led here
    
    return SELECT_PLAN

async def select_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment method selection"""
    query = update.callback_query
    telegram_id = update.effective_user.id

    Database.update_user_activity(telegram_id) # Ensures user exists in DB

    user_record = Database.get_user_by_telegram_id(telegram_id)
    if not user_record:
        logger.error(f"Critical: User with telegram_id {telegram_id} not found in database after update_user_activity.")
        await query.message.edit_text("خطای سیستمی: اطلاعات کاربری شما یافت نشد. لطفاً با پشتیبانی تماس بگیرید.")
        return ConversationHandler.END
    user_db_id = user_record['user_id']

    payment_method = query.data.split('_')[1]
    context.user_data['payment_method'] = payment_method
    await query.answer()

    selected_plan = context.user_data.get('selected_plan_details')
    if not selected_plan:
        logger.warning(f"No selected_plan_details in context for telegram_id {telegram_id} in select_payment_method.")
        await query.message.edit_text("خطا: اطلاعات طرح یافت نشد. لطفاً از ابتدا شروع کنید.", reply_markup=get_subscription_plans_keyboard(telegram_id))
        return SELECT_PLAN

    plan_id = selected_plan['id']
    plan_name = selected_plan['name']

    if payment_method == 'rial':
        transaction_id = str(uuid.uuid4())[:8].upper()
        context.user_data['transaction_id'] = transaction_id
        plan_price_irr = selected_plan['price']

        payment_db_id = Database.add_payment(
            user_id=user_db_id,
            plan_id=plan_id,
            amount=plan_price_irr,
            payment_method="rial",
            description=f"اشتراک {plan_name}",
            transaction_id=transaction_id,
            status="pending"
        )

        if not payment_db_id:
            UserAction.log_user_action(
                telegram_id=telegram_id,
                user_db_id=user_db_id,
                action_type='rial_payment_creation_failed_db',
                details={
                    'plan_id': plan_id,
                    'amount': plan_price_irr,
                    'transaction_id': transaction_id
                }
            )
            logger.error(f"Failed to create Rial payment record in DB for user_db_id {user_db_id}, telegram_id {telegram_id}, plan_id {plan_id}")
            await query.message.edit_text("خطا در ایجاد درخواست پرداخت ریالی. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=get_main_menu_keyboard(telegram_id))
            return ConversationHandler.END

        UserAction.log_user_action(
            telegram_id=telegram_id,
            user_db_id=user_db_id,
            action_type='rial_payment_initiated',
            details={
                'payment_db_id': payment_db_id,
                'plan_id': plan_id,
                'amount': plan_price_irr,
                'transaction_id': transaction_id
            }
        )
        context.user_data['payment_id'] = payment_db_id

        await query.message.edit_text(
            "شما به صفحه پرداخت هدایت می‌شوید. پس از تکمیل پرداخت، لطفاً دکمه زیر را برای تأیید فشار دهید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("انتقال به صفحه پرداخت", url=RIAL_PAYMENT_GATEWAY_URL)],
                [InlineKeyboardButton("پرداخت انجام شد، بررسی شود", callback_data="payment_verify")],
                [get_back_to_payment_methods_button()]
            ])
        )
        return VERIFY_PAYMENT

    elif payment_method == 'crypto':
        rial_amount = selected_plan.get('price')
        if rial_amount is None or rial_amount <= 0:
            logger.warning(f"Plan {plan_id} has invalid rial_amount {rial_amount} for crypto payment. telegram_id: {telegram_id}")
            await query.message.edit_text("خطا: قیمت ریالی طرح برای محاسبه معادل تتر مشخص نشده است.", reply_markup=get_payment_methods_keyboard(telegram_id, plan_name, selected_plan.get('price'), selected_plan.get('price_usdt')))
            return SELECT_PAYMENT_METHOD

        try:
            usdt_amount_requested = CryptoPaymentService.calculate_unique_usdt_amount(rial_amount)
            if usdt_amount_requested is None:
                logger.error(f"calculate_unique_usdt_amount returned None for rial_amount {rial_amount}. telegram_id: {telegram_id}")
                await query.message.edit_text("خطا: امکان محاسبه مبلغ تتر وجود ندارد. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=get_payment_methods_keyboard(telegram_id, plan_name, selected_plan.get('price'), selected_plan.get('price_usdt')))
                return SELECT_PAYMENT_METHOD
        except Exception as e:
            logger.exception(f"Error calculating USDT amount for rial_amount {rial_amount}. telegram_id: {telegram_id}")
            await query.message.edit_text("خطا در سیستم تبدیل ارز. لطفاً لحظاتی دیگر تلاش کنید یا با پشتیبانی تماس بگیرید.", reply_markup=get_payment_methods_keyboard(telegram_id, plan_name, selected_plan.get('price'), selected_plan.get('price_usdt')))
            return SELECT_PAYMENT_METHOD

        expires_at = datetime.now() + timedelta(minutes=CRYPTO_PAYMENT_TIMEOUT_MINUTES)

        crypto_payment_request_db_id = Database.create_crypto_payment_request(
            user_id=user_db_id,
            plan_id=plan_id,
            rial_amount=rial_amount,
            usdt_amount_requested=usdt_amount_requested,
            wallet_address=CRYPTO_WALLET_ADDRESS,
            expires_at=expires_at
        )

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
            await query.message.edit_text("خطا: امکان ایجاد درخواست پرداخت کریپتو وجود ندارد. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=get_payment_methods_keyboard(telegram_id, plan_name, selected_plan.get('price'), selected_plan.get('price_usdt')))
            return SELECT_PAYMENT_METHOD

        context.user_data['crypto_payment_id'] = crypto_payment_request_db_id
        context.user_data['usdt_amount_requested'] = usdt_amount_requested

        payment_info_text = CRYPTO_PAYMENT_UNIQUE_AMOUNT_MESSAGE.format(
            wallet_address=CRYPTO_WALLET_ADDRESS,
            usdt_amount=f"{usdt_amount_requested:.6f}",
            timeout_minutes=CRYPTO_PAYMENT_TIMEOUT_MINUTES
        )

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"کپی آدرس: {CRYPTO_WALLET_ADDRESS}", callback_data=f"copy_wallet_addr_{CRYPTO_WALLET_ADDRESS}")],
            [InlineKeyboardButton(f"کپی مبلغ: {usdt_amount_requested:.6f} USDT", callback_data=f"copy_usdt_amount_{usdt_amount_requested:.6f}")],
            [InlineKeyboardButton("تراکنش را انجام دادم، بررسی شود", callback_data="payment_verify_crypto")],
            [get_back_to_payment_methods_button()]
        ])

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

async def copy_wallet_address_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Data format: copy_wallet_addr_THE_WALLET_ADDRESS
    try:
        wallet_address = query.data.split('copy_wallet_addr_')[1]
        await query.answer(text=f"{wallet_address}", show_alert=True) # Show address in a popup to copy
    except IndexError:
        await query.answer(text="خطا در پردازش درخواست کپی آدرس.", show_alert=True)
    return # Stay in the current state

async def copy_usdt_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Data format: copy_usdt_amount_THE_USDT_AMOUNT
    try:
        usdt_amount = query.data.split('copy_usdt_amount_')[1]
        await query.answer(text=f"{usdt_amount} USDT", show_alert=True) # Show amount in a popup to copy
    except IndexError:
        await query.answer(text="خطا در پردازش درخواست کپی مبلغ.", show_alert=True)
    return # Stay in the current state

async def payment_verify_crypto_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("در حال بررسی پرداخت تتر شما، لطفاً چند لحظه صبر کنید...")
    user_id = query.from_user.id
    telegram_id = query.from_user.id # Assuming user_id from DB is same as telegram_id

    crypto_payment_id = context.user_data.get('crypto_payment_id')
    usdt_amount_requested = context.user_data.get('usdt_amount_requested')
    selected_plan = context.user_data.get('selected_plan_details')

    if not crypto_payment_id or not usdt_amount_requested or not selected_plan:
        await query.edit_message_text(
            "متاسفانه اطلاعات مورد نیاز برای بررسی پرداخت یافت نشد. لطفاً مجدداً فرآیند پرداخت را طی کنید.",
            reply_markup=get_main_menu_keyboard(user_id)
        )
        UserAction.log_user_action(
            telegram_id=user_id,
            user_db_id=None, # db_payment['user_id'] if db_payment else None,
            action_type='crypto_payment_verify_error',
            details={
                'crypto_payment_db_id': None, # db_payment['id'] if db_payment else None,
                'payment_id_uuid': context.user_data.get('crypto_payment_id'),
                'error': 'missing_context_data'
            }
        )
        return ConversationHandler.END

    db_payment = Database.get_crypto_payment_by_id(crypto_payment_id)

    if not db_payment:
        await query.edit_message_text(
            "متاسفانه درخواست پرداخت شما یافت نشد. ممکن است منقضی شده باشد یا خطایی رخ داده باشد.",
            reply_markup=get_main_menu_keyboard(user_id)
        )
        UserAction.log_user_action(
            telegram_id=user_id,
            user_db_id=None, # db_payment['user_id'] if db_payment else None,
            action_type='crypto_payment_verify_error',
            details={
                'crypto_payment_db_id': None, # db_payment['id'] if db_payment else None,
                'payment_id_uuid': context.user_data.get('crypto_payment_id'),
                'error': 'db_payment_not_found'
            }
        )
        return ConversationHandler.END

    if datetime.now() > datetime.fromisoformat(db_payment['expires_at']):
        Database.update_crypto_payment_status(crypto_payment_id, 'expired', None)
        await query.edit_message_text(
            "متاسفانه مهلت پرداخت شما برای این درخواست به پایان رسیده است. لطفاً یک درخواست پرداخت جدید ایجاد کنید.",
            reply_markup=get_payment_methods_keyboard(selected_plan['id'], selected_plan['name'], selected_plan['price'], selected_plan.get('price_usdt'))
        )
        UserAction.log_user_action(
            telegram_id=user_id,
            user_db_id=db_payment['user_id'], # db_payment might be None if expired before first check
            action_type='crypto_payment_expired',
            details={
                'crypto_payment_db_id': db_payment['id'], # db_payment might be None if expired before first check
                'payment_id_uuid': context.user_data.get('crypto_payment_id')
            }
        )
        return VERIFY_PAYMENT

    try:
        # Ensure usdt_amount_requested from context matches the one in DB for safety
        if abs(float(db_payment['usdt_amount_requested']) - float(usdt_amount_requested)) > 1e-9: # Compare floats carefully
             logger.warning(f"Mismatch in USDT amount for crypto_payment_id {crypto_payment_id}. Context: {usdt_amount_requested}, DB: {db_payment['usdt_amount_requested']}. Using DB value as source of truth.")
        
        service_usdt_amount = float(db_payment['usdt_amount_requested'])

        status, transaction_id, error_message = await CryptoPaymentService.find_usdt_payment(
            payment_id=str(crypto_payment_id),
            receiver_address=CRYPTO_WALLET_ADDRESS,
            expected_amount=service_usdt_amount,
        )
        
        UserAction.log_user_action(
            telegram_id=user_id,
            user_db_id=db_payment['user_id'],
            action_type='crypto_payment_service_check_result',
            details={
                'crypto_payment_db_id': db_payment['id'],
                'payment_id_uuid': crypto_payment_id,
                'service_status': status,
                'transaction_id': transaction_id,
                'error_message': error_message
            }
        )

        if status == CryptoPaymentService.CONFIRMED:
            Database.update_crypto_payment_status(crypto_payment_id, 'confirmed', transaction_id, datetime.now())
            UserAction.log_user_action(
                telegram_id=user_id,
                user_db_id=db_payment['user_id'],
                action_type='crypto_payment_confirmed_by_service',
                details={
                    'crypto_payment_db_id': db_payment['id'],
                    'payment_id_uuid': crypto_payment_id,
                    'transaction_id': transaction_id,
                    'amount_usdt': service_usdt_amount
                }
            )
            
            activation_success, activation_message = await activate_or_extend_subscription(
                user_id=user_id,
                telegram_id=telegram_id,
                plan_id=selected_plan['id'],
                plan_name=selected_plan['name'],
                payment_amount=service_usdt_amount,
                payment_method="crypto",
                transaction_id=transaction_id,
                context=context,
                payment_table_id=crypto_payment_id
            )

            if activation_success:
                await query.edit_message_text(
                    PAYMENT_SUCCESS_MESSAGE + f"\n\n{activation_message}",
                    reply_markup=InlineKeyboardMarkup([
                        [get_subscription_status_button(user_id)],
                        [get_main_menu_button()]
                    ])
                )
                context.user_data.pop('crypto_payment_id', None)
                context.user_data.pop('usdt_amount_requested', None)
                UserAction.log_user_action(
                    telegram_id=user_id,
                    user_db_id=db_payment['user_id'],
                    action_type='subscription_activation_succeeded_crypto',
                    details={
                        'crypto_payment_db_id': db_payment['id'],
                        'payment_id_uuid': crypto_payment_id,
                        'plan_id': selected_plan['id'],
                        'activation_message': activation_message
                    }
                )
                return ConversationHandler.END
            else:
                logger.error(f"Subscription activation failed for user {user_id} (crypto_payment_id: {crypto_payment_id}, TXID: {transaction_id}). Message: {activation_message}")
                UserAction.log_user_action(
                    telegram_id=user_id,
                    user_db_id=db_payment['user_id'],
                    action_type='subscription_activation_failed_crypto',
                    details={
                        'crypto_payment_db_id': db_payment['id'],
                        'payment_id_uuid': crypto_payment_id,
                        'plan_id': selected_plan['id'],
                        'error_reason': activation_message
                    }
                )
                await query.edit_message_text(
                    f"پرداخت شما با موفقیت تأیید شد (TXID: {transaction_id}) اما در فعالسازی اشتراک خطایی رخ داد: {activation_message}. لطفاً فوراً با پشتیبانی تماس بگیرید و شماره پیگیری {crypto_payment_id} را اعلام کنید.",
                    reply_markup=get_main_menu_keyboard(user_id)
                )
                return ConversationHandler.END

        elif status == CryptoPaymentService.PENDING_CONFIRMATION:
            UserAction.log_user_action(
                telegram_id=user_id,
                user_db_id=db_payment['user_id'],
                action_type='crypto_payment_pending_confirmation',
                details={
                    'crypto_payment_db_id': db_payment['id'],
                    'payment_id_uuid': crypto_payment_id,
                    'transaction_id': transaction_id
                }
            )
            await query.edit_message_text(
                "تراکنش شما در شبکه بلاکچین یافت شد اما هنوز به تعداد تأییدهای لازم نرسیده است. لطفاً چند دقیقه دیگر مجدداً بررسی کنید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("دوباره بررسی کن", callback_data="payment_verify_crypto")],
                    [get_back_to_payment_methods_button()]
                ])
            )
            return VERIFY_PAYMENT

        elif status == CryptoPaymentService.UNDERPAID:
            Database.update_crypto_payment_status(crypto_payment_id, 'underpaid', transaction_id, datetime.now())
            UserAction.log_user_action(
                telegram_id=user_id,
                user_db_id=db_payment['user_id'],
                action_type='crypto_payment_underpaid',
                details={
                    'crypto_payment_db_id': db_payment['id'],
                    'payment_id_uuid': crypto_payment_id,
                    'expected_usdt': service_usdt_amount,
                    'transaction_id': transaction_id,
                    'error_message': error_message # error_message from service likely contains received amount
                }
            )
            await query.edit_message_text(
                f"مبلغ واریزی شما کمتر از مقدار مورد انتظار است. لطفاً با پشتیبانی تماس بگیرید. شماره پیگیری: {crypto_payment_id}\nجزئیات خطا: {error_message}",
                reply_markup=get_main_menu_keyboard(user_id)
            )
            return ConversationHandler.END

        elif status == CryptoPaymentService.OVERPAID:
            # This case might still lead to subscription activation depending on policy
            # For now, we log it and inform user, then proceed like a confirmed payment
            Database.update_crypto_payment_status(crypto_payment_id, 'overpaid', transaction_id, datetime.now())
            UserAction.log_user_action(
                telegram_id=user_id,
                user_db_id=db_payment['user_id'],
                action_type='crypto_payment_overpaid',
                details={
                    'crypto_payment_db_id': db_payment['id'],
                    'payment_id_uuid': crypto_payment_id,
                    'expected_usdt': service_usdt_amount,
                    'transaction_id': transaction_id,
                    'error_message': error_message # error_message from service likely contains received amount
                }
            )
            # Proceed to activate subscription even on overpayment, as the minimum was met.
            # The message from activate_or_extend_subscription will be shown.
            activation_success, activation_message = await activate_or_extend_subscription(
                user_id=user_id,
                telegram_id=telegram_id,
                plan_id=selected_plan['id'],
                plan_name=selected_plan['name'],
                payment_amount=service_usdt_amount, # Or actual received amount if available and policy dictates
                payment_method="crypto",
                transaction_id=transaction_id,
                context=context,
                payment_table_id=crypto_payment_id
            )
            if activation_success:
                await query.edit_message_text(
                    f"پرداخت شما با موفقیت تأیید شد (مبلغ بیشتر از حد انتظار دریافت شد). TXID: {transaction_id}\n\n{activation_message}",
                    reply_markup=InlineKeyboardMarkup([
                        [get_subscription_status_button(user_id)],
                        [get_main_menu_button()]
                    ])
                )
                context.user_data.pop('crypto_payment_id', None)
                context.user_data.pop('usdt_amount_requested', None)
                UserAction.log_user_action(
                    telegram_id=user_id,
                    user_db_id=db_payment['user_id'],
                    action_type='subscription_activation_succeeded_crypto_overpaid',
                    details={
                        'crypto_payment_db_id': db_payment['id'],
                        'payment_id_uuid': crypto_payment_id,
                        'plan_id': selected_plan['id'],
                        'activation_message': activation_message
                    }
                )
                return ConversationHandler.END
            else:
                logger.error(f"Subscription activation failed after OVERPAYMENT for user {user_id} (crypto_payment_id: {crypto_payment_id}, TXID: {transaction_id}). Message: {activation_message}")
                UserAction.log_user_action(
                    telegram_id=user_id,
                    user_db_id=db_payment['user_id'],
                    action_type='subscription_activation_failed_crypto_overpaid',
                    details={
                        'crypto_payment_db_id': db_payment['id'],
                        'payment_id_uuid': crypto_payment_id,
                        'plan_id': selected_plan['id'],
                        'error_reason': activation_message
                    }
                )
                await query.edit_message_text(
                    f"پرداخت شما با مبلغ بیشتر از حد انتظار تأیید شد (TXID: {transaction_id}) اما در فعالسازی اشتراک خطایی رخ داد: {activation_message}. لطفاً فوراً با پشتیبانی تماس بگیرید و شماره پیگیری {crypto_payment_id} را اعلام کنید.",
                    reply_markup=get_main_menu_keyboard(user_id)
                )
                return ConversationHandler.END
        
        elif status == CryptoPaymentService.NOT_FOUND:
            UserAction.log_user_action(
                telegram_id=user_id,
                user_db_id=db_payment['user_id'],
                action_type='crypto_payment_not_found_by_service',
                details={
                    'crypto_payment_db_id': db_payment['id'],
                    'payment_id_uuid': crypto_payment_id
                }
            )
            await query.edit_message_text(
                "متاسفانه تراکنشی با مشخصات پرداخت شما یافت نشد. لطفاً از صحت اطلاعات و انجام تراکنش اطمینان حاصل کنید و مجدداً تلاش نمایید. اگر از انجام تراکنش مطمئن هستید، ممکن است هنوز در شبکه ثبت نشده باشد، کمی صبر کرده و دوباره امتحان کنید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("دوباره بررسی کن", callback_data="payment_verify_crypto")],
                    [get_back_to_payment_methods_button()]
                ])
            )
            return VERIFY_PAYMENT
        
        else: # ERROR or other statuses
            Database.update_crypto_payment_status(crypto_payment_id, 'error', transaction_id, datetime.now()) # transaction_id might be None
            UserAction.log_user_action(
                telegram_id=user_id,
                user_db_id=db_payment['user_id'],
                action_type='crypto_payment_service_error',
                details={
                    'crypto_payment_db_id': db_payment['id'],
                    'payment_id_uuid': crypto_payment_id,
                    'service_status': status, # Log the actual status received
                    'transaction_id': transaction_id,
                    'error_message': error_message
                }
            )
            await query.edit_message_text(
                f"هنگام بررسی پرداخت شما خطایی رخ داد: {error_message}. لطفاً با پشتیبانی تماس بگیرید. شماره پیگیری: {crypto_payment_id}",
                reply_markup=get_main_menu_keyboard(user_id)
            )
            return ConversationHandler.END

    except Exception as e:
        logger.exception(f"Exception in payment_verify_crypto_handler for user {user_id}, payment_id {crypto_payment_id}: {e}")
        await query.edit_message_text(
            "خطای پیش‌بینی نشده‌ای در هنگام بررسی پرداخت شما رخ داد. لطفاً با پشتیبانی تماس بگیرید.",
            reply_markup=get_main_menu_keyboard(user_id)
        )
        return ConversationHandler.END

async def verify_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify payment status and activate/extend subscription."""
    query = update.callback_query
    telegram_id = update.effective_user.id # Renamed from user_id for clarity
    user_db_id = None # Will be populated after fetching payment record

    Database.update_user_activity(telegram_id) # Uses telegram_id

    payment_id = context.user_data.get('payment_id')
    selected_plan_details = context.user_data.get('selected_plan_details')
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
        subscription_record_id = Database.add_subscription(
            user_id=user_db_id if user_db_id else telegram_id,
            plan_id=plan_id,
            payment_id=payment_id,
            plan_duration_days=plan_duration_days,
            amount_paid=float(amount_paid),
            payment_method=payment_method
        )

        if subscription_record_id:
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
                reply_markup=get_main_menu_keyboard(user_id=telegram_id, has_active_subscription=True),
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
            PAYMENT_FAILED_MESSAGE,
            reply_markup=get_payment_methods_keyboard()
        )
        context.user_data.pop('payment_id', None)
        context.user_data.pop('transaction_id', None)
        return SELECT_PAYMENT_METHOD

async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the payment conversation."""
    user_id = update.effective_user.id
    Database.update_user_activity(user_id)
    # Clean up context data related to this payment flow
    for key in ['selected_plan_details', 'payment_id', 'transaction_id', 'payment_method']:
        context.user_data.pop(key, None)

    # Check active subscription status for correct main menu
    has_sub = Database.has_active_subscription(user_id)
    is_admin_user = Database.is_admin(user_id) # Assuming is_admin check is available

    await update.message.reply_text(
        "عملیات پرداخت لغو شد.", 
        reply_markup=get_main_menu_keyboard(user_id=user_id, is_admin=is_admin_user, has_active_subscription=has_sub)
    )
    return ConversationHandler.END

async def back_to_plans_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Go back to plan selection from payment method selection."""
    query = update.callback_query
    user_id = update.effective_user.id
    Database.update_user_activity(user_id)
    await query.answer()
    await query.message.edit_text(
        SUBSCRIPTION_PLANS_MESSAGE,
        reply_markup=get_subscription_plans_keyboard(user_id)
    )
    return SELECT_PLAN

async def back_to_payment_methods_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Go back to payment method selection from verification step."""
    query = update.callback_query
    user_id = update.effective_user.id
    Database.update_user_activity(user_id)
    
    selected_plan = context.user_data.get('selected_plan_details')
    if not selected_plan:
        await query.message.edit_text(
            SUBSCRIPTION_PLANS_MESSAGE,
            reply_markup=get_subscription_plans_keyboard(user_id)
        )
        return SELECT_PLAN

    await query.answer()
    plan_price_irr_formatted = f"{int(selected_plan['price']):,}" if selected_plan['price'] is not None else "N/A"
    plan_price_usdt_formatted = f"{selected_plan['price_tether']}" if selected_plan['price_tether'] is not None else "N/A"
    message_text = PAYMENT_METHOD_MESSAGE.format(
        plan_name=selected_plan['name'],
        plan_price=plan_price_irr_formatted,
        plan_tether=plan_price_usdt_formatted
    )
    await query.message.edit_text(
        text=message_text,
        reply_markup=get_payment_methods_keyboard()
    )
    return SELECT_PAYMENT_METHOD


payment_conversation = ConversationHandler(
    # Entry point might need adjustment, e.g. a command /subscribe or a main menu button callback
    entry_points=[
        CommandHandler('subscribe', select_plan), # Entry via /subscribe command
        CallbackQueryHandler(select_plan, pattern='^start_subscription_flow$') # Entry via callback button
    ],
    states={
        SELECT_PLAN: [CallbackQueryHandler(select_plan, pattern='^plan_(\d+)$')], # Regex for plan_ID
        SELECT_PAYMENT_METHOD: [
            CallbackQueryHandler(select_payment_method, pattern='^payment_(rial|crypto)$'),
            CallbackQueryHandler(back_to_plans_handler, pattern='^back_to_plans$') 
        ],
        VERIFY_PAYMENT: [
            CallbackQueryHandler(verify_payment_status, pattern='^payment_verify$'),
            CallbackQueryHandler(copy_wallet_address_handler, pattern='^copy_wallet_addr_'),
            CallbackQueryHandler(copy_usdt_amount_handler, pattern='^copy_usdt_amount_'),
            CallbackQueryHandler(payment_verify_crypto_handler, pattern='^payment_verify_crypto$'),
            CallbackQueryHandler(back_to_payment_methods_handler, pattern='^back_to_payment_methods$')
        ],
    },
    fallbacks=[
        CommandHandler('cancel_payment', cancel_payment), # Specific command for payment cancel
        CallbackQueryHandler(cancel_payment, pattern='^cancel_payment_flow$'), # Specific callback for payment cancel
        # A general back_to_main from payment flow could also be added here
        # CallbackQueryHandler(main_menu_utils.back_to_main_menu, pattern='^back_to_main_menu_from_payment$') 
    ],
    map_to_parent={
        # If this conversation is part of a larger one, map states appropriately
        ConversationHandler.END: ConversationHandler.END 
    },
    # Allow re-entry into the conversation if it was previously ended by a sub-conversation
    allow_reentry=True,
    # Name for persistence
    name="payment_flow_conversation",
    persistent=True # Consider if you need persistence for payment states across bot restarts
)
