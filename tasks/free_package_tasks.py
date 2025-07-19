"""Background validation and wait-list management for Free Package (Toobit).

This module is **agent-scheduled** via `schedule_tasks(app)` and relies on
`APScheduler` integration that ships with python-telegram-bot's JobQueue.
It performs the following every hour (configurable):
    1. Checks all *active* Free-Package subscriptions and revokes access for
       users who no longer meet the 7-day ≥500 USD volume requirement.
    2. Fills freed capacity (up to `FREE_PACKAGE_CAPACITY`) with users from the
       wait-list, re-validating their eligibility before activation.

Database layout assumptions (already in repo):
    tables: plans, subscriptions, free_package_users, free_package_waitlist

You must ensure `ToobitService.get_volume_last_7d(uid)` exists and returns
float volume in USD, or raise/return None on error.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Final, List

from telegram.ext import Application, CallbackContext

import config
from database.queries import DatabaseQueries as Db
from services.toobit_service import ToobitService
from utils.helpers import get_current_time

logger = logging.getLogger(__name__)

FREE_PKG_PLAN_NAME: Final[str] = "پکیج رایگان"

# ---------------------------------------------------------------------------
# Core validation logic
# ---------------------------------------------------------------------------
async def validate_free_package(app: Application) -> None:
    """Validate active subscriptions and process wait-list replacements."""
    db = Db()

    # 1. Resolve plan_id & capacity
    plans = db.get_all_plans()
    plan_row = next((p for p in plans if (p[1] if isinstance(p, tuple) else p["name"]) == FREE_PKG_PLAN_NAME), None)
    if not plan_row:
        logger.warning("Free Package plan not found – nothing to validate")
        return
    plan_id = plan_row[0] if isinstance(plan_row, tuple) else plan_row["id"]
    capacity = int(getattr(config, "FREE_PACKAGE_CAPACITY", 100))

    # 2. Fetch active subs for plan_id
    active_subs_rows = db.db.execute(
        "SELECT user_id FROM subscriptions WHERE plan_id = ? AND status = 'active'",
        (plan_id,),
    ).fetchall()
    active_user_ids: List[int] = [r[0] if isinstance(r, tuple) else r["user_id"] for r in active_subs_rows]

    logger.info("[FreePkg] Active subs: %d, Capacity: %d", len(active_user_ids), capacity)

    # 3. Check each active user
    removed_users: List[int] = []
    for uid in active_user_ids:
        toobit_record = db.db.execute("SELECT uid FROM free_package_users WHERE user_id = ?", (uid,)).fetchone()
        toobit_uid = toobit_record[0] if toobit_record else None
        if not toobit_uid:
            logger.warning("[FreePkg] User %s missing toobit UID, revoking", uid)
            await _revoke_subscription(db, app, user_id=uid, plan_id=plan_id)
            removed_users.append(uid)
            continue
        try:
            vol = await ToobitService.get_volume_last_7d_async(str(toobit_uid))
        except Exception as exc:
            logger.error("[FreePkg] Error fetching volume for %s – %s. Keeping subscription this cycle.", uid, exc)
            continue
        if vol is None or vol < 500:
            logger.info("[FreePkg] User %s volume %.2f <500. Revoking.", uid, vol or -1)
            await _revoke_subscription(db, app, user_id=uid, plan_id=plan_id)
            removed_users.append(uid)

    # 4. Fill freed slots
    freed_slots = capacity - (len(active_user_ids) - len(removed_users))
    if freed_slots <= 0:
        return
    logger.info("[FreePkg] Freed slots available: %d", freed_slots)

    # Iterate wait-list ordered by position
    while freed_slots > 0:
        candidate_row = db.db.execute(
            "SELECT user_id, position FROM free_package_waitlist ORDER BY position LIMIT 1"
        ).fetchone()
        if not candidate_row:
            logger.info("[FreePkg] Wait-list empty.")
            break
        cand_user_id = candidate_row[0] if isinstance(candidate_row, tuple) else candidate_row["user_id"]
        cand_position = candidate_row[1] if isinstance(candidate_row, tuple) else candidate_row["position"]

        # Fetch Toobit uid/email
        rec = db.db.execute(
            "SELECT uid FROM free_package_users WHERE user_id = ?", (cand_user_id,)
        ).fetchone()
        cand_toobit_uid = rec[0] if rec else None
        eligible = False
        if cand_toobit_uid:
            try:
                vol = await ToobitService.get_volume_last_7d_async(str(cand_toobit_uid))
                eligible = vol is not None and vol >= 500
            except Exception as exc:
                logger.error("[FreePkg] Error validating wait-list user %s – %s", cand_user_id, exc)
                eligible = False
        if eligible:
            # Activate subscription
            await _activate_subscription(db, app, user_id=cand_user_id, plan_id=plan_id)
            # Remove from wait-list
            db.db.execute("DELETE FROM free_package_waitlist WHERE user_id = ?", (cand_user_id,))
            db.db.commit()
            freed_slots -= 1
        else:
            # Move to end
            max_pos = db.db.execute("SELECT MAX(position) FROM free_package_waitlist").fetchone()[0] or 0
            db.db.execute("UPDATE free_package_waitlist SET position = ? WHERE user_id = ?", (max_pos + 1, cand_user_id))
            db.db.commit()
            # Notify about ineligibility
            await _notify(app, cand_user_id, "⚠️ هنوز شرط حجم ۵۰۰ دلاری تکمیل نشده است. جایگاه شما به انتهای صف منتقل شد.")
            # Break loop early to avoid infinite loop if all remaining are ineligible
            break

# ---------------------------------------------------------------------------
# Helper actions
# ---------------------------------------------------------------------------
async def _revoke_subscription(db: Db, app: Application, *, user_id: int, plan_id: int):
    now = get_current_time()
    db.db.execute(
        "UPDATE subscriptions SET status='revoked', end_date=? WHERE user_id=? AND plan_id=? AND status='active'",
        (now.isoformat(sep=" ", timespec="seconds"), user_id, plan_id),
    )
    db.db.commit()
    # Optionally also decrement capacity if you track remaining slots.
    await _notify(app, user_id, "❌ دسترسی رایگان شما لغو شد. در صورت تمایل دوباره اقدام کنید.")

async def _activate_subscription(db: Db, app: Application, *, user_id: int, plan_id: int):
    now = get_current_time()
    db.db.execute(
        "INSERT INTO subscriptions (user_id, plan_id, start_date, end_date, amount_paid, payment_method, status, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (
            user_id,
            plan_id,
            now.isoformat(sep=" ", timespec="seconds"),
            None,
            0,
            "free_package",
            "active",
            now.isoformat(sep=" ", timespec="seconds"),
            now.isoformat(sep=" ", timespec="seconds"),
        ),
    )
    db.db.commit()
    await _notify(app, user_id, "🎉 دسترسی رایگان شما فعال شد. لطفاً فعال بمانید!")
    logger.info("[FreePkg] Activated subscription for user %s", user_id)

async def _notify(app: Application, chat_id: int, text: str):
    try:
        await app.bot.send_message(chat_id=chat_id, text=text)
    except Exception as exc:
        logger.warning("[FreePkg] Failed to notify user %s – %s", chat_id, exc)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def schedule_tasks(app: Application) -> None:
    """Attach hourly validation job to application's job_queue."""
    # Run immediately after startup, then every hour
    app.job_queue.run_repeating(
        _job_wrapper,
        interval=3600,
        first=5,
        name="validate_free_package",
    )

async def _job_wrapper(context: CallbackContext):
    await validate_free_package(context.application)
