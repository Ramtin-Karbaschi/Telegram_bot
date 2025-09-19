"""
Admin handler for granting subscriptions to users
اعطای اشتراک دستی به کاربران توسط ادمین
"""

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, 
    CallbackQueryHandler, MessageHandler, filters
)
from telegram.constants import ParseMode
from database.queries import DatabaseQueries
from database.subscription_manager import SubscriptionManager
import jdatetime

logger = logging.getLogger(__name__)

# Conversation states
SELECT_PRODUCT, CONFIRM_GRANT = range(2)


class GrantSubscriptionHandler:
    """Handler for granting subscriptions to users by admin"""
    
    def __init__(self):
        self.db_queries = DatabaseQueries()
    
    async def start_grant_subscription(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ):
        """شروع فرایند اعطای اشتراک به کاربر"""
        query = update.callback_query
        await query.answer()
        
        # Extract user_id from callback data (grant_sub_123)
        try:
            user_id = int(query.data.split('_')[-1])
            context.user_data['grant_sub_user_id'] = user_id
        except (ValueError, IndexError):
            await query.edit_message_text("❌ خطا در شناسایی کاربر")
            return ConversationHandler.END
        
        # Get user info
        user_info = self.db_queries.get_user_details(user_id)
        if not user_info:
            await query.edit_message_text("❌ کاربر یافت نشد")
            return ConversationHandler.END
        
        user_name = user_info.get('full_name') or user_info.get('username') or f"ID: {user_id}"
        
        # Get all active products with categories
        products = self._get_products_by_category()
        
        if not products:
            await query.edit_message_text(
                "❌ هیچ محصول فعالی برای اعطا یافت نشد.\n"
                "لطفاً ابتدا محصولات را در بخش مدیریت محصولات تعریف کنید."
            )
            return ConversationHandler.END
        
        # Build product selection keyboard
        keyboard = []
        message_parts = [
            f"🎁 **اعطای اشتراک به کاربر**\n",
            f"👤 کاربر: {user_name}\n",
            f"🆔 آیدی: `{user_id}`\n",
            "━━━━━━━━━━━━━━━━━━━━━\n",
            "لطفاً محصول مورد نظر را انتخاب کنید:\n"
        ]
        
        for category_name, category_products in products.items():
            # Add category header
            message_parts.append(f"\n📁 **{category_name}:**")
            
            for product in category_products:
                plan_id = product['id']
                plan_name = product['name']
                duration = product.get('days', 0)
                
                # Create button text with duration
                button_text = f"📦 {plan_name} ({duration} روز)"
                callback_data = f"grant_plan_{plan_id}_{user_id}"
                
                # Check if callback_data is too long (max 64 bytes)
                if len(callback_data.encode()) > 64:
                    callback_data = f"gp_{plan_id}_{user_id}"
                
                keyboard.append([
                    InlineKeyboardButton(button_text, callback_data=callback_data)
                ])
                
                # Add to message
                message_parts.append(f"  • {plan_name}: {duration} روز")
        
        # Add cancel button
        keyboard.append([
            InlineKeyboardButton("❌ انصراف", callback_data="cancel_grant")
        ])
        
        await query.edit_message_text(
            "\n".join(message_parts),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return SELECT_PRODUCT
    
    async def select_product(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ):
        """انتخاب محصول برای اعطا"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "cancel_grant":
            await query.edit_message_text("❌ عملیات لغو شد")
            return ConversationHandler.END
        
        # Extract plan_id and user_id
        try:
            parts = query.data.split('_')
            if query.data.startswith('grant_plan_'):
                plan_id = int(parts[2])
                user_id = int(parts[3])
            else:  # gp_ format
                plan_id = int(parts[1])
                user_id = int(parts[2])
            
            context.user_data['grant_plan_id'] = plan_id
            context.user_data['grant_user_id'] = user_id
        except (ValueError, IndexError):
            await query.edit_message_text("❌ خطا در پردازش انتخاب")
            return ConversationHandler.END
        
        # Get plan details
        plan = self.db_queries.get_plan_by_id(plan_id)
        if not plan:
            await query.edit_message_text("❌ محصول یافت نشد")
            return ConversationHandler.END
        
        # Get user details
        user_info = self.db_queries.get_user_details(user_id)
        user_name = user_info.get('full_name') or user_info.get('username') or f"ID: {user_id}"
        
        # Check current subscription status for this category
        from database.subscription_manager import SubscriptionManager
        user_subs = SubscriptionManager.get_user_subscriptions_detailed(user_id)
        
        category_id = plan.get('category_id')
        current_days = 0
        
        if category_id and user_subs.get('by_category', {}).get(category_id):
            current_days = user_subs['by_category'][category_id].get('total_days', 0)
        
        # Build confirmation message
        message_parts = [
            "✅ **تأیید اعطای اشتراک**\n",
            "━━━━━━━━━━━━━━━━━━━━━\n",
            f"👤 **کاربر:** {user_name}\n",
            f"📦 **محصول:** {plan['name']}\n",
            f"⏱ **مدت زمان:** {plan.get('days', 0)} روز\n"
        ]
        
        if current_days > 0:
            message_parts.append(
                f"\n⚠️ **توجه:** این کاربر در حال حاضر {current_days} روز "
                f"اشتراک فعال در این دسته‌بندی دارد.\n"
                f"با اعطای این محصول، مدت زمان به اشتراک فعلی اضافه خواهد شد.\n"
                f"**مجموع جدید:** {current_days + plan.get('days', 0)} روز"
            )
        
        message_parts.append("\n\nآیا از اعطای این اشتراک اطمینان دارید؟")
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ بله، اعطا کن", callback_data="confirm_grant"),
                InlineKeyboardButton("❌ خیر، انصراف", callback_data="cancel_grant")
            ]
        ])
        
        await query.edit_message_text(
            "\n".join(message_parts),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
        return CONFIRM_GRANT
    
    async def confirm_grant(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ):
        """تأیید نهایی و اعطای اشتراک"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "cancel_grant":
            await query.edit_message_text("❌ عملیات لغو شد")
            return ConversationHandler.END
        
        # Get stored data
        user_id = context.user_data.get('grant_user_id')
        plan_id = context.user_data.get('grant_plan_id')
        admin_id = update.effective_user.id
        
        if not user_id or not plan_id:
            await query.edit_message_text("❌ خطا: اطلاعات ناقص")
            return ConversationHandler.END
        
        # Grant subscription using SubscriptionManager
        success, message = SubscriptionManager.create_or_extend_subscription(
            user_id=user_id,
            plan_id=plan_id,
            payment_method="admin_grant",
            amount_paid=0,
            admin_id=admin_id
        )
        
        if success:
            # Get plan and user details for report
            plan = self.db_queries.get_plan_by_id(plan_id)
            user_info = self.db_queries.get_user_details(user_id)
            user_name = user_info.get('full_name') or user_info.get('username') or f"ID: {user_id}"
            
            # Success message
            result_message = [
                "✅ **اشتراک با موفقیت اعطا شد**\n",
                "━━━━━━━━━━━━━━━━━━━━━\n",
                f"👤 کاربر: {user_name}\n",
                f"📦 محصول: {plan['name']}\n",
                f"⏱ مدت: {plan.get('days', 0)} روز\n",
                f"\n📝 {message}"
            ]
            
            # Send notification to user if possible
            try:
                # Get user's telegram_id (assuming user_id is the database ID)
                telegram_id = user_info.get('user_id')  # or appropriate field
                if telegram_id:
                    notification = (
                        "🎁 **اشتراک رایگان!**\n\n"
                        f"مدیر سیستم برای شما اشتراک «{plan['name']}» "
                        f"به مدت {plan.get('days', 0)} روز اعطا کرد.\n\n"
                        "از اشتراک خود لذت ببرید! 🎉"
                    )
                    await context.bot.send_message(
                        chat_id=telegram_id,
                        text=notification,
                        parse_mode=ParseMode.MARKDOWN
                    )
                    result_message.append("\n✅ پیام اطلاع‌رسانی به کاربر ارسال شد")
            except Exception as e:
                logger.warning(f"Could not send notification to user: {e}")
            
            await query.edit_message_text(
                "\n".join(result_message),
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Log admin action
            try:
                from utils.user_actions import UserAction
                UserAction.log_user_action(
                    telegram_id=admin_id,
                    action_type='grant_subscription',
                    details={
                        'target_user_id': user_id,
                        'plan_id': plan_id,
                        'plan_name': plan['name'],
                        'duration_days': plan.get('days', 0)
                    }
                )
            except:
                pass
            
        else:
            await query.edit_message_text(
                f"❌ **خطا در اعطای اشتراک**\n\n{message}",
                parse_mode=ParseMode.MARKDOWN
            )
        
        # Clear user data
        context.user_data.pop('grant_user_id', None)
        context.user_data.pop('grant_plan_id', None)
        
        return ConversationHandler.END
    
    def _get_products_by_category(self):
        """دریافت محصولات فعال به تفکیک دسته‌بندی"""
        try:
            # Get all active plans
            plans = self.db_queries.get_all_plans()
            if not plans:
                return {}
            
            # Group by category
            categorized = {}
            for plan in plans:
                if not plan.get('is_active', True):
                    continue
                
                # Get category name
                category_id = plan.get('category_id')
                if category_id:
                    category = self.db_queries.get_category_by_id(category_id)
                    category_name = category.get('name') if category else 'بدون دسته‌بندی'
                else:
                    category_name = 'بدون دسته‌بندی'
                
                if category_name not in categorized:
                    categorized[category_name] = []
                
                categorized[category_name].append(plan)
            
            return categorized
            
        except Exception as e:
            logger.error(f"Error getting categorized products: {e}")
            return {}
    
    def get_conversation_handler(self):
        """بازگرداندن ConversationHandler برای این قابلیت"""
        return ConversationHandler(
            entry_points=[
                CallbackQueryHandler(
                    self.start_grant_subscription, 
                    pattern=r'^grant_sub_\d+$'
                )
            ],
            states={
                SELECT_PRODUCT: [
                    CallbackQueryHandler(
                        self.select_product,
                        pattern=r'^(grant_plan_\d+_\d+|gp_\d+_\d+|cancel_grant)$'
                    )
                ],
                CONFIRM_GRANT: [
                    CallbackQueryHandler(
                        self.confirm_grant,
                        pattern=r'^(confirm_grant|cancel_grant)$'
                    )
                ]
            },
            fallbacks=[
                CallbackQueryHandler(
                    lambda u, c: ConversationHandler.END,
                    pattern='^cancel_grant$'
                )
            ],
            per_user=True,
            per_chat=True,
            allow_reentry=True
        )
