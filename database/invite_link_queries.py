from __future__ import annotations

"""Utility queries for managing one-time Telegram invite links.
This module is intentionally kept separate from the very large
`database.queries` module, so that invite-link–specific logic is easy to
maintain and avoids further bloat of that file.

Functions here are **simple wrappers** around SQL statements targeting the
`invite_links` table (declared in `database.schema`).  They do NOT perform
any Telegram API calls – generation of the actual `invite_link` string must
be done elsewhere (bots that have the required admin rights).

All datetime values are stored as ISO formatted strings in local time.  We
use `utils.helpers.get_current_time()` to obtain a timezone-aware timestamp
that is already aligned with the rest of the codebase.
"""

import sqlite3
import logging
from typing import Optional

from database.models import Database
from utils.helpers import get_current_time

__all__ = [
    "create_invite_link",
    "mark_invite_link_used",
    "get_active_invite_link",
]


def create_invite_link(
    user_id: int,
    invite_link: str,
    expiration_date: Optional[str] = None,
) -> bool:
    """Insert a new *unused* invite-link record.

    Args:
        user_id:      Telegram `user_id` that the link is intended for.
        invite_link:  The full t.me/… invite link string.
        expiration_date: Optional ISO-formatted datetime string.  Use *None*
                         to indicate "no explicit expiry" – the link may still
                         expire in Telegram per-link settings (max_age, etc.).
    Returns:
        bool – *True* on success, *False* otherwise.
    """
    db = Database()
    if not db.connect():
        return False

    try:
        db.execute(
            """
            INSERT INTO invite_links (user_id, invite_link, creation_date, expiration_date, is_used)
            VALUES (?, ?, ?, ?, 0)
            """,
            (
                user_id,
                invite_link,
                get_current_time().isoformat(sep=" ", timespec="seconds"),
                expiration_date,
            ),
        )
        db.commit()
        return True
    except sqlite3.Error as exc:
        logging.error("SQLite error in create_invite_link: %s", exc)
        return False
    finally:
        db.close()


def mark_invite_link_used(invite_link: str) -> bool:
    """Set `is_used = 1` for a given link (idempotent)."""
    db = Database()
    if not db.connect():
        return False

    try:
        db.execute(
            "UPDATE invite_links SET is_used = 1 WHERE invite_link = ?",
            (invite_link,),
        )
        db.commit()
        return db.cursor.rowcount > 0
    except sqlite3.Error as exc:
        logging.error("SQLite error in mark_invite_link_used: %s", exc)
        return False
    finally:
        db.close()


def get_active_invite_link(user_id: int) -> Optional[str]:
    """Return the newest *unused* invite link for a user, or *None*."""
    db = Database()
    if not db.connect():
        return None

    try:
        db.cursor.execute(
            """
            SELECT invite_link
            FROM invite_links
            WHERE user_id = ? AND is_used = 0
            ORDER BY creation_date DESC
            LIMIT 1
            """,
            (user_id,),
        )
        result = db.cursor.fetchone()
        return result[0] if result else None
    except sqlite3.Error as exc:
        logging.error("SQLite error in get_active_invite_link: %s", exc)
        return None
    finally:
        db.close()
