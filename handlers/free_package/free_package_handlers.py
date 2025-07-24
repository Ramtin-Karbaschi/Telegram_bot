"""Conversation flow for the new Free Package promotion.

This feature lets users claim a *Free Package* subscription provided they:
1. Registered on Toobit **using our referral code**.
2. Have total trading volume > 500 USD.
3. Remain active (trade once every 7 days).  Inactivity revokes access (handled by
   a periodic background validation job – TODO).
4. Capacity is limited to 100 users; extra users are queued.

High-level flow:
1. User clicks "🎁 پکیج رایگان" → `start_free_package_flow` callback.
2. We ask for Toobit-registered email.
3. Ask for UID.
4. Verify eligibility via `ToobitService`.
5. If not eligible → politely reject.
6. If eligible:
   • If capacity available → create/activate subscription under *Free Package* plan.
   • Else → insert user into wait-list table and show their position.

NOTE: The actual check for *last trade <= 7 days* is **not** performed here –
that logic should run in a scheduled job similar to existing membership
validation.  We only store UID so that job can query it later.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Final

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (CallbackQueryHandler, ConversationHandler,
                          ContextTypes, MessageHandler, filters)
from telegram.error import BadRequest

import config
from database.queries import DatabaseQueries as Db
from services.toobit_service import ToobitService
from utils.constants import (
    TEXT_MAIN_MENU_FREE_PACKAGE,
    TEXT_MAIN_MENU_BUY_SUBSCRIPTION,
)
from utils.keyboards import get_main_menu_keyboard, get_subscription_plans_keyboard
from utils.helpers import get_current_time

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------
ASK_EMAIL: Final[int] = 0
ASK_UID: Final[int] = 1
PROCESSING: Final[int] = 2

FREE_PACKAGE_PLAN_NAME: Final[str] = "پکیج رایگان"

# ---------------------------------------------------------------------------
# Helpers – DB level (wait-list, plan id, etc.)
# ---------------------------------------------------------------------------

db = Db()

def _ensure_free_package_plan_id() -> int:
    """Return plan_id for the Free Package; create one if it does not exist."""
    existing = db.get_all_plans()
    plan = next((p for p in existing if p[1] == FREE_PACKAGE_PLAN_NAME), None)
    if plan:
        return plan[0] if isinstance(plan, tuple) else plan["id"]

    capacity = int(getattr(config, "FREE_PACKAGE_CAPACITY", 100))
    logger.info("Creating Free Package plan with capacity %d", capacity)
    plan_id = db.add_plan(
        name=FREE_PACKAGE_PLAN_NAME,
        price=0,
        duration_days=3650,  # effectively unlimited (10 years)
        description="اشتراک رایگان مشروط به فعالیت در توبیت",
        capacity=capacity,
    )
    # Update plan_type to 'free_package'
    db.update_plan(plan_id, description="اشتراک رایگان ویژه کاربران فعال توبیت")
    db.db.execute("UPDATE plans SET plan_type = 'free_package' WHERE id = ?", (plan_id,))
    db.db.commit()
    return plan_id


def _count_active_free_package_subs(plan_id: int) -> int:
    return Db.count_subscribers_for_plan(plan_id)


def _queue_position(user_id: int) -> int:
    db.db.execute("SELECT position FROM free_package_waitlist WHERE user_id = ?", (user_id,))
    row = db.db.fetchone()
    if row:
        return row[0] if isinstance(row, tuple) else row["position"]
    return -1


def _upsert_free_pkg_user(user_id: int, email: str, uid: str):
    now = get_current_time().isoformat(sep=" ", timespec="seconds")
    db.db.execute(
        "INSERT INTO free_package_users (user_id, email, uid, last_checked) VALUES (?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET email=excluded.email, uid=excluded.uid",
        (user_id, email, uid, now),
    )
    db.db.commit()


async def show_queue_position(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback handler to show user's queue position or status."""
    await update.callback_query.answer()
    user_id = update.effective_user.id
    pos = _queue_position(user_id)
    if pos <= 0:
        text = "✅ شما در صف انتظار نیستید یا اشتراک فعال دارید."
    else:
        text = f"📊 جایگاه فعلی شما در صف رایگان: {pos}"
    await update.callback_query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩ بازگشت به منوی اصلی", callback_data="back_to_main_menu")]
        ]),
    )


