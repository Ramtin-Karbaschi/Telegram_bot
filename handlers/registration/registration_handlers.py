"""
Registration handlers for the Daraei Academy Telegram bot
"""

import logging

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, 
    MessageHandler, filters, CallbackQueryHandler
)
from database.queries import DatabaseQueries as Database
from utils.keyboards import (
    get_contact_button, get_education_keyboard, 
    get_occupation_keyboard, get_back_button,
    get_subscription_plans_keyboard, get_main_menu_keyboard
)
from utils.constants import (

    TEXT_GENERAL_BACK_TO_MAIN_MENU,
    CALLBACK_VIEW_SUBSCRIPTION_STATUS_FROM_REG,
    CALLBACK_BACK_TO_MAIN_MENU,
    REGISTRATION_WELCOME, PHONE_REQUEST, FULLNAME_REQUEST,
    BIRTHYEAR_REQUEST, EDUCATION_REQUEST, OCCUPATION_REQUEST,
    SUBSCRIPTION_PLANS_MESSAGE,
    CITY_REQUEST,
)
from utils.helpers import is_valid_full_name
import config

logger = logging.getLogger(__name__)

# Conversation states
REGISTRATION_START = 0
GET_PHONE = 1
GET_FULLNAME = 2
GET_BIRTHYEAR = 3
GET_EDUCATION = 4
GET_OCCUPATION = 5
GET_CITY = 6

# SHOW_PLANS = 8 # This state is no longer directly part of registration flow

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the registration process. Supports both /register command and inline button callback."""

    # Determine whether this was triggered via a callback query or a normal command/message.
    is_callback = bool(update.callback_query)
    if is_callback:
        # Answer the callback to remove the "loading" state on the client.
        await update.callback_query.answer()
        effective_message = update.callback_query.message
    else:
        effective_message = update.message

    user = update.effective_user
    user_id = user.id
    
    # Check if user is already registered (with complete profile)
    if Database.is_registered(user_id):
        await effective_message.reply_text(
            "شما قبلاً ثبت‌نام کرده‌اید! می‌توانید از منوی اصلی برای مدیریت اشتراک خود استفاده کنید.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(TEXT_GENERAL_BACK_TO_MAIN_MENU, callback_data=CALLBACK_BACK_TO_MAIN_MENU)]
            ])
        )
        return ConversationHandler.END
    
    # Start registration process
    await effective_message.reply_text(
        REGISTRATION_WELCOME,
        reply_markup=get_back_button()
    )
    
    # Move to phone number step
    await effective_message.reply_text(
        PHONE_REQUEST,
        reply_markup=get_contact_button()
    )
    
    logger.critical("CRITICAL_LOG: START_REGISTRATION_ATTEMPTING_TO_RETURN_GET_PHONE")
    return GET_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get user's phone number"""
    logger.critical("CRITICAL_LOG: GET_PHONE_HANDLER_ENTERED")
    logger.info(f"Entering GET_PHONE state for user {update.effective_user.id}")
    logger.debug(f"Update.message content: contact={update.message.contact}, text='{update.message.text}'")

    user = update.effective_user
    user_id = user.id
    phone = None  # Initialize phone

    if update.message.contact:
        phone = update.message.contact.phone_number
        logger.info(f"Received phone via contact: {phone}")
        if not phone.startswith('+'):
            phone = '+' + phone
    elif update.message.text:
        logger.info(f"Received phone via text: '{update.message.text}'")
        # Consider using a constant for "🔙 بازگشت"
        if update.message.text == "🔙 بازگشت": 
            logger.info("Back button pressed in GET_PHONE. Cancelling registration.")
            return await cancel_registration(update, context)
        
        phone = update.message.text.strip()
        if not phone.startswith('+'):
            phone = '+' + phone
    else:
        logger.warning(f"No contact or text message received in GET_PHONE for user {user_id}. Re-prompting.")
        await update.message.reply_text("لطفاً شماره تماس خود را به اشتراک بگذارید یا از دکمه زیر استفاده کنید.", reply_markup=get_contact_button())
        return GET_PHONE
    
    logger.info(f"Processed phone number: {phone} for user {user_id}")

    if not Database.user_exists(user_id):
        logger.info(f"User {user_id} does not exist. Adding new user.")
        username = user.username
        add_success = Database.add_user(user_id, username=username)
        logger.info(f"Add user result for {user_id}: {add_success}")
    else:
        logger.info(f"User {user_id} already exists.")
    
    logger.info(f"Updating user profile for {user_id} with phone: {phone}")
    update_success = Database.update_user_profile(user_id, phone=phone)
    logger.info(f"Update user profile (phone) result for {user_id}: {update_success}")
    
    if not update_success:
        logger.error(f"Failed to update phone for user {user_id}. Staying in GET_PHONE state.")
        await update.message.reply_text("مشکلی در ذخیره شماره شما پیش آمد. لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید.")
        return GET_PHONE

    # Move to full name step
    await update.message.reply_text(
        FULLNAME_REQUEST,
        reply_markup=get_back_button()
    )
    logger.info(f"Proceeding to GET_FULLNAME state for user {user_id}.")
    return GET_FULLNAME

