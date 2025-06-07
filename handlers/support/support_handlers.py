"""
Support ticket handlers for the Daraei Academy Telegram bot
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, filters, CallbackQueryHandler
)
from database.queries import DatabaseQueries as Database
from utils.keyboards import get_main_menu_keyboard, get_support_menu_keyboard, get_ticket_conversation_keyboard, get_back_button
from utils.constants import (
    SUPPORT_WELCOME_MESSAGE, NEW_TICKET_SUBJECT_REQUEST, NEW_TICKET_MESSAGE_REQUEST,
    TICKET_CREATED_MESSAGE, TICKET_CLOSED_MESSAGE, TICKET_REOPENED_MESSAGE
)
import config
import logging

# Configure logger
logger = logging.getLogger(__name__)

# Conversation states
SUPPORT_MENU = 0
NEW_TICKET_SUBJECT = 1
NEW_TICKET_MESSAGE = 2
VIEW_TICKET = 3
TICKET_CONVERSATION = 4

async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the support process"""
    user_id = update.effective_user.id
    
    # Update user activity
    Database.update_user_activity(user_id)
    
    # Get user's tickets
    tickets = Database.get_user_tickets(user_id)
    
    # Send welcome message with support menu
    await update.message.reply_text(
        SUPPORT_WELCOME_MESSAGE,
        reply_markup=get_support_menu_keyboard(tickets)
    )
    
    return SUPPORT_MENU

async def create_new_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start creating a new ticket"""
    # Check if from callback query or direct command
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        await query.message.reply_text(
            NEW_TICKET_SUBJECT_REQUEST,
            reply_markup=get_back_button()
        )
    else:
        await update.message.reply_text(
            NEW_TICKET_SUBJECT_REQUEST,
            reply_markup=get_back_button()
        )
    
    return NEW_TICKET_SUBJECT

async def get_ticket_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get the subject for a new ticket"""
    # Store the ticket subject
    subject = update.message.text
    
    if not subject or len(subject) < 5:
        await update.message.reply_text(
            "موضوع تیکت باید حداقل ۵ کاراکتر باشد. لطفاً دوباره وارد کنید:",
            reply_markup=get_back_button()
        )
        return NEW_TICKET_SUBJECT
    
    # Store in context
    context.user_data['ticket_subject'] = subject
    
    # Ask for message
    await update.message.reply_text(
        NEW_TICKET_MESSAGE_REQUEST,
        reply_markup=get_back_button()
    )
    
    return NEW_TICKET_MESSAGE

