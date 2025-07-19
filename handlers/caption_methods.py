"""
Caption Management Methods for Video Handling
These methods should be added to AdminProductHandler class
"""

async def _handle_edit_caption(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle editing caption for a specific video."""
    query = update.callback_query
    await query.answer()
    
    video_id = int(query.data.split('_')[2])
    mode = context.user_data.get('extra_mode', 'add')
    prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
    
    video_data = context.user_data.get(f'{prefix}video_data', {})
    
    if video_id not in video_data:
        await query.answer("❌ ویدئو یافت نشد.", show_alert=True)
        return FIELD_VALUE
    
    video_info = video_data[video_id]
    current_caption = video_info.get('custom_caption', '')
    
    # Set caption editing mode
    context.user_data['caption_editing_video_id'] = video_id
    context.user_data['caption_step'] = 'input'
    
    text = f"📝 **ویرایش کپشن ویدئو**\n\n"
    text += f"🎥 **ویدئو:** {video_info['display_name']}\n\n"
    
    if current_caption:
        text += f"📄 **کپشن فعلی:**\n{current_caption}\n\n"
    else:
        text += "📄 **کپشن فعلی:** تعریف نشده\n\n"
    
    text += "✏️ **کپشن جدید را وارد کنید:**\n\n"
    text += "💡 **راهنمایی:**\n"
    text += "• کپشن باید توضیح مختصری از محتوای ویدئو باشد\n"
    text += "• می‌توانید از ایموجی استفاده کنید\n"
    text += "• حداکثر 500 کاراکتر\n"
    text += "• برای پاک کردن کپشن، عبارت 'حذف' را وارد کنید"
    
    keyboard = [[
        InlineKeyboardButton("❌ لغو", callback_data="cancel_caption_edit")
    ]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return FIELD_VALUE

async def _handle_caption_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle caption text input."""
    if context.user_data.get('caption_step') != 'input':
        return FIELD_VALUE
    
    video_id = context.user_data.get('caption_editing_video_id')
    if not video_id:
        await update.message.reply_text("❌ خطا در ویرایش کپشن.")
        return FIELD_VALUE
    
    mode = context.user_data.get('extra_mode', 'add')
    prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
    
    video_data = context.user_data.get(f'{prefix}video_data', {})
    
    if video_id not in video_data:
        await update.message.reply_text("❌ ویدئو یافت نشد.")
        return FIELD_VALUE
    
    caption_text = update.message.text.strip()
    
    # Handle deletion
    if caption_text.lower() in ['حذف', 'delete', 'remove']:
        video_data[video_id]['custom_caption'] = ''
        success_text = "🗑️ کپشن حذف شد."
    else:
        # Validate length
        if len(caption_text) > 500:
            await update.message.reply_text(
                "❌ کپشن خیلی طولانی است. حداکثر 500 کاراکتر مجاز است.\n"
                f"طول فعلی: {len(caption_text)} کاراکتر"
            )
            return FIELD_VALUE
        
        video_data[video_id]['custom_caption'] = caption_text
        success_text = "✅ کپشن با موفقیت ذخیره شد."
    
    # Clear editing state
    context.user_data.pop('caption_editing_video_id', None)
    context.user_data.pop('caption_step', None)
    
    # Update video data
    context.user_data[f'{prefix}video_data'] = video_data
    
    # Show success message
    await update.message.reply_text(success_text)
    
    # Return to caption management after 1 second
    import asyncio
    await asyncio.sleep(1)
    
    # Simulate callback query for returning to caption management
    class MockQuery:
        def __init__(self, chat_id):
            self.message = type('obj', (object,), {'chat_id': chat_id})()
        
        async def answer(self):
            pass
        
        async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
            await context.bot.send_message(
                chat_id=self.message.chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    
    mock_query = MockQuery(update.message.chat_id)
    mock_update = type('obj', (object,), {'callback_query': mock_query})()
    await self._handle_manage_video_captions(mock_update, context)
    
    return FIELD_VALUE

async def _handle_cancel_caption_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle canceling caption edit."""
    query = update.callback_query
    await query.answer()
    
    # Clear editing state
    context.user_data.pop('caption_editing_video_id', None)
    context.user_data.pop('caption_step', None)
    
    # Return to caption management
    await self._handle_manage_video_captions(update, context)
    return FIELD_VALUE

# Additional callback handlers to add to conversation handlers:
CAPTION_HANDLERS = [
    "CallbackQueryHandler(self._handle_edit_caption, pattern='^edit_caption_'),",
    "CallbackQueryHandler(self._handle_cancel_caption_edit, pattern='^cancel_caption_edit$'),"
]
