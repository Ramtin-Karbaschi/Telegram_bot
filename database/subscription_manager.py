"""
Subscription Manager Module
مدیریت پیشرفته اشتراک‌ها با پشتیبانی از تفکیک بر اساس دسته‌بندی
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from database.models import Database
from database.queries import DatabaseQueries

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """مدیریت پیشرفته اشتراک‌ها با قابلیت تجمیع زمان برای دسته‌بندی‌های یکسان"""
    
    @staticmethod
    def create_or_extend_subscription(
        user_id: int, 
        plan_id: int, 
        payment_id: Optional[int] = None,
        payment_method: Optional[str] = None,
        amount_paid: float = 0,
        admin_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        ایجاد یا تمدید اشتراک برای کاربر
        اگر محصول در دسته‌بندی مشابه با اشتراک فعال باشد، زمان اضافه می‌شود
        
        Returns:
            Tuple[bool, str]: (Success, Message)
        """
        db = Database()
        if not db.connect():
            return False, "خطا در اتصال به دیتابیس"
        
        try:
            cursor = db.conn.cursor()
            
            # Get plan details
            cursor.execute("""
                SELECT p.*, c.name as category_name 
                FROM plans p 
                LEFT JOIN categories c ON p.category_id = c.id 
                WHERE p.id = ?
            """, (plan_id,))
            plan = cursor.fetchone()
            
            if not plan:
                return False, "محصول یافت نشد"
            
            plan_dict = dict(plan) if hasattr(plan, 'keys') else {
                'id': plan[0],
                'name': plan[1],
                'duration_days': plan[7] if len(plan) > 7 else 30,
                'category_id': plan[11] if len(plan) > 11 else None
            }
            
            duration_days = plan_dict.get('duration_days', 30) or 30
            category_id = plan_dict.get('category_id')
            
            # Update subscription category_id
            cursor.execute("""
                UPDATE subscriptions 
                SET category_id = ? 
                WHERE plan_id = ? AND category_id IS NULL
            """, (category_id, plan_id))
            
            # Check for existing active subscription in same category
            if category_id:
                cursor.execute("""
                    SELECT s.*, p.category_id 
                    FROM subscriptions s
                    JOIN plans p ON s.plan_id = p.id
                    WHERE s.user_id = ? 
                    AND p.category_id = ?
                    AND s.status = 'active'
                    AND (s.end_date IS NULL OR s.end_date > datetime('now'))
                    ORDER BY s.end_date DESC
                    LIMIT 1
                """, (user_id, category_id))
            else:
                # If no category, check for same plan
                cursor.execute("""
                    SELECT * FROM subscriptions
                    WHERE user_id = ? AND plan_id = ? 
                    AND status = 'active'
                    AND (end_date IS NULL OR end_date > datetime('now'))
                    ORDER BY end_date DESC
                    LIMIT 1
                """, (user_id, plan_id))
            
            existing_sub = cursor.fetchone()
            
            now = datetime.utcnow()
            
            if existing_sub:
                # Extend existing subscription
                existing_dict = dict(existing_sub) if hasattr(existing_sub, 'keys') else {
                    'id': existing_sub[0],
                    'end_date': existing_sub[5] if len(existing_sub) > 5 else None
                }
                
                sub_id = existing_dict['id']
                current_end = existing_dict.get('end_date')
                
                if current_end:
                    if isinstance(current_end, str):
                        current_end_dt = datetime.fromisoformat(current_end.replace('Z', '+00:00'))
                    else:
                        current_end_dt = current_end
                    
                    # If current end date is in future, add to it
                    if current_end_dt > now:
                        new_end = current_end_dt + timedelta(days=duration_days)
                    else:
                        # If expired, start from now
                        new_end = now + timedelta(days=duration_days)
                else:
                    new_end = now + timedelta(days=duration_days)
                
                new_end_str = new_end.isoformat()
                
                # Update subscription
                cursor.execute("""
                    UPDATE subscriptions 
                    SET end_date = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_end_str, sub_id))
                
                # Log to history
                cursor.execute("""
                    INSERT INTO subscription_history 
                    (subscription_id, user_id, plan_id, category_id, action, 
                     old_end_date, new_end_date, days_added, created_by, notes)
                    VALUES (?, ?, ?, ?, 'extended', ?, ?, ?, ?, ?)
                """, (
                    sub_id, user_id, plan_id, category_id,
                    existing_dict.get('end_date'), new_end_str, duration_days,
                    admin_id, f"Extended with plan: {plan_dict.get('name', '')}"
                ))
                
                db.conn.commit()
                
                message = f"اشتراک شما در دسته‌بندی {plan_dict.get('category_name', 'محصول')} تمدید شد. "
                message += f"تاریخ انقضای جدید: {new_end.strftime('%Y/%m/%d')}"
                
                return True, message
                
            else:
                # Create new subscription
                start_date = now.isoformat()
                end_date = (now + timedelta(days=duration_days)).isoformat()
                
                cursor.execute("""
                    INSERT INTO subscriptions 
                    (user_id, plan_id, start_date, end_date, status, 
                     amount_paid, payment_method, payment_id, category_id,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, 
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    user_id, plan_id, start_date, end_date,
                    amount_paid, payment_method, payment_id, category_id
                ))
                
                sub_id = cursor.lastrowid
                
                # Log to history
                cursor.execute("""
                    INSERT INTO subscription_history 
                    (subscription_id, user_id, plan_id, category_id, action,
                     new_end_date, days_added, created_by, notes)
                    VALUES (?, ?, ?, ?, 'created', ?, ?, ?, ?)
                """, (
                    sub_id, user_id, plan_id, category_id,
                    end_date, duration_days, admin_id,
                    f"New subscription: {plan_dict.get('name', '')}"
                ))
                
                db.conn.commit()
                
                message = f"اشتراک جدید برای {plan_dict.get('name', 'محصول')} ایجاد شد. "
                message += f"تاریخ انقضا: {(now + timedelta(days=duration_days)).strftime('%Y/%m/%d')}"
                
                return True, message
                
        except Exception as e:
            logger.error(f"Error in create_or_extend_subscription: {e}")
            db.conn.rollback()
            return False, f"خطا در ایجاد/تمدید اشتراک: {str(e)}"
        finally:
            db.close()
    
    @staticmethod
    def get_user_subscriptions_detailed(user_id: int) -> Dict:
        """
        دریافت جزئیات کامل اشتراک‌های کاربر به تفکیک دسته‌بندی
        
        Returns:
            Dict with categorized subscriptions and remaining days
        """
        db = Database()
        if not db.connect():
            return {}
        
        try:
            cursor = db.conn.cursor()
            
            # Get all active subscriptions grouped by category
            cursor.execute("""
                SELECT 
                    s.id,
                    s.plan_id,
                    p.name as plan_name,
                    p.category_id,
                    c.name as category_name,
                    s.start_date,
                    s.end_date,
                    s.status,
                    p.channels_json,
                    CASE 
                        WHEN s.status = 'active' AND s.end_date > datetime('now')
                        THEN CAST((julianday(s.end_date) - julianday(datetime('now'))) AS INTEGER)
                        ELSE 0
                    END as remaining_days
                FROM subscriptions s
                JOIN plans p ON s.plan_id = p.id
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE s.user_id = ?
                AND s.status = 'active'
                ORDER BY c.name, s.end_date DESC
            """, (user_id,))
            
            rows = cursor.fetchall()
            
            result = {
                'by_category': {},
                'by_product': [],
                'total_active': 0,
                'channels_access': set()
            }
            
            for row in rows:
                row_dict = dict(row) if hasattr(row, 'keys') else {
                    'id': row[0],
                    'plan_id': row[1],
                    'plan_name': row[2],
                    'category_id': row[3],
                    'category_name': row[4],
                    'start_date': row[5],
                    'end_date': row[6],
                    'status': row[7],
                    'channels_json': row[8] if len(row) > 8 else None,
                    'remaining_days': row[9] if len(row) > 9 else 0
                }
                
                # Add to by_product list
                result['by_product'].append({
                    'subscription_id': row_dict['id'],
                    'plan_id': row_dict['plan_id'],
                    'plan_name': row_dict['plan_name'],
                    'category': row_dict['category_name'] or 'بدون دسته‌بندی',
                    'start_date': row_dict['start_date'],
                    'end_date': row_dict['end_date'],
                    'remaining_days': max(0, row_dict['remaining_days'])
                })
                
                # Aggregate by category
                category_key = row_dict['category_id'] or 0
                category_name = row_dict['category_name'] or 'بدون دسته‌بندی'
                
                if category_key not in result['by_category']:
                    result['by_category'][category_key] = {
                        'category_name': category_name,
                        'total_days': 0,
                        'products': [],
                        'earliest_start': row_dict['start_date'],
                        'latest_end': row_dict['end_date']
                    }
                
                result['by_category'][category_key]['products'].append(row_dict['plan_name'])
                result['by_category'][category_key]['total_days'] += max(0, row_dict['remaining_days'])
                
                # Update earliest/latest dates
                if row_dict['start_date'] < result['by_category'][category_key]['earliest_start']:
                    result['by_category'][category_key]['earliest_start'] = row_dict['start_date']
                if row_dict['end_date'] > result['by_category'][category_key]['latest_end']:
                    result['by_category'][category_key]['latest_end'] = row_dict['end_date']
                
                # Parse channels
                if row_dict['channels_json']:
                    try:
                        import json
                        channels = json.loads(row_dict['channels_json'])
                        if isinstance(channels, list):
                            for channel in channels:
                                if isinstance(channel, dict):
                                    result['channels_access'].add(channel.get('id'))
                    except:
                        pass
                
                result['total_active'] += 1
            
            # Convert set to list for JSON serialization
            result['channels_access'] = list(result['channels_access'])
            
            return result
            
        except Exception as e:
            logger.error(f"Error in get_user_subscriptions_detailed: {e}")
            return {}
        finally:
            db.close()
    
    @staticmethod
    def check_user_access_to_channel(user_id: int, channel_id: int) -> Tuple[bool, Optional[str]]:
        """
        بررسی دسترسی کاربر به کانال با در نظر گرفتن همه اشتراک‌های فعال
        
        Returns:
            Tuple[bool, Optional[str]]: (has_access, category_name)
        """
        db = Database()
        if not db.connect():
            return False, None
        
        try:
            cursor = db.conn.cursor()
            
            # Check all active subscriptions
            cursor.execute("""
                SELECT 
                    s.id,
                    p.channels_json,
                    c.name as category_name
                FROM subscriptions s
                JOIN plans p ON s.plan_id = p.id
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE s.user_id = ?
                AND s.status = 'active'
                AND (s.end_date IS NULL OR s.end_date > datetime('now'))
            """, (user_id,))
            
            rows = cursor.fetchall()
            
            for row in rows:
                channels_json = row[1]
                category_name = row[2]
                
                if channels_json:
                    try:
                        import json
                        channels = json.loads(channels_json)
                        if isinstance(channels, list):
                            for channel in channels:
                                if isinstance(channel, dict) and channel.get('id') == channel_id:
                                    return True, category_name
                    except:
                        continue
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error checking channel access: {e}")
            return False, None
        finally:
            db.close()
    
    @staticmethod
    def get_subscription_history(user_id: int, limit: int = 20) -> List[Dict]:
        """دریافت تاریخچه تغییرات اشتراک کاربر"""
        db = Database()
        if not db.connect():
            return []
        
        try:
            cursor = db.conn.cursor()
            
            cursor.execute("""
                SELECT 
                    h.*,
                    p.name as plan_name
                FROM subscription_history h
                JOIN plans p ON h.plan_id = p.id
                WHERE h.user_id = ?
                ORDER BY h.created_at DESC
                LIMIT ?
            """, (user_id, limit))
            
            rows = cursor.fetchall()
            history = []
            
            for row in rows:
                row_dict = dict(row) if hasattr(row, 'keys') else {
                    'id': row[0],
                    'action': row[4] if len(row) > 4 else 'unknown',
                    'old_end_date': row[5] if len(row) > 5 else None,
                    'new_end_date': row[6] if len(row) > 6 else None,
                    'days_added': row[7] if len(row) > 7 else 0,
                    'created_at': row[8] if len(row) > 8 else None,
                    'notes': row[10] if len(row) > 10 else None,
                    'plan_name': row[-1]  # Last column from JOIN
                }
                
                history.append(row_dict)
            
            return history
            
        except Exception as e:
            logger.error(f"Error getting subscription history: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def expire_outdated_subscriptions() -> int:
        """انقضای اشتراک‌های منقضی شده و بازگرداندن تعداد"""
        db = Database()
        if not db.connect():
            return 0
        
        try:
            cursor = db.conn.cursor()
            
            # Find expired subscriptions
            cursor.execute("""
                SELECT id, user_id, plan_id, category_id, end_date
                FROM subscriptions
                WHERE status = 'active'
                AND end_date IS NOT NULL
                AND end_date < datetime('now')
            """)
            
            expired = cursor.fetchall()
            
            for sub in expired:
                sub_id, user_id, plan_id, category_id, end_date = sub[:5]
                
                # Update status
                cursor.execute("""
                    UPDATE subscriptions
                    SET status = 'expired', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (sub_id,))
                
                # Log to history
                cursor.execute("""
                    INSERT INTO subscription_history
                    (subscription_id, user_id, plan_id, category_id, action,
                     old_end_date, notes)
                    VALUES (?, ?, ?, ?, 'expired', ?, 'Auto-expired by system')
                """, (sub_id, user_id, plan_id, category_id, end_date))
            
            db.conn.commit()
            return len(expired)
            
        except Exception as e:
            logger.error(f"Error expiring subscriptions: {e}")
            db.conn.rollback()
            return 0
        finally:
            db.close()
