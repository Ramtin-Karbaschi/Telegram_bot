"""
Survey management service for the Telegram bot
Handles survey creation, question management, and response collection
"""

import json
import logging
from typing import List, Dict, Optional, Any
from database.queries import DatabaseQueries
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

class SurveyService:
    """Service for managing surveys and their responses"""
    
    def __init__(self, db_queries: DatabaseQueries = None):
        """Initialize SurveyService with database queries instance"""
        self.db_queries = db_queries or DatabaseQueries()
    
    def create_plan_survey(self, plan_id: int, title: str, description: str = None) -> Optional[int]:
        """Create a new survey for a plan"""
        return self.db_queries.create_survey(plan_id, title, description)
    
    def add_survey_question(self, survey_id: int, question_text: str, question_type: str = 'text',
                    options: List[str] = None, is_required: bool = True, 
                    display_order: int = 0) -> Optional[int]:
        """Add a question to a survey"""
        options_json = json.dumps(options, ensure_ascii=False) if options else None
        return self.db_queries.add_survey_question(
            survey_id, question_text, question_type, options_json, is_required, display_order
        )
    
    def get_plan_survey(self, plan_id: int) -> Optional[Dict]:
        """Get the survey associated with a plan"""
        return self.db_queries.get_plan_survey(plan_id)
    
    def get_survey_questions(self, survey_id: int) -> List[Dict]:
        """Get all questions for a survey"""
        questions = self.db_queries.get_survey_questions(survey_id)
        
        # Parse options JSON for multiple choice questions
        for question in questions:
            if question['options']:
                try:
                    question['options'] = json.loads(question['options'])
                except json.JSONDecodeError:
                    question['options'] = []
            else:
                question['options'] = []
        
        return questions
    
    def save_survey_response(self, survey_id: int, question_id: int, user_id: int, response_text: str) -> bool:
        """Save a user's response to a survey question"""
        return self.db_queries.save_survey_response(user_id, survey_id, question_id, response_text)
    
    def mark_survey_completed(self, user_id: int, survey_id: int, plan_id: int = None) -> bool:
        """Mark a survey as completed by a user"""
        return self.db_queries.mark_survey_completed(user_id, survey_id, plan_id)
    
    def is_survey_completed(self, user_id: int, survey_id: int) -> bool:
        """Check if a user has completed a survey"""
        return self.db_queries.has_user_completed_survey(user_id, survey_id)
    
    def get_user_survey_responses(self, user_id: int, survey_id: int) -> List[Dict]:
        """Get all responses from a user for a survey"""
        return self.db_queries.get_user_survey_responses(user_id, survey_id)
    
    @staticmethod
    def create_question_keyboard(question: Dict, survey_id: int, question_index: int) -> InlineKeyboardMarkup:
        """Create inline keyboard for a survey question"""
        keyboard = []
        
        if question['question_type'] == 'multiple_choice' and question['options']:
            # Create buttons for each option
            for i, option in enumerate(question['options']):
                callback_data = f"survey_answer_{survey_id}_{question['id']}_{i}"
                keyboard.append([InlineKeyboardButton(option, callback_data=callback_data)])
        
        elif question['question_type'] == 'rating':
            # Create rating buttons (1-5 stars)
            rating_row = []
            for rating in range(1, 6):
                stars = "⭐" * rating
                callback_data = f"survey_answer_{survey_id}_{question['id']}_{rating}"
                rating_row.append(InlineKeyboardButton(stars, callback_data=callback_data))
            keyboard.append(rating_row)
        
        # Add skip button if question is not required
        if not question['is_required']:
            skip_callback = f"survey_skip_{survey_id}_{question['id']}"
            keyboard.append([InlineKeyboardButton("⏭️ رد کردن", callback_data=skip_callback)])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def format_question_text(question: Dict, question_index: int, total_questions: int) -> str:
        """Format question text with numbering and type indicators"""
        question_text = f"📋 سوال {question_index} از {total_questions}\n\n"
        question_text += f"❓ {question['question_text']}\n\n"
        
        if question['question_type'] == 'text':
            question_text += "💬 لطفاً پاسخ خود را تایپ کنید:"
        elif question['question_type'] == 'multiple_choice':
            question_text += "🔘 یکی از گزینه‌های زیر را انتخاب کنید:"
        elif question['question_type'] == 'rating':
            question_text += "⭐ امتیاز خود را انتخاب کنید (1 تا 5 ستاره):"
        
        if not question['is_required']:
            question_text += "\n\n💡 این سوال اختیاری است و می‌توانید آن را رد کنید."
        
        return question_text
    
    def create_default_survey_for_plan(self, plan_id: int, plan_name: str) -> Optional[int]:
        """Create a default survey for a video content plan"""
        survey_title = f"نظرسنجی پیش از دریافت محتوای {plan_name}"
        survey_description = "لطفاً قبل از دریافت ویدئوهای آموزشی، به سوالات زیر پاسخ دهید."
        
        survey_id = self.create_plan_survey(plan_id, survey_title, survey_description)
        if not survey_id:
            return None
        
        # Add default questions
        default_questions = [
            {
                "text": "سطح تجربه شما در این زمینه چگونه است؟",
                "type": "multiple_choice",
                "options": ["مبتدی", "متوسط", "پیشرفته", "حرفه‌ای"],
                "required": True,
                "order": 1
            },
            {
                "text": "انگیزه اصلی شما برای یادگیری این مطالب چیست؟",
                "type": "multiple_choice", 
                "options": ["توسعه شغلی", "علاقه شخصی", "پروژه خاص", "سایر"],
                "required": True,
                "order": 2
            },
            {
                "text": "چقدر زمان در هفته می‌توانید به یادگیری اختصاص دهید؟",
                "type": "multiple_choice",
                "options": ["کمتر از 2 ساعت", "2-5 ساعت", "5-10 ساعت", "بیشتر از 10 ساعت"],
                "required": True,
                "order": 3
            },
            {
                "text": "کیفیت محتوای آموزشی برای شما چقدر مهم است؟",
                "type": "rating",
                "options": None,
                "required": True,
                "order": 4
            },
            {
                "text": "آیا سوال یا نظر خاصی در مورد این دوره دارید؟",
                "type": "text",
                "options": None,
                "required": False,
                "order": 5
            }
        ]
        
        for question_data in default_questions:
            question_id = self.add_survey_question(
                survey_id=survey_id,
                question_text=question_data["text"],
                question_type=question_data["type"],
                options=question_data["options"],
                is_required=question_data["required"],
                display_order=question_data["order"]
            )
            
            if not question_id:
                logger.error(f"Failed to add question to survey {survey_id}")
        
        logger.info(f"Created default survey {survey_id} for plan {plan_id}")
        return survey_id
    
    def format_survey_questions_for_telegram(self, survey_id: int) -> str:
        """Format survey questions for display in Telegram"""
        questions = self.get_survey_questions(survey_id)
        if not questions:
            return "هیچ سوالی برای این نظرسنجی تعریف نشده است."
        
        text = "📋 سوالات نظرسنجی:\n\n"
        
        for i, question in enumerate(questions, 1):
            text += f"{i}. {question['question_text']}\n"
            text += f"   نوع: {question['question_type']}\n"
            
            if question['options']:
                text += "   گزینه‌ها:\n"
                for j, option in enumerate(question['options'], 1):
                    text += f"     {j}. {option}\n"
            
            text += f"   اجباری: {'بله' if question['is_required'] else 'خیر'}\n\n"
        
        return text
    
    @staticmethod
    def get_survey_progress(user_id: int, survey_id: int) -> Dict[str, Any]:
        """Get user's progress in a survey"""
        questions = SurveyService.get_survey_questions(survey_id)
        total_questions = len(questions)
        
        if total_questions == 0:
            return {
                'total_questions': 0,
                'answered_questions': 0,
                'progress_percentage': 100,
                'is_complete': True,
                'next_question': None
            }
        
        # Check which questions have been answered
        answered_count = 0
        next_question = None
        
        for i, question in enumerate(questions):
            # This would need to be implemented in DatabaseQueries
            # For now, we'll assume all questions need to be answered in sequence
            if next_question is None:
                next_question = {
                    'question': question,
                    'index': i + 1
                }
        
        progress_percentage = (answered_count / total_questions) * 100
        is_complete = answered_count == total_questions
        
        return {
            'total_questions': total_questions,
            'answered_questions': answered_count,
            'progress_percentage': progress_percentage,
            'is_complete': is_complete,
            'next_question': next_question
        }

# Global instance
survey_service = SurveyService()