def _add_to_waitlist(user_id: int) -> int:
    """Insert user to waitlist (if not already) and return their position."""
    pos = _queue_position(user_id)
    if pos > 0:
        return pos

    db.db.execute("SELECT MAX(position) FROM free_package_waitlist")
    max_pos = db.db.fetchone()[0] or 0
    new_pos = max_pos + 1
    now = get_current_time().isoformat(sep=" ", timespec="seconds")
    db.db.execute(
        "INSERT OR IGNORE INTO free_package_waitlist (user_id, position, created_at) VALUES (?,?,?)",
        (user_id, new_pos, now),
    )
    db.db.commit()
    return new_pos

# ---------------------------------------------------------------------------
# Helper to build keyboard for free packages menu
# ---------------------------------------------------------------------------
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)
from utils.keyboards import get_subscription_plans_keyboard

async def free_packages_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show menu listing free subscription plans plus the Toobit free package."""
    query = update.callback_query
    if query:
        await query.answer()
        send_func = query.message.edit_text
    else:
        send_func = update.message.reply_text

    logger.debug("free_packages_menu invoked")
    # Build keyboard – reuse existing util for free plans
    free_plans_markup = get_subscription_plans_keyboard(free_only=True, paid_only=False)
    logger.debug("free_packages_menu: received %s rows from get_subscription_plans_keyboard", len(free_plans_markup.inline_keyboard) if hasattr(free_plans_markup, 'inline_keyboard') else 'N/A')
    # InlineKeyboardMarkup object → underlying list is .inline_keyboard
    keyboard: list[list[InlineKeyboardButton]] = []
    # Extend keyboard with plan rows
    if hasattr(free_plans_markup, "inline_keyboard"):
        keyboard.extend(free_plans_markup.inline_keyboard)

    # If the last row is the default back-to-products button, convert it to profile-action
    if keyboard and len(keyboard[-1]) == 1 and keyboard[-1][0].callback_data == "back_to_main_menu_from_plans":
        back_button = keyboard[-1][0]
        keyboard[-1][0] = InlineKeyboardButton(back_button.text, callback_data="show_status")
    else:
        # Fallback: ensure a single back row exists pointing to profile
        keyboard.append([InlineKeyboardButton("بازگشت", callback_data="show_status")])

    # Remove any residual back button that still points to products menu
    keyboard = [row for row in keyboard if not (len(row) == 1 and row[0].callback_data == "products_menu")]

    logger.debug("free_packages_menu: final keyboard rows=%s", len(keyboard))

    try:
        await send_func(
            text="🎁 پکیج‌های رایگان موجود:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            # Message content is the same, no need to edit
            pass
        else:
            raise

# ---------------------------------------------------------------------------
# Conversation entry-point
# ---------------------------------------------------------------------------

async def start_free_package_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    user_id = update.effective_user.id
    
    # Check if user is registered before proceeding
    from utils.helpers import is_user_registered
    if not is_user_registered(user_id):
        logger.warning(f"[start_free_package_flow] Unregistered user {user_id} tried to access free package")
        text = (
            "⚠️ برای استفاده از پکیج‌های رایگان، ابتدا باید ثبت‌نام کنید.\n\n"
            "لطفاً از منوی اصلی گزینه '📝 ثبت نام' را انتخاب کنید."
        )
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 ثبت نام", callback_data="start_registration_flow")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main_menu")]
        ])
        
        if query:
            await query.message.edit_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
        return ConversationHandler.END

    msg = update.effective_message or update.effective_chat
    await msg.reply_text(
        text="لطفاً ایمیل ثبت-شده در توبیت را ارسال کنید:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩ بازگشت", callback_data="free_package_flow")]
        ])
    )
    return ASK_EMAIL


async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    context.user_data["free_pkg_email"] = email

    await update.message.reply_text(
        "اکنون UID (شناسه کاربری) خود در توبیت را ارسال کنید:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩ بازگشت", callback_data="free_package_flow")]
        ])
    )
    return ASK_UID

# ---------------------------------------------------------------------------
# Text-based entry points (triggered by ReplyKeyboard buttons)
# ---------------------------------------------------------------------------

async def start_free_package_flow_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start free package flow via text button."""
    # Delegate to the same logic
    if update.callback_query:
        await update.callback_query.answer()
    return await start_free_package_flow(update, context)

