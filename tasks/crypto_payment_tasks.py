"""Background jobs related to crypto payment lifecycle.

- Send reminder 15 minutes before the 30-minute user deadline.
- Scan for late (≤12 h) on-chain payments that were sent after invoice expiry and
  mark them as `paid-late`, then alert admins with approval buttons.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application

from database.models import Database
from services.comprehensive_payment_system import get_payment_system, PaymentStatus
import config

logger = logging.getLogger(__name__)

REMINDER_OFFSET_MINUTES = 15  # send reminder 15 min before user's 30 min window ends
LATE_PAYMENT_GRACE_HOURS = 12
SCAN_INTERVAL_MINUTES = 10  # how often to scan for late payments

# ---------------------------------------------------------------------------
# Reminder job (scheduled individually when invoice is created)
# ---------------------------------------------------------------------------

async def crypto_payment_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback: reminds user 15 minutes before invoice expires."""
    job_data: Dict = context.job.data or {}
    payment_id: str | None = job_data.get("payment_id")
    if not payment_id:
        return

    db = Database()
    payment = db.get_crypto_payment_by_payment_id(payment_id)
    if not payment:
        return

    # still pending and within last 15 minutes?
    if payment["status"] != "pending":
        return
    try:
        expires_at = payment.get("expires_at")
        if isinstance(expires_at, str):
            expires_dt = datetime.fromisoformat(expires_at)
        else:
            expires_dt = expires_at  # assume datetime
    except Exception:
        return

    now = datetime.now(expires_dt.tzinfo) if expires_dt.tzinfo else datetime.now()
    if expires_dt - now > timedelta(minutes=REMINDER_OFFSET_MINUTES):
        # job fired too early due to clock drift, re-schedule at correct time
        delay = (expires_dt - timedelta(minutes=REMINDER_OFFSET_MINUTES) - now).total_seconds()
        if delay > 0:
            context.job_queue.run_once(
                crypto_payment_reminder_job, delay, chat_id=context.job.chat_id, data=job_data
            )
        return

    try:
        await context.bot.send_message(
            chat_id=context.job.chat_id,
            text=(
                "⏰ 15 دقیقه تا انقضای فاکتور باقی مانده است.\n"
                "لطفاً پرداخت تتر خود را تکمیل و TX Hash را ارسال کنید تا اشتراک شما فعال شود."
            ),
        )
    except Exception as e:
        logger.error(f"Failed to send payment reminder for {payment_id} to chat {context.job.chat_id}: {e}")

# ---------------------------------------------------------------------------
# Periodic scanner for late payments
# ---------------------------------------------------------------------------

async def scan_late_payments_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback: scans blockchain for late user payments (≤12 h)."""
    db = Database()

    now = datetime.now()
    threshold = now - timedelta(hours=LATE_PAYMENT_GRACE_HOURS)

    # fetch pending payments that are expired but still within 12 h window
    query = (
        "SELECT * FROM crypto_payments WHERE status='pending' AND expires_at < ? AND expires_at > ?"
    )
    db.execute(query, (now, threshold))
    rows = db.fetchall()
    if not rows:
        return

    payment_system = get_payment_system()

    for row in rows:
        payment = dict(row)
        try:
            results = await payment_system.search_automatic_payments(payment, time_window_hours=LATE_PAYMENT_GRACE_HOURS)
        except Exception as exc:
            logger.error(f"Late-payment scan failed for {payment['payment_id']}: {exc}")
            continue

        if not results:
            continue

        # pick the first verified result that matches amount & wallet
        verified_tx = next((r for r in results if r.status == PaymentStatus.VERIFIED), None)
        if not verified_tx:
            continue

        # mark as paid-late
        success = db.update_crypto_payment_on_success(
            payment["payment_id"], verified_tx.tx_hash, float(verified_tx.amount), late=True
        )
        if not success:
            continue

        # alert admins
        await _notify_admins_of_late_payment(context.application, payment, verified_tx)

async def _notify_admins_of_late_payment(app: Application, payment: Dict, tx) -> None:
    """Sends inline-keyboard message to admins for manual approval."""
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ فعال‌سازی اشتراک",
                callback_data=f"approve_late_payment:{payment['payment_id']}",
            ),
            InlineKeyboardButton(
                "❌ رد پرداخت",
                callback_data=f"reject_late_payment:{payment['payment_id']}",
            ),
        ]
    ])

    msg = (
        "⚠️ پرداخت دیرهنگام شناسایی شد\n\n"
        f"User ID: {payment['user_id']}\n"
        f"TX Hash: `{tx.tx_hash}`\n"
        f"Amount: {tx.amount} USDT\n"
        f"Status: paid-late\n\n"
        "لطفاً تایید یا رد کنید."
    )

    for admin_id in getattr(config, "ADMIN_USER_IDS", []):
        try:
            await app.bot.send_message(
                chat_id=admin_id,
                text=msg,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id} for late payment {payment['payment_id']}: {e}")

