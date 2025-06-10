"""
Core handlers for the Daraei Academy Telegram bot
"""

from datetime import datetime
from urllib.parse import parse_qs # For robustly parsing query strings if needed, though manual split is used here.

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram import CallbackQuery

from database.queries import DatabaseQueries # Assuming direct import is fine
from services.zarinpal_service import ZarinpalPaymentService
from utils.keyboards import get_main_menu_keyboard, get_main_reply_keyboard
from utils.constants.all_constants import (
    ZARINPAL_GOTO_GATEWAY_MESSAGE_USER,
    ZARINPAL_PAYMENT_NOT_FOUND_MESSAGE_USER,
    ZARINPAL_PAYMENT_ALREADY_VERIFIED_MESSAGE_USER,
    ZARINPAL_PAYMENT_FAILED_MESSAGE_TRY_AGAIN_USER,
    ZARINPAL_PAYMENT_VERIFIED_SUCCESS_AND_SUB_ACTIVATED_MESSAGE_USER,
    ZARINPAL_PAYMENT_VERIFIED_SUCCESS_SUB_ACTIVATION_FAILED_MESSAGE_USER,
    ZARINPAL_PAYMENT_VERIFIED_SUCCESS_PLAN_NOT_FOUND_MESSAGE_USER,
    ZARINPAL_PAYMENT_VERIFICATION_FAILED_MESSAGE_USER,
    ZARINPAL_PAYMENT_CANCELLED_MESSAGE_USER,
    GENERAL_ERROR_MESSAGE_USER,
    WELCOME_MESSAGE, HELP_MESSAGE, RULES_MESSAGE, TEXT_MAIN_MENU_BUY_SUBSCRIPTION, SUBSCRIPTION_PLANS_MESSAGE,
    ZARINPAL_VERIFY_SUCCESS_STATUS, ZARINPAL_ALREADY_VERIFIED_STATUS,
    TEXT_BACK_BUTTON, CALLBACK_BACK_TO_MAIN_MENU
)
import config # For logger
from handlers.registration.registration_handlers import start_registration
from handlers.subscription.subscription_handlers import start_subscription_status
from handlers.support.support_handlers import start_support
from handlers.subscription.subscription_handlers import view_active_subscription

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command, including Zarinpal payment verification via deep linking."""
    user = update.effective_user
    user_id = user.id
    username = user.username
    args = context.args

    processed_payment_callback = False

    if args and args[0].startswith("zarinpal_verify&Authority="):
        try:
            params_str = args[0].split("zarinpal_verify&", 1)[1]
            params = dict(qc.split("=") for qc in params_str.split("&"))
            authority = params.get("Authority")
            status_from_url = params.get("Status")

            if not authority or not status_from_url:
                await update.message.reply_text(GENERAL_ERROR_MESSAGE_USER)
                processed_payment_callback = True # Prevent further default start logic for this case
            else:
                payment_details = DatabaseQueries.get_payment_by_authority(authority)

                if not payment_details:
                    await update.message.reply_text(ZARINPAL_PAYMENT_NOT_FOUND_MESSAGE_USER)
                    processed_payment_callback = True
                elif payment_details['status'] not in ['pending_verification', 'pending']:
                    # Payment already processed or in an unexpected state
                    # Check if it was successful and inform user, or if failed
                    if payment_details['status'] == 'completed' or payment_details['status'] == 'already_verified':
                        await update.message.reply_text(ZARINPAL_PAYMENT_ALREADY_VERIFIED_MESSAGE_USER)
                    else:
                        await update.message.reply_text(ZARINPAL_PAYMENT_FAILED_MESSAGE_TRY_AGAIN_USER.format(status=payment_details['status']))
                    processed_payment_callback = True
                else:
                    # Payment is pending verification, proceed
                    if status_from_url == 'OK':
                        rial_amount = int(payment_details['amount']) # Zarinpal expects integer amount
                        verification_result = ZarinpalPaymentService.verify_payment(amount=rial_amount, authority=authority)
                        
                        if verification_result and verification_result.get('status') == ZARINPAL_VERIFY_SUCCESS_STATUS:
                            ref_id = verification_result.get('ref_id')
                            DatabaseQueries.update_payment_verification_status(payment_details['payment_id'], 'completed', str(ref_id))
                            
                            plan_info = DatabaseQueries.get_plan_by_id(payment_details['plan_id'])
                            if plan_info:
                                subscription_id = DatabaseQueries.add_subscription(
                                    user_id=user_id,
                                    plan_id=payment_details['plan_id'],
                                    payment_id=payment_details['payment_id'],
                                    plan_duration_days=plan_info['days'],
                                    amount_paid=payment_details['amount'],
                                    payment_method='zarinpal'
                                )
                                if subscription_id:
                                    await update.message.reply_text(ZARINPAL_PAYMENT_VERIFIED_SUCCESS_AND_SUB_ACTIVATED_MESSAGE_USER.format(ref_id=ref_id, plan_name=plan_info['name']))
                                else:
                                    await update.message.reply_text(ZARINPAL_PAYMENT_VERIFIED_SUCCESS_SUB_ACTIVATION_FAILED_MESSAGE_USER.format(ref_id=ref_id))
                            else:
                                # Plan info not found, should not happen if data integrity is maintained
                                await update.message.reply_text(ZARINPAL_PAYMENT_VERIFIED_SUCCESS_PLAN_NOT_FOUND_MESSAGE_USER.format(ref_id=ref_id))
                        
                        elif verification_result and verification_result.get('status') == ZARINPAL_ALREADY_VERIFIED_STATUS:
                            ref_id = verification_result.get('ref_id') # Usually available
                            DatabaseQueries.update_payment_verification_status(payment_details['payment_id'], 'already_verified', str(ref_id) if ref_id else None)
                            # Potentially re-check and activate subscription if it wasn't due to some race condition or error
                            # For simplicity, just informing the user it's already verified.
                            await update.message.reply_text(ZARINPAL_PAYMENT_ALREADY_VERIFIED_MESSAGE_USER)
                        else:
                            # Verification failed
                            error_code = verification_result.get('status', 'N/A')
                            DatabaseQueries.update_payment_verification_status(payment_details['payment_id'], 'failed')
                            await update.message.reply_text(ZARINPAL_PAYMENT_VERIFICATION_FAILED_MESSAGE_USER.format(error_code=error_code))
                    else: # Status from URL was not 'OK' (e.g., user cancelled)
                        DatabaseQueries.update_payment_verification_status(payment_details['payment_id'], 'cancelled')
                        await update.message.reply_text(ZARINPAL_PAYMENT_CANCELLED_MESSAGE_USER)
                    processed_payment_callback = True
        except Exception as e:
            config.logger.error(f"Error processing Zarinpal callback in start_handler: {e}", exc_info=True)
            await update.message.reply_text(GENERAL_ERROR_MESSAGE_USER)
            processed_payment_callback = True # Prevent default start logic on error

    # Standard /start command logic (if not a payment callback or after processing it)
    if not processed_payment_callback:
        # Update or create user in database
        if not DatabaseQueries.user_exists(user_id):
            DatabaseQueries.add_user(user_id, username)
            user_db_data = None # New user, not yet registered with details
        else:
            DatabaseQueries.update_user_activity(user_id)
            user_db_data = DatabaseQueries.get_user_details(user_id)
        
        is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
        has_active_sub = False
        if is_registered and user_db_data:
             active_sub_details = DatabaseQueries.get_user_active_subscription(user_id)
             has_active_sub = active_sub_details is not None

        await update.message.reply_text(
            WELCOME_MESSAGE,
            reply_markup=get_main_reply_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=has_active_sub) # This will set the persistent reply keyboard
        )
        # To also show an inline keyboard under the welcome message (optional, if desired)
        # await update.message.reply_text(
        #     "گزینه های اصلی:", # Or some other relevant text
        #     reply_markup=get_main_menu_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=has_active_sub)
        # )

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command or main_menu_help callback query"""
    user_id = update.effective_user.id
    DatabaseQueries.update_user_activity(user_id)
    user_db_data = DatabaseQueries.get_user_details(user_id)
    is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
    has_active_subscription = DatabaseQueries.get_user_active_subscription(user_id) is not None
    back_button_help = InlineKeyboardButton(TEXT_BACK_BUTTON, callback_data=CALLBACK_BACK_TO_MAIN_MENU)
    back_keyboard_markup_help = InlineKeyboardMarkup([[back_button_help]])

    if update.callback_query:
        await update.callback_query.answer()
        # Check if the message text or markup needs updating to avoid unnecessary edits
        if update.callback_query.message.text != HELP_MESSAGE or update.callback_query.message.reply_markup != back_keyboard_markup_help:
            await update.callback_query.message.edit_text(
                HELP_MESSAGE,
                reply_markup=back_keyboard_markup_help,
                parse_mode=ParseMode.HTML
            )
    elif update.message:
        await update.message.reply_text(
            HELP_MESSAGE,
            reply_markup=back_keyboard_markup_help,
            parse_mode=ParseMode.HTML
        )

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /menu command"""
    user_id = update.effective_user.id
    DatabaseQueries.update_user_activity(user_id)
    user_db_data = DatabaseQueries.get_user_details(user_id)
    is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
    
    await update.message.reply_text(
        "منوی اصلی:",
        reply_markup=get_main_menu_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=DatabaseQueries.get_user_active_subscription(user_id) is not None)
    )

async def rules_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /rules command or main_menu_rules callback query"""
    user_id = update.effective_user.id
    DatabaseQueries.update_user_activity(user_id)
    user_db_data = DatabaseQueries.get_user_details(user_id)
    is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
    has_active_subscription = DatabaseQueries.get_user_active_subscription(user_id) is not None
    back_button_rules = InlineKeyboardButton(TEXT_BACK_BUTTON, callback_data=CALLBACK_BACK_TO_MAIN_MENU)
    back_keyboard_markup_rules = InlineKeyboardMarkup([[back_button_rules]])

    if update.callback_query:
        await update.callback_query.answer()
        # Check if the message text or markup needs updating to avoid unnecessary edits
        if update.callback_query.message.text != RULES_MESSAGE or update.callback_query.message.reply_markup != back_keyboard_markup_rules:
            await update.callback_query.message.edit_text(
                RULES_MESSAGE,
                reply_markup=back_keyboard_markup_rules,
                parse_mode=ParseMode.HTML
            )
    elif update.message:
        await update.message.reply_text(
            RULES_MESSAGE,
            reply_markup=back_keyboard_markup_rules,
            parse_mode=ParseMode.HTML
        )

