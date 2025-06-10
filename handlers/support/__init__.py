"""
Support ticket handlers package initialization
"""

from handlers.support.support_handlers import (
    # Handler functions
    start_support, 
    create_new_ticket,
    get_ticket_subject,
    get_ticket_message,
    view_ticket,
    send_ticket_message,
    close_ticket,
    reopen_ticket,
    back_to_tickets,
    # Handler functions for main_bot.py
    support_menu_handler,
    support_ticket_list_handler,
    new_ticket_handler,
    view_ticket_handler,
    close_ticket_handler,
    reopen_ticket_handler,
    ticket_conversation # ticket_conversation is the ConversationHandler instance
)

__all__ = [
    'start_support',
    'create_new_ticket',
    'get_ticket_subject',
    'get_ticket_message',
    'view_ticket',
    'send_ticket_message',
    'close_ticket',
    'reopen_ticket',
    'back_to_tickets',
    'support_menu_handler',
    'support_ticket_list_handler',
    'new_ticket_handler',
    'view_ticket_handler',
    'close_ticket_handler',
    'reopen_ticket_handler',
    'ticket_conversation' # This is the ConversationHandler instance
]
