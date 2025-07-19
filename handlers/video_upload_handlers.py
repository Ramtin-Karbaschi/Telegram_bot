"""VideoUploadConversation
A standalone conversation handler that allows an admin to upload one or more new videos to the
bot's storage and immediately set an optional custom caption for each video.

Flow:
ENTRY (via CallbackQuery "upload_new_video") -> state WAIT_VIDEO:
    - Prompt the admin to send a .mp4 / Telegram video file.
Upon receiving the file (state WAIT_VIDEO):
    - Save to `video_service.save_uploaded_video` (utility already used elsewhere).
    - Store temp `video_id` returned under `context.user_data['upload_video_id']`.
    - Ask for caption with inline keyboard:
          "✏️ ویرایش کپشن" (goto WAIT_CAPTION)
          "➕ ویدئوی بعدی" (reset WAIT_VIDEO)
          "✅ پایان آپلود" (END and jump back to manage_videos callback)
    - If admin chooses to skip caption, caption remains empty.
WAIT_CAPTION:
    - Accept text message up to 500 chars (similar validation).
    - Update caption in DB via video_service.set_video_caption(video_id, caption)
    - Return to same keyboard for next action.

At the end the conversation returns to the parent handler by emitting a CallbackQuery
with data `back_to_video_selection` so that the existing video management UI refreshes.
"""
from __future__ import annotations

import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Video,
)
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from services.video_service import video_service

logger = logging.getLogger(__name__)

# States
WAIT_VIDEO, WAIT_CAPTION = range(2)

# Callback data constants
CB_EDIT_CAPTION = "vu_edit_caption"
CB_NEXT_VIDEO = "vu_next_video"
CB_FINISH = "vu_finish_upload"


async def entrypoint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt admin to send a video."""
    logger.info("Video upload conversation started")
    query = update.callback_query
    await query.answer()
    context.user_data.pop("upload_video_id", None)
    await query.edit_message_text(
        "🎥 لطفاً فایل ویدئویی را ارسال کنید یا /cancel را بزنید.",
    )
    logger.info("Returning WAIT_VIDEO state")
    return WAIT_VIDEO


async def handle_video_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the uploaded video and ask for next action."""
    logger.info("Video file received in conversation handler")
    video: Video | None = update.message.video
    if not video:
        await update.message.reply_text("❌ لطفاً یک فایل ویدئویی ارسال کنید.")
        return WAIT_VIDEO

    try:
        file_obj = await video.get_file()
        # Save using existing util, returns video_id
        video_id = await video_service.save_uploaded_video(file_obj, original_file_name=f"{video.file_unique_id}.mp4")
    except Exception as exc:
        logger.error("Error saving uploaded video: %s", exc)
        await update.message.reply_text("⚠️ خطا در ذخیره‌سازی ویدئو. لطفاً دوباره تلاش کنید.")
        return WAIT_VIDEO

    context.user_data["upload_video_id"] = video_id

    keyboard = [
        [
            InlineKeyboardButton("✏️ ویرایش کپشن", callback_data=CB_EDIT_CAPTION),
        ],
        [
            InlineKeyboardButton("➕ ویدئوی بعدی", callback_data=CB_NEXT_VIDEO),
        ],
        [
            InlineKeyboardButton("✅ پایان آپلود", callback_data=CB_FINISH),
        ],
    ]
    await update.message.reply_text(
        "✅ ویدئو ذخیره شد. حالا چه کاری می‌خواهید انجام دهید؟",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return WAIT_CAPTION  # expecting a callback


async def prompt_caption_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📝 کپشن دلخواه را ارسال کنید (حداکثر 500 کاراکتر). برای حذف /skip بزنید.")
    return WAIT_CAPTION


async def handle_caption_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vid = context.user_data.get("upload_video_id")
    if not vid:
        await update.message.reply_text("❌ خطا: شناسه ویدئو یافت نشد.")
        return WAIT_CAPTION

    text = update.message.text.strip()
    if text.lower() == "/skip":
        caption = ""
    else:
        if len(text) > 500:
            await update.message.reply_text("❌ کپشن بیش از 500 کاراکتر است. دوباره تلاش کنید.")
            return WAIT_CAPTION
        caption = text
    try:
        video_service.set_video_caption(vid, caption)
    except Exception as exc:
        logger.error("Error setting caption: %s", exc)
        await update.message.reply_text("⚠️ خطا در ذخیره کپشن.")
        return WAIT_CAPTION

    await update.message.reply_text("✅ کپشن ذخیره شد.")
    # Offer next actions again
    keyboard = [
        [InlineKeyboardButton("➕ ویدئوی بعدی", callback_data=CB_NEXT_VIDEO)],
        [InlineKeyboardButton("✅ پایان آپلود", callback_data=CB_FINISH)],
    ]
    await update.message.reply_text("ادامه دهید:", reply_markup=InlineKeyboardMarkup(keyboard))
    return WAIT_CAPTION


async def handle_next_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("upload_video_id", None)
    await query.edit_message_text("🎥 لطفاً ویدئوی بعدی را ارسال کنید یا /cancel را بزنید.")
    return WAIT_VIDEO


async def finish_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """End conversation and return to video selection UI."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✅ عملیات آپلود به پایان رسید.\n\n"
        "برای بازگشت به مدیریت ویدئوها از منوی اصلی استفاده کنید."
    )
    
    # Clear upload data
    context.user_data.pop("upload_video_id", None)
    
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ عملیات آپلود لغو شد.")
    else:
        await update.message.reply_text("❌ عملیات آپلود لغو شد.")
    return ConversationHandler.END


def get_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(entrypoint, pattern=r"^upload_new_video$")],
        states={
            WAIT_VIDEO: [MessageHandler(filters.VIDEO & ~filters.COMMAND, handle_video_file)],
            WAIT_CAPTION: [
                CallbackQueryHandler(prompt_caption_input, pattern=CB_EDIT_CAPTION),
                CallbackQueryHandler(handle_next_video, pattern=CB_NEXT_VIDEO),
                CallbackQueryHandler(finish_upload, pattern=CB_FINISH),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_caption_text),
            ],
        },
        fallbacks=[MessageHandler(filters.Command("cancel"), cancel), CallbackQueryHandler(cancel, pattern="^cancel$")],
        name="video_upload_conv",
        per_chat=True,
    )
