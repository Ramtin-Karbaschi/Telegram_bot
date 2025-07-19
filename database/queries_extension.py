"""
Extension for DatabaseQueries class
"""

import sqlite3
import logging
from database.models import Database

class DatabaseQueriesExtension:
    @staticmethod
    def has_user_used_free_plan(user_id: int, plan_id: int) -> bool:
        """Check if user has already used this specific free plan."""
        db = Database()
        if not db.connect():
            return False
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM subscriptions 
                WHERE user_id = ? AND plan_id = ? AND payment_method = 'free'
            """, (user_id, plan_id))
            count = cursor.fetchone()[0]
            return count > 0
        except Exception as e:
            logging.error(f"Error checking if user {user_id} used free plan {plan_id}: {e}")
            return False
        finally:
            db.close()