async def get_ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get the message for a new ticket"""
    # Get the message
    message = update.message.text
    
    if not message or len(message) < 10:
        await update.message.reply_text(
            "پیام شما باید حداقل ۱۰ کاراکتر باشد. لطفاً دوباره وارد کنید:",
            reply_markup=get_back_button()
        )
        return NEW_TICKET_MESSAGE
    
    # Get subject from context
    subject = context.user_data.get('ticket_subject')
    
    if not subject:
        # Something went wrong, start over
        await update.message.reply_text(
            "متأسفانه مشکلی پیش آمد. لطفاً دوباره تلاش کنید.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    # Create the ticket
    user_id = update.effective_user.id
    ticket_id = Database.create_ticket(
        user_id=user_id,
        subject=subject,
        message=message
    )
    
    # Clear context
    if 'ticket_subject' in context.user_data:
        del context.user_data['ticket_subject']
    
    # Show success message
    await update.message.reply_text(
        TICKET_CREATED_MESSAGE.format(
            ticket_id=ticket_id,
            subject=subject
        ),
        reply_markup=get_main_menu_keyboard()
    )
    
    return ConversationHandler.END

async def view_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_id=None):
    """View a specific ticket conversation"""
    # Check if from callback query
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        # Get ticket ID from callback data
        if not ticket_id:
            ticket_id = query.data.replace("view_ticket_", "")
    
    # Get ticket from database
    ticket = Database.get_ticket(ticket_id)
    
    if not ticket:
        # Ticket not found
        message = "تیکت مورد نظر یافت نشد."
        
        if update.callback_query:
            await update.callback_query.message.edit_text(
                message,
                reply_markup=get_main_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                message,
                reply_markup=get_main_menu_keyboard()
            )
        
        return ConversationHandler.END
    
    # Get all messages for this ticket
    messages = Database.get_ticket_messages(ticket_id)
    
    # Prepare message text
    message_text = f"📋 تیکت #{ticket_id}: {ticket['subject']}\n"
    message_text += f"🕒 تاریخ ایجاد: {ticket['created_at']}\n"
    message_text += f"📊 وضعیت: {'باز' if ticket['status'] == 'open' else 'بسته'}\n\n"
    
    # Add all messages
    for msg in messages:
        sender = "شما" if msg['is_user'] else "پشتیبانی"
        message_text += f"[{msg['created_at']}] {sender}:\n{msg['message']}\n\n"
    
    # Determine keyboard based on ticket status
    if ticket['status'] == 'open':
        keyboard = get_ticket_conversation_keyboard(ticket_id, can_close=True)
    else:
        keyboard = get_ticket_conversation_keyboard(ticket_id, can_reopen=True)
    
    # Send or edit message based on update type
    if update.callback_query:
        await update.callback_query.message.edit_text(
            message_text,
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=keyboard
        )
    
    # Set active ticket in context
    context.user_data['active_ticket'] = ticket_id
    
    return VIEW_TICKET

async def send_ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message in an open ticket conversation"""
    # Get active ticket
    ticket_id = context.user_data.get('active_ticket')
    
    if not ticket_id:
        # No active ticket
        await update.message.reply_text(
            "لطفاً ابتدا یک تیکت را انتخاب کنید.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    # Get ticket status
    ticket = Database.get_ticket(ticket_id)
    
    if not ticket or ticket['status'] != 'open':
        # Ticket closed or not found
        await update.message.reply_text(
            "این تیکت بسته شده است و امکان ارسال پیام جدید وجود ندارد.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    # Add message to ticket
    user_id = update.effective_user.id
    Database.add_ticket_message(
        ticket_id=ticket_id,
        user_id=user_id,
        message=update.message.text,
        is_user=True
    )
    
    # View updated ticket
    return await view_ticket(update, context, ticket_id)

async def close_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Close an open ticket"""
    query = update.callback_query
    await query.answer()
    
    # Get ticket ID from callback data
    ticket_id = query.data.replace("close_ticket_", "")
    
    # Get ticket from database
    ticket = Database.get_ticket(ticket_id)
    
    if not ticket:
        # Ticket not found
        await query.message.edit_text(
            "تیکت مورد نظر یافت نشد.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    # Check if ticket is already closed
    if ticket['status'] != 'open':
        await query.message.edit_text(
            "این تیکت قبلاً بسته شده است.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    # Close the ticket
    Database.update_ticket_status(ticket_id, 'closed')
    
    # Add system message
    Database.add_ticket_message(
        ticket_id=ticket_id,
        user_id=query.from_user.id,
        message=TICKET_CLOSED_MESSAGE,
        is_user=False
    )
    
    # View updated ticket
    return await view_ticket(update, context, ticket_id)

async def reopen_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reopen a closed ticket"""
    query = update.callback_query
    await query.answer()
    
    # Get ticket ID from callback data
    ticket_id = query.data.replace("reopen_ticket_", "")
    
    # Get ticket from database
    ticket = Database.get_ticket(ticket_id)
    
    if not ticket:
        # Ticket not found
        await query.message.edit_text(
            "تیکت مورد نظر یافت نشد.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    # Check if ticket is already open
    if ticket['status'] == 'open':
        await query.message.edit_text(
            "این تیکت قبلاً باز است.",
            reply_markup=get_main_menu_keyboard()
        )
        return ConversationHandler.END
    
    # Reopen the ticket
    Database.update_ticket_status(ticket_id, 'open')
    
    # Add system message
    Database.add_ticket_message(
        ticket_id=ticket_id,
        user_id=query.from_user.id,
        message=TICKET_REOPENED_MESSAGE,
        is_user=False
    )
    
    # View updated ticket
    return await view_ticket(update, context, ticket_id)

async def back_to_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Go back to tickets list"""
    query = update.callback_query
    await query.answer()
    
    # Get user's tickets
    user_id = update.effective_user.id
    tickets = Database.get_user_tickets(user_id)
    
    # Send support menu
    await query.message.edit_text(
        SUPPORT_WELCOME_MESSAGE,
        reply_markup=get_support_menu_keyboard(tickets)
    )
    
    return SUPPORT_MENU

async def handle_back_to_main_from_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handles the 'back_to_main' callback from the support conversation."""
    main_menu_text = "بازگشت به منوی اصلی. لطفاً از دکمه‌های زیر استفاده کنید:"
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete previous message in support 'back_to_main': {e}")
        await query.message.reply_text(
            text=main_menu_text,
            reply_markup=get_main_menu_keyboard()
        )
    elif update.message:
        await update.message.reply_text(
            text=main_menu_text,
            reply_markup=get_main_menu_keyboard()
        )
    
    # Clear any support conversation related data
    if 'active_ticket' in context.user_data:
        del context.user_data['active_ticket']
    if 'ticket_subject' in context.user_data:
        del context.user_data['ticket_subject']
        
    return ConversationHandler.END


# Callback handler functions for main_bot.py

async def support_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for support menu callbacks"""
    # This is a wrapper around start_support for use with CallbackQueryHandler
    query = update.callback_query
    await query.answer()
    
    # Get user's tickets
    user_id = update.effective_user.id
    tickets = Database.get_user_tickets(user_id)
    
    # Send support menu
    await query.message.edit_text(
        SUPPORT_WELCOME_MESSAGE,
        reply_markup=get_support_menu_keyboard(tickets)
    )
    
    return SUPPORT_MENU

async def support_ticket_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for ticket list callbacks"""
    # This is the same as support_menu_handler
    return await support_menu_handler(update, context)

async def new_ticket_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for new ticket callbacks"""
    # This is a wrapper around create_new_ticket for use with CallbackQueryHandler
    return await create_new_ticket(update, context)

async def view_ticket_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for view ticket callbacks"""
    # This is a wrapper around view_ticket for use with CallbackQueryHandler
    return await view_ticket(update, context)

async def close_ticket_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for close ticket callbacks"""
    # This is a wrapper around close_ticket for use with CallbackQueryHandler
    return await close_ticket(update, context)

async def reopen_ticket_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for reopen ticket callbacks"""
    # This is a wrapper around reopen_ticket for use with CallbackQueryHandler
    return await reopen_ticket(update, context)

# Define the conversation handler for ticket system
ticket_conversation = ConversationHandler(
    entry_points=[
        CommandHandler("support", start_support),
        CallbackQueryHandler(new_ticket_handler, pattern="^new_ticket$"),
        CallbackQueryHandler(view_ticket_handler, pattern="^view_ticket_")
    ],
    states={
        SUPPORT_MENU: [
            CallbackQueryHandler(new_ticket_handler, pattern="^new_ticket$"),
            CallbackQueryHandler(view_ticket_handler, pattern="^view_ticket_")
        ],
        NEW_TICKET_SUBJECT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_ticket_subject),
            CallbackQueryHandler(back_to_tickets, pattern="^back$")
        ],
        NEW_TICKET_MESSAGE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_ticket_message),
            CallbackQueryHandler(back_to_tickets, pattern="^back$")
        ],
        VIEW_TICKET: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, send_ticket_message),
            CallbackQueryHandler(close_ticket_handler, pattern="^close_ticket_"),
            CallbackQueryHandler(reopen_ticket_handler, pattern="^reopen_ticket_"),
            CallbackQueryHandler(back_to_tickets, pattern="^back$")
        ]
    },
    fallbacks=[
        CommandHandler("cancel", back_to_tickets),
        CallbackQueryHandler(back_to_tickets, pattern="^back$"),
            CallbackQueryHandler(handle_back_to_main_from_support, pattern="^back_to_main$")
    ],
    name="ticket_conversation"
)
