"""
Video Caption Management Methods for Admin Product Handlers
"""

async def _handle_manage_video_captions(self, update, context):
    """Show video caption management interface."""
    query = update.callback_query
    await query.answer()
    
    mode = context.user_data.get('extra_mode', 'add')
    prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
    
    video_data = context.user_data.get(f'{prefix}video_data', {})
    
    if not video_data:
        await query.answer("❌ هیچ ویدئویی انتخاب نشده است.", show_alert=True)
        return FIELD_VALUE
    
    text = "📝 **مدیریت کپشن ویدئوها**\n\n"
    text += "ویدئوهای انتخاب شده:\n\n"
    
    keyboard = []
    for i, (video_id, video_info) in enumerate(video_data.items(), 1):
        video_name = video_info['display_name']
        has_caption = bool(video_info.get('custom_caption', '').strip())
        status = "✅" if has_caption else "❌"
        
        text += f"{i}. {status} {video_name}\n"
        if has_caption:
            caption_preview = video_info['custom_caption'][:50] + '...' if len(video_info['custom_caption']) > 50 else video_info['custom_caption']
            text += f"   📝 {caption_preview}\n"
        else:
            text += "   ⚠️ کپشن تعریف نشده\n"
        
        keyboard.append([InlineKeyboardButton(
            f"✏️ {video_name[:25]}{'...' if len(video_name) > 25 else ''}",
            callback_data=f"edit_caption_{video_id}"
        )])
    
    # Add button to upload new video
    keyboard.insert(0, [InlineKeyboardButton("➕ افزودن ویدئو جدید", callback_data="upload_new_video")])

    keyboard.extend([
        [InlineKeyboardButton("🔙 بازگشت به انتخاب ویدئو", callback_data="back_to_video_selection")],
        [InlineKeyboardButton("✅ تأیید و ادامه", callback_data="confirm_video_selection")]
    ])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return FIELD_VALUE

async def _handle_edit_caption(self, update, context):
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

async def _handle_caption_input(self, update, context):
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
    
    # Return to caption management
    import asyncio
    await asyncio.sleep(1)
    
    # Create mock query for returning to caption management
    class MockQuery:
        def __init__(self, chat_id):
            self.message = type('obj', (object,), {'chat_id': chat_id})
        
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
    await self._handle_manage_video_captions(type('obj', (object,), {'callback_query': mock_query})(), context)
    
    return FIELD_VALUE

async def _handle_video_help(self, update, context):
    """Show video management help."""
    query = update.callback_query
    await query.answer()
    
    text = "❓ **راهنمای مدیریت ویدئو**\n\n"
    text += "🎯 **هدف:**\n"
    text += "برای هر محصول می‌توانید چندین ویدئو با کپشن‌های سفارشی تعریف کنید.\n\n"
    
    text += "📋 **مراحل:**\n"
    text += "1️⃣ **انتخاب ویدئوها:** روی ویدئوهای مورد نظر کلیک کنید\n"
    text += "2️⃣ **تعریف کپشن:** برای هر ویدئو توضیح مناسب بنویسید\n"
    text += "3️⃣ **تنظیم ترتیب:** ترتیب نمایش ویدئوها را مشخص کنید\n"
    text += "4️⃣ **تأیید نهایی:** تنظیمات را ذخیره کنید\n\n"
    
    text += "💡 **نکات مهم:**\n"
    text += "• هر ویدئو باید کپشن داشته باشد\n"
    text += "• کپشن باید توضیح مختصری از محتوا باشد\n"
    text += "• ترتیب ویدئوها مهم است (از آسان به سخت)\n"
    text += "• می‌توانید بعداً ویدئوها را ویرایش کنید\n\n"
    
    text += "🔧 **عملکردها:**\n"
    text += "• ✅/▫️ انتخاب/لغو انتخاب ویدئو\n"
    text += "• 📝 مدیریت کپشن‌ها\n"
    text += "• 🔄 تغییر ترتیب نمایش\n"
    text += "• ✅ تأیید و ذخیره"
    
    keyboard = [[
        InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_video_selection")
    ]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return FIELD_VALUE

async def _handle_reorder_videos(self, update, context):
    """Handle video reordering interface."""
    query = update.callback_query
    await query.answer()
    
    mode = context.user_data.get('extra_mode', 'add')
    prefix = 'new_plan_' if mode == 'add' else 'edit_plan_'
    
    video_data = context.user_data.get(f'{prefix}video_data', {})
    
    if len(video_data) < 2:
        await query.answer("❌ برای تغییر ترتیب حداقل 2 ویدئو نیاز است.", show_alert=True)
        return FIELD_VALUE
    
    # Sort videos by current order
    sorted_videos = sorted(video_data.items(), key=lambda x: x[1].get('order', 0))
    
    text = "🔄 **تنظیم ترتیب ویدئوها**\n\n"
    text += "ترتیب فعلی:\n\n"
    
    keyboard = []
    for i, (video_id, video_info) in enumerate(sorted_videos):
        text += f"{i+1}. {video_info['display_name']}\n"
        
        # Add move up/down buttons (except for first/last)
        row = []
        if i > 0:  # Not first
            row.append(InlineKeyboardButton(f"⬆️ {i+1}", callback_data=f"move_video_up_{video_id}"))
        if i < len(sorted_videos) - 1:  # Not last
            row.append(InlineKeyboardButton(f"⬇️ {i+1}", callback_data=f"move_video_down_{video_id}"))
        
        if row:
            keyboard.append(row)
    
    text += "\n💡 از دکمه‌های ⬆️⬇️ برای تغییر ترتیب استفاده کنید."
    
    keyboard.extend([
        [InlineKeyboardButton("✅ تأیید ترتیب", callback_data="confirm_video_order")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_video_selection")]
    ])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return FIELD_VALUE

# Additional callback handlers that need to be added to conversation handler
ADDITIONAL_VIDEO_HANDLERS = [
    "CallbackQueryHandler(self._handle_manage_video_captions, pattern='^manage_video_captions$'),",
    "CallbackQueryHandler(self._handle_edit_caption, pattern='^edit_caption_'),",
    "CallbackQueryHandler(self._handle_video_help, pattern='^video_help$'),",
    "CallbackQueryHandler(self._handle_reorder_videos, pattern='^reorder_videos$'),",
    "CallbackQueryHandler(self._handle_force_confirm_videos, pattern='^force_confirm_videos$'),",
    "CallbackQueryHandler(self._handle_back_to_video_selection, pattern='^back_to_video_selection$'),",
    "CallbackQueryHandler(self._handle_video_page_nav, pattern='^vidsel_page_'),",
    "CallbackQueryHandler(self._handle_toggle_video, pattern='^toggle_video_'),",
    "CallbackQueryHandler(self._handle_confirm_video_selection, pattern='^confirm_video_selection$'),",
    "CallbackQueryHandler(self._handle_clear_video_selection, pattern='^clear_video_selection$'),"
]