async def get_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_name = update.message.text
    if not is_valid_full_name(full_name):
        await update.message.reply_text(
            "نام و نام خانوادگی وارد شده معتبر نیست.\n"
            "- لطفاً فقط از حروف فارسی و فاصله استفاده کنید.\n"
            "- نام باید حداقل ۳ کاراکتر داشته باشد.\n"
            "- استفاده از اعداد و کاراکترهای خاص (مانند نقطه، ویرگول و ...) مجاز نیست.\n\n"
            "لطفاً نام کامل خود را دوباره وارد کنید:"
        )
        return GET_FULLNAME

    context.user_data['full_name'] = full_name
    """Get user's full name and complete initial registration."""
    user = update.effective_user
    user_id = user.id
    
    # Check if back button was pressed
    if update.message.text == "🔙 بازگشت":
        return await cancel_registration(update, context)
    
    full_name = update.message.text.strip()
    
    # Update full name and set other fields to None in database
    Database.update_user_profile(
        user_id,
        full_name=full_name,
        age=None,
        birth_year=None,
        education=None,
        occupation=None,
        city=None,
        email=None
    )
    
    # Notify user of successful initial registration
    await update.message.reply_text(
        "✅ ثبت نام اولیه شما با موفقیت انجام شد. \n برای تکمیل اطلاعات خود و استفاده از امکانات ربات، لطفاً از منوی «پروفایل کاربری» اقدام کنید.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(TEXT_GENERAL_BACK_TO_MAIN_MENU, callback_data=CALLBACK_BACK_TO_MAIN_MENU)]
        ])
    )
    
    return ConversationHandler.END

async def get_birthyear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get user's birth year in Shamsi/Persian calendar"""
    user = update.effective_user
    user_id = user.id
    
    # Check if back button was pressed
    if update.message.text == "🔙 بازگشت":
        return await cancel_registration(update, context)
    
    try:
        birthyear = update.message.text.strip()
        birth_year_int = int(birthyear)
        
        # Basic validation for Shamsi year (adjust min/max years as needed)
        current_shamsi_year = 1404  # 2025 in Shamsi/Persian calendar
        if birth_year_int < 1320 or birth_year_int > current_shamsi_year - 10:
            await update.message.reply_text(
                "سال تولد وارد شده معتبر نیست. لطفاً یک سال تولد شمسی معتبر وارد کنید (بین ۱۳۲۰ تا ۱۳۹۴)."
            )
            return GET_BIRTHYEAR
        
        # Calculate age based on Shamsi years
        age = current_shamsi_year - birth_year_int
        
        # Update age and birth_year in database
        Database.update_user_profile(user_id, age=age, birth_year=birth_year_int)
        
        # Move to education step
        await update.message.reply_text(
            EDUCATION_REQUEST,
            reply_markup=get_education_keyboard()
        )
        
        return GET_EDUCATION
    except ValueError:
        await update.message.reply_text(
            BIRTHYEAR_REQUEST
        )
        return GET_BIRTHYEAR

async def get_education(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get user's education level"""
    user = update.effective_user
    user_id = user.id
    
    # Check if back button was pressed
    if update.message.text == "🔙 بازگشت":
        return await cancel_registration(update, context)
    
    education = update.message.text.strip()
    
    # Basic validation
    valid_educations = ["دیپلم", "کاردانی", "کارشناسی", "کارشناسی ارشد", "دکتری", "زیر دیپلم"]
    if education not in valid_educations:
        await update.message.reply_text(
            "لطفاً یکی از گزینه‌های موجود را انتخاب کنید."
        )
        return GET_EDUCATION
    
    # Update education in database
    Database.update_user_profile(user_id, education=education)
    
    # Move to occupation step
    await update.message.reply_text(
        OCCUPATION_REQUEST,
        reply_markup=get_occupation_keyboard()
    )
    
    return GET_OCCUPATION

async def get_occupation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get user's occupation from predefined options"""
    user = update.effective_user
    user_id = user.id
    
    # Check if back button was pressed
    if update.message.text == "🔙 بازگشت":
        return await cancel_registration(update, context)
    
    occupation = update.message.text.strip()
    
    # Basic validation
    valid_occupations = ["ارز، طلا، سکه", "فارکس", "کریپتو", "بورس"]
    if occupation not in valid_occupations:
        await update.message.reply_text(
            "لطفاً حیطه‌های فعالیت خود را از گزینه‌های زیر انتخاب کنید:\n\n"
        )
        return GET_OCCUPATION
    
    # Update occupation in database
    Database.update_user_profile(user_id, occupation=occupation)
    
    # Move to city step
    await update.message.reply_text(
        CITY_REQUEST,
        reply_markup=get_back_button()
    )
    
    return GET_CITY

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the registration process"""
    await update.message.reply_text(
        "ثبت‌نام لغو شد. می‌توانید از منوی اصلی گزینه مورد نظر خود را انتخاب کنید.",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END

# Define the conversation handler for registration
registration_conversation = ConversationHandler(
    entry_points=[
        CommandHandler("register", start_registration),
        MessageHandler(filters.Regex("^📝 ثبت نام$"), start_registration),
        CallbackQueryHandler(start_registration, pattern="^start_registration_flow$")
    ],
    states={
        GET_PHONE: [
            MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND), get_phone)
        ],
        GET_FULLNAME: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_fullname)
        ]
    },
    fallbacks=[
        MessageHandler(filters.Regex("^🔙 بازگشت$"), cancel_registration),
        CommandHandler("cancel", cancel_registration)
    ],
    per_message=False
)