async def show_queue_position_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show queue position via text button."""
    user_id = update.effective_user.id
    pos = _queue_position(user_id)
    if pos <= 0:
        text = "✅ شما در صف انتظار نیستید یا اشتراک فعال دارید."
    else:
        text = f"📊 جایگاه فعلی شما در صف رایگان: {pos}"
    await update.message.reply_text(text)


async def receive_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.message.text.strip()
    context.user_data["free_pkg_uid"] = uid

    await update.message.reply_text("⏳ در حال بررسی شرایط…")
    return await _process_eligibility(update, context)


async def _process_eligibility(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    email = context.user_data.get("free_pkg_email")
    uid = context.user_data.get("free_pkg_uid")

    svc = ToobitService()
    referred = svc.is_user_referred_by_us(uid)
    volume = svc.get_user_total_volume(uid)

    if not referred:
        await update.message.reply_text(
            "متأسفانه حساب شما با کد معرف ما ثبت نشده است. امکان دریافت پکیج رایگان وجود ندارد.")
        return ConversationHandler.END
    if volume < 500:
        await update.message.reply_text(
            "حجم معاملات شما کمتر از ۵۰۰ دلار است. پس از رسیدن به این حد می‌توانید دوباره اقدام کنید.")
        return ConversationHandler.END

    plan_id = _ensure_free_package_plan_id()
    capacity = int(getattr(config, "FREE_PACKAGE_CAPACITY", 100))
    active_subs = _count_active_free_package_subs(plan_id)

    if active_subs >= capacity:
        _upsert_free_pkg_user(user_id, email, uid)
        position = _add_to_waitlist(user_id)
        await update.message.reply_text(
            f"ظرفیت پکیج رایگان تکمیل است. شما در صف انتظار قرار گرفتید. جایگاه فعلی شما: {position}")
        return ConversationHandler.END

    # Upsert UID/email record
    _upsert_free_pkg_user(user_id, email, uid)

    # Activate subscription
    now = get_current_time()
    db.db.execute(
        "INSERT INTO subscriptions (user_id, plan_id, start_date, end_date, amount_paid, payment_method, status, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
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

    await update.message.reply_text(
        "✅ پکیج رایگان شما فعال شد. تا زمانی که در توبیت فعال باشید، دسترسی شما برقرار خواهد بود.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("بازگشت به منوی اصلی", callback_data="back_to_main_menu")]
        ]),
    )
    return ConversationHandler.END

# ---------------------------------------------------------------------------
# Conversation handler factory
# ---------------------------------------------------------------------------

def get_free_package_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
             # Trigger via inline button callback
             CallbackQueryHandler(free_packages_menu, pattern=r"^free_package_flow$"),
             # Trigger via reply-keyboard text
             MessageHandler(filters.Regex(r"^🎁\s*پکیج\s*رایگان$"), free_packages_menu),
            CallbackQueryHandler(start_free_package_flow, pattern=r"^freepkg_toobit$"),
            
        ],
        states={
            ASK_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email),
                CallbackQueryHandler(free_packages_menu, pattern=r"^free_package_flow$")
            ],
            ASK_UID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_uid),
                CallbackQueryHandler(free_packages_menu, pattern=r"^free_package_flow$")
            ],
        },
        fallbacks=[],
        name="free_package_conversation",
        persistent=True,
    )
