"""
Channel Access Validator Task
بررسی دوره‌ای دسترسی کاربران به کانال‌ها بر اساس اشتراک‌های محصول-محور
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Set
from database.subscription_manager import SubscriptionManager
from database.queries import DatabaseQueries
from database.models import Database
import json

logger = logging.getLogger(__name__)


class ChannelAccessValidator:
    """
    مدیریت دسترسی به کانال‌ها بر اساس اشتراک‌های محصول-محور
    هر کاربر ممکن است برای کانال‌های مختلف زمان‌های متفاوتی داشته باشد
    """
    
    @staticmethod
    async def validate_channel_memberships(bot, context=None):
        """
        بررسی و به‌روزرسانی دسترسی کاربران به کانال‌ها
        بر اساس اشتراک‌های فعال هر محصول
        """
        logger.info("Starting channel access validation based on product subscriptions...")
        
        # Get all configured channels
        import config
        channels = config.TELEGRAM_CHANNELS_INFO if hasattr(config, 'TELEGRAM_CHANNELS_INFO') else []
        
        if not channels:
            logger.warning("No channels configured for validation")
            return
        
        stats = {
            'channels_checked': 0,
            'users_kicked': 0,
            'users_retained': 0,
            'errors': 0
        }
        
        for channel_info in channels:
            channel_id = channel_info.get('id')
            channel_title = channel_info.get('title', f'Channel {channel_id}')
            
            if not channel_id:
                continue
            
            stats['channels_checked'] += 1
            logger.info(f"Checking channel: {channel_title} ({channel_id})")
            
            # Check if kick is enabled for this channel
            kick_enabled = DatabaseQueries.is_kick_enabled_for_channel(channel_id)
            if not kick_enabled:
                logger.info(f"Kick disabled for channel {channel_title}, skipping...")
                continue
            
            # Get all channel members
            try:
                members = await ChannelAccessValidator._get_channel_members(bot, channel_id)
                logger.info(f"Found {len(members)} members in channel {channel_title}")
            except Exception as e:
                logger.error(f"Error getting members for channel {channel_id}: {e}")
                stats['errors'] += 1
                continue
            
            # Check each member's access to THIS specific channel
            for member_id in members:
                # Skip bot itself and admins
                if member_id == bot.id:
                    continue
                
                try:
                    # Check if user is admin
                    member = await bot.get_chat_member(channel_id, member_id)
                    if member.status in ['administrator', 'creator']:
                        continue
                    
                    # Check if user has access through any active subscription
                    has_access = ChannelAccessValidator._user_has_channel_access(
                        member_id, channel_id
                    )
                    
                    if not has_access:
                        # User doesn't have valid subscription for this channel
                        logger.info(f"User {member_id} has no valid subscription for channel {channel_title}")
                        
                        # Kick user from channel
                        try:
                            await bot.ban_chat_member(chat_id=channel_id, user_id=member_id)
                            await asyncio.sleep(1)  # Brief delay
                            await bot.unban_chat_member(chat_id=channel_id, user_id=member_id)
                            
                            stats['users_kicked'] += 1
                            logger.info(f"Kicked user {member_id} from channel {channel_title}")
                            
                            # Send notification to user
                            try:
                                notification = (
                                    f"⏰ **اشتراک شما برای کانال {channel_title} به پایان رسید**\n\n"
                                    "دسترسی شما به این کانال قطع شد.\n"
                                    "برای تمدید، لطفاً از ربات اصلی استفاده کنید."
                                )
                                await bot.send_message(
                                    chat_id=member_id,
                                    text=notification,
                                    parse_mode='Markdown'
                                )
                            except:
                                pass  # User may have blocked bot
                                
                        except Exception as e:
                            logger.error(f"Error kicking user {member_id} from channel {channel_id}: {e}")
                            stats['errors'] += 1
                    else:
                        stats['users_retained'] += 1
                        
                except Exception as e:
                    logger.error(f"Error processing member {member_id} in channel {channel_id}: {e}")
                    stats['errors'] += 1
        
        # Log statistics
        logger.info(
            f"Channel validation completed: "
            f"Channels: {stats['channels_checked']}, "
            f"Kicked: {stats['users_kicked']}, "
            f"Retained: {stats['users_retained']}, "
            f"Errors: {stats['errors']}"
        )
        
        return stats
    
    @staticmethod
    async def _get_channel_members(bot, channel_id: int) -> Set[int]:
        """دریافت لیست اعضای یک کانال"""
        members = set()
        
        try:
            # For channels, we can't get all members directly
            # We need to check from our database who should have access
            db = Database()
            if not db.connect():
                return members
            
            try:
                cursor = db.conn.cursor()
                
                # Get all users who have ever had subscriptions
                cursor.execute("""
                    SELECT DISTINCT user_id 
                    FROM subscriptions 
                    WHERE status IN ('active', 'expired')
                """)
                
                potential_members = cursor.fetchall()
                
                for row in potential_members:
                    user_id = row[0]
                    try:
                        # Check if user is in channel
                        member = await bot.get_chat_member(channel_id, user_id)
                        if member.status not in ['left', 'kicked']:
                            members.add(user_id)
                    except:
                        # User not in channel or error
                        pass
                        
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting channel members: {e}")
        
        return members
    
    @staticmethod
    def _user_has_channel_access(user_id: int, channel_id: int) -> bool:
        """
        بررسی دقیق دسترسی کاربر به کانال خاص
        بر اساس اشتراک‌های فعال و محصولات خریداری شده
        """
        try:
            db = Database()
            if not db.connect():
                return False
            
            try:
                cursor = db.conn.cursor()
                
                # Get active subscriptions with channel configurations
                cursor.execute("""
                    SELECT p.channels_json, s.end_date
                    FROM subscriptions s
                    JOIN plans p ON s.plan_id = p.id
                    WHERE s.user_id = ?
                    AND s.status = 'active'
                    AND (s.end_date IS NULL OR s.end_date > datetime('now'))
                """, (user_id,))
                
                rows = cursor.fetchall()
                
                # Check each active subscription
                for row in rows:
                    channels_json, end_date = row
                    
                    if not channels_json:
                        continue
                    
                    try:
                        channels = json.loads(channels_json)
                        if isinstance(channels, list):
                            for channel in channels:
                                if isinstance(channel, dict) and channel.get('id') == channel_id:
                                    # User has access through this subscription
                                    return True
                    except json.JSONDecodeError:
                        continue
                
                return False
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error checking channel access for user {user_id}: {e}")
            return False
    
    @staticmethod
    async def expire_subscriptions():
        """
        انقضای خودکار اشتراک‌های منقضی شده
        و به‌روزرسانی وضعیت آنها در دیتابیس
        """
        count = SubscriptionManager.expire_outdated_subscriptions()
        
        if count > 0:
            logger.info(f"Expired {count} outdated subscriptions")
        
        return count
    
    @staticmethod
    async def send_expiration_reminders(bot, days_before: List[int] = [7, 3, 1]):
        """
        ارسال یادآوری انقضای اشتراک به کاربران
        
        Args:
            bot: Bot instance for sending messages
            days_before: List of days before expiration to send reminders
        """
        logger.info(f"Sending expiration reminders for {days_before} days before...")
        
        db = Database()
        if not db.connect():
            return
        
        try:
            cursor = db.conn.cursor()
            reminders_sent = 0
            
            for days in days_before:
                # Find subscriptions expiring in X days
                cursor.execute("""
                    SELECT DISTINCT
                        s.user_id,
                        s.end_date,
                        p.name as plan_name,
                        p.category_id,
                        c.name as category_name
                    FROM subscriptions s
                    JOIN plans p ON s.plan_id = p.id
                    LEFT JOIN categories c ON p.category_id = c.id
                    WHERE s.status = 'active'
                    AND date(s.end_date) = date('now', '+{} days')
                """.format(days))
                
                rows = cursor.fetchall()
                
                for row in rows:
                    user_id, end_date, plan_name, category_id, category_name = row
                    
                    # Create reminder message
                    if days == 1:
                        urgency = "🔴 فوری"
                        time_text = "فردا"
                    elif days == 3:
                        urgency = "🟡 توجه"
                        time_text = f"{days} روز دیگر"
                    else:
                        urgency = "🟢 یادآوری"
                        time_text = f"{days} روز دیگر"
                    
                    message = (
                        f"{urgency}: **انقضای اشتراک**\n\n"
                        f"اشتراک شما برای «{plan_name}» "
                        f"در دسته‌بندی {category_name or 'عمومی'} "
                        f"{time_text} به پایان می‌رسد.\n\n"
                        "برای تمدید از ربات اصلی استفاده کنید."
                    )
                    
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text=message,
                            parse_mode='Markdown'
                        )
                        reminders_sent += 1
                    except Exception as e:
                        logger.warning(f"Could not send reminder to user {user_id}: {e}")
            
            logger.info(f"Sent {reminders_sent} expiration reminders")
            return reminders_sent
            
        except Exception as e:
            logger.error(f"Error sending expiration reminders: {e}")
            return 0
        finally:
            db.close()