async def registration_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the registration message from keyboard"""
    # This simply calls the start_registration function from registration handlers
    return await start_registration(update, context)

async def subscription_status_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the subscription status message from keyboard"""
    # This simply calls the start_subscription_status function from subscription handlers
    return await start_subscription_status(update, context)

async def support_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the support message from keyboard"""
    # This simply calls the start_support function from support handlers
    return await start_support(update, context)

async def show_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the menu callback button"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    DatabaseQueries.update_user_activity(user_id)
    user_db_data = DatabaseQueries.get_user_details(user_id)
    is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
    
    await query.message.edit_text(
        "منوی اصلی:",
        reply_markup=get_main_menu_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=DatabaseQueries.get_user_active_subscription(user_id) is not None)
    )

async def handle_back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to main menu button/command - now redirects to subscription status."""
    # user_id = update.effective_user.id # Not strictly needed here if view_active_subscription handles it
    # DatabaseQueries.update_user_activity(user_id) # Consider if view_active_subscription handles user activity

    if update.callback_query:
        await update.callback_query.answer() # Answer callback query if applicable

    # Call the function to show subscription status
    await view_active_subscription(update, context)

async def unknown_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown messages"""
    user_id = update.effective_user.id
    DatabaseQueries.update_user_activity(user_id)
    user_db_data = DatabaseQueries.get_user_details(user_id)
    is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
    
    await update.message.reply_text(
        "متوجه نشدم! لطفاً از دکمه‌های منو استفاده کنید یا دستور /help را برای راهنمایی وارد کنید.",
        reply_markup=get_main_menu_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=DatabaseQueries.get_user_active_subscription(user_id) is not None)
    )
