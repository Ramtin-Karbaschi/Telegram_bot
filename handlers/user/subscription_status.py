"""
User subscription status handler with detailed category-based view
نمایش وضعیت تفکیکی اشتراک‌های کاربر بر اساس دسته‌بندی
"""

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database.subscription_manager import SubscriptionManager
from database.queries import DatabaseQueries
import jdatetime

logger = logging.getLogger(__name__)


async def show_detailed_subscription_status(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """نمایش وضعیت تفکیکی اشتراک‌های کاربر"""
    
    user = update.effective_user
    telegram_id = user.id
    
    # Get user from database
    user_info = DatabaseQueries.get_user_by_telegram_id(telegram_id)
    if not user_info:
        await update.message.reply_text(
            "❌ ابتدا باید در ربات ثبت نام کنید.\n"
            "لطفاً از گزینه «📝 ثبت نام» استفاده کنید."
        )
        return
    
    user_db_id = user_info.get('user_id') if isinstance(user_info, dict) else user_info[0]
    
    # Get detailed subscription info
    sub_details = SubscriptionManager.get_user_subscriptions_detailed(user_db_id)
    
    # Build message
    message_parts = [
        "📊 <b>وضعیت تفکیکی اشتراک‌های شما</b>\n",
        "━━━━━━━━━━━━━━━━━━━━━"
    ]
    
    if not sub_details.get('by_product'):
        message_parts.append("\n❌ شما در حال حاضر اشتراک فعالی ندارید.")
    else:
        # Show by category (aggregated)
        if sub_details.get('by_category'):
            message_parts.append("\n<b>🗂 بر اساس دسته‌بندی:</b>\n")
            
            for cat_id, cat_info in sub_details['by_category'].items():
                cat_name = cat_info['category_name']
                total_days = cat_info['total_days']
                products_count = len(cat_info['products'])
                
                # Calculate end date
                if total_days > 0:
                    try:
                        end_date = datetime.now() + timedelta(days=total_days)
                        persian_date = jdatetime.datetime.fromgregorian(
                            datetime=end_date
                        ).strftime('%Y/%m/%d')
                    except:
                        persian_date = "نامشخص"
                    
                    status_emoji = "✅" if total_days > 7 else "⚠️"
                    
                    message_parts.append(
                        f"\n{status_emoji} <b>{cat_name}</b>\n"
                        f"   📦 تعداد محصولات: {products_count}\n"
                        f"   ⏱ مجموع روزهای باقی‌مانده: <b>{total_days} روز</b>\n"
                        f"   📅 انقضای نهایی: {persian_date}\n"
                    )
                else:
                    message_parts.append(
                        f"\n❌ <b>{cat_name}</b>\n"
                        f"   منقضی شده\n"
                    )
        
        # Show individual products
        message_parts.append("\n<b>📋 محصولات به تفکیک:</b>\n")
        
        for product in sub_details['by_product']:
            plan_name = product['plan_name']
            category = product['category']
            remaining_days = product['remaining_days']
            end_date_str = product['end_date']
            
            if remaining_days > 0:
                # Convert end date to Persian
                try:
                    end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                    persian_date = jdatetime.datetime.fromgregorian(
                        datetime=end_date
                    ).strftime('%Y/%m/%d')
                except:
                    persian_date = end_date_str[:10] if end_date_str else "نامشخص"
                
                status_icon = "🟢" if remaining_days > 30 else ("🟡" if remaining_days > 7 else "🔴")
                
                message_parts.append(
                    f"\n{status_icon} <b>{plan_name}</b>\n"
                    f"   📁 دسته: {category}\n"
                    f"   ⏱ باقی‌مانده: {remaining_days} روز\n"
                    f"   📅 انقضا: {persian_date}\n"
                )
            else:
                message_parts.append(
                    f"\n⚫ <s>{plan_name}</s> (منقضی شده)\n"
                    f"   📁 دسته: {category}\n"
                )
    
    # Add channel access info
    if sub_details.get('channels_access'):
        message_parts.append("\n<b>🔐 دسترسی به کانال‌ها:</b>")
        message_parts.append(f"شما به {len(sub_details['channels_access'])} کانال دسترسی دارید.")
    
    message_parts.append("\n━━━━━━━━━━━━━━━━━━━━━")
    
    # Add renewal buttons if needed
    keyboard = []
    
    has_expiring_soon = any(
        0 < prod.get('remaining_days', 0) <= 7 
        for prod in sub_details.get('by_product', [])
    )
    
    if has_expiring_soon or not sub_details.get('by_product'):
        keyboard.append([
            InlineKeyboardButton("🔄 تمدید اشتراک", callback_data="buy_subscription")
        ])
    
    keyboard.append([
        InlineKeyboardButton("📜 تاریخچه اشتراک‌ها", callback_data="subscription_history")
    ])
    
    keyboard.append([
        InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")
    ])
    
    # Send message
    await update.message.reply_text(
        "\n".join(message_parts),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )


async def show_subscription_history(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """نمایش تاریخچه تغییرات اشتراک کاربر"""
    
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    telegram_id = user.id
    
    # Get user from database
    user_info = DatabaseQueries.get_user_by_telegram_id(telegram_id)
    if not user_info:
        await query.edit_message_text("❌ کاربر یافت نشد.")
        return
    
    user_db_id = user_info.get('user_id') if isinstance(user_info, dict) else user_info[0]
    
    # Get history
    history = SubscriptionManager.get_subscription_history(user_db_id, limit=10)
    
    if not history:
        await query.edit_message_text(
            "📜 تاریخچه‌ای یافت نشد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data="show_subscription_status")
            ]])
        )
        return
    
    # Build history message
    message_parts = [
        "📜 <b>تاریخچه اشتراک‌های شما</b>\n",
        "━━━━━━━━━━━━━━━━━━━━━"
    ]
    
    for item in history[:10]:  # Show last 10 items
        action = item.get('action', 'unknown')
        plan_name = item.get('plan_name', 'نامشخص')
        created_at = item.get('created_at', '')
        days_added = item.get('days_added', 0)
        
        # Convert date to Persian
        try:
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            persian_date = jdatetime.datetime.fromgregorian(
                datetime=dt
            ).strftime('%Y/%m/%d %H:%M')
        except:
            persian_date = created_at[:16] if created_at else "نامشخص"
        
        # Action icons
        action_icons = {
            'created': '🆕',
            'extended': '🔄',
            'expired': '⏰',
            'cancelled': '❌'
        }
        icon = action_icons.get(action, '📝')
        
        # Action text in Persian
        action_text = {
            'created': 'ایجاد اشتراک',
            'extended': 'تمدید اشتراک',
            'expired': 'انقضای خودکار',
            'cancelled': 'لغو اشتراک'
        }.get(action, action)
        
        message_parts.append(
            f"\n{icon} <b>{action_text}</b>\n"
            f"   📦 محصول: {plan_name}\n"
        )
        
        if days_added > 0:
            message_parts.append(f"   ➕ روزهای اضافه شده: {days_added}\n")
        
        message_parts.append(f"   🕐 زمان: {persian_date}\n")
    
    message_parts.append("\n━━━━━━━━━━━━━━━━━━━━━")
    
    keyboard = [[
        InlineKeyboardButton("🔙 بازگشت", callback_data="show_subscription_status")
    ]]
    
    await query.edit_message_text(
        "\n".join(message_parts),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
