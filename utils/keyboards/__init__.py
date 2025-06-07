"""
Keyboard utilities for the Daraei Academy Telegram bot
"""

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
# import config # No longer needed directly here
from utils import ui_texts
from utils import constants
from database.queries import DatabaseQueries # Import DatabaseQueries

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) # Ensure this logger also picks up debugs if not configured globally

def get_main_menu_keyboard(user_id=None, is_admin=False, has_active_subscription=False, is_registered=False):
    """Get the main menu keyboard with all options, dynamically showing channel link button and registration/subscription status button."""
    keyboard_buttons = []

    if is_registered:
        keyboard_buttons.append([KeyboardButton(constants.TEXT_MAIN_MENU_SUBSCRIPTION_STATUS)])
    else:
        keyboard_buttons.append([KeyboardButton(constants.TEXT_MAIN_MENU_REGISTRATION)])

    keyboard_buttons.append([
        KeyboardButton(constants.TEXT_MAIN_MENU_HELP),
        KeyboardButton(constants.TEXT_MAIN_MENU_SUPPORT),
        KeyboardButton(constants.TEXT_MAIN_MENU_RULES)
    ])

    if has_active_subscription or is_admin:
        # Ensure this button is added correctly relative to others if needed
        # For now, appending it. If it should be in a specific row, adjust list construction.
        keyboard_buttons.append([KeyboardButton(constants.MAIN_MENU_BUTTON_TEXT_GET_CHANNEL_LINK)])
    
    # Removed commented out logic for MAIN_MENU_BUTTON_TEXT_REGISTER_OR_LOGIN as it's now handled by is_registered

    return ReplyKeyboardMarkup(keyboard_buttons, resize_keyboard=True)

