"""
Video Access Handlers
Handles video content access with survey pre-conditions.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from database.queries import DatabaseQueries
from services.video_service import video_service
from handlers.user_survey_handlers import user_survey_handler
from utils.helpers import safe_edit_message_text
import logging
import os

logger = logging.getLogger(__name__)

class VideoAccessHandler:
    def __init__(self):
        self.db_queries = DatabaseQueries()
    
    def _has_active_subscription(self, user_id: int, plan_id: int) -> bool:
        """Check if user has active subscription for the plan."""
        try:
            # Get user's subscription summary
            user_summary = self.db_queries.get_user_subscription_summary(user_id)
            if not user_summary:
                return False
            
            # Check if subscription is still active
            expiration_str = user_summary.get('subscription_expiration_date')
            if not expiration_str:
                return False
            
            from datetime import datetime
            expiration_date = datetime.fromisoformat(expiration_str)
            now = datetime.now()
            
            # Check if subscription is still valid
            if expiration_date <= now:
                return False
            
            # Check if user has subscription for this specific plan
            subscriptions = self.db_queries.get_user_subscriptions(user_id)
            for sub in subscriptions:
                if sub['plan_id'] == plan_id and sub['status'] == 'active':
                    return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking subscription for user {user_id}, plan {plan_id}: {e}")
            return False

    async def handle_plan_access(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle user request to access plan content."""
        query = update.callback_query
        await query.answer()
        
        # Extract plan_id from callback data
        plan_id = int(query.data.split('_')[-1])
        user_id = update.effective_user.id
        
        # Check if user has active subscription for this plan
        if not self._has_active_subscription(user_id, plan_id):
            await safe_edit_message_text(
                query,
                "❌ شما اشتراک فعال برای این پلن ندارید.\n\n"
                "💡 ابتدا پلن را خریداری کنید.",
                parse_mode='Markdown'
            )
            return
        
        # Check if plan requires survey completion
        survey = self.db_queries.get_plan_survey(plan_id)
        if survey:
            survey_id = survey['id']
            
            # Check if user has completed the survey
            if not self.db_queries.has_user_completed_survey(user_id, survey_id):
                # Start survey
                await safe_edit_message_text(
                    query,
                    "📋 **نظرسنجی مورد نیاز**\n\n"
                    "🔒 برای دسترسی به محتوای این پلن، ابتدا باید نظرسنجی را تکمیل کنید.\n\n"
                    "⏱️ زمان تکمیل: حدود 2-3 دقیقه",
                    parse_mode='Markdown'
                )
                
                # Start survey conversation
                return await user_survey_handler.start_survey(update, context, plan_id)
        
        # Survey completed or not required, show plan content
        await self._show_plan_content(update, context, plan_id)

    async def _show_plan_content(self, update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: int):
        """Show plan content (videos) to user."""
        # Get plan details
        plan = self.db_queries.get_plan_by_id(plan_id)
        if not plan:
            await safe_edit_message_text(update.callback_query, "❌ پلن یافت نشد.")
            return
        
        # Get videos for this plan
        videos = self.db_queries.get_plan_videos(plan_id)
        
        if not videos:
            await safe_edit_message_text(
                update.callback_query,
                f"📦 **{plan['name']}**\n\n"
                "📹 هنوز ویدئویی برای این پلن اضافه نشده است.\n\n"
                "⏳ لطفاً بعداً مراجعه کنید.",
                parse_mode='Markdown'
            )
            return
        
        # Show video list
        text = f"🎬 **{plan['name']}**\n\n"
        text += f"📝 {plan['description']}\n\n"
        text += f"📹 **ویدئوهای موجود:** ({len(videos)} ویدئو)\n\n"
        
        keyboard = []
        for i, video in enumerate(videos, 1):
            video_title = video['display_name'] or f"ویدئو {i}"
            keyboard.append([InlineKeyboardButton(
                f"▶️ {video_title}", 
                callback_data=f"play_video_{video['id']}"
            )])
        
        # Add back button
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_plans")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_edit_message_text(
            update.callback_query,
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def handle_video_play(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle video play request."""
        query = update.callback_query
        await query.answer()
        
        # Extract video_id from callback data
        video_id = int(query.data.split('_')[-1])
        user_id = update.effective_user.id
        
        # Get video details
        video = self.db_queries.get_video_by_id(video_id)
        if not video:
            await safe_edit_message_text(query, "❌ ویدئو یافت نشد.")
            return
        
        # Check if user has access to this video's plan
        plan_videos = self.db_queries.get_video_plans(video_id)
        has_access = False
        
        for plan_video in plan_videos:
            plan_id = plan_video['plan_id']
            if self._has_active_subscription(user_id, plan_id):
                # Check survey completion if required
                survey = self.db_queries.get_plan_survey(plan_id)
                if survey:
                    survey_id = survey['id']
                    if not self.db_queries.has_user_completed_survey(user_id, survey_id):
                        continue  # Survey not completed for this plan
                has_access = True
                break
        
        if not has_access:
            await safe_edit_message_text(
                query,
                "❌ شما دسترسی به این ویدئو ندارید.\n\n"
                "💡 ابتدا پلن مربوطه را خریداری کرده و نظرسنجی را تکمیل کنید.",
                parse_mode='Markdown'
            )
            return
        
        # Send video to user
        try:
            video_path = video_service.get_video_path(video['filename'])
            
            if not os.path.exists(video_path):
                await safe_edit_message_text(
                    query,
                    "❌ فایل ویدئو یافت نشد.\n\n"
                    "🔧 لطفاً با پشتیبانی تماس بگیرید.",
                    parse_mode='Markdown'
                )
                return
            
            # Send video file
            caption = f"🎦 **{video['display_name'] or 'ویدئو'}**\n\n"
            caption += "✅ از طریق ربات دارایی آکادمی"
            
            await safe_edit_message_text(query, "📤 در حال ارسال ویدئو...")
            
            with open(video_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=video_file,
                    caption=caption,
                    parse_mode='Markdown'
                )
            
            # Update message to show success
            keyboard = [[InlineKeyboardButton("🔙 بازگشت به لیست", callback_data=f"access_plan_{plan_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await safe_edit_message_text(
                query,
                "✅ ویدئو با موفقیت ارسال شد!",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error sending video {video_id}: {e}")
            await safe_edit_message_text(
                query,
                "❌ خطا در ارسال ویدئو.\n\n"
                "🔧 لطفاً بعداً تلاش کنید یا با پشتیبانی تماس بگیرید.",
                parse_mode='Markdown'
            )

    def _has_active_subscription(self, user_id: int, plan_id: int) -> bool:
        """Check if user has active subscription for plan."""
        # Get user's active subscriptions
        subscriptions = self.db_queries.get_user_active_subscriptions(user_id)
        return any(sub['plan_id'] == plan_id for sub in subscriptions)

    def get_callback_handlers(self):
        """Get callback handlers for video access."""
        return [
            CallbackQueryHandler(self.handle_plan_access, pattern='^access_plan_'),
            CallbackQueryHandler(self.handle_video_play, pattern='^play_video_'),
        ]

    def get_callback_handlers(self):
        """Get all callback handlers for video access."""
        return [
            CallbackQueryHandler(self.handle_plan_access, pattern=r"^access_plan_\d+$"),
            CallbackQueryHandler(self._handle_play_video, pattern=r"^play_video_\d+$"),
            CallbackQueryHandler(self._handle_send_all_videos, pattern=r"^send_all_videos_\d+$")
        ]
    
    async def _handle_play_video(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle individual video play request."""
        query = update.callback_query
        await query.answer()
        
        video_id = int(query.data.split('_')[-1])
        user_id = update.effective_user.id
        
        # Get video details
        video = self.db_queries.get_video_by_id(video_id)
        if not video:
            await safe_edit_message_text(query, "❌ ویدیو یافت نشد.")
            return
        
        # Send the video using video service
        try:
            await video_service.send_video_to_user(context.bot, user_id, video)
            await query.answer("✅ ویدیو ارسال شد!", show_alert=True)
        except Exception as e:
            logger.error(f"Error sending video {video_id} to user {user_id}: {e}")
            await query.answer("⚠️ خطا در ارسال ویدیو", show_alert=True)
    
    async def _handle_send_all_videos(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle send all videos request."""
        query = update.callback_query
        await query.answer()
        
        plan_id = int(query.data.split('_')[-1])
        user_id = update.effective_user.id
        
        # Get plan details
        plan = self.db_queries.get_plan_by_id(plan_id)
        if not plan:
            await safe_edit_message_text(query, "❌ پلن یافت نشد.")
            return
        
        # Send all videos
        try:
            success = await video_service.send_plan_videos(context.bot, user_id, plan_id)
            if success:
                await safe_edit_message_text(query, f"✅ تمام ویدیوهای «{plan['name']}» با موفقیت ارسال شد.")
            else:
                await safe_edit_message_text(query, "⚠️ خطا در ارسال ویدیوها")
        except Exception as e:
            logger.error(f"Error sending all videos for plan {plan_id} to user {user_id}: {e}")
            await safe_edit_message_text(query, "⚠️ خطا در ارسال ویدیوها")

# Global instance
video_access_handler = VideoAccessHandler()
