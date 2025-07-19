"""Survey Builder Conversation for Admins.
Allows creating a simple multi-question, multi-option survey and stores it
in context.user_data under `<prefix>survey_data` so that AdminProductHandler
can persist it when saving the plan.
"""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

logger = logging.getLogger(__name__)

# States
WAIT_Q_TEXT, WAIT_Q_OPTIONS, CONFIRM_Q = range(3)

CB_ADD_NEXT = "survey_add_next"
CB_FINISH = "survey_finish"
CB_CANCEL = "survey_cancel"

async def entrypoint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Clear temp survey buffer
    context.user_data['survey_builder_buffer'] = []
    await query.edit_message_text(
        "📝 لطفاً متن سوال شماره 1 را وارد کنید یا /cancel را بزنید.")
    context.user_data['survey_q_counter'] = 1
    return WAIT_Q_TEXT

async def handle_q_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data['current_q_text'] = text
    await update.message.reply_text(
        "🔹 گزینه‌های پاسخ را هرکدام در یک خط ارسال کنید (حداقل 2 مورد).\nمثال:\nالف\nب\nج")
    return WAIT_Q_OPTIONS

async def handle_q_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    options = [o.strip() for o in raw.split('\n') if o.strip()]
    if len(options) < 2:
        await update.message.reply_text("❌ حداقل 2 گزینه لازم است. دوباره ارسال کنید.")
        return WAIT_Q_OPTIONS
    # Store question
    buffer: list = context.user_data.get('survey_builder_buffer', [])
    buffer.append({
        'text': context.user_data.pop('current_q_text'),
        'options': options,
        'type': 'single'
    })
    context.user_data['survey_builder_buffer'] = buffer
    q_idx = len(buffer) + 1
    keyboard = [
        [InlineKeyboardButton("➕ سوال بعدی", callback_data=CB_ADD_NEXT)],
        [InlineKeyboardButton("✅ پایان", callback_data=CB_FINISH)],
        [InlineKeyboardButton("❌ لغو", callback_data=CB_CANCEL)],
    ]
    await update.message.reply_text(
        "سوال ذخیره شد. چه کاری انجام می‌دهید؟",
        reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM_Q

async def add_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    counter = len(context.user_data.get('survey_builder_buffer', [])) + 1
    await query.edit_message_text(f"📝 متن سوال شماره {counter} را وارد کنید:")
    return WAIT_Q_TEXT

async def finish_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    buffer = context.user_data.pop('survey_builder_buffer', [])
    mode = context.user_data.get('extra_mode', 'add')
    prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
    context.user_data[f'{prefix}survey_data'] = buffer
    await query.edit_message_text("✅ نظرسنجی با موفقیت ذخیره شد.")
    return ConversationHandler.END

async def cancel_builder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ سازنده نظرسنجی لغو شد.")
    else:
        await update.message.reply_text("❌ سازنده نظرسنجی لغو شد.")
    context.user_data.pop('survey_builder_buffer', None)
    context.user_data.pop('current_q_text', None)
    return ConversationHandler.END


def get_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(entrypoint, pattern=r"^survey_builder_start$")],
        states={
            WAIT_Q_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_q_text)],
            WAIT_Q_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_q_options)],
            CONFIRM_Q: [
                CallbackQueryHandler(add_next_question, pattern=CB_ADD_NEXT),
                CallbackQueryHandler(finish_survey, pattern=CB_FINISH),
                CallbackQueryHandler(cancel_builder, pattern=CB_CANCEL),
            ],
        },
        fallbacks=[MessageHandler(filters.Command("cancel"), cancel_builder), CallbackQueryHandler(cancel_builder, pattern="^cancel$")],
        name="survey_builder_conv",
        per_message=True,
    )
