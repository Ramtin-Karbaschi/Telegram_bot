"""
Keyboard utilities for the Daraei Academy Telegram bot
"""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def get_main_reply_keyboard(user_id=None, is_admin=False, is_registered=False):
    """Get the main menu keyboard as a ReplyKeyboardMarkup for all options."""
    # Import constants inside the function to avoid circular imports if this file grows
    from utils import constants

    keyboard_buttons = []

    row1 = []
    if is_registered:
        row1.append(KeyboardButton(constants.TEXT_MAIN_MENU_BUY_SUBSCRIPTION))
    else:
        row1.append(KeyboardButton(constants.TEXT_MAIN_MENU_REGISTRATION))
    keyboard_buttons.append(row1)

    row2 = [
        KeyboardButton(constants.TEXT_MAIN_MENU_HELP),
        KeyboardButton(constants.TEXT_MAIN_MENU_SUPPORT),
        KeyboardButton(constants.TEXT_MAIN_MENU_RULES)
    ]
    keyboard_buttons.append(row2)



    return ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True, one_time_keyboard=False)




from utils import constants
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) # Ensure this logger also picks up debugs if not configured globally

def get_main_menu_keyboard(user_id=None, is_admin=False, is_registered=False):
    """Get the main menu keyboard as an InlineKeyboardMarkup for all options, including buy subscription as callback."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard_buttons = []

    if is_registered:
        keyboard_buttons.append([
            InlineKeyboardButton("🎫 خرید اشتراک", callback_data="start_subscription_flow")
        ])
    else:
        keyboard_buttons.append([InlineKeyboardButton(constants.TEXT_MAIN_MENU_REGISTRATION, callback_data="start_registration_flow")])

    keyboard_buttons.append([
        InlineKeyboardButton(constants.TEXT_MAIN_MENU_HELP, callback_data="main_menu_help"),
        InlineKeyboardButton(constants.TEXT_MAIN_MENU_SUPPORT, callback_data="main_menu_support"),
        InlineKeyboardButton(constants.TEXT_MAIN_MENU_RULES, callback_data="main_menu_rules")
    ])



    return InlineKeyboardMarkup(keyboard_buttons)


def get_back_button(text="↩ بازگشت"):
    """Get a single back button"""
    keyboard = [[KeyboardButton(text)]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_contact_button():
    """Get a button to share contact information"""
    keyboard = [
        [KeyboardButton("📱 اشتراک گذاری شماره تماس", request_contact=True)],
        [KeyboardButton("↩ بازگشت")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_education_keyboard():
    """Get keyboard with education level options"""
    keyboard = [
        [KeyboardButton("دیپلم")],
        [KeyboardButton("کاردانی")],
        [KeyboardButton("کارشناسی")],
        [KeyboardButton("کارشناسی ارشد")],
        [KeyboardButton("دکتری")],
        [KeyboardButton("سایر")],
        [KeyboardButton("↩ بازگشت")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_occupation_keyboard():
    """Get keyboard with occupation options"""
    keyboard = [
        [KeyboardButton("بازار سرمایه")],
        [KeyboardButton("فارکس")],
        [KeyboardButton("کریپتو")],
        [KeyboardButton("سایر")],
        [KeyboardButton("↩ بازگشت")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from utils.constants.all_constants import TEXT_GENERAL_BACK
import logging

logger = logging.getLogger(__name__)

def get_subscription_plans_keyboard(telegram_id=None): # Added telegram_id as optional param, might be needed later
    """Get keyboard with subscription plan options, showing discounted prices."""
    keyboard = []
    # Lazy import to avoid circular dependency
    from database.queries import DatabaseQueries as _DB
    active_plans = _DB.get_active_plans()

    if not active_plans:
        keyboard.append([InlineKeyboardButton("در حال حاضر طرح فعالی وجود ندارد.", callback_data='no_plans_available')])
    else:
        plan_buttons_row = []
        for plan in active_plans:
            plan_id = plan['id']
            button_text = plan['name'] # Use plan's name directly for the button
            plan_buttons_row.append(InlineKeyboardButton(button_text, callback_data=f"plan_{plan_id}"))
        
        if plan_buttons_row: # If there are any plan buttons
            keyboard.append(plan_buttons_row) # Add them as a single row
    
    # Ensure TEXT_GENERAL_BACK is defined and imported correctly
    try:
        back_button_text = TEXT_GENERAL_BACK
    except AttributeError:
        logger.warning("'TEXT_GENERAL_BACK' not found, using default '↩ بازگشت'. Check 'utils.constants.all_constants'.")
        back_button_text = "↩ بازگشت"
        
    keyboard.append([InlineKeyboardButton(back_button_text, callback_data="back_to_main_menu_from_plans")])
    return InlineKeyboardMarkup(keyboard)

def get_payment_methods_keyboard():
    """Get keyboard with payment method options"""
    keyboard = [
        [
            InlineKeyboardButton("💳 پرداخت ریالی", callback_data="payment_rial"),
            InlineKeyboardButton("💲 پرداخت با تتر (USDT)", callback_data="payment_crypto")
        ],
        [get_back_to_plans_button()]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_to_plans_button():
    """Get a button to go back to plans selection"""
    return InlineKeyboardButton("↩ بازگشت به طرح‌ها", callback_data="back_to_plans")

def get_back_to_payment_methods_button():
    """Get a button to go back to payment methods"""
    return InlineKeyboardButton("↩ بازگشت به روش‌های پرداخت", callback_data="back_to_payment_methods")

def get_support_menu_keyboard(tickets=None):
    """Get keyboard for support menu"""
    keyboard = []
    
    # Add open tickets if available
    if tickets:
        for ticket in tickets[:5]:  # Show max 5 tickets
            ticket_id = ticket['id']
            subject = ticket['subject']
            # Truncate subject if too long
            if len(subject) > 20:
                subject = subject[:18] + "..."
            keyboard.append([
                InlineKeyboardButton(f"#{ticket_id}: {subject}", callback_data=f"view_ticket_{ticket_id}")
            ])
    
    # Add new ticket button
    keyboard.append([InlineKeyboardButton("🎫 تیکت جدید", callback_data="new_ticket")])
    
    # Add back button
    keyboard.append([InlineKeyboardButton("↩ بازگشت به منوی اصلی", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(keyboard)

def get_profile_edit_menu_keyboard():
    """Get keyboard for profile editing field selection."""
    logger.debug(f"KEYBOARDS: Generating profile edit menu. FULLNAME_CALLBACK: '{constants.CALLBACK_PROFILE_EDIT_FULLNAME}', BIRTHYEAR_CALLBACK: '{constants.CALLBACK_PROFILE_EDIT_BIRTHYEAR}'")
    keyboard = [
        [InlineKeyboardButton("نام و نام خانوادگی", callback_data=constants.CALLBACK_PROFILE_EDIT_FULLNAME)],
        [InlineKeyboardButton("سال تولد", callback_data=constants.CALLBACK_PROFILE_EDIT_BIRTHYEAR)],
        [InlineKeyboardButton("میزان تحصیلات", callback_data=constants.CALLBACK_PROFILE_EDIT_EDUCATION)],
        [InlineKeyboardButton("شغل", callback_data=constants.CALLBACK_PROFILE_EDIT_OCCUPATION)],
        [InlineKeyboardButton("شماره همراه", callback_data=constants.CALLBACK_PROFILE_EDIT_PHONE)],
        [InlineKeyboardButton("شهر محل سکونت", callback_data=constants.CALLBACK_PROFILE_EDIT_CITY)],
        [InlineKeyboardButton("ایمیل", callback_data=constants.CALLBACK_PROFILE_EDIT_EMAIL)],
        [InlineKeyboardButton("↩ بازگشت به منوی اصلی", callback_data=constants.CALLBACK_BACK_TO_MAIN_MENU_FROM_EDIT)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_education_inline_keyboard(back_callback=constants.CALLBACK_PROFILE_EDIT_BACK_TO_MENU):
    """Get inline keyboard with education level options."""
    keyboard = [
        [InlineKeyboardButton("دیپلم", callback_data="education_دیپلم")],
        [InlineKeyboardButton("کاردانی", callback_data="education_کاردانی")],
        [InlineKeyboardButton("کارشناسی", callback_data="education_کارشناسی")],
        [InlineKeyboardButton("کارشناسی ارشد", callback_data="education_کارشناسی ارشد")],
        [InlineKeyboardButton("دکتری", callback_data="education_دکتری")],
        [InlineKeyboardButton("سایر", callback_data="education_سایر")],
        [InlineKeyboardButton("↩ بازگشت به منوی ویرایش", callback_data=back_callback)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_occupation_inline_keyboard(back_callback=constants.CALLBACK_PROFILE_EDIT_BACK_TO_MENU):
    """Get inline keyboard with occupation options."""
    keyboard = [
        [InlineKeyboardButton("بازار سرمایه", callback_data="occupation_بازار سرمایه")],
        [InlineKeyboardButton("فارکس", callback_data="occupation_فارکس")],
        [InlineKeyboardButton("کریپتو", callback_data="occupation_کریپتو")],
        [InlineKeyboardButton("سایر", callback_data="occupation_سایر")],
        [InlineKeyboardButton("↩ بازگشت به منوی ویرایش", callback_data=back_callback)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_edit_field_action_keyboard(cancel_callback=constants.CALLBACK_PROFILE_EDIT_CANCEL, back_to_menu_callback=constants.CALLBACK_PROFILE_EDIT_BACK_TO_MENU):
    """Get an inline keyboard with cancel and back to edit menu buttons."""
    keyboard = [
        [
            InlineKeyboardButton("لغو ویرایش این مورد", callback_data=cancel_callback),
            InlineKeyboardButton("↩ بازگشت به منوی ویرایش", callback_data=back_to_menu_callback)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_phone_edit_keyboard(back_callback=constants.CALLBACK_PROFILE_EDIT_BACK_TO_MENU):
    """Get keyboard for phone editing, including contact sharing and back button."""
    # ReplyKeyboard for contact sharing
    reply_keyboard_markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📱 اشتراک گذاری شماره تماس", request_contact=True)],
            [KeyboardButton("↩ بازگشت به منوی ویرایش")] # This text will be caught by a MessageHandler
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    # InlineKeyboard for fallback if user types or wants to go back without using ReplyKeyboard
    inline_keyboard_markup = InlineKeyboardMarkup([
         [InlineKeyboardButton("↩ بازگشت به منوی ویرایش", callback_data=back_callback)]
    ])
    return reply_keyboard_markup, inline_keyboard_markup

def get_ticket_conversation_keyboard(ticket_id, is_open=True):
    """Get keyboard for ticket conversation view"""
    keyboard = []
    
    # Add back button
    keyboard.append([
        InlineKeyboardButton("↩ بازگشت به لیست تیکت‌ها", callback_data="back_to_tickets")
    ])
    
    return InlineKeyboardMarkup(keyboard)
