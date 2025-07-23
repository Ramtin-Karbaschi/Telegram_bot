"""Admin-side AltSeason management handler."""

from __future__ import annotations
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, ConversationHandler, ContextTypes, MessageHandler, filters
import pandas as pd
import io
from database.altseason_queries import AltSeasonQueries
from database.models import Database

logger = logging.getLogger(__name__)

MENU, TOGGLE, EXPORT, Q_LIST, ADD_Q, EDIT_Q, V_LIST, ADD_V, EDIT_V, POLL_INPUT, TEXT_INPUT, ORDER_MANAGE, KEYBOARD_SETTINGS = range(13)

aqs = AltSeasonQueries()

class AdminAltSeasonHandler:
    """Provide simple admin controls: enable/disable button and export excel."""

    def __init__(self):
        self.db = aqs

    async def _go_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Safely reconstruct the Products submenu and end the conversation
        keyboard = [
            [InlineKeyboardButton("➕ محصول جدید", callback_data="products_add"), InlineKeyboardButton("📜 محصولات", callback_data="products_list")],
            [InlineKeyboardButton("📂 مدیریت دسته‌بندی‌ها", callback_data="manage_categories")],
            [InlineKeyboardButton("آلت‌سیزن", callback_data="altseason_admin")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")],
        ]
        text = "📦 *مدیریت محصولات*:\nچه کاری می‌خواهید انجام دهید؟"
        try:
            await update.callback_query.edit_message_text(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except BadRequest:
            # If message is not modified, send new message
            await update.callback_query.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        return ConversationHandler.END

    async def entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("فعال/غیرفعال کردن دکمه", callback_data="alt_toggle")],
            [InlineKeyboardButton("📄 دریافت گزارش اکسل", callback_data="alt_export")],
            [InlineKeyboardButton("📝 مدیریت سؤال‌ها", callback_data="alt_q_list")],
            [InlineKeyboardButton("🎥 مدیریت ویدیوها", callback_data="alt_v_list")],
            [InlineKeyboardButton("🔄 ترتیب نمایش کلی", callback_data="alt_order_manage")],
            [InlineKeyboardButton("⌨️ تنظیمات کیبورد پایان", callback_data="alt_keyboard_settings")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")],
        ]
        flag = "✅ فعال" if self.db.is_enabled() else "❌ غیرفعال"
        text = f"مدیریت آلت‌سیزن\n\nوضعیت فعلی دکمه: {flag}"
        try:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        except BadRequest:
            # If nothing changed, avoid error
            pass
        return MENU

    async def toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        new_flag = not self.db.is_enabled()
        self.db.set_enabled(new_flag)
        await update.callback_query.answer("وضعیت ذخیره شد")
        return await self.entry(update, context)

    async def export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Export answers to Excel file."""
        try:
            df = self.db.export_answers_dataframe()
            if df is None or df.empty:
                await update.callback_query.answer("هیچ داده‌ای برای صادرات یافت نشد")
                return await self.entry(update, context)
            
            # Create Excel file in memory
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='AltSeason Answers', index=False)
            
            output.seek(0)
            
            # Send file to admin
            from datetime import datetime
            filename = f"altseason_answers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            await update.callback_query.message.reply_document(
                document=output,
                filename=filename,
                caption=f"📄 گزارش پاسخ‌های آلت‌سیزن\nتعداد کاربران: {len(df)}"
            )
            
            await update.callback_query.answer("گزارش ارسال شد")
            
        except Exception as e:
            logger.error(f"Error exporting Excel: {e}")
            await update.callback_query.answer("خطا در صادرات گزارش")
        
        return await self.entry(update, context)

    async def q_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show list of questions with controls"""
        qs = self.db.list_questions()
        keyboard = []
        for q in qs:
            display = f"{q['question_order']}. {q.get('title', 'بدون نام')}"
            row_btns = [InlineKeyboardButton(display, callback_data=f"alt_qsel_{q['id']}")]
            keyboard.append(row_btns)
        keyboard.append([InlineKeyboardButton("➕ سؤال جدید", callback_data="alt_q_add")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])
        await update.callback_query.edit_message_text("📝 *سؤال‌های آلت‌سیزن*:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return Q_LIST

    async def q_add_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.edit_message_text("📝 نام سؤال جدید را وارد کنید:")
        context.user_data['adding_question'] = True
        return TEXT_INPUT

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text when bot expects a title."""
        text = update.message.text.strip()
        # Determine flow based on context flags
        if context.user_data.get('adding_question'):
            context.user_data['question_title'] = text
            await update.message.reply_text("📊 حالا Poll سؤال را ارسال کنید:")
            return POLL_INPUT
        if context.user_data.get('adding_video'):
            context.user_data['video_title'] = text
            await update.message.reply_text("🎥 حالا فایل ویدیویی را ارسال کنید:")
            return ADD_V
        if context.user_data.get('editing_v_caption'):
            v_id = context.user_data.pop('editing_v_id', None)
            context.user_data.pop('editing_v_caption', None)
            if v_id:
                db = Database()
                if db.connect():
                    try:
                        db.conn.execute("UPDATE altseason_videos SET caption = ? WHERE id = ?", (text, v_id))
                        db.conn.commit()
                        await update.message.reply_text("✅ کپشن ذخیره شد")
                    finally:
                        db.close()
            # Return to video list
            from types import SimpleNamespace
            fake_query = SimpleNamespace()
            fake_query.callback_query = SimpleNamespace()
            fake_query.callback_query.edit_message_text = update.message.reply_text
            return await self.v_list(fake_query, context)
        # Fallback: ignore text when not expected
        await update.message.reply_text("متن دریافت شد اما عملیات معتبری در جریان نیست.")
        return TEXT_INPUT

    async def q_save_poll(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Save poll as question"""
        if not update.message.poll:
            await update.message.reply_text("لطفاً یک Poll ارسال کنید.")
            return POLL_INPUT
            
        poll = update.message.poll
        poll_id = poll.id
        order = len(self.db.list_questions()) + 1
        title = context.user_data.pop('question_title', f'سؤال {order}')
        context.user_data.pop('adding_question', None)
        poll_chat_id = update.message.chat_id
        poll_message_id = update.message.message_id
        
        # Store poll details for reconstruction
        poll_question = poll.question
        poll_options = [option.text for option in poll.options]
        poll_data = {
            'question': poll_question,
            'options': poll_options,
            'is_anonymous': poll.is_anonymous,
            'allows_multiple_answers': poll.allows_multiple_answers
        }
        
        self.db.add_question(order, poll_id, poll_chat_id, poll_message_id, title, poll_data=poll_data)
        await update.message.reply_text("✅ سؤال Poll ثبت شد")
        
        # Return to question list
        keyboard = []
        qs = self.db.list_questions()
        for q in qs:
            display = f"{q['question_order']}. {q.get('title', 'بدون نام')}"
            keyboard.append([InlineKeyboardButton(display, callback_data=f"alt_qsel_{q['id']}")])
        keyboard.append([InlineKeyboardButton("➕ سؤال جدید", callback_data="alt_q_add")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])
        
        await update.message.reply_text(
            "📝 *سؤال‌های آلت‌سیزن*:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return Q_LIST

    async def q_select(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle selection of a specific question for editing"""
        q_id = int(update.callback_query.data.split('_')[-1])
        context.user_data['editing_q_id'] = q_id
        
        # Get question details
        qs = self.db.list_questions()
        q = next((x for x in qs if x['id'] == q_id), None)
        if not q:
            await update.callback_query.answer("سؤال یافت نشد")
            return Q_LIST
            
        keyboard = [
            [InlineKeyboardButton("✏️ ویرایش متن", callback_data=f"alt_q_edit_{q_id}")],
            [InlineKeyboardButton("▲ بالا بردن", callback_data=f"alt_q_up_{q_id}"), 
             InlineKeyboardButton("▼ پایین بردن", callback_data=f"alt_q_down_{q_id}")],
            [InlineKeyboardButton("🗑 حذف", callback_data=f"alt_q_del_{q_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="alt_q_list")],
        ]
        
        text = f"سؤال شماره {q['question_order']}\nPoll ID: {q['poll_id']}\n\nعملیات مورد نظر را انتخاب کنید:"
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return EDIT_Q

    async def q_edit_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt for new question poll"""
        await update.callback_query.edit_message_text("📊 Poll جدید را برای ویرایش ارسال کنید:")
        return POLL_INPUT

    async def q_edit_save(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Save edited question"""
        q_id = context.user_data.get('editing_q_id')
        if not q_id:
            await update.message.reply_text("خطا در ویرایش")
            return Q_LIST
            
        new_poll_id = update.message.text.strip()
        # Update in database
        db = Database()
        if db.connect():
            try:
                db.conn.execute("UPDATE altseason_questions SET poll_id = ? WHERE id = ?", (new_poll_id, q_id))
                db.conn.commit()
                await update.message.reply_text("ویرایش شد")
            finally:
                db.close()
        
        # Return to question list
        from types import SimpleNamespace
        fake_query = SimpleNamespace()
        fake_query.callback_query = SimpleNamespace()
        fake_query.callback_query.edit_message_text = update.message.reply_text
        return await self.q_list(fake_query, context)

    async def q_edit_save_poll(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Save edited poll question"""
        if not update.message.poll:
            await update.message.reply_text("لطفاً یک Poll ارسال کنید.")
            return POLL_INPUT
            
        q_id = context.user_data.get('editing_q_id')
        if not q_id:
            await update.message.reply_text("خطا در ویرایش")
            return Q_LIST
            
        new_poll_id = update.message.poll.id
        # Update in database
        db = Database()
        if db.connect():
            try:
                db.conn.execute("UPDATE altseason_questions SET poll_id = ? WHERE id = ?", (new_poll_id, q_id))
                db.conn.commit()
                await update.message.reply_text("✅ سؤال Poll ویرایش شد")
            finally:
                db.close()
        
        # Return to question list
        keyboard = []
        qs = self.db.list_questions()
        for q in qs:
            display = f"{q['question_order']}. {q.get('title', 'بدون نام')}"
            keyboard.append([InlineKeyboardButton(display, callback_data=f"alt_qsel_{q['id']}")])
        keyboard.append([InlineKeyboardButton("➕ سؤال جدید", callback_data="alt_q_add")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])
        
        await update.message.reply_text(
            "📝 *سؤال‌های آلت‌سیزن*:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return Q_LIST

    async def q_move(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Move question up or down"""
        data = update.callback_query.data
        q_id = int(data.split('_')[-1])
        direction = 'up' if 'up' in data else 'down'
        
        success = self.db.move_question(q_id, direction)
        if success:
            await update.callback_query.answer("جابه‌جا شد")
        else:
            await update.callback_query.answer("امکان جابه‌جایی نیست")
            
        return await self.q_list(update, context)

    async def q_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delete question"""
        q_id = int(update.callback_query.data.split('_')[-1])
        success = self.db.delete_question(q_id)
        
        if success:
            await update.callback_query.answer("حذف شد")
        else:
            await update.callback_query.answer("خطا در حذف")
            
        return await self.q_list(update, context)

    # Video Management Methods
    async def v_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show list of videos with controls"""
        vs = self.db.list_videos()
        keyboard = []
        for v in vs:
            display = f"{v['video_order']}. {v.get('title', 'بدون نام')}"
            keyboard.append([InlineKeyboardButton(display, callback_data=f"alt_vsel_{v['id']}")])
        keyboard.append([InlineKeyboardButton("➕ ویدیو جدید", callback_data="alt_v_add")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])
        await update.callback_query.edit_message_text("🎥 *ویدیوهای آلت‌سیزن*:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        return V_LIST

    async def v_add_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Show options: upload new video or select from local files
        keyboard = [
            [InlineKeyboardButton("📤 آپلود ویدیو جدید", callback_data="alt_v_upload")],
            [InlineKeyboardButton("📁 انتخاب از فایل‌های محلی", callback_data="alt_v_browse")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="alt_v_list")],
        ]
        await update.callback_query.edit_message_text(
            "🎥 *افزودن ویدیو جدید*\n\nنحوه افزودن را انتخاب کنید:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADD_V

    async def v_upload_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.edit_message_text("📝 نام ویدیو جدید را وارد کنید:")
        context.user_data['adding_video'] = True
        return TEXT_INPUT

    async def v_browse_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show local video files for selection"""
        from telegram.error import BadRequest
        """Show local video files for selection"""
        await update.callback_query.answer()
        import os
        from pathlib import Path
        # Determine project root based on current file location (three levels up)
        project_root = Path(__file__).resolve().parents[2]
        videos_dir = project_root / "database" / "data" / "videos"
        videos_dir = videos_dir.as_posix()  # use POSIX-style path for Telegram messages
        
        if not os.path.exists(videos_dir):
            await update.callback_query.answer("📁 پوشه ویدیوها یافت نشد")
            return await self.v_add_prompt(update, context)
        
        try:
            video_files = [f for f in os.listdir(videos_dir) if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv"))]
            print(f"DEBUG: Found {len(video_files)} video files: {video_files}")
        except Exception as e:
            print(f"DEBUG: Error listing directory: {e}")
            video_files = []
        
        if not video_files:
            try:
                await update.callback_query.edit_message_text(
                    "📁 هیچ فایل ویدیویی در پوشه یافت نشد.\n\nلطفاً فایل‌های ویدیو را در مسیر زیر قرار دهید:\n`{videos_dir}`",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="alt_v_add")]])
                )
            except BadRequest:
                pass
            return ADD_V
        
        keyboard = []
        for i, filename in enumerate(video_files[:10]):  # Limit to 10 files
            keyboard.append([InlineKeyboardButton(f"📹 {filename[:30]}...", callback_data=f"alt_v_file_{i}")])
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="alt_v_add")])
        
        # Store files list in context for callback
        context.user_data['video_files'] = video_files
        
        try:
            await update.callback_query.edit_message_text(
                "📁 *انتخاب فایل ویدیو*\n\nفایل مورد نظر را انتخاب کنید:",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except BadRequest:
            pass
        return ADD_V

    async def v_select_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle selection of a local video file"""
        import os
        file_index = int(update.callback_query.data.split('_')[-1])
        video_files = context.user_data.get('video_files', [])
        
        if file_index >= len(video_files):
            await update.callback_query.answer("❌ فایل یافت نشد")
            return ADD_V
        
        selected_file = video_files[file_index]
        from pathlib import Path
        project_root = Path(__file__).resolve().parents[2]
        videos_dir = project_root / "database" / "data" / "videos"
        file_path = videos_dir / selected_file
        
        # Upload the file to Telegram and get file_id
        try:
            with open(file_path, 'rb') as video_file:
                msg = await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=video_file,
                    caption=f"📤 آپلود {selected_file}"
                )
                
                # Save to database
                order = len(self.db.list_videos()) + 1
                file_id = msg.video.file_id
                title = os.path.splitext(selected_file)[0]  # Remove extension
                
                self.db.add_video(
                    order=order,
                    file_id=file_id,
                    caption=f"ویدیو {title}",
                    title=title,
                    origin_chat_id=msg.chat_id,
                    origin_message_id=msg.message_id
                )
                
                await update.callback_query.answer("✅ ویدیو با موفقیت اضافه شد")
                return await self.v_list(update, context)
                
        except Exception as e:
            await update.callback_query.answer(f"❌ خطا در آپلود: {str(e)}")
            return ADD_V

    async def v_save(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Save video with optional caption"""
        if not update.message.video:
            await update.message.reply_text("لطفاً یک ویدیو ارسال کنید.")
            return ADD_V
            
        order = len(self.db.list_videos()) + 1
        file_id = update.message.video.file_id
        caption = update.message.caption or ""
        title = context.user_data.pop('video_title', f'ویدیو {order}')
        context.user_data.pop('adding_video', None)
        order = len(self.db.list_videos()) + 1
        origin_chat_id = update.message.chat.id
        origin_message_id = update.message.message_id
        self.db.add_video(order, file_id, caption, title, origin_chat_id, origin_message_id)
        await update.message.reply_text("✅ ویدیو ثبت شد")
        
        # Return to video list
        keyboard = []
        vs = self.db.list_videos()
        for v in vs:
            display = f"{v['video_order']}. {v.get('title', 'بدون نام')}"
            keyboard.append([InlineKeyboardButton(display, callback_data=f"alt_vsel_{v['id']}")])
        keyboard.append([InlineKeyboardButton("➕ ویدیو جدید", callback_data="alt_v_add")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])
        
        await update.message.reply_text(
            "🎥 *ویدیوهای آلت‌سیزن*:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return V_LIST

    async def v_edit_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt admin to send new caption for selected video"""
        v_id = int(update.callback_query.data.split('_')[-1])
        context.user_data['editing_v_id'] = v_id
        context.user_data['editing_v_caption'] = True
        await update.callback_query.edit_message_text("📝 کپشن جدید را وارد کنید:")
        return TEXT_INPUT

    async def v_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Delete selected video"""
        v_id = int(update.callback_query.data.split('_')[-1])
        self.db.delete_video(v_id)
        # Reorder remaining videos
        vids = self.db.list_videos()
        for idx, v in enumerate(vids, start=1):
            if v['video_order'] != idx:
                self.db.update_item_order(v['id'], 'video', idx)
        await update.callback_query.answer("🗑 حذف شد")
        return await self.v_list(update, context)

    async def v_select(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle selection of a specific video for editing"""
        v_id = int(update.callback_query.data.split('_')[-1])
        context.user_data['editing_v_id'] = v_id
        
        # Get video details
        vs = self.db.list_videos()
        v = next((x for x in vs if x['id'] == v_id), None)
        if not v:
            await update.callback_query.answer("ویدیو یافت نشد")
            return V_LIST
            
        keyboard = [
            [InlineKeyboardButton("✏️ ویرایش کپشن", callback_data=f"alt_v_edit_{v_id}")],
            [InlineKeyboardButton("▲ بالا بردن", callback_data=f"alt_v_up_{v_id}"), 
             InlineKeyboardButton("▼ پایین بردن", callback_data=f"alt_v_down_{v_id}")],
            [InlineKeyboardButton("🗑 حذف", callback_data=f"alt_v_del_{v_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="alt_v_list")],
        ]
        
        text = f"ویدیو شماره {v['video_order']}\nکپشن: {v['caption'] or 'بدون کپشن'}\n\nعملیات مورد نظر را انتخاب کنید:"
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return EDIT_V

    async def export_excel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        df = self.db.export_answers_dataframe()
        if df.empty:
            await update.callback_query.answer("داده‌ای یافت نشد")
            return MENU
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='AltSeason')
        buf.seek(0)
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=InputFile(buf, filename='altseason_report.xlsx'),
            caption="گزارش آلت‌سیزن"
        )
        await update.callback_query.answer()
        return MENU

    async def order_manage(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show unified order management interface"""
        items = self.db.get_all_items_ordered()
        if not items:
            await update.callback_query.edit_message_text(
                "هیچ سؤال یا ویدیویی یافت نشد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")]])
            )
            return ORDER_MANAGE
        
        keyboard = []
        for item in items:
            item_type_icon = "📝" if item['item_type'] == 'question' else "🎥"
            title = item.get('title', 'بدون نام')
            display_text = f"{item['item_order']}. {item_type_icon} {title}"
            
            row = [
                InlineKeyboardButton("▲", callback_data=f"alt_order_up_{item['item_type']}_{item['id']}"),
                InlineKeyboardButton(display_text, callback_data=f"alt_order_info_{item['item_type']}_{item['id']}"),
                InlineKeyboardButton("▼", callback_data=f"alt_order_down_{item['item_type']}_{item['id']}")
            ]
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])
        
        text = "🔄 *ترتیب نمایش کلی*\n\nبرای تغییر ترتیب از دکمه‌های ▲ و ▼ استفاده کنید:"
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ORDER_MANAGE
    
    async def keyboard_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show keyboard settings for completion message."""
        settings = self.db.get_all_keyboard_settings()
        
        # Create toggle buttons for each setting
        keyboard = []
        
        # Free package setting
        free_status = "✅" if settings.get('show_free_package') == '1' else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{free_status} 🎁 رایگان", 
                callback_data="alt_kb_toggle_free"
            )
        ])
        
        # Products menu setting
        products_status = "✅" if settings.get('show_products_menu') == '1' else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{products_status} 🛒 محصولات", 
                callback_data="alt_kb_toggle_products"
            )
        ])
        
        # Dynamically list active product sub-categories
        from database.models import Database as _DBModel
        db_tmp = _DBModel()
        subcategories = []
        if db_tmp.connect():
            try:
                cur = db_tmp.conn.cursor()
                cur.execute("""
                    SELECT id, name FROM categories
                    WHERE path LIKE '🛒 محصولات/%'
                    AND is_active = 1
                    ORDER BY display_order, name
                """)
                subcategories = cur.fetchall()
            finally:
                db_tmp.close()
        for cat_id, cat_name in subcategories:
            cat_key = f"show_category_{cat_id}"
            cat_status = "✅" if settings.get(cat_key, '1') == '1' else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{cat_status} {cat_name}",
                    callback_data=f"alt_kb_toggle_cat_{cat_id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])
        
        text = (
            "⌨️ *تنظیمات کیبورد پایان*\n\n"
            "برای فعال/غیرفعال کردن هر گزینه روی آن کلیک کنید:\n\n"
            "✅ = فعال\n"
            "❌ = غیرفعال"
        )
        
        await update.callback_query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return KEYBOARD_SETTINGS
    
    async def toggle_keyboard_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Toggle a keyboard setting."""
        callback_data = update.callback_query.data
        
        if callback_data == "alt_kb_toggle_free":
            setting_key = "show_free_package"
        elif callback_data == "alt_kb_toggle_products":
            setting_key = "show_products_menu"
        elif callback_data.startswith("alt_kb_toggle_cat_"):
            cat_id = callback_data.split("_")[-1]
            setting_key = f"show_category_{cat_id}"
        else:
            await update.callback_query.answer("خطا در تنظیمات")
            return KEYBOARD_SETTINGS
        
        # Get current value and toggle it
        current_value = self.db.get_keyboard_setting(setting_key)
        new_value = '0' if current_value == '1' else '1'
        
        # Update setting
        success = self.db.update_keyboard_setting(setting_key, new_value)
        
        if success:
            status_text = "فعال" if new_value == '1' else "غیرفعال"
            await update.callback_query.answer(f"تنظیمات به‌روزرسانی شد: {status_text}")
        else:
            await update.callback_query.answer("خطا در ذخیره‌سازی")
        
        # Refresh the settings menu
        return await self.keyboard_settings(update, context)
    
    async def handle_order_move(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle moving items up or down in global order"""
        data_parts = update.callback_query.data.split('_')
        direction = data_parts[2]  # 'up' or 'down'
        item_type = data_parts[3]  # 'question' or 'video'
        item_id = int(data_parts[4])
        
        items = self.db.get_all_items_ordered()
        current_item = next((item for item in items if item['id'] == item_id and item['item_type'] == item_type), None)
        
        if not current_item:
            await update.callback_query.answer("آیتم یافت نشد")
            return ORDER_MANAGE
        
        current_order = current_item['item_order']
        new_order = current_order - 1 if direction == 'up' else current_order + 1
        
        # Find item to swap with
        swap_item = next((item for item in items if item['item_order'] == new_order), None)
        
        if swap_item:
            # Swap orders
            self.db.update_item_order(current_item['id'], current_item['item_type'], new_order)
            self.db.update_item_order(swap_item['id'], swap_item['item_type'], current_order)
            await update.callback_query.answer("ترتیب تغییر یافت")
        else:
            await update.callback_query.answer("امکان جابجایی وجود ندارد")
        
        return await self.order_manage(update, context)

    async def _handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text input for both adding and editing questions"""
        if context.user_data.get('editing_q_id'):
            return await self.q_edit_save(update, context)
        else:
            return await self.q_save(update, context)

    def get_conv_handler(self):
        return ConversationHandler(
            entry_points=[CallbackQueryHandler(self.entry, pattern='^altseason_admin$')],
            states={
                MENU: [
                    CallbackQueryHandler(self.toggle, pattern='^alt_toggle$'),
                    CallbackQueryHandler(self.export, pattern='^alt_export$'),
                    CallbackQueryHandler(self.q_list, pattern='^alt_q_list$'),
                    CallbackQueryHandler(self.v_list, pattern='^alt_v_list$'),
                    CallbackQueryHandler(self.order_manage, pattern='^alt_order_manage$'),
                    CallbackQueryHandler(self.keyboard_settings, pattern='^alt_keyboard_settings$'),
                    CallbackQueryHandler(self._go_back, pattern='^admin_back_main$'),
                ],
                KEYBOARD_SETTINGS: [
                    CallbackQueryHandler(self.toggle_keyboard_setting, pattern='^alt_kb_toggle_'),
                    CallbackQueryHandler(self._go_back, pattern='^admin_back_main$'),
                ],
                Q_LIST: [
                    CallbackQueryHandler(self.q_add_prompt, pattern='^alt_q_add$'),
                    CallbackQueryHandler(self.q_select, pattern='^alt_qsel_'),
                    CallbackQueryHandler(self._go_back, pattern='^admin_back_main$'),
                ],
                TEXT_INPUT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_input),
                ],
                POLL_INPUT: [
                    MessageHandler(filters.POLL, self.q_save_poll),
                ],

                EDIT_Q: [
                    CallbackQueryHandler(self.q_edit_prompt, pattern='^alt_q_edit_'),
                    CallbackQueryHandler(self.q_move, pattern='^alt_q_up_|^alt_q_down_'),
                    CallbackQueryHandler(self.q_delete, pattern='^alt_q_del_'),
                    CallbackQueryHandler(self.q_list, pattern='^alt_q_list$'),
                    MessageHandler(filters.POLL, self.q_edit_save_poll),
                ],
                V_LIST: [
                    CallbackQueryHandler(self.v_add_prompt, pattern='^alt_v_add$'),
                    CallbackQueryHandler(self.v_select, pattern='^alt_vsel_'),
                    CallbackQueryHandler(self._go_back, pattern='^admin_back_main$'),
                ],
                ADD_V: [
                    CallbackQueryHandler(self.v_upload_prompt, pattern='^alt_v_upload$'),
                    CallbackQueryHandler(self.v_browse_files, pattern='^alt_v_browse$'),
                    CallbackQueryHandler(self.v_select_file, pattern='^alt_v_file_'),
                    CallbackQueryHandler(self.v_add_prompt, pattern='^alt_v_add$'),
                    CallbackQueryHandler(self.v_list, pattern='^alt_v_list$'),
                    MessageHandler(filters.VIDEO, self.v_save),
                ],
                EDIT_V: [
                    CallbackQueryHandler(self.v_edit_prompt, pattern='^alt_v_edit_'),
                    CallbackQueryHandler(self.v_delete, pattern='^alt_v_del_'),
                    CallbackQueryHandler(self.v_list, pattern='^alt_v_list$'),
                ],
                ORDER_MANAGE: [
                    CallbackQueryHandler(self.handle_order_move, pattern='^alt_order_up_|^alt_order_down_'),
                    CallbackQueryHandler(self._go_back, pattern='^admin_back_main$'),
                ],
                KEYBOARD_SETTINGS: [
                    CallbackQueryHandler(self.toggle_keyboard_setting, pattern='^alt_kb_toggle_'),
                    CallbackQueryHandler(self._go_back, pattern='^admin_back_main$'),
                ],
            },
            fallbacks=[CallbackQueryHandler(self._go_back, pattern='.*')],
            name="altseason_admin_conv",
            persistent=False,
        )
