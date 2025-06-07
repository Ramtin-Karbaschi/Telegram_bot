"""
Core handlers for the Daraei Academy Telegram bot
"""

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from utils.keyboards import get_main_menu_keyboard
from database.queries import DatabaseQueries as Database
from utils.constants import WELCOME_MESSAGE, HELP_MESSAGE, RULES_MESSAGE
from handlers.registration.registration_handlers import start_registration
from handlers.subscription.subscription_handlers import start_subscription_status
from handlers.support.support_handlers import start_support

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command"""
    user = update.effective_user
    user_id = user.id
    username = user.username
    
    # Update or create user in database
    if not Database.user_exists(user_id):
        Database.add_user(user_id, username)
        user_db_data = None # New user, not yet registered with details
    else:
        Database.update_user_activity(user_id)
        user_db_data = Database.get_user_details(user_id)
    
    is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
    # Add other mandatory fields to the check if necessary, e.g., user_db_data['city']

    # Send welcome message with main menu
    await update.message.reply_text(
        WELCOME_MESSAGE,
        reply_markup=get_main_menu_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=Database.get_user_active_subscription(user_id) is not None if (is_registered and user_db_data) else False)
    )
    
    return ConversationHandler.END

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /help command"""
    user_id = update.effective_user.id
    Database.update_user_activity(user_id)
    user_db_data = Database.get_user_details(user_id)
    is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
    
    await update.message.reply_text(
        HELP_MESSAGE,
        reply_markup=get_main_menu_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=Database.get_user_active_subscription(user_id) is not None)
    )
    
    return ConversationHandler.END

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /menu command"""
    user_id = update.effective_user.id
    Database.update_user_activity(user_id)
    user_db_data = Database.get_user_details(user_id)
    is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
    
    await update.message.reply_text(
        "منوی اصلی:",
        reply_markup=get_main_menu_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=Database.get_user_active_subscription(user_id) is not None)
    )
    
    return ConversationHandler.END

async def rules_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the rules command/button"""
    user_id = update.effective_user.id
    Database.update_user_activity(user_id)
    user_db_data = Database.get_user_details(user_id)
    is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
    
    await update.message.reply_text(
        RULES_MESSAGE,
        reply_markup=get_main_menu_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=Database.get_user_active_subscription(user_id) is not None)
    )
    
    return ConversationHandler.END

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
    Database.update_user_activity(user_id)
    user_db_data = Database.get_user_details(user_id)
    is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
    
    await query.message.reply_text(
        "منوی اصلی:",
        reply_markup=get_main_menu_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=Database.get_user_active_subscription(user_id) is not None)
    )
    
    return ConversationHandler.END

async def handle_back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to main menu button/command"""
    user_id = update.effective_user.id
    Database.update_user_activity(user_id)
    user_db_data = Database.get_user_details(user_id)
    is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
    
    # If it's a callback query
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        # It's better to edit the message if possible, or send a new one if edit is not suitable.
        # For simplicity, sending a new message similar to original behavior.
        await query.message.reply_text(
            "منوی اصلی:",
            reply_markup=get_main_menu_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=Database.get_user_active_subscription(user_id) is not None)
        )
    # If it's a message
    else:
        await update.message.reply_text(
            "منوی اصلی:",
            reply_markup=get_main_menu_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=Database.get_user_active_subscription(user_id) is not None)
        )
    
    return ConversationHandler.END

async def unknown_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown messages"""
    user_id = update.effective_user.id
    Database.update_user_activity(user_id)
    user_db_data = Database.get_user_details(user_id)
    is_registered = bool(user_db_data and user_db_data['full_name'] and user_db_data['phone'])
    
    await update.message.reply_text(
        "متوجه نشدم! لطفاً از دکمه‌های منو استفاده کنید یا دستور /help را برای راهنمایی وارد کنید.",
        reply_markup=get_main_menu_keyboard(user_id=user_id, is_registered=is_registered, has_active_subscription=Database.get_user_active_subscription(user_id) is not None)
    )
    
    return ConversationHandler.END
