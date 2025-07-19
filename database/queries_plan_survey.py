"""
Extension for get_plan_survey method
"""

import sqlite3
import logging
from database.models import Database

def get_plan_survey(plan_id: int):
    """Get survey associated with a plan."""
    db = Database()
    if not db.connect():
        return None
    
    try:
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT s.* FROM surveys s
            WHERE s.plan_id = ? AND s.is_active = 1
            LIMIT 1
        """, (plan_id,))
        result = cursor.fetchone()
        return dict(result) if result else None
    except Exception as e:
        logging.error(f"Error getting survey for plan {plan_id}: {e}")
        return None
    finally:
        db.close()

# Add this method to DatabaseQueries class
from database.queries import DatabaseQueries
DatabaseQueries.get_plan_survey = staticmethod(get_plan_survey)