def get_back_button(text="🔙 بازگشت"):
    """Get a single back button"""
    keyboard = [[KeyboardButton(text)]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_back_to_main_button():
    """Get a button to return to main menu"""
    keyboard = [[KeyboardButton("بازگشت به منوی اصلی")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_contact_button():
    """Get a button to share contact information"""
    keyboard = [
        [KeyboardButton("📱 اشتراک گذاری شماره تماس", request_contact=True)],
        [KeyboardButton("🔙 بازگشت")]
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
        [KeyboardButton("🔙 بازگشت")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_occupation_keyboard():
    """Get keyboard with occupation options"""
    keyboard = [
        [KeyboardButton("بازار سرمایه")],
        [KeyboardButton("فارکس")],
        [KeyboardButton("کریپتو")],
        [KeyboardButton("سایر")],
        [KeyboardButton("🔙 بازگشت")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_subscription_plans_keyboard():
    """Get keyboard with subscription plan options"""
    keyboard = []
    active_plans = DatabaseQueries.get_active_plans()

    if not active_plans:
        keyboard.append([InlineKeyboardButton("در حال حاضر طرح فعالی وجود ندارد.", callback_data='no_plans_available')])
    else:
        for plan in active_plans:
            plan_id = plan['id']
            plan_name = plan['name']
            price_irr = plan['price']
            price_usdt = None # price_tether is no longer fetched from the database
            duration_days = plan['days']

            price_irr_formatted = f"{int(price_irr):,}" if price_irr is not None else "N/A"
            price_usdt_formatted = f"{price_usdt}" if price_usdt is not None else "N/A"
            
            duration_text = f"{duration_days} روز"
            if duration_days % 30 == 0 and duration_days // 30 > 0:
                months = duration_days // 30
                duration_text = f"{months} ماه{'ه' if months > 1 else ''}"
            elif duration_days % 7 == 0 and duration_days // 7 > 0:
                weeks = duration_days // 7
                duration_text = f"{weeks} هفته{' ' if weeks > 1 else ''}"

            button_text = f"{plan_name} ({duration_text}) - {price_irr_formatted} تومان"
            if price_usdt is not None and price_usdt > 0:
                button_text += f" / {price_usdt_formatted} تتر"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"plan_{plan_id}")])
    
    logger.debug(f"KEYBOARDS: Inspecting ui_texts module before use. Attributes: {dir(ui_texts)}")
    logger.debug(f"KEYBOARDS: ui_texts module file path: {ui_texts.__file__}")
    keyboard.append([InlineKeyboardButton(ui_texts.BACK_BUTTON_TEXT, callback_data="back_to_main_menu_from_plans")]) # Differentiated callback
    return InlineKeyboardMarkup(keyboard)

def get_payment_methods_keyboard():
    """Get keyboard with payment method options"""
    keyboard = [
        [InlineKeyboardButton("💳 پرداخت با تومان", callback_data="payment_rial")],
        [InlineKeyboardButton("💲 پرداخت با تتر (USDT)", callback_data="payment_crypto")],
        [get_back_to_plans_button()]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_to_plans_button():
    """Get a button to go back to plans selection"""
    return InlineKeyboardButton("🔙 بازگشت به طرح‌ها", callback_data="back_to_plans")

def get_back_to_payment_methods_button():
    """Get a button to go back to payment methods"""
    return InlineKeyboardButton("🔙 بازگشت به روش‌های پرداخت", callback_data="back_to_payment_methods")

def get_payment_verification_keyboard():
    """Get keyboard for payment verification"""
    keyboard = [
        [InlineKeyboardButton("تأیید پرداخت", callback_data="payment_verify")],
        [get_back_to_payment_methods_button()]
    ]
    return InlineKeyboardMarkup(keyboard)

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
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")])
    
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
        [InlineKeyboardButton("بازگشت به منوی اصلی", callback_data=constants.CALLBACK_BACK_TO_MAIN_MENU_FROM_EDIT)]
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
        [InlineKeyboardButton("🔙 بازگشت به منوی ویرایش", callback_data=back_callback)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_occupation_inline_keyboard(back_callback=constants.CALLBACK_PROFILE_EDIT_BACK_TO_MENU):
    """Get inline keyboard with occupation options."""
    keyboard = [
        [InlineKeyboardButton("بازار سرمایه", callback_data="occupation_بازار سرمایه")],
        [InlineKeyboardButton("فارکس", callback_data="occupation_فارکس")],
        [InlineKeyboardButton("کریپتو", callback_data="occupation_کریپتو")],
        [InlineKeyboardButton("سایر", callback_data="occupation_سایر")],
        [InlineKeyboardButton("🔙 بازگشت به منوی ویرایش", callback_data=back_callback)]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_edit_field_action_keyboard(cancel_callback=constants.CALLBACK_PROFILE_EDIT_CANCEL, back_to_menu_callback=constants.CALLBACK_PROFILE_EDIT_BACK_TO_MENU):
    """Get an inline keyboard with cancel and back to edit menu buttons."""
    keyboard = [
        [
            InlineKeyboardButton("لغو ویرایش این مورد", callback_data=cancel_callback),
            InlineKeyboardButton("بازگشت به منوی ویرایش", callback_data=back_to_menu_callback)
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_phone_edit_keyboard(back_callback=constants.CALLBACK_PROFILE_EDIT_BACK_TO_MENU):
    """Get keyboard for phone editing, including contact sharing and back button."""
    # ReplyKeyboard for contact sharing
    reply_keyboard_markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("📱 اشتراک گذاری شماره تماس", request_contact=True)],
            [KeyboardButton("بازگشت به منوی ویرایش")] # This text will be caught by a MessageHandler
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    # InlineKeyboard for fallback if user types or wants to go back without using ReplyKeyboard
    inline_keyboard_markup = InlineKeyboardMarkup([
         [InlineKeyboardButton("🔙 بازگشت به منوی ویرایش", callback_data=back_callback)]
    ])
    return reply_keyboard_markup, inline_keyboard_markup

def get_cancel_keyboard(text="لغو ویرایش"):
    """Get an inline keyboard with a cancel button for conversations."""
    keyboard = [[InlineKeyboardButton(text, callback_data="cancel_edit_profile")]]
    return InlineKeyboardMarkup(keyboard)

def get_ticket_conversation_keyboard(ticket_id, is_open=True):
    """Get keyboard for ticket conversation view"""
    keyboard = []
    
    # Add close/reopen button based on status
    if is_open:
        keyboard.append([
            InlineKeyboardButton("🔴 بستن تیکت", callback_data=f"close_ticket_{ticket_id}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("🟢 بازگشایی تیکت", callback_data=f"reopen_ticket_{ticket_id}")
        ])
    
    # Add back button
    keyboard.append([
        InlineKeyboardButton("🔙 بازگشت به لیست تیکت‌ها", callback_data="back_to_tickets")
    ])
    
    return InlineKeyboardMarkup(keyboard)
