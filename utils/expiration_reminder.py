"""Utility functions for subscription expiration reminder handling.

Provides helper methods to:
1. Ensure the reminders log table exists
2. Query subscriptions that are expiring within N days
3. Check whether a reminder for a user & days_left was already sent today
4. Log a sent reminder event

These helpers are intentionally written outside the massive `database.queries` module so
that we avoid further bloating that file. All interactions use the same low-level
`Database` class that other modules rely on, so there are no new external
dependencies.
"""
from __future__ import annotations

from datetime import datetime
import logging
import sqlite3
from typing import List, Dict

from database.models import Database  # low-level wrapper used elsewhere

logger = logging.getLogger(__name__)

REMINDERS_TABLE_SQL = (
    """CREATE TABLE IF NOT EXISTS reminders (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            days_left     INTEGER NOT NULL,
            sent_at       TEXT    NOT NULL
        )"""
)


def _ensure_reminders_table() -> None:
    """Create the `reminders` table if it doesn't exist yet."""
    db = Database()
    if db.connect():
        try:
            db.execute(REMINDERS_TABLE_SQL)
            db.commit()
        except sqlite3.Error as exc:
            logger.error("SQLite error creating reminders table: %s", exc)
        finally:
            db.close()


def get_expiring_subscriptions(days: int = 5) -> List[Dict]:
    """Return list of active subs ending within `days` days (inclusive)."""
    from database.queries import DatabaseQueries  # import here to avoid circular

    db = Database()
    subs: List[Dict] = []
    if db.connect():
        try:
            query = (
                """SELECT user_id, end_date FROM subscriptions
                   WHERE status = 'active'
                     AND date(end_date) BETWEEN date('now') AND date('now', '+' || ? || ' day')"""
            )
            db.execute(query, (days,))
            rows = db.fetchall()
            subs = [dict(zip(["user_id", "end_date"], row)) for row in rows]
        except sqlite3.Error as exc:
            logger.error("SQLite error in get_expiring_subscriptions: %s", exc)
        finally:
            db.close()
    return subs


def was_reminder_sent_today(user_id: int, days_left: int) -> bool:
    """Check if a reminder for `days_left` has already been sent to `user_id` today."""
    _ensure_reminders_table()
    db = Database()
    if db.connect():
        try:
            db.execute(
                """SELECT 1 FROM reminders
                   WHERE user_id = ? AND days_left = ? AND date(sent_at) = date('now') LIMIT 1""",
                (user_id, days_left),
            )
            return db.fetchone() is not None
        except sqlite3.Error as exc:
            logger.error("SQLite error in was_reminder_sent_today: %s", exc)
        finally:
            db.close()
    return False


def log_reminder_sent(user_id: int, days_left: int) -> None:
    """Insert a log entry showing that reminder was sent just now."""
    _ensure_reminders_table()
    db = Database()
    if db.connect():
        try:
            db.execute(
                "INSERT INTO reminders (user_id, days_left, sent_at) VALUES (?,?,datetime('now'))",
                (user_id, days_left),
            )
            db.commit()
        except sqlite3.Error as exc:
            logger.error("SQLite error in log_reminder_sent: %s", exc)
        finally:
            db.close()
