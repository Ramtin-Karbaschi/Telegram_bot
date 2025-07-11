
"""Helper to guarantee existence of 20-day free subscription plan."""

import sqlite3
import logging
from typing import Optional

from database.models import Database

logger = logging.getLogger(__name__)

FREE_PLAN_NAME = "free_20d"


def ensure_free_plan() -> Optional[int]:
    """Return ID of the 20-day free plan, creating it if necessary."""
    db = Database()
    if not db.connect():
        return None
    try:
        # Try fetch
        db.execute("SELECT id, days FROM plans WHERE name = ? LIMIT 1", (FREE_PLAN_NAME,))
        row = db.fetchone()
        if row:
            pid = row[0] if isinstance(row, (list, tuple)) else row["id"]
            current_days = row[1] if isinstance(row, (list, tuple)) else row["days"]
            if current_days != 20:
                db.execute("UPDATE plans SET days = ?, description = ? WHERE id = ?", (20, 'هدیه ۲۰ روزه', pid))
                db.commit()
            return pid
        # Otherwise insert
        db.execute(
            """
            INSERT INTO plans (name, description, price, original_price_irr, days, plan_type, is_active, display_order)
                 VALUES (?, 'هدیه ۲۰ روزه', 0, 0, 20, 'subscription', 1, 0)
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
