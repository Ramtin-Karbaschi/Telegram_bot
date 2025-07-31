"""Callback handler allowing user to request up-to-5 manual verifications for an expired crypto invoice."""
from __future__ import annotations

import logging
from datetime import timedelta

from telegram import Update
from telegram.ext import ContextTypes

from database.models import Database
from services.comprehensive_payment_system import get_payment_system, PaymentStatus
from handlers.subscription.subscription_handlers import activate_or_extend_subscription

logger = logging.getLogger(__name__)

MAX_MANUAL_CHECKS = 5
LATE_WINDOW_HOURS = 12


async def retry_crypto_payment_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        _, payment_id = query.data.split(":", 1)
    except ValueError:
        return

    db = Database.get_instance()
    payment = db.get_crypto_payment_by_payment_id(payment_id)
    if not payment:
        await query.edit_message_text("رکورد پرداخت یافت نشد یا پاک شده است.")
        return

    if payment["status"] != "pending":
        await query.edit_message_text("این پرداخت دیگر در وضعیت انتظار نیست.")
        return

    manual_checks = payment.get("manual_checks", 0) or 0
    if manual_checks >= MAX_MANUAL_CHECKS:
        await query.answer("شما بیش از ۵ بار درخواست بررسی داده‌اید.", show_alert=True)
        return

    # increment manual_checks counter
    db.execute("UPDATE crypto_payments SET manual_checks = manual_checks + 1 WHERE payment_id = ?", (payment_id,))
    db.commit()

    # Perform on-chain scan for late payment within allowed window
    payment_system = get_payment_system()
    try:
        results = await payment_system.search_automatic_payments(payment, time_window_hours=LATE_WINDOW_HOURS)
    except Exception as exc:
        logger.error(f"Manual late-payment scan failed for {payment_id}: {exc}")
        await query.answer("خطای سیستمی در بررسی. لطفا بعدا تلاش کنید.", show_alert=True)
        return

    verified_tx = next((r for r in results if r.status == PaymentStatus.VERIFIED), None) if results else None
    if not verified_tx:
        await query.answer("هنوز تراکنش تائیدشده‌ای یافت نشد.", show_alert=True)
        return

    # Mark as paid-late & activate subscription
    success = db.update_crypto_payment_on_success(
        payment_id, verified_tx.tx_hash, float(verified_tx.amount), late=True
    )
    if success:
        await activate_or_extend_subscription(
            user_id=payment["user_id"],
            telegram_id=update.effective_user.id,
            plan_id=payment.get("plan_id"),
            plan_name="",  # not needed
            payment_amount=verified_tx.amount,
            payment_method="tether-late-user",
            transaction_id=verified_tx.tx_hash,
            context=context,
            payment_table_id=payment_id,
        )
        await query.edit_message_text("✅ پرداخت شما با موفقیت شناسایی شد و اشتراک فعال گردید.")
    else:
        await query.answer("خطا در به‌روزرسانی وضعیت پرداخت.", show_alert=True)
