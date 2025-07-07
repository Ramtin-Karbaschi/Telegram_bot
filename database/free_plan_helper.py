"""Helper to guarantee existence of 30-day free subscription plan."""

import sqlite3
import logging

# Assuming the database path is constant
DB_PATH = "database/data/app.db"
PLAN_NAME = "Free 30-Day Plan"

logger = logging.getLogger(__name__)

def ensure_free_plan() -> int | None:
    """
    Checks if the free plan exists in the database and creates it if not.
    Returns the plan_id.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if the plan already exists
        cursor.execute("SELECT plan_id FROM plans WHERE plan_name = ?", (PLAN_NAME,))
        result = cursor.fetchone()

        if result:
            logger.info(f"Free plan '{PLAN_NAME}' already exists with ID: {result[0]}.")
            return result[0]
        else:
            # Plan does not exist, so create it
            logger.info(f"Creating new free plan: '{PLAN_NAME}'")
            cursor.execute(
                """INSERT INTO plans (plan_name, price, duration_days, is_active, description) 
                   VALUES (?, ?, ?, ?, ?)""",
                (PLAN_NAME, 0, 30, 1, "30-day free trial provided by admin.")
            )
            conn.commit()
            new_plan_id = cursor.lastrowid
            logger.info(f"Successfully created free plan with ID: {new_plan_id}")
            return new_plan_id

    except sqlite3.Error as e:
        logger.error(f"Database error in ensure_free_plan: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

"""Helper to guarantee existence of 30-day free subscription plan."""

import sqlite3
import logging
from typing import Optional

from database.models import Database

logger = logging.getLogger(__name__)

FREE_PLAN_NAME = "free_30d"


def ensure_free_plan() -> Optional[int]:
    """Return ID of the 30-day free plan, creating it if necessary."""
    db = Database()
    if not db.connect():
        return None
    try:
        # Try fetch
        db.execute("SELECT id FROM plans WHERE name = ? LIMIT 1", (FREE_PLAN_NAME,))
        row = db.fetchone()
        if row:
            return row[0] if isinstance(row, (list, tuple)) else row["id"]
        # Otherwise insert
        db.execute(
            """
            INSERT INTO plans (name, description, price, original_price_irr, days, plan_type, is_active, display_order)
                 VALUES (?, 'هدیه ۳۰ روزه', 0, 0, 30, 'subscription', 1, 0)
            """,
            (FREE_PLAN_NAME,),
        )
        db.commit()
        return db.cursor.lastrowid
    except sqlite3.Error as exc:
        logger.error("SQLite error in ensure_free_plan: %s", exc)
        return None
    finally:
        db.close()
