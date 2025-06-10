"""
Support ticket handlers for the Daraei Academy Telegram bot
"""

from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode
from database.queries import DatabaseQueries as Database
from utils.keyboards import get_main_menu_keyboard, get_support_menu_keyboard, get_ticket_conversation_keyboard, get_back_button
from utils.constants import (
    SUPPORT_WELCOME_MESSAGE, NEW_TICKET_SUBJECT_REQUEST, NEW_TICKET_MESSAGE_REQUEST,
    TICKET_CREATED_MESSAGE, TICKET_CLOSED_MESSAGE, TICKET_REOPENED_MESSAGE,
    SUPPORT_MENU, NEW_TICKET_SUBJECT, NEW_TICKET_MESSAGE, VIEW_TICKET # Added conversation states
)
import config
import logging

# Configure logger
logger = logging.getLogger(__name__)

async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the support process, handling both command and callback query"""
    user_id = update.effective_user.id
    
    # Update user activity
    Database.update_user_activity(user_id)
    
    # Get user's tickets
    tickets = Database.get_user_tickets(user_id)
    reply_markup = get_support_menu_keyboard(tickets)
    
    if update.callback_query:
        await update.callback_query.answer()
        # Check if the message text is already SUPPORT_WELCOME_MESSAGE to avoid unnecessary edits
        # Or if the current keyboard is already the support menu keyboard (more complex to check reliably without message ID)
        # For simplicity, we'll just edit if the text is different or assume it's a fresh request for the menu.
        if update.callback_query.message.text != SUPPORT_WELCOME_MESSAGE:
            await update.callback_query.message.edit_text(
                SUPPORT_WELCOME_MESSAGE,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
        # If the text is the same, it might mean the user clicked the support button again from the main menu.
        # We still want to present the support menu, so no action if text is same, keyboard is already there.
        # However, if the callback is from a different message, edit_text is appropriate.
        # The current logic will re-send/edit the message if text is different.

    elif update.message: # Called by /support command
        await update.message.reply_text(
            SUPPORT_WELCOME_MESSAGE,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
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
        f"لطفاً متن پیام خود را در ارتباط با موضوع <b>{subject}</b> وارد کنید.",
        reply_markup=get_back_button(),
        parse_mode=ParseMode.HTML
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
    ticket_number_from_db = Database.create_ticket( # Renamed to avoid confusion
        user_id=user_id,
        subject=subject,
        message=message
    )

    if ticket_number_from_db is None: # Check if ticket creation failed
        logger.error(f"Failed to create ticket for user {user_id} with subject '{subject}'")
        await update.message.reply_text(
            "متأسفانه در ایجاد تیکت مشکلی پیش آمد. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.",
            reply_markup=get_main_menu_keyboard() # Or support menu if preferred
        )
        # Clear context even on failure to prevent issues
        if 'ticket_subject' in context.user_data:
            del context.user_data['ticket_subject']
        return ConversationHandler.END

    formatted_ticket_id = f"{user_id}-{ticket_number_from_db}"
    
    # Clear context
    if 'ticket_subject' in context.user_data:
        del context.user_data['ticket_subject']
    
    # Show success message to user
    success_message_user = (
        f"✅ تیکت شما با شناسه <b>{formatted_ticket_id}</b> با موفقیت ثبت شد.\n"
        f"موضوع: {subject}\n\n"
        "به زودی توسط تیم پشتیبانی بررسی خواهد شد."
    )
    
    # Get user's tickets again to update the support menu
    tickets = Database.get_user_tickets(user_id)
    await update.message.reply_text(
        success_message_user,
        reply_markup=get_support_menu_keyboard(tickets),
        parse_mode=ParseMode.HTML
    )
    
    # Notify admins
    admin_notification_message = (
        f"🔔 تیکت جدید ثبت شد! 🔔\n\n"
        f"👤 کاربر: {update.effective_user.full_name} (ID: {user_id})\n"
        f"🎫 شناسه تیکت: {formatted_ticket_id}\n"
        f"📋 موضوع: {subject}\n"
        f"📝 پیام اولیه: {message[:100]}{'...' if len(message) > 100 else ''}" # Show first 100 chars of message
    )
    
    if hasattr(config, 'ADMIN_IDS') and isinstance(config.ADMIN_IDS, list) and config.ADMIN_IDS:
        for admin_id in config.ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_notification_message,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Failed to send new ticket notification to admin {admin_id}: {e}")
    else:
        logger.warning("ADMIN_IDS not configured or not a list. Cannot send new ticket notification to admins.")
            
    return ConversationHandler.END

async def view_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_id=None):
    """View a specific ticket conversation"""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        if not ticket_id:
            # Extract ticket_id from callback_data like 'view_ticket_123'
            try:
                ticket_id = int(query.data.split('_')[-1])
            except (IndexError, ValueError):
                logger.error(f"Could not parse ticket_id from callback_data: {query.data}")
                await query.message.edit_text(
                    "خطا در پردازش درخواست. لطفاً دوباره تلاش کنید.",
                    reply_markup=get_support_menu_keyboard([]) # Show basic support menu
                )
                logger.debug(f"view_ticket returning SUPPORT_MENU due to parsing error for ticket_id from {query.data}")
                return SUPPORT_MENU # Or an appropriate state

    # If ticket_id is still None (e.g., direct call without callback or parsing failed)
    # This part might need adjustment based on how view_ticket can be invoked without a callback.
    # For now, we assume ticket_id is primarily from callback.

    ticket = Database.get_ticket(ticket_id)
    if not ticket:
        not_found_message = "تیکت مورد نظر یافت نشد یا شما دسترسی به آن ندارید."
        if update.callback_query:
            await update.callback_query.message.edit_text(
                not_found_message,
                reply_markup=get_support_menu_keyboard(Database.get_user_tickets(update.effective_user.id))
            )
        else:
            # This case (direct message to view_ticket) is less common for viewing existing tickets
            await update.message.reply_text(
                not_found_message,
                reply_markup=get_support_menu_keyboard(Database.get_user_tickets(update.effective_user.id))
            )
        logger.debug(f"view_ticket returning SUPPORT_MENU because ticket {ticket_id} not found or no access (direct message path).")
        return SUPPORT_MENU

    messages = Database.get_ticket_messages(ticket_id)

    message_text = f"<b>📋 تیکت #{ticket_id}: {ticket['subject']}</b>\n"
    message_text += f"🕒 تاریخ ایجاد: {ticket['created_at']}\n"
    # Display a more user-friendly status
    status_translation = {
        'open': 'باز',
        'closed': 'بسته',
        'pending_admin_reply': 'در انتظار پاسخ پشتیبانی',
        'pending_user_reply': 'پاسخ داده شده توسط پشتیبانی'
    }
    displayed_status = status_translation.get(ticket['status'], ticket['status'])
    message_text += f"📊 وضعیت: {displayed_status}\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n\n"

    for msg in messages:
        sender = "پشتیبانی" if msg['is_admin'] else "شما"
        msg_time = msg['timestamp']
        msg_content = msg['message']
        message_text += f"<i>[{msg_time}]</i> <b>{sender}:</b>\n{msg_content}\n\n"

    # Determine keyboard based on ticket status
    # is_open should be True if the ticket is in a state where the user might want to close it 
    # or reply to it (e.g., 'open', 'pending_user_reply', 'pending_admin_reply').
    # is_open should be False if the ticket is 'closed', so the 'reopen' button is shown.
    ticket_is_currently_open_for_user_action = ticket['status'] in ['open', 'pending_user_reply', 'pending_admin_reply']
    keyboard = get_ticket_conversation_keyboard(ticket_id, is_open=ticket_is_currently_open_for_user_action)

    context.user_data['active_ticket_id'] = ticket_id # Store for sending messages

    if update.callback_query:
        await update.callback_query.message.edit_text(
            message_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    elif update.message: # Should ideally not happen for viewing an existing ticket this way
        await update.message.reply_text(
            message_text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    
    logger.debug(f"view_ticket successfully processed ticket {ticket_id} and is returning VIEW_TICKET")
    return VIEW_TICKET # State for when viewing a ticket and can send messages

async def send_ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message in an open ticket conversation"""
    ticket_id = context.user_data.get('active_ticket_id')

    if not ticket_id:
        await update.message.reply_text(
            "خطایی رخ داده است. لطفاً ابتدا یک تیکت را از منوی پشتیبانی انتخاب کنید.",
            reply_markup=get_support_menu_keyboard(Database.get_user_tickets(update.effective_user.id))
        )
        return SUPPORT_MENU

    ticket = Database.get_ticket(ticket_id)

    # User can send message if ticket exists and is not 'closed'
    # Valid statuses for sending a message: 'open', 'pending_admin_reply', 'pending_user_reply'
    if not ticket or ticket['status'] == 'closed':
        await update.message.reply_text(
            "این تیکت بسته شده است و امکان ارسال پیام جدید وجود ندارد. برای ادامه، لطفاً تیکت را بازگشایی کنید یا تیکت جدیدی ایجاد نمایید.",
            reply_markup=get_support_menu_keyboard(Database.get_user_tickets(update.effective_user.id))
        )
        # Optionally, show the specific ticket view again so they can see the reopen button if applicable
        # return await view_ticket(update, context, ticket_id) 
        return SUPPORT_MENU # Or return to the specific ticket view if preferred

    user_id = update.effective_user.id
    message_text = update.message.text

    if not message_text.strip():
        await update.message.reply_text("پیام شما نمی‌تواند خالی باشد. لطفاً متن پیام را وارد کنید.")
        return VIEW_TICKET # Stay in the same state to allow user to re-enter message

    # Add message to ticket, for user messages, is_admin_message is False (default)
    success = Database.add_ticket_message(
        ticket_id=ticket_id,
        sender_user_id=user_id,
        message_text=message_text,
        is_admin_message=False 
    )

    if success:
        # View updated ticket
        # Ensure the view_ticket function is called correctly, it might need context or update object if called directly
        # The current structure of view_ticket expects to be a handler, so we pass update and context.
        await update.message.reply_text("پیام شما با موفقیت ارسال شد.") # Optimistic send
        return await view_ticket(update, context, ticket_id=ticket_id)
    else:
        await update.message.reply_text(
            "متاسفانه در ارسال پیام شما مشکلی پیش آمد. لطفاً دوباره تلاش کنید."
        )
        # Stay in the same state or return to ticket view
        return VIEW_TICKET

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
    result_state = await view_ticket(update, context)
    logger.debug(f"view_ticket_handler returning state: {result_state}")
    return result_state

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
            MessageHandler(filters.TEXT & filters.Regex(f"^🔙 بازگشت$"), support_menu_handler)  # Go back to support menu
        ],
        NEW_TICKET_MESSAGE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_ticket_message),
            MessageHandler(filters.TEXT & filters.Regex(f"^🔙 بازگشت$"), new_ticket_handler)  # Go back to subject input
        ],
        VIEW_TICKET: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, send_ticket_message),
            CallbackQueryHandler(close_ticket_handler, pattern="^close_ticket_"),
            CallbackQueryHandler(reopen_ticket_handler, pattern="^reopen_ticket_"),
            CallbackQueryHandler(back_to_tickets, pattern="^back_to_tickets$") # Go back to ticket list (support menu)
        ]
    },
    fallbacks=[
        CommandHandler("cancel", back_to_tickets),
        CallbackQueryHandler(back_to_tickets, pattern="^back$"),
            CallbackQueryHandler(handle_back_to_main_from_support, pattern="^back_to_main$")
    ],
    name="ticket_conversation"
)
