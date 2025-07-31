"""Send daily crypto payment summary to admins."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List

from telegram.ext import ContextTypes, Application

from database.models import Database
import config

logger = logging.getLogger(__name__)


async def send_daily_crypto_report_job(context: ContextTypes.DEFAULT_TYPE):
    """JobQueue callback to send yesterday's crypto payment report to admins."""
    db = Database.get_instance()

    now_tehran = datetime.now(tz=context.job.data.get("tz")) if context.job and context.job.data else datetime.now()
    start_of_day = (now_tehran.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1))
    end_of_day = start_of_day + timedelta(hours=24)

    query = (
        "SELECT user_id, payment_id, usdt_amount_requested, usdt_amount_received, status, created_at "
        "FROM crypto_payments WHERE created_at >= ? AND created_at < ?"
    )
    db.execute(query, (start_of_day, end_of_day))
    rows = [dict(r) for r in db.fetchall()]

    paid_statuses = {"paid", "paid-late"}
    failed_statuses = {"pending", "late-rejected", "failed", "expired"}

    paid_rows = [r for r in rows if r["status"] in paid_statuses]
    failed_rows = [r for r in rows if r["status"] in failed_statuses]

    def _fmt(row):
        received = row.get("usdt_amount_received") or "-"
        return (
            f"• UID {row['user_id']} | {row['status']} | Req {row['usdt_amount_requested']} USDT | Rec {received} | ID {row['payment_id'][:8]}…"
        )

    paid_text = "\n".join(_fmt(r) for r in paid_rows) or "هیچ"  # none
    failed_text = "\n".join(_fmt(r) for r in failed_rows) or "هیچ"

    report_text = (
        "📊 گزارش پرداخت‌های کریپتو (دیروز)\n\n"
        f"✅ تاییدشده ({len(paid_rows)}):\n{paid_text}\n\n"
        f"❌ تاییدنشده ({len(failed_rows)}):\n{failed_text}"
    )

    for admin_id in getattr(config, "ADMIN_USER_IDS", []):
        try:
            await context.bot.send_message(chat_id=admin_id, text=report_text)
        except Exception as exc:
            logger.error(f"Failed to send daily crypto report to {admin_id}: {exc}")
