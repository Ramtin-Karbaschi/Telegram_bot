import logging
import config
from utils.helpers import is_user_in_admin_list, is_user_registered, is_valid_full_name
import re
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,  # Added for type hinting
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,  # Added for fallbacks
    filters,
)

from database.queries import DatabaseQueries
from utils import constants
from utils import keyboards
from utils.validators import is_valid_persian_birth_year

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Explicitly set level for this specific logger

async def _update_profile_field(user_id: int, field_name_key: str, new_value, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Updates a single profile field in the database."""
    actual_field_name_in_db = None
    if field_name_key == constants.EDIT_FULL_NAME:
        actual_field_name_in_db = 'full_name'
    elif field_name_key == constants.EDIT_BIRTH_YEAR:
        actual_field_name_in_db = 'birth_year'
    elif field_name_key == constants.EDIT_EDUCATION:
        actual_field_name_in_db = 'education'
    elif field_name_key == constants.EDIT_OCCUPATION:
        actual_field_name_in_db = 'occupation'
    elif field_name_key == constants.EDIT_PHONE:
        actual_field_name_in_db = 'phone'
    elif field_name_key == constants.EDIT_CITY:
        actual_field_name_in_db = 'city'
    elif field_name_key == constants.EDIT_EMAIL:
        actual_field_name_in_db = 'email'
    
    if actual_field_name_in_db:
        db_success = DatabaseQueries.update_user_single_field(user_id, actual_field_name_in_db, new_value)
        return db_success
    logger.warning(f"Attempted to update an unknown field key: {field_name_key}")
    return False

async def start_profile_edit_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    logger.debug(f"PROFILE_HANDLER: Entering start_profile_edit_conversation. User: {update.effective_user.id}")
    """Displays the profile editing menu."""
    if update.callback_query:
        logger.debug(f"PROFILE_HANDLER: Callback query data in start_profile_edit_conversation: {update.callback_query.data}")
        await update.callback_query.answer()
        message_sender = update.callback_query.edit_message_text
        # If coming from a callback, ensure any reply keyboard is removed
        # This might not be necessary if the previous message didn't have one or was text-only
        # but can be a safeguard.
        # await update.callback_query.message.reply_text("Loading edit menu...", reply_markup=ReplyKeyboardRemove())
    else:
        logger.debug("PROFILE_HANDLER: No callback query in start_profile_edit_conversation, likely a command /edit_profile.")
        message_sender = update.effective_message.reply_text
        # Send a temporary message and then remove it if needed, or just send the menu directly
        # await update.effective_message.reply_text("Loading edit menu...", reply_markup=ReplyKeyboardRemove())

    logger.debug("PROFILE_HANDLER: Sending profile edit menu from start_profile_edit_conversation...")
    await message_sender(
        constants.PROFILE_EDIT_MENU_PROMPT,
        reply_markup=keyboards.get_profile_edit_menu_keyboard(user_id=update.effective_user.id)
    )
    logger.debug(f"PROFILE_HANDLER: Returning state: {constants.SELECT_FIELD_TO_EDIT} from start_profile_edit_conversation.")
    return constants.SELECT_FIELD_TO_EDIT

async def _ask_for_field_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                              field_key_constant: str, prompt_message: str, 
                              next_state: str, reply_markup_func=None, args=None) -> str:
    logger.debug(f"PROFILE_HANDLER: Entering _ask_for_field_edit. User: {update.effective_user.id}, Field: {field_key_constant}, Expected next state (from constants): {next_state}")
    query = update.callback_query
    await query.answer()
    context.user_data['editing_field_key'] = field_key_constant
    
    # Try to get a readable name from the button's text if possible
    button_text = "این مورد"
    if query.message and query.message.reply_markup:
        for row in query.message.reply_markup.inline_keyboard:
            for button in row:
                if button.callback_data == query.data:
                    button_text = button.text
                    break
            if button_text != "این مورد": break
    context.user_data['editing_field_readable_name'] = button_text

    markup_to_send = keyboards.get_edit_field_action_keyboard()
    if reply_markup_func:
        markup_to_send = reply_markup_func(*(args or []))
    
    await query.edit_message_text(
        text=prompt_message,
        reply_markup=markup_to_send
    )
    return next_state

async def ask_edit_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    logger.debug(f"PROFILE_HANDLER: Entering ask_edit_fullname. User: {update.effective_user.id}")
    logger.debug(f"Entering ask_edit_fullname. User: {update.effective_user.id}. Callback data: {update.callback_query.data if update.callback_query else 'No callback query'}")
    return await _ask_for_field_edit(update, context, constants.EDIT_FULL_NAME, constants.PROFILE_EDIT_FULL_NAME, constants.EDIT_FULL_NAME)

async def ask_edit_birthyear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    logger.debug(f"PROFILE_HANDLER: Entering ask_edit_birthyear. User: {update.effective_user.id}")
    return await _ask_for_field_edit(update, context, constants.EDIT_BIRTH_YEAR, constants.PROFILE_EDIT_BIRTH_YEAR, constants.EDIT_BIRTH_YEAR)

async def ask_edit_education(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    logger.debug(f"PROFILE_HANDLER: Entering ask_edit_education. User: {update.effective_user.id}")
    return await _ask_for_field_edit(update, context, constants.EDIT_EDUCATION, constants.PROFILE_EDIT_EDUCATION, constants.EDIT_EDUCATION, keyboards.get_education_inline_keyboard)

async def ask_edit_occupation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    logger.debug(f"PROFILE_HANDLER: Entering ask_edit_occupation. User: {update.effective_user.id}")
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user_profile_row = DatabaseQueries.get_user_details(user_id)
    user_profile = dict(user_profile_row) if user_profile_row else {}
    occupation_str = user_profile.get('occupation')
    current_occupations = occupation_str.split(',') if occupation_str else []
    context.user_data['selected_occupations'] = current_occupations

    await query.edit_message_text(
        text=constants.PROFILE_EDIT_OCCUPATION,
        reply_markup=keyboards.get_occupation_inline_keyboard(selected_occupations=current_occupations)
    )
    return constants.SELECT_OCCUPATION

async def ask_edit_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    logger.debug(f"PROFILE_HANDLER: Entering ask_edit_city. User: {update.effective_user.id}")
    return await _ask_for_field_edit(update, context, constants.EDIT_CITY, constants.PROFILE_EDIT_CITY_PROMPT, constants.EDIT_CITY)

async def ask_edit_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    logger.debug(f"PROFILE_HANDLER: Entering ask_edit_email. User: {update.effective_user.id}")
    return await _ask_for_field_edit(update, context, constants.EDIT_EMAIL, constants.PROFILE_EDIT_EMAIL_PROMPT, constants.EDIT_EMAIL)

async def ask_edit_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    logger.debug(f"PROFILE_HANDLER: Entering ask_edit_phone. User: {update.effective_user.id}")
    query = update.callback_query
    await query.answer()
    context.user_data['editing_field_key'] = constants.EDIT_PHONE
    context.user_data['editing_field_readable_name'] = "شماره تلفن"
    
    # Remove the inline keyboard message first
    await query.edit_message_reply_markup(reply_markup=None) 
    # await query.message.delete() # Alternative: delete the menu message

    reply_kb_markup, _ = keyboards.get_phone_edit_keyboard() # We only need reply keyboard part here
    
    await query.message.reply_text( 
        text=constants.PROFILE_ASK_PHONE_EDIT_WITH_CONTACT,
        reply_markup=reply_kb_markup
    )
    return constants.EDIT_PHONE

async def _handle_text_or_contact_input(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                        is_valid_value_func=None, error_message=None, 
                                        success_field_name_override=None) -> str:
    user_id = update.effective_user.id
    message = update.message
    new_value = None
    
    if message.contact:
        new_value = message.contact.phone_number
    elif message.text:
        new_value = message.text
    
    field_key = context.user_data.get('editing_field_key')
    field_readable_name = context.user_data.get('editing_field_readable_name', "این مورد")

    if not field_key:
        logger.error("editing_field_key not found in user_data during input handling.")
        await message.reply_text("یک خطای داخلی رخ داده است. لطفاً مجدداً تلاش کنید.", reply_markup=keyboards.get_main_menu_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

    if is_valid_value_func and not is_valid_value_func(new_value):
        current_state_reply_markup = keyboards.get_edit_field_action_keyboard()
        if field_key == constants.EDIT_PHONE:
            current_state_reply_markup, _ = keyboards.get_phone_edit_keyboard()

        await message.reply_text(
            error_message or "مقدار وارد شده معتبر نیست. لطفاً دوباره تلاش کنید.",
            reply_markup=current_state_reply_markup
        )
        return field_key

    if await _update_profile_field(user_id, field_key, new_value, context):
        await message.reply_text(
            constants.PROFILE_EDIT_FIELD_SUCCESS.format(field_name=success_field_name_override or field_readable_name),
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await message.reply_text(f"خطایی در به‌روزرسانی {success_field_name_override or field_readable_name} رخ داد.", reply_markup=ReplyKeyboardRemove())

    await message.reply_text(
        constants.PROFILE_EDIT_MENU_PROMPT,
        reply_markup=keyboards.get_profile_edit_menu_keyboard(user_id=user_id)
    )
    context.user_data.pop('editing_field_key', None)
    context.user_data.pop('editing_field_readable_name', None)
    return constants.SELECT_FIELD_TO_EDIT

async def handle_fullname_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Handles user input for the full name, validates it, and updates the profile."""
    return await _handle_text_or_contact_input(
        update,
        context,
        is_valid_value_func=is_valid_full_name,
        error_message=(
            "نام و نام خانوادگی وارد شده معتبر نیست.\n"
            "- لطفاً فقط از حروف فارسی و فاصله استفاده کنید.\n"
            "- نام باید حداقل ۳ کاراکتر داشته باشد.\n"
            "- استفاده از اعداد و کاراکترهای خاص (مانند نقطه، ویرگول و ...) مجاز نیست.\n\n"
            "لطفاً نام کامل خود را دوباره وارد کنید:"
        ),
        success_field_name_override="نام و نام خانوادگی"
    )

async def handle_city_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    return await _handle_text_or_contact_input(update, context, success_field_name_override="شهر محل سکونت")

async def handle_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    # Basic email validation (similar to registration)
    email = update.message.text
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        await update.message.reply_text(
            "فرمت ایمیل وارد شده صحیح نیست.\nلطفاً یک ایمیل معتبر وارد کنید.",
            reply_markup=keyboards.get_edit_field_action_keyboard()
        )
        return constants.EDIT_EMAIL # Stay in the same state
    return await _handle_text_or_contact_input(update, context, success_field_name_override="ایمیل")

async def handle_birthyear_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    return await _handle_text_or_contact_input(update, context, 
                                             is_valid_value_func=is_valid_persian_birth_year, 
                                             error_message=constants.PROFILE_INVALID_BIRTHYEAR,
                                             success_field_name_override="سال تولد")

async def _handle_callback_query_input(update: Update, context: ContextTypes.DEFAULT_TYPE, data_prefix: str, success_field_name_override=None) -> str:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    try:
        new_value = query.data.split(data_prefix, 1)[1]
    except IndexError:
        logger.error(f"Could not parse value from callback_data: {query.data} with prefix {data_prefix}")
        await query.edit_message_text("خطا در پردازش انتخاب شما. لطفاً دوباره تلاش کنید.")
        await query.message.reply_text(constants.PROFILE_EDIT_MENU_PROMPT, reply_markup=keyboards.get_profile_edit_menu_keyboard(user_id=user_id))
        context.user_data.clear()
        return constants.SELECT_FIELD_TO_EDIT

    field_key = context.user_data.get('editing_field_key')
    field_readable_name = context.user_data.get('editing_field_readable_name', "این مورد")

    if not field_key:
        logger.error("editing_field_key not found for callback query input.")
        await query.edit_message_text("یک خطای داخلی رخ داده است. لطفاً مجدداً تلاش کنید.")
        await query.message.reply_text(constants.PROFILE_EDIT_MENU_PROMPT, reply_markup=keyboards.get_profile_edit_menu_keyboard(user_id=user_id))
        context.user_data.clear()
        return constants.SELECT_FIELD_TO_EDIT
        
    if await _update_profile_field(user_id, field_key, new_value, context):
        await query.edit_message_text(constants.PROFILE_EDIT_FIELD_SUCCESS.format(field_name=success_field_name_override or field_readable_name))
    else:
        await query.edit_message_text(f"خطایی در به‌روزرسانی {success_field_name_override or field_readable_name} رخ داد.")

    await query.message.reply_text(
        constants.PROFILE_EDIT_MENU_PROMPT,
        reply_markup=keyboards.get_profile_edit_menu_keyboard(user_id=user_id)
    )
    context.user_data.pop('editing_field_key', None)
    context.user_data.pop('editing_field_readable_name', None)
    return constants.SELECT_FIELD_TO_EDIT

async def handle_education_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    return await _handle_callback_query_input(update, context, "education_", success_field_name_override="میزان تحصیلات")

async def handle_occupation_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Handles user clicking on an occupation to select/deselect it."""
    query = update.callback_query
    await query.answer()
    occupation = query.data.split('occupation_', 1)[1]

    selected_occupations = context.user_data.get('selected_occupations', [])
    if occupation in selected_occupations:
        selected_occupations.remove(occupation)
    else:
        selected_occupations.append(occupation)
    
    context.user_data['selected_occupations'] = selected_occupations

    await query.edit_message_text(
        text=constants.PROFILE_EDIT_OCCUPATION,
        reply_markup=keyboards.get_occupation_inline_keyboard(selected_occupations=selected_occupations)
    )
    return constants.SELECT_OCCUPATION

async def confirm_occupation_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Saves the selected occupations to the database."""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    selected_occupations = context.user_data.get('selected_occupations', [])
    new_value = ','.join(selected_occupations)

    if await _update_profile_field(user_id, constants.EDIT_OCCUPATION, new_value, context):
        await query.edit_message_text(constants.PROFILE_EDIT_FIELD_SUCCESS.format(field_name="حیطه فعالیت"))
    else:
        await query.edit_message_text("خطایی در به‌روزرسانی حیطه فعالیت رخ داد.")

    await query.message.reply_text(
        constants.PROFILE_EDIT_MENU_PROMPT,
        reply_markup=keyboards.get_profile_edit_menu_keyboard(user_id=user_id)
    )
    context.user_data.pop('selected_occupations', None)
    return constants.SELECT_FIELD_TO_EDIT

async def handle_phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    def is_valid_phone(value):
        if value:
            cleaned_value = value.replace("+", "").strip()
            return cleaned_value.isdigit() and 9 <= len(cleaned_value) <= 15
        return False

    return await _handle_text_or_contact_input(update, context, 
                                             is_valid_value_func=is_valid_phone,
                                             error_message="شماره تلفن وارد شده معتبر نیست. لطفاً شماره صحیح را وارد کنید یا با دکمه اشتراک بگذارید.",
                                             success_field_name_override="شماره تلفن")

async def cancel_current_field_edit_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    await query.answer()
    field_readable_name = context.user_data.get('editing_field_readable_name', "این مورد")

    await query.edit_message_text(
        constants.PROFILE_EDIT_FIELD_CANCELLED.format(field_name=field_readable_name)
    )
    await query.message.reply_text( 
        constants.PROFILE_EDIT_MENU_PROMPT,
        reply_markup=keyboards.get_profile_edit_menu_keyboard(user_id=user_id)
    )
    context.user_data.pop('editing_field_key', None)
    context.user_data.pop('editing_field_readable_name', None)
    return constants.SELECT_FIELD_TO_EDIT

async def end_profile_edit_globally(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.debug(f"PROFILE_HANDLER: Entering FALLBACK end_profile_edit_globally (cancel). User: {update.effective_user.id}. Callback data: {update.callback_query.data if update.callback_query else 'No callback query'}")
    message_to_send = constants.PROFILE_EDIT_CANCELLED
    user_id = update.effective_user.id
    is_admin = is_user_in_admin_list(user_id, config.ALL_ADMINS_LIST)
    is_registered = is_user_registered(user_id)
    logger.debug(f"PROFILE_HANDLER: end_profile_edit_globally for user {user_id}, admin: {is_admin}, registered: {is_registered}")
    reply_markup_to_send = keyboards.get_main_menu_keyboard(user_id=user_id, is_admin=is_admin, is_registered=is_registered)
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(message_to_send, reply_markup=reply_markup_to_send)
        except Exception as e:
            logger.info(f"Could not edit message on global cancel, sending new one: {e}")
            await update.effective_message.reply_text(message_to_send, reply_markup=reply_markup_to_send)
    else:
        await update.effective_message.reply_text(message_to_send, reply_markup=reply_markup_to_send)

    # await update.effective_message.reply_text(
    #     "به منوی اصلی بازگشتید.",
    #     reply_markup=reply_markup_to_send
    # )
    context.user_data.clear()
    return ConversationHandler.END

async def catch_all_select_field_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    if query:
        logger.debug(
            f"PROFILE_HANDLER: CATCH_ALL_SELECT_FIELD_CALLBACK triggered. Data: '{query.data}'. "
            f"User: {update.effective_user.id}."
        )
        await query.answer("Callback caught by catch-all in select field state.")
    else:
        logger.debug(
            f"PROFILE_HANDLER: CATCH_ALL_SELECT_FIELD_CALLBACK triggered without query. Update: {update}"
        )
    return constants.SELECT_FIELD_TO_EDIT # Keep the conversation in the same state

async def update_user_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Update the user's full name after validation."""
    user_id = update.effective_user.id
    new_fullname = update.message.text

    if not is_valid_full_name(new_fullname):
        await update.message.reply_text(
            "نام و نام خانوادگی وارد شده معتبر نیست.\n"
            "- لطفاً فقط از حروف فارسی و فاصله استفاده کنید.\n"
            "- نام باید حداقل ۳ کاراکتر داشته باشد.\n"
            "- استفاده از اعداد و کاراکترهای خاص (مانند نقطه، ویرگول و ...) مجاز نیست.\n\n"
            "لطفاً نام کامل خود را دوباره وارد کنید:"
        )
        return constants.EDIT_FULL_NAME

    db_query = DatabaseQueries()
    db_query.update_user_field(user_id, 'full_name', new_fullname)
    await update.message.reply_text(
        f"نام و نام خانوادگی شما با موفقیت به '{new_fullname}' تغییر یافت.",
        reply_markup=await keyboards.get_profile_edit_menu_keyboard(user_id)
    )
    return constants.SELECT_FIELD_TO_EDIT

from utils.constants import (
    SELECT_FIELD_TO_EDIT, EDIT_FULL_NAME, EDIT_BIRTH_YEAR, EDIT_EDUCATION, EDIT_OCCUPATION, SELECT_OCCUPATION, EDIT_PHONE, EDIT_CITY, EDIT_EMAIL,
    CALLBACK_PROFILE_EDIT_FULLNAME, CALLBACK_PROFILE_EDIT_BIRTHYEAR, CALLBACK_PROFILE_EDIT_EDUCATION, 
    CALLBACK_PROFILE_EDIT_OCCUPATION, CALLBACK_PROFILE_EDIT_OCCUPATION_CONFIRM, CALLBACK_PROFILE_EDIT_PHONE, CALLBACK_PROFILE_EDIT_CITY, CALLBACK_PROFILE_EDIT_EMAIL,
    CALLBACK_BACK_TO_MAIN_MENU_FROM_EDIT, CALLBACK_PROFILE_EDIT_CANCEL, CALLBACK_PROFILE_EDIT_BACK_TO_MENU,
    TEXT_MAIN_MENU_EDIT_PROFILE, CALLBACK_START_PROFILE_EDIT # Added for entry points
)

def get_profile_edit_conv_handler() -> ConversationHandler:
    logger.debug("PROFILE_HANDLER: Entering get_profile_edit_conv_handler")

    # Entry point via text from main menu (ReplyKeyboard)
    entry_point_text_filter = filters.TEXT & filters.Regex(f"^{TEXT_MAIN_MENU_EDIT_PROFILE}$")
    # Entry point via callback data (e.g., from an inline button elsewhere)
    entry_point_callback_pattern = f"^{CALLBACK_START_PROFILE_EDIT}$"

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(entry_point_text_filter, start_profile_edit_conversation),
            CallbackQueryHandler(start_profile_edit_conversation, pattern=entry_point_callback_pattern)
        ],
        states={
            constants.SELECT_FIELD_TO_EDIT: [
                CallbackQueryHandler(ask_edit_fullname, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_FULLNAME}$" ),
                CallbackQueryHandler(ask_edit_birthyear, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_BIRTHYEAR}$" ),
                CallbackQueryHandler(ask_edit_education, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_EDUCATION}$" ),
                CallbackQueryHandler(ask_edit_occupation, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_OCCUPATION}$" ),
                CallbackQueryHandler(ask_edit_city, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_CITY}$"),
                CallbackQueryHandler(ask_edit_email, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_EMAIL}$"),
                CallbackQueryHandler(ask_edit_phone, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_PHONE}$" ),
                CallbackQueryHandler(end_profile_edit_globally, pattern=f"^{constants.CALLBACK_BACK_TO_MAIN_MENU_FROM_EDIT}$" ),
                CallbackQueryHandler(catch_all_select_field_callback, pattern="^.*$") # Catch-all handler, MUST BE LAST
            ],
            constants.EDIT_FULL_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_fullname_input),
                CallbackQueryHandler(cancel_current_field_edit_cb, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_CANCEL}$")
            ],
            constants.EDIT_BIRTH_YEAR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_birthyear_input),
                CallbackQueryHandler(cancel_current_field_edit_cb, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_CANCEL}$")
            ],
            constants.EDIT_EDUCATION: [
                CallbackQueryHandler(handle_education_input, pattern="^education_"),
                CallbackQueryHandler(cancel_current_field_edit_cb, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_CANCEL}$")
            ],
            constants.SELECT_OCCUPATION: [
                CallbackQueryHandler(handle_occupation_selection, pattern="^occupation_"),
                CallbackQueryHandler(confirm_occupation_selection, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_OCCUPATION_CONFIRM}$"),
                CallbackQueryHandler(cancel_current_field_edit_cb, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_BACK_TO_MENU}$")
            ],
            constants.EDIT_PHONE: [
                MessageHandler(filters.CONTACT | (filters.TEXT & ~filters.COMMAND & ~filters.Regex(f"^{constants.REPLY_KEYBOARD_BACK_TO_EDIT_MENU_TEXT}$")), handle_phone_input),
                CallbackQueryHandler(cancel_current_field_edit_cb, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_CANCEL}$")
            ],
            constants.EDIT_CITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city_input),
                CallbackQueryHandler(cancel_current_field_edit_cb, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_CANCEL}$")
            ],
            constants.EDIT_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email_input),
                CallbackQueryHandler(cancel_current_field_edit_cb, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_CANCEL}$")
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_current_field_edit_cb, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_BACK_TO_MENU}$"),
            CallbackQueryHandler(cancel_current_field_edit_cb, pattern=f"^{constants.CALLBACK_PROFILE_EDIT_CANCEL}$"),
            CommandHandler("cancel_edit", end_profile_edit_globally), # More specific cancel command
            CallbackQueryHandler(end_profile_edit_globally, pattern=f"^{constants.CALLBACK_BACK_TO_MAIN_MENU_FROM_EDIT}$"), # If pressed from a sub-state
        ],
        map_to_parent={},
        name="profile_edit_conversation",
        persistent=False,
        per_message=False
    )
    logger.debug("PROFILE_HANDLER: profile_edit_conv_handler created and RETURNED from get_profile_edit_conv_handler.")
    return conv_handler
