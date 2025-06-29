import logging
from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler
)
from database.queries import DatabaseQueries
from utils import keyboards, constants

logger = logging.getLogger(__name__)

# States for conversation
(CODE, TYPE, VALUE, START_DATE, END_DATE, MAX_USES, PLANS, CONFIRM) = range(8)

async def create_discount_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation to create a new discount code."""
    context.user_data['discount_info'] = {}
    await update.message.reply_text("لطفا کد تخفیف را وارد کنید:")
    return CODE

async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the discount code and asks for the type."""
    code = update.message.text
    context.user_data['discount_info']['code'] = code
    await update.message.reply_text("نوع تخفیف را انتخاب کنید:", reply_markup=keyboards.discount_type_keyboard())
    return TYPE

async def get_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the discount type and asks for the value."""
    query = update.callback_query
    await query.answer()
    context.user_data['discount_info']['type'] = query.data
    await query.edit_message_text("لطفا مقدار تخفیف را وارد کنید (برای درصدی عدد بین 1 تا 100 و برای مبلغ ثابت، مبلغ به تومان):")
    return VALUE

async def get_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the discount value and asks for the start date."""
    try:
        value = float(update.message.text)
        context.user_data['discount_info']['value'] = value
        await update.message.reply_text("تاریخ شروع را وارد کنید (YYYY-MM-DD) یا برای شروع فوری، 'skip' را بزنید:")
        return START_DATE
    except ValueError:
        await update.message.reply_text("مقدار نامعتبر است. لطفا یک عدد وارد کنید.")
        return VALUE

async def get_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the start date and asks for the end date."""
    if update.message.text.lower() != 'skip':
        context.user_data['discount_info']['start_date'] = update.message.text
    await update.message.reply_text("تاریخ پایان را وارد کنید (YYYY-MM-DD) یا برای بدون انقضا، 'skip' را بزنید:")
    return END_DATE

async def get_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the end date and asks for max uses."""
    if update.message.text.lower() != 'skip':
        context.user_data['discount_info']['end_date'] = update.message.text
    await update.message.reply_text("حداکثر تعداد استفاده را وارد کنید یا برای نامحدود، 'skip' را بزنید:")
    return MAX_USES

async def get_max_uses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets max uses and asks for applicable plans."""
    if update.message.text.lower() != 'skip':
        try:
            max_uses = int(update.message.text)
            context.user_data['discount_info']['max_uses'] = max_uses
        except ValueError:
            await update.message.reply_text("مقدار نامعتبر. لطفا یک عدد صحیح وارد کنید.")
            return MAX_USES
    
    plans = DatabaseQueries.get_active_plans()
    await update.message.reply_text("این تخفیف برای کدام پلن‌ها اعمال شود؟", reply_markup=keyboards.plans_for_discount_keyboard(plans))
    return PLANS

async def get_plans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Gets the selected plans and shows a confirmation."""
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split('_')[-1])
    
    if 'plan_ids' not in context.user_data['discount_info']:
        context.user_data['discount_info']['plan_ids'] = []
    
    context.user_data['discount_info']['plan_ids'].append(plan_id)
    
    # For simplicity, we'll just confirm after one plan is selected.
    # This can be improved to allow multiple selections.
    
    info = context.user_data['discount_info']
    summary = f"کد: {info['code']}\nنوع: {info['type']}\nمقدار: {info['value']}\nپلن‌ها: {info['plan_ids']}"
    await query.edit_message_text(f"خلاصه تخفیف:\n{summary}\n\nآیا تایید می‌کنید؟", reply_markup=keyboards.confirm_discount_keyboard())
    return CONFIRM

async def confirm_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirms and creates the discount."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'confirm_discount':
        info = context.user_data['discount_info']
        discount_id = DatabaseQueries.create_discount(
            code=info['code'],
            type=info['type'],
            value=info['value'],
            start_date=info.get('start_date'),
            end_date=info.get('end_date'),
            max_uses=info.get('max_uses')
        )
        if discount_id:
            DatabaseQueries.link_discount_to_plans(discount_id, info['plan_ids'])
            await query.edit_message_text("تخفیف با موفقیت ایجاد شد.")
        else:
            await query.edit_message_text("خطا در ایجاد تخفیف.")
    else:
        await query.edit_message_text("ایجاد تخفیف لغو شد.")
        
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the conversation."""
    await update.message.reply_text("عملیات لغو شد.")
    context.user_data.clear()
    return ConversationHandler.END

def get_create_discount_conv_handler() -> ConversationHandler:
    """Returns the conversation handler for creating a discount."""
    return ConversationHandler(
        entry_points=[CommandHandler('create_discount', create_discount_start)],
        states={
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_code)],
            TYPE: [CallbackQueryHandler(get_type, pattern='^(percentage|fixed_amount)$')],
            VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_value)],
            START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_start_date)],
            END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_end_date)],
            MAX_USES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_max_uses)],
            PLANS: [CallbackQueryHandler(get_plans, pattern='^select_plan_for_discount_')],
            CONFIRM: [CallbackQueryHandler(confirm_creation, pattern='^(confirm_discount|cancel_discount)$')]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
