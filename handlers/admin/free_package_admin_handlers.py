"""Admin utilities for managing Free Package users.

Available admin commands (manager_bot):

/freepkg_active – نمایش کاربران فعال پکیج رایگان
/freepkg_queue  – نمایش صف انتظار و جایگاه افراد
/freepkg_promote <user_id> – انتقال کاربر از صف به فعال (در صورت ظرفیت)
/freepkg_remove <user_id>  – حذف کاربر از صف انتظار
/freepkg_deactivate <user_id> – غیرفعال کردن اشتراک رایگان کاربر فعال
/freepkg_capacity <n> – تغییر ظرفیت کل پکیج رایگان
/freepkg_help – فهرست دستورات
"""
from __future__ import annotations

import logging
import config
from utils.helpers import get_current_time
from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from database.queries import DatabaseQueries as Db
from utils.helpers import is_admin

LOGGER = logging.getLogger(__name__)

PAGE_SIZE = 15

FREE_PACKAGE_PLAN_NAME = "پکیج رایگان"

db = Db()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_free_package_plan_id() -> int | None:
    row = db.db.execute("SELECT id FROM plans WHERE name = ? LIMIT 1", (FREE_PACKAGE_PLAN_NAME,)).fetchone()
    if row:
        return row[0] if isinstance(row, tuple) else row["id"]
    return None


def _fetch_active_users(plan_id: int) -> List[dict]:
    sql = (
        "SELECT u.user_id, u.username, u.full_name "
        "FROM subscriptions s "
        "JOIN users u ON u.user_id = s.user_id "
        "WHERE s.plan_id = ? AND s.status = 'active'"
    )
    db.db.execute(sql, (plan_id,))
    rows = db.db.fetchall()
    return [dict(row) if not isinstance(row, tuple) else {
        "user_id": row[0], "username": row[1], "full_name": row[2]
    } for row in rows]


def _fetch_waiting_users() -> List[dict]:
    sql = (
        "SELECT w.user_id, w.position, u.username, u.full_name "
        "FROM free_package_waitlist w "
        "LEFT JOIN users u ON u.user_id = w.user_id "
        "ORDER BY w.position"
    )
    db.db.execute(sql)
    rows = db.db.fetchall()
    result = []
    for r in rows:
        if isinstance(r, tuple):
            result.append({"user_id": r[0], "position": r[1], "username": r[2], "full_name": r[3]})
        else:
            result.append(dict(r))
    return result

# ---------------------------------------------------------------------------
# Low-level DB actions
# ---------------------------------------------------------------------------

def _remove_from_waitlist(user_id: int):
    db.db.execute("DELETE FROM free_package_waitlist WHERE user_id = ?", (user_id,))
    # Re-order positions
    db.db.execute("SELECT id FROM free_package_waitlist ORDER BY position")
    rows = db.db.fetchall()
    for new_pos, row in enumerate(rows, 1):
        db.db.execute("UPDATE free_package_waitlist SET position = ? WHERE id = ?", (new_pos, row[0]))
    db.db.commit()


def _promote_from_queue(user_id: int, plan_id: int):
    # ensure capacity
    capacity = int(getattr(config, "FREE_PACKAGE_CAPACITY", 100))
    active_cnt = len(_fetch_active_users(plan_id))
    if active_cnt >= capacity:
        return False, "ظرفیت تکمیل است."
    _remove_from_waitlist(user_id)
    now = get_current_time().isoformat(sep=" ", timespec="seconds")
    db.db.execute(
        "INSERT OR REPLACE INTO subscriptions (user_id, plan_id, start_date, amount_paid, payment_method, status, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (user_id, plan_id, now, 0, "admin_promote", "active", now, now),
    )
    db.db.commit()
    return True, "کاربر به لیست فعال منتقل شد."


def _deactivate_subscription(user_id: int, plan_id: int):
    db.db.execute(
        "UPDATE subscriptions SET status = 'cancelled', end_date = ?, updated_at = ? "
        "WHERE user_id = ? AND plan_id = ? AND status = 'active'",
        (get_current_time().isoformat(sep=" ", timespec="seconds"), get_current_time().isoformat(sep=" ", timespec="seconds"), user_id, plan_id),
    )
    db.db.commit()

# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def freepkg_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(__doc__)

def _build_nav_keyboard(prefix: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"{prefix}:{page-1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"{prefix}:{page+1}"))
    return InlineKeyboardMarkup([buttons]) if buttons else InlineKeyboardMarkup([])

# ------------------ Active users with pagination ------------------
async def freepkg_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    plan_id = _get_free_package_plan_id()
    users = _fetch_active_users(plan_id) if plan_id else []
    page = 0
    if context.args and context.args[0].isdigit():
        page = int(context.args[0])
    total_pages = max(1, (len(users) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    subset = users[start:start + PAGE_SIZE]
    lines = [f"کاربران فعال ({len(users)}) - صفحه {page+1}/{total_pages}:"]
    for u in subset:
        lines.append(f"• {u['user_id']} @{u.get('username') or ''} {u.get('full_name') or ''}")
    msg_text = "\n".join(lines) if lines else "هیچ کاربر فعالی نیست."
    if update.message:
        await update.message.reply_text(msg_text, reply_markup=_build_nav_keyboard("freepkg_active", page, total_pages))
    else:
        await update.callback_query.edit_message_text(msg_text, reply_markup=_build_nav_keyboard("freepkg_active", page, total_pages))

# ------------------ Waitlist with pagination ------------------
async def freepkg_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    users = _fetch_waiting_users()
    page = 0
    if context.args and context.args[0].isdigit():
        page = int(context.args[0])
    total_pages = max(1, (len(users) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    subset = users[start:start + PAGE_SIZE]
    lines = [f"صف انتظار ({len(users)}) - صفحه {page+1}/{total_pages}:"]
    for u in subset:
        lines.append(f"{u['position']}. {u['user_id']} @{u.get('username') or ''}")
    msg_text = "\n".join(lines) if lines else "صف خالی است."
    if update.message:
        await update.message.reply_text(msg_text, reply_markup=_build_nav_keyboard("freepkg_queue", page, total_pages))
    else:
        await update.callback_query.edit_message_text(msg_text, reply_markup=_build_nav_keyboard("freepkg_queue", page, total_pages))

async def freepkg_promote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /freepkg_promote <user_id>")
        return
    user_id = int(context.args[0])
    plan_id = _get_free_package_plan_id()
    success, msg = _promote_from_queue(user_id, plan_id)
    await update.message.reply_text(msg)

async def freepkg_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /freepkg_remove <user_id>")
        return
    _remove_from_waitlist(int(context.args[0]))
    await update.message.reply_text("کاربر از صف حذف شد.")

async def freepkg_deactivate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /freepkg_deactivate <user_id>")
        return
    user_id = int(context.args[0])
    plan_id = _get_free_package_plan_id()
    _deactivate_subscription(user_id, plan_id)
    await update.message.reply_text("اشتراک کاربر غیرفعال شد.")

async def freepkg_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /freepkg_capacity <n>")
        return
    new_cap = int(context.args[0])
    db.db.execute("UPDATE plans SET capacity = ? WHERE name = ?", (new_cap, FREE_PACKAGE_PLAN_NAME))
    db.db.commit()
    await update.message.reply_text(f"ظرفیت جدید تنظیم شد: {new_cap}")

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def get_freepkg_admin_handlers():
    return [
        CallbackQueryHandler(freepkg_active, pattern=r"^freepkg_active:\d+$"),
        CallbackQueryHandler(freepkg_queue, pattern=r"^freepkg_queue:\d+$"),
        CommandHandler("freepkg_help", freepkg_help),
        CommandHandler("freepkg_active", freepkg_active),
        CommandHandler("freepkg_queue", freepkg_queue),
        CommandHandler("freepkg_promote", freepkg_promote),
        CommandHandler("freepkg_remove", freepkg_remove),
        CommandHandler("freepkg_deactivate", freepkg_deactivate),
        CommandHandler("freepkg_capacity", freepkg_capacity),
    ]
