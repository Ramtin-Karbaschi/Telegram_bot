"""
User Survey Handlers
Handles survey presentation and response collection for regular users.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from database.queries import DatabaseQueries
from services.survey_service import SurveyService
from utils.helpers import safe_edit_message_text
import logging

logger = logging.getLogger(__name__)

# Conversation states
SURVEY_RESPONSE = 1  # Single conversation state

class UserSurveyHandler:
    def __init__(self):
        self.db_queries = DatabaseQueries()
        self.survey_service = SurveyService(self.db_queries)

    async def start_survey(self, update: Update, context: ContextTypes.DEFAULT_TYPE, plan_id: int):
        """Start a survey for a user before accessing plan content."""
        user_id = update.effective_user.id
        
        # Get survey for this plan
        survey = self.db_queries.get_plan_survey(plan_id)
        if not survey:
            # No survey required for this plan
            return ConversationHandler.END
        
        survey_id = survey['id']
        
        # Check if user has already completed this survey
        if self.db_queries.has_user_completed_survey(user_id, survey_id):
            return ConversationHandler.END
        
        # Get survey questions
        questions = self.db_queries.get_survey_questions(survey_id)
        if not questions:
            return ConversationHandler.END
        
        # Store survey data in context
        context.user_data['current_survey'] = {
            'survey_id': survey_id,
            'plan_id': plan_id,
            'questions': questions,
            'current_question': 0,
            'responses': {}
        }
        
        # Start with first question
        await self._show_current_question(update, context)
        return SURVEY_RESPONSE

    async def _show_current_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Display the current survey question."""
        survey_data = context.user_data.get('current_survey', {})
        questions = survey_data.get('questions', [])
        current_index = survey_data.get('current_question', 0)
        
        if current_index >= len(questions):
            # All questions answered, complete survey
            await self._complete_survey(update, context)
            return ConversationHandler.END
        
        question = questions[current_index]
        question_text = question['question_text']
        question_type = question['question_type']
        question_id = question['id']
        
        # Store current question ID
        context.user_data['current_survey']['current_question_id'] = question_id
        
        text = f"📋 **نظرسنجی** (سوال {current_index + 1} از {len(questions)})\n\n"
        text += f"❓ {question_text}\n\n"
        
        keyboard = []
        
        if question_type == 'multiple_choice':
            # Parse options - handle both string and list formats
            options_raw = question['options']
            if isinstance(options_raw, list):
                options = options_raw
            elif isinstance(options_raw, str) and options_raw:
                options = options_raw.split('|')
            else:
                options = []
            for i, option in enumerate(options):
                keyboard.append([InlineKeyboardButton(f"{i+1}. {option}", callback_data=f"survey_choice_{i}")])
        
        elif question_type == 'rating':
            # Rating 1-5 stars
            rating_row = []
            for i in range(1, 6):
                rating_row.append(InlineKeyboardButton(f"{i}⭐", callback_data=f"survey_rating_{i}"))
            keyboard.append(rating_row)
        
        # Skip button for non-required questions
        if not question['is_required']:
            keyboard.append([InlineKeyboardButton("⏭️ رد کردن", callback_data="survey_skip")])
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        if question_type == 'text':
            text += "💬 لطفاً پاسخ خود را تایپ کنید:"
        
        if update.callback_query:
            await safe_edit_message_text(update.callback_query, text=text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    async def handle_text_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text response from user."""
        survey_data = context.user_data.get('current_survey', {})
        current_question_id = survey_data.get('current_question_id')
        
        if not current_question_id:
            return ConversationHandler.END
        
        response_text = update.message.text
        
        # Save response
        await self._save_response(update, context, response_text)
        
        # Move to next question
        await self._next_question(update, context)
        return SURVEY_RESPONSE

    async def handle_choice_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle multiple choice response."""
        query = update.callback_query
        await query.answer()
        
        survey_data = context.user_data.get('current_survey', {})
        questions = survey_data.get('questions', [])
        current_index = survey_data.get('current_question', 0)
        
        if current_index >= len(questions):
            return ConversationHandler.END
        
        question = questions[current_index]
        options = question['options'].split('|') if question['options'] else []
        
        # Extract choice index from callback data
        choice_index = int(query.data.split('_')[-1])
        if choice_index < len(options):
            response_text = options[choice_index]
            await self._save_response(update, context, response_text)
        
        # Move to next question
        await self._next_question(update, context)
        return SURVEY_RESPONSE

    async def handle_rating_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle rating response."""
        query = update.callback_query
        await query.answer()
        
        # Extract rating from callback data
        rating = query.data.split('_')[-1]
        await self._save_response(update, context, rating)
        
        # Move to next question
        await self._next_question(update, context)
        return SURVEY_RESPONSE

    async def handle_skip_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle skip response for non-required questions."""
        query = update.callback_query
        await query.answer()
        
        # Move to next question without saving response
        await self._next_question(update, context)
        return SURVEY_RESPONSE

    async def _save_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE, response_text: str):
        """Save user response to database."""
        user_id = update.effective_user.id
        survey_data = context.user_data.get('current_survey', {})
        survey_id = survey_data.get('survey_id')
        current_question_id = survey_data.get('current_question_id')
        
        if survey_id and current_question_id:
            self.db_queries.save_survey_response(user_id, survey_id, current_question_id, response_text)
            
            # Store in context for summary
            responses = survey_data.get('responses', {})
            responses[current_question_id] = response_text
            context.user_data['current_survey']['responses'] = responses

    async def _next_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Move to the next question."""
        survey_data = context.user_data.get('current_survey', {})
        current_index = survey_data.get('current_question', 0)
        context.user_data['current_survey']['current_question'] = current_index + 1
        
        await self._show_current_question(update, context)

    async def _complete_survey(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Complete the survey and mark as finished."""
        user_id = update.effective_user.id
        survey_data = context.user_data.get('current_survey', {})
        survey_id = survey_data.get('survey_id')
        plan_id = survey_data.get('plan_id')
        
        if survey_id and plan_id:
            # Mark survey as completed
            self.db_queries.mark_survey_completed(user_id, survey_id, plan_id)
        
        # Prepare database access
        from database.queries import DatabaseQueries
        plan = DatabaseQueries.get_plan_by_id(plan_id)
        plan_name = plan['name'] if plan else 'پلن'

        # Determine whether the plan has videos
        plan_videos = DatabaseQueries.get_plan_videos(plan_id)
        has_videos = bool(plan_videos)

        # Initial acknowledgement
        ack_text = "✅ **نظرسنجی تکمیل شد!**\n\n" \
                   "🙏 از شرکت شما در نظرسنجی متشکریم."
        if has_videos:
            ack_text += "\n📹 در حال ارسال ویدئوهای پلن..."

        if update.callback_query:
            await safe_edit_message_text(update.callback_query, text=ack_text, parse_mode='Markdown')
        else:
            await update.message.reply_text(ack_text, parse_mode='Markdown')

        # Send content based on plan type
        if has_videos:
            # Attempt to send all videos
            from handlers.subscription.subscription_handlers import send_plan_videos
            await send_plan_videos(user_id, context, plan_id, plan_name)
            final_text = (
                f"🎉 **تمام ویدئوهای «{plan_name}» ارسال شد!**\n\n"
                "✨ از مشاهده محتوا لذت ببرید!\n"
                "💡 در صورت نیاز به راهنمایی، با پشتیبانی تماس بگیرید."
            )
            await context.bot.send_message(chat_id=user_id, text=final_text, parse_mode='Markdown')
        else:
            # اگر پلن ویدئو ندارد، فقط پیام تکمیل نمایش دهید (کانال یا محتوای دیگر قبلاً ارسال می‌شود)
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎉 دسترسی شما به «{plan_name}» فعال شد!\n\n"
                    "✨ از محتوای خود لذت ببرید!\n"
                    "💡 در صورت نیاز به راهنمایی، با پشتیبانی تماس بگیرید."
                ),
                parse_mode='Markdown'
            )
        
        # Clear survey data
        if 'current_survey' in context.user_data:
            del context.user_data['current_survey']

    async def cancel_survey(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the survey."""
        text = "❌ نظرسنجی لغو شد.\n\n"
        text += "💡 برای دسترسی به محتوای پلن، باید نظرسنجی را تکمیل کنید."
        
        if update.callback_query:
            await safe_edit_message_text(update.callback_query, text=text, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, parse_mode='Markdown')
        
        # Clear survey data
        if 'current_survey' in context.user_data:
            del context.user_data['current_survey']
        
        return ConversationHandler.END

    def get_survey_conversation_handler(self):
        """Get the conversation handler for surveys."""
        return ConversationHandler(
            entry_points=[],  # This will be called programmatically
            states={
                SURVEY_RESPONSE: [
                    CallbackQueryHandler(self.handle_choice_response, pattern='^survey_choice_'),
                    CallbackQueryHandler(self.handle_rating_response, pattern='^survey_rating_'),
                    CallbackQueryHandler(self.handle_skip_response, pattern='^survey_skip$'),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_response)
                ]
            },
            fallbacks=[CallbackQueryHandler(self.cancel_survey, pattern='^cancel_survey$')],
            per_user=True,
            per_chat=True
        )

    def get_survey_conversation_handler(self):
        """Get the conversation handler for surveys."""
        return ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self._start_survey_callback, pattern=r"^start_survey_\d+$")
            ],
            states={
                SURVEY_RESPONSE: [
                    CallbackQueryHandler(self._handle_survey_choice, pattern=r"^survey_choice_\d+$"),
                    CallbackQueryHandler(self._handle_survey_rating, pattern=r"^survey_rating_\d+$"),
                    CallbackQueryHandler(self._handle_survey_skip, pattern="^survey_skip$"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_text_response)
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self._cancel_survey, pattern="^cancel_survey$")
            ],
            per_chat=True,
            per_user=True
        )
    
    async def _start_survey_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle start_survey callback."""
        survey_id = int(update.callback_query.data.split('_')[-1])
        
        # Get plan_id from survey
        survey = self.db_queries.get_survey_by_id(survey_id)
        if not survey:
            await safe_edit_message_text(update.callback_query, text="❌ نظرسنجی یافت نشد.")
            return ConversationHandler.END
        
        plan_id = survey['plan_id']
        return await self.start_survey(update, context, plan_id)
    
    async def _handle_survey_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle multiple choice response."""
        choice_index = int(update.callback_query.data.split('_')[-1])
        survey_data = context.user_data.get('current_survey', {})
        questions = survey_data.get('questions', [])
        current_index = survey_data.get('current_question', 0)
        
        if current_index < len(questions):
            question = questions[current_index]
            # Parse options - handle both string and list formats
            options_raw = question['options']
            if isinstance(options_raw, list):
                options = options_raw
            elif isinstance(options_raw, str) and options_raw:
                options = options_raw.split('|')
            else:
                options = []
            if choice_index < len(options):
                response = options[choice_index]
                await self._save_response_and_continue(update, context, response)
        
        return SURVEY_RESPONSE
    
    async def _handle_survey_rating(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle rating response."""
        rating = int(update.callback_query.data.split('_')[-1])
        response = f"{rating} ستاره"
        await self._save_response_and_continue(update, context, response)
        return SURVEY_RESPONSE
    
    async def _handle_survey_skip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle skip response."""
        await self._save_response_and_continue(update, context, "رد شد")
        return SURVEY_RESPONSE
    
    async def _handle_text_response(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text response."""
        response = update.message.text
        await self._save_response_and_continue(update, context, response)
        return SURVEY_RESPONSE
    
    async def _save_response_and_continue(self, update: Update, context: ContextTypes.DEFAULT_TYPE, response: str):
        """Save response and move to next question."""
        survey_data = context.user_data.get('current_survey', {})
        survey_id = survey_data.get('survey_id')
        question_id = survey_data.get('current_question_id')
        user_id = update.effective_user.id
        
        # Save response
        self.db_queries.save_survey_response(user_id, survey_id, question_id, response)
        
        # Move to next question
        survey_data['current_question'] += 1
        context.user_data['current_survey'] = survey_data
        
        # Show next question or complete
        await self._show_current_question(update, context)
    
    async def _cancel_survey(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel survey."""
        await safe_edit_message_text(update.callback_query, text="❌ نظرسنجی لغو شد.")
        context.user_data.pop('current_survey', None)
        return ConversationHandler.END

# Global instance
user_survey_handler = UserSurveyHandler()
