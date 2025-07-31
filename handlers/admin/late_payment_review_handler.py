"""Handlers for admin review of late crypto payments."""

from __future__ import annotations

import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from utils.admin_utils import admin_required
from database.models import Database
from handlers.subscription.subscription_handlers import activate_or_extend_subscription
import config

logger = logging.getLogger(__name__)

@admin_required
async def approve_late_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payment_id = query.data.split(":", 1)[1]
    db = Database()
    payment = db.get_crypto_payment_by_payment_id(payment_id)
    if not payment or payment["status"] != "paid-late":
        await query.edit_message_text("این پرداخت در وضعیت تایید دیرهنگام نیست یا قبلاً پردازش شده است.")
        return

    # change status to 'paid' and log
    db.log_payment_status_change(payment_id, "paid-late", "paid", changed_by=str(update.effective_user.id))
    db.execute(
        "UPDATE crypto_payments SET status='paid', updated_at=? WHERE payment_id=?",
        (datetime.now(), payment_id),
    )
    db.commit()

    # activate subscription
    user_id = payment["user_id"]
    telegram_id = user_id  # design assumption
    plan_id = payment.get("plan_id")  # may be null

    if plan_id:
        ok, msg = await activate_or_extend_subscription(
            user_id=user_id,
            telegram_id=telegram_id,
            plan_id=plan_id,
            plan_name="",  # not needed
            payment_amount=payment.get("usdt_amount_received", 0),
            payment_method="tether-late",
            transaction_id=payment["transaction_id"],
            context=context,
            payment_table_id=payment_id,
        )
    else:
        ok = False

    await query.edit_message_text(
        "✅ پرداخت دیرهنگام تایید و اشتراک کاربر فعال شد." if ok else "✅ پرداخت تایید شد اما فعال‌سازی اشتراک انجام نشد.",
        parse_mode=ParseMode.MARKDOWN,
    )

    # notify user
    try:
        await context.bot.send_message(
            chat_id=telegram_id,
            text="🎉 پرداخت شما با تاخیر تایید و اشتراک شما فعال شد.",
        )
    except Exception as e:
        logger.error(f"Failed to notify user {telegram_id} after late payment approval: {e}")

@admin_required
async def reject_late_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    payment_id = query.data.split(":", 1)[1]
    db = Database()
    payment = db.get_crypto_payment_by_payment_id(payment_id)
    if not payment or payment["status"] != "paid-late":
        await query.edit_message_text("این پرداخت در وضعیت تایید دیرهنگام نیست یا قبلاً پردازش شده است.")
        return

    db.log_payment_status_change(payment_id, "paid-late", "late-rejected", changed_by=str(update.effective_user.id))
    db.execute(
        "UPDATE crypto_payments SET status='late-rejected', updated_at=? WHERE payment_id=?",
        (datetime.now(), payment_id),
    )
    db.commit()

    await query.edit_message_text("❌ پرداخت دیرهنگام رد شد.")

    # inform user
    telegram_id = payment["user_id"]
    try:
        await context.bot.send_message(
            chat_id=telegram_id,
            text="متاسفانه پرداخت شما با تاخیر تایید نشد. لطفاً به پشتیبانی پیام دهید.",
        )
    except Exception as e:
        logger.error(f"Failed to notify user {telegram_id} after late payment rejection: {e}")
