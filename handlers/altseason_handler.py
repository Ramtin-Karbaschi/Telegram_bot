"""User-facing AltSeason flow handler."""

import logging
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackContext, ContextTypes, ConversationHandler, CommandHandler, MessageHandler,
    CallbackQueryHandler, PollAnswerHandler, filters
)

from database.altseason_queries import AltSeasonQueries
from utils.constants.all_constants import TEXT_MAIN_MENU_ALTSEASON

logger = logging.getLogger(__name__)

ALTSEASON_Q = 1  # Conversation state placeholder (we'll keep single state)


class AltSeasonHandler:
    """Handles the AltSeason interactive flow for users."""

    def __init__(self):
        self.db = AltSeasonQueries()

    # ---------------- Conversation flow ----------------
    async def start_flow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Entry point when user presses the AltSeason button."""
        user = update.effective_user
        if not user:
            return ConversationHandler.END
        
        # Handle both message and callback_query
        if update.callback_query:
            await update.callback_query.answer()
            reply_method = update.callback_query.message.reply_text
        else:
            reply_method = update.message.reply_text
            
        # Get all items (questions and videos) in unified order
        all_items = self.db.get_all_items_ordered()
        if not all_items:
            await reply_method("در حال حاضر محتوایی برای بخش آلت‌سیزن تعریف نشده است.")
            return ConversationHandler.END
        
        # Separate questions and videos while maintaining order
        questions = [item for item in all_items if item['item_type'] == 'question']
        videos = [item for item in all_items if item['item_type'] == 'video']
        if not questions:
            await reply_method("در حال حاضر محتوایی برای بخش آلت‌سیزن تعریف نشده است.")
            return ConversationHandler.END
        # Save into user_data with unified flow
        context.user_data['altseason_all_items'] = all_items
        context.user_data['altseason_questions'] = questions
        context.user_data['altseason_videos'] = videos
        context.user_data['altseason_current_idx'] = 0
        context.user_data['altseason_active'] = True
        # ensure user in db
        self.db.ensure_user(user.id, user.first_name, user.last_name)
        # Persist chat_id for later use (poll_answer updates lack chat context)
        chat_id_val = update.effective_chat.id if update.effective_chat else user.id
        context.user_data['altseason_chat_id'] = chat_id_val
        # Send first item (question or video) based on unified order
        result = await self._send_current_item(update, context)
        return result if result is not None else ALTSEASON_Q

    async def _send_current_item(self, update: Update | None, context: ContextTypes.DEFAULT_TYPE):
        """Send current item (question or video) based on unified order
        `update` may be None (e.g., when called from PollAnswer update)."""
        idx = context.user_data.get('altseason_current_idx', 0)
        all_items = context.user_data.get('altseason_all_items', [])
        chat_id_val = None
        if update and update.effective_chat:
            chat_id_val = update.effective_chat.id
        else:
            chat_id_val = context.user_data.get('altseason_chat_id')
        if chat_id_val is None:
            logger.warning("AltSeason: chat_id missing, cannot send next item")
            return
        
        if idx >= len(all_items):
            # flow finished
            await self._send_completion_message(context, chat_id_val)
            context.user_data.pop('altseason_active', None)
            return ConversationHandler.END
        
        current_item = all_items[idx]
        
        if current_item['item_type'] == 'question':
            await self._send_question(context, chat_id_val, current_item)
        elif current_item['item_type'] == 'video':
            success = await self._send_video(context, chat_id_val, current_item)
            if success:
                # Video sent successfully, advance index and continue to next item
                context.user_data['altseason_current_idx'] = idx + 1
                # Check if there are more items after this video
                if context.user_data['altseason_current_idx'] >= len(all_items):
                    # This was the last item, finish the flow
                    await self._send_completion_message(context, chat_id_val)
                    context.user_data.pop('altseason_active', None)
                    return ConversationHandler.END
                # Continue to next item automatically
                return await self._send_current_item(None, context)
            else:
                # If video failed, skip to next item
                context.user_data['altseason_current_idx'] = idx + 1
                return await self._send_current_item(None, context)
    
    async def _send_question(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, question):
        """Send a specific question to given chat_id"""
        # Try to reconstruct poll from stored data first
        poll_data_json = question.get('poll_data')
        if poll_data_json:
            try:
                import json
                poll_data = json.loads(poll_data_json)
                await context.bot.send_poll(
                    chat_id=chat_id,
                    question=poll_data['question'],
                    options=poll_data['options'],
                    is_anonymous=poll_data.get('is_anonymous', False),
                    allows_multiple_answers=poll_data.get('allows_multiple_answers', False)
                )
                return
            except Exception as e:
                logger.warning(f"Failed to send poll from stored data: {e}")
        
        # Always send a fresh poll to capture PollAnswer updates reliably
        await context.bot.send_poll(
            chat_id=chat_id,
            question=question.get('title') or poll_data.get('question', 'سؤال') if 'poll_data' in locals() else 'سؤال',
            options=poll_data.get('options', ['گزینه ۱', 'گزینه ۲']) if 'poll_data' in locals() else ['گزینه ۱', 'گزینه ۲'],
            is_anonymous=False,
            allows_multiple_answers=poll_data.get('allows_multiple_answers', False) if 'poll_data' in locals() else False
        )
    
    async def _send_video(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, video):
        """Send a specific video to given chat_id.
        Prefer copy_message for speed; fallback to send_video with file_id."""
        origin_chat_id = video.get('origin_chat_id')
        origin_message_id = video.get('origin_message_id')
        # Try copy_message first if origin info exists
        if origin_chat_id and origin_message_id:
            try:
                msg = await context.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=origin_chat_id,
                    message_id=origin_message_id,
                )
                # Ensure we cache the file_id even when using copy_message
                if getattr(msg, 'video', None) or getattr(msg, 'document', None):
                    self.db.update_video_sent(
                        v_id=video.get('id'),
                        file_id=msg.video.file_id,
                        origin_chat_id=msg.chat_id,
                        origin_message_id=msg.message_id,
                    )
                return True
            except Exception as e:
                logger.warning(f"AltSeason: copy_message failed ({e}), fallback to send_video")
        # Determine if we have a saved telegram_file_id; if missing go straight to local upload
        telegram_file_id = video.get('telegram_file_id')
        if not telegram_file_id:
            logger.info("AltSeason: no telegram_file_id stored, trying local file upload")
            return await self._try_local_video_upload(context, chat_id, video)

        # Fallback to send_video with saved file_id
        try:
            try:
                msg = await context.bot.send_video(
                    chat_id=chat_id,
                    video=video['telegram_file_id'],
                    caption=video.get('caption') or ''
                )
            except Exception as e_vid:
                logger.warning(f"AltSeason: send_video failed ({e_vid}), trying send_document")
                msg = await context.bot.send_document(
                    chat_id=chat_id,
                    document=video['telegram_file_id'],
                    caption=video.get('caption') or ''
                )
            # Cache new file_id & origin so next time copy_message works faster
            self.db.update_video_sent(
                v_id=video.get('id'),
                file_id=(msg.video.file_id if getattr(msg, 'video', None) else msg.document.file_id if getattr(msg, 'document', None) else video['telegram_file_id']),
                origin_chat_id=msg.chat_id,
                origin_message_id=msg.message_id,
            )
        except Exception as e:
            logger.error(f"AltSeason: failed to send video via file_id ({e}); trying local file fallback")
            # Try to find and upload from local files as last resort
            success = await self._try_local_video_upload(context, chat_id, video)
            if success:
                return True
            logger.error(f"AltSeason: all methods failed for video id {video.get('id')}; skipping")
            return False  # signal failure
        return True
    
    async def _try_local_video_upload(self, context, chat_id: int, video):
        """Try to upload video from local files as last resort"""
        import os
        from pathlib import Path
        project_root = Path(__file__).resolve().parents[2]
        videos_dir = project_root / "database" / "data" / "videos"
        
        if not videos_dir.exists():
            return False
            
        # Look for video files that might match
        video_files = [f.name for f in videos_dir.iterdir() if f.suffix.lower() in {'.mp4','.mov','.avi','.mkv'}]
        
        # Try each file (simple fallback - could be improved with better matching)
        for filename in video_files:
            try:
                file_path = videos_dir / filename
                with open(file_path, 'rb') as video_file:
                    msg = await context.bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        caption=video.get('caption') or f"ویدیو {video.get('title', '')}"
                    )
                    
                    # Update DB with new valid file_id and origin info
                    self.db.update_video_sent(
                        v_id=video.get('id'),
                        file_id=msg.video.file_id,
                        origin_chat_id=msg.chat_id,
                        origin_message_id=msg.message_id,
                    )
                    
                    logger.info(f"AltSeason: successfully uploaded video from local file {filename}")
                    return True
                    
            except Exception as e:
                logger.warning(f"AltSeason: failed to upload local file {filename}: {e}")
                continue
                
        return False

    async def poll_answer_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user's poll answers during AltSeason flow."""
        if not context.user_data.get('altseason_active'):
            return
        
        user_id = update.poll_answer.user.id
        current_idx = context.user_data.get('altseason_current_idx', 0)
        all_items = context.user_data.get('altseason_all_items', [])
        
        if current_idx >= len(all_items):
            return
        
        current_item = all_items[current_idx]
        
        # Only process if current item is a question
        if current_item['item_type'] == 'question':
            question_id = current_item['id']
            option_ids = update.poll_answer.option_ids
            if option_ids:
                self.db.save_answer(user_id, question_id, option_ids[0])
        
        # Move to next item
        context.user_data['altseason_current_idx'] = current_idx + 1
        
        # Send next item or finish
        result = await self._send_current_item(update, context)
        return result if result is not None else ALTSEASON_Q

    async def _send_completion_message(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        """Send completion message with configurable keyboard."""
        keyboard = await self._create_completion_keyboard()
        
        message = "با تشکر از شما! 🎉"
        if keyboard:
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=chat_id, 
                text=message, 
                reply_markup=reply_markup
            )
        else:
            await context.bot.send_message(chat_id=chat_id, text=message)
    
    async def _create_completion_keyboard(self):
        """Create completion keyboard based on admin settings."""
        from telegram import InlineKeyboardButton
        
        # Get keyboard settings
        settings = self.db.get_all_keyboard_settings()
        
        keyboard = []
        
        # Add free package button if enabled
        if settings.get('show_free_package') == '1':
            keyboard.append([
                InlineKeyboardButton("🎁 رایگان", callback_data="free_package_menu")
            ])
        
        # Get product subcategories and check which ones are enabled
        from database.models import Database
        db = Database()
        if db.connect():
            try:
                cur = db.conn.cursor()
                # Fetch all active sub-categories under "🛒 VIP"
                cur.execute(
                    """
                    SELECT id, name FROM categories
                    WHERE path LIKE '🛒 محصولات/%'
                    AND is_active = 1
                    ORDER BY display_order, name
                    """
                )
                subcategories = [(row[0], row[1]) for row in cur.fetchall()]

                # Filter enabled subcategories
                enabled_subcats = [
                    (cid, cname) for cid, cname in subcategories
                    if settings.get(f"show_category_{cid}", '1') == '1'
                ]
                
                # Add main products button if enabled OR if there are enabled subcategories
                show_main_products = settings.get('show_products_menu') == '1'
                if show_main_products or enabled_subcats:
                    if show_main_products:
                        keyboard.append([
                            InlineKeyboardButton("🛒 VIP", callback_data="products_menu")
                        ])
                    
                    # Add enabled subcategory buttons (max 2 per row)
                    for i in range(0, len(enabled_subcats), 2):
                        row = []
                        for cid, cname in enabled_subcats[i:i + 2]:
                            row.append(
                                InlineKeyboardButton(cname, callback_data=f"products_menu_{cid}")
                            )
                        keyboard.append(row)
                        
            except Exception as e:
                logger.error(f"Error getting product categories: {e}")
                # Fallback: show main products button if enabled
                if settings.get('show_products_menu') == '1':
                    keyboard.append([
                        InlineKeyboardButton("🛒 VIP", callback_data="products_menu")
                    ])
            finally:
                db.close()
        
        return keyboard

    # ---------------- conversation helpers ----------------
    def get_handlers(self):
        """Return list of handlers: conversation + global PollAnswerHandler."""
        conv = self._build_conv_handler()
        return [conv, PollAnswerHandler(self.poll_answer_handler)]

    # Backward-compat: keep original method name if other modules use it
    def get_conv_handler(self):
        return self._build_conv_handler()

    def _build_conv_handler(self):
        return ConversationHandler(
            entry_points=[
                MessageHandler(filters.TEXT & filters.Regex(r'آلت.*سیزن'), self.start_flow),
                CallbackQueryHandler(self.start_flow, pattern='^altseason_flow$')
            ],
            states={
                ALTSEASON_Q: [
                    MessageHandler(filters.TEXT & filters.Regex(r'آلت.*سیزن'), self.start_flow),
                ],
            },
            fallbacks=[MessageHandler(filters.ALL, self._fallback)],
            name="altseason_conv",
            per_chat=False,
            per_user=True,
            per_message=False,
            persistent=False,
        )

    async def _fallback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # If user sends AltSeason button again, restart the flow
        if update.message and update.message.text and 'آلت' in update.message.text and 'سیزن' in update.message.text:
            return await self.start_flow(update, context)
        # For other messages, end conversation
        return ConversationHandler.END
