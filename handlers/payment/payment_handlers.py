"""
Payment handlers for the Daraei Academy Telegram bot
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode # Added for message formatting
import config # Added for TELEGRAM_CHANNELS_INFO
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, 
    MessageHandler, filters, CallbackQueryHandler
)
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
    RIAL_PAYMENT_MESSAGE, CRYPTO_PAYMENT_MESSAGE,
    PAYMENT_VERIFICATION_MESSAGE, PAYMENT_SUCCESS_MESSAGE,
    PAYMENT_FAILED_MESSAGE
)
from utils.helpers import calculate_days_left

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
    user_id = update.effective_user.id
    
    # Update user activity
    Database.update_user_activity(user_id)
    
    # Extract payment method from callback data
    payment_method = query.data.split('_')[1]
    
    # Store payment method in user data
    context.user_data['payment_method'] = payment_method
    
    # Answer callback query
    await query.answer()
    
    # Handle different payment methods
    if payment_method == 'rial':
        # Generate a unique transaction ID
        transaction_id = str(uuid.uuid4())[:8].upper()
        context.user_data['transaction_id'] = transaction_id
        
        # Get plan details from context
        selected_plan = context.user_data.get('selected_plan_details')
        if not selected_plan:
            await query.message.edit_text("خطا: اطلاعات طرح یافت نشد. لطفاً از ابتدا شروع کنید.", reply_markup=get_subscription_plans_keyboard(user_id))
            return SELECT_PLAN

        plan_name = selected_plan['name']
        plan_price_irr = selected_plan['price']
        
        # Record payment in database (pending status)
        payment_id = Database.add_payment(
            user_id=user_id,
            amount=plan_price_irr,
            payment_method="rial",
            description=f"اشتراک {plan_name}",
            transaction_id=transaction_id,
            status="pending"
        )
        
        # Store payment ID in user data
        context.user_data['payment_id'] = payment_id
        
        # Show payment redirection
        await query.message.edit_text(
            "شما به صفحه پرداخت هدایت می‌شوید. پس از تکمیل پرداخت، لطفاً دکمه زیر را برای تأیید فشار دهید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("انتقال به صفحه پرداخت", url="https://google.com")],
                [InlineKeyboardButton("پرداخت انجام شد، بررسی شود", callback_data="payment_verify")],
                [get_back_to_payment_methods_button()]
            ])
        )
        
        return VERIFY_PAYMENT
        
    elif payment_method == 'crypto':
        # Generate a unique transaction ID
        transaction_id = str(uuid.uuid4())[:8].upper()
        context.user_data['transaction_id'] = transaction_id
        
        # Get plan details from context
        selected_plan = context.user_data.get('selected_plan_details')
        if not selected_plan:
            await query.message.edit_text("خطا: اطلاعات طرح یافت نشد. لطفاً از ابتدا شروع کنید.", reply_markup=get_subscription_plans_keyboard(user_id))
            return SELECT_PLAN

        plan_name = selected_plan['name']
        plan_price_usdt = selected_plan['price_tether']
        
        if plan_price_usdt is None or plan_price_usdt <= 0:
            await query.message.edit_text("خطا: پرداخت با تتر برای این طرح در دسترس نیست.", reply_markup=get_payment_methods_keyboard())
            return SELECT_PAYMENT_METHOD

        # Record payment in database (pending status)
        payment_id = Database.add_payment(
            user_id=user_id,
            amount=plan_price_usdt,
            payment_method="crypto",
            description=f"اشتراک {plan_name}",
            transaction_id=transaction_id,
            status="pending"
        )
        
        # Store payment ID in user data
        context.user_data['payment_id'] = payment_id
        
        # Show payment redirection
        await query.message.edit_text(
            "شما به صفحه پرداخت هدایت می‌شوید. پس از تکمیل پرداخت، لطفاً دکمه زیر را برای تأیید فشار دهید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("انتقال به صفحه پرداخت", url="https://google.com")],
                [InlineKeyboardButton("پرداخت انجام شد، بررسی شود", callback_data="payment_verify")],
                [get_back_to_payment_methods_button()]
            ])
        )
        
        return VERIFY_PAYMENT
    
    # If something goes wrong, return to plan selection
    await query.message.edit_text(
        "خطایی در انتخاب روش پرداخت رخ داد. لطفاً مجدداً یک طرح را انتخاب کنید.",
        reply_markup=get_subscription_plans_keyboard(user_id) # Pass user_id if needed
    )
    
    return SELECT_PLAN

async def verify_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify payment status and activate/extend subscription."""
    query = update.callback_query
    user_id = update.effective_user.id
    
    Database.update_user_activity(user_id)
    
    payment_id = context.user_data.get('payment_id')
    selected_plan_details = context.user_data.get('selected_plan_details')
    payment_method = context.user_data.get('payment_method') # Get payment_method

    if not payment_id or not selected_plan_details or not payment_method: # Added check for payment_method
        await query.message.edit_text(
            "خطایی در بازیابی اطلاعات پرداخت، طرح یا روش پرداخت رخ داد. لطفاً دوباره تلاش کنید.",
            reply_markup=get_subscription_plans_keyboard(user_id)
        )
        print(f"Error: Missing payment_id, selected_plan_details, or payment_method in verify_payment_status for user {user_id}")
        return SELECT_PLAN

    # Simulate payment verification 
    payment_successful = True # TODO: Replace with actual payment gateway verification logic

    if payment_successful:
        # Update payment status in the 'payments' table
        # Consider adding transaction_id_from_gateway if available
        # The transaction_id from context.user_data can be passed to update_payment_status if it's from the gateway
        gateway_transaction_id = context.user_data.get('transaction_id') # Assuming this is the one from gateway if crypto, or our generated one for rial
        if not Database.update_payment_status(payment_id, "completed", gateway_transaction_id if payment_method == 'crypto' else None):
            # Handle error if payment status update fails
            await query.message.edit_text(
                "خطا در به‌روزرسانی وضعیت پرداخت. لطفاً با پشتیبانی تماس بگیرید.",
                reply_markup=get_main_menu_keyboard(user_id=user_id) # Or other appropriate keyboard
            )
            print(f"Error: Failed to update payment status for payment_id {payment_id} for user {user_id}")
            # Clean up context data to prevent reuse of failed payment info
            for key in ['selected_plan_details', 'payment_id', 'transaction_id', 'payment_method']:
                context.user_data.pop(key, None)
            return ConversationHandler.END # Or an error state

        # Extract necessary details for add_subscription
        plan_id = selected_plan_details['id']
        plan_duration_days = selected_plan_details['days']
        plan_name = selected_plan_details['name'] # For success message

        # Determine amount_paid based on payment_method
        if payment_method == 'rial':
            amount_paid = selected_plan_details.get('price')
        elif payment_method == 'crypto':
            amount_paid = selected_plan_details.get('price_tether')
        else:
            # Should not happen if payment_method was validated earlier
            print(f"Error: Unknown payment_method '{payment_method}' for user {user_id}, payment_id {payment_id}")
            await query.message.edit_text("خطای داخلی: روش پرداخت ناشناخته است.", reply_markup=get_main_menu_keyboard(user_id=user_id))
            return ConversationHandler.END
        
        if amount_paid is None:
            print(f"Error: Amount for plan_id {plan_id} with payment_method '{payment_method}' is None for user {user_id}")
            await query.message.edit_text("خطای داخلی: مبلغ طرح یافت نشد.", reply_markup=get_main_menu_keyboard(user_id=user_id))
            return ConversationHandler.END

        # Add or extend subscription
        subscription_record_id = Database.add_subscription(
            user_id=user_id,
            plan_id=plan_id,
            payment_id=payment_id, # This is the ID from the 'payments' table
            plan_duration_days=plan_duration_days,
            amount_paid=float(amount_paid), # Ensure amount is float
            payment_method=payment_method
            # status defaults to 'active' in add_subscription
        )

        if subscription_record_id:
            # Fetch the updated subscription details to show the correct end_date
            updated_subscription = Database.get_subscription(subscription_record_id) # Assumes get_subscription returns the specific sub
            if not updated_subscription:
                 # Fallback if get_subscription fails or if we need the *active* one specifically
                updated_subscription = Database.get_user_active_subscription(user_id)

            display_end_date = "نامشخص"
            if updated_subscription and updated_subscription.get('end_date'):
                try:
                    end_date_dt = datetime.strptime(updated_subscription['end_date'], "%Y-%m-%d %H:%M:%S")
                    display_end_date = end_date_dt.strftime("%Y-%m-%d")
                except ValueError:
                    print(f"Error parsing end_date from updated_subscription: {updated_subscription.get('end_date')}")
            
            # Construct the success message with channel links
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
                        # Using simple Markdown: [title](link)
                        # Ensure title doesn't contain special markdown characters like '[' or ']'
                        # or escape them if necessary for ParseMode.MARKDOWN.
                        channel_links_parts.append(f"- [{title}]({link})")
            
            full_success_message = base_success_message + "\n".join(channel_links_parts)

            await query.message.edit_text(
                full_success_message,
                reply_markup=get_main_menu_keyboard(user_id=user_id, has_active_subscription=True),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            # Handle failure in add_subscription
            await query.message.edit_text(
                "خطا در فعال‌سازی اشتراک. لطفاً با پشتیبانی تماس بگیرید.",
                reply_markup=get_main_menu_keyboard(user_id=user_id)
            )
            print(f"Error: add_subscription returned None for user {user_id}, payment_id {payment_id}")

        # Clean up context data
        for key in ['selected_plan_details', 'payment_id', 'transaction_id', 'payment_method']:
            context.user_data.pop(key, None)
        return ConversationHandler.END
    else: # payment_successful is False
        gateway_transaction_id = context.user_data.get('transaction_id')
        if not Database.update_payment_status(payment_id, "failed", gateway_transaction_id if payment_method == 'crypto' else None):
             print(f"Warning: Failed to update payment status to 'failed' for payment_id {payment_id} for user {user_id}")
        
        await query.message.edit_text(
            PAYMENT_FAILED_MESSAGE,
            reply_markup=get_payment_methods_keyboard() # Allow user to try another method or plan
        )
        # Do not clear selected_plan_details or payment_method yet, user might want to retry with different method for same plan
        context.user_data.pop('payment_id', None) # Clear only payment_id as it's specific to this attempt
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
