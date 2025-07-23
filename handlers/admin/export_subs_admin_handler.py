from __future__ import annotations

"""Export subscribers per product to Excel and send to admin via inline keyboard flow."""

from io import BytesIO
import logging
from typing import List, Tuple

import pandas as pd
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

logger = logging.getLogger(__name__)


class ExportSubsAdminHandler:
    """Provide inline-flow for admins to export subscribers list of any product as Excel."""

    ENTRY_CALLBACK = "export_subs_menu"
    PRODUCT_PREFIX = "exp_prod_"

    def __init__(self, db_queries, dispatcher=None, db_path: str | None = None, admin_ids: set[int] | None = None):
        # We accept either db_queries (preferred) or raw db_path
        self.db_queries = db_queries
        self.db_path = db_path or getattr(db_queries, "DB_PATH", "database/data/daraei_academy.db")
        self.admin_ids = admin_ids or set(getattr(db_queries, "ADMIN_IDS", []))

        if dispatcher is not None:
            self.register(dispatcher)

    # ---------------------------------------------------------------------
    # Public helpers to attach to existing AdminMenuHandler
    # ---------------------------------------------------------------------
    async def entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send product list keyboard."""
        await update.callback_query.answer()
        products = self._get_products()
        if not products:
            await update.callback_query.edit_message_text("هیچ پلنی ثبت نشده است.")
            return
        keyboard = [
            [InlineKeyboardButton(p[1][:30], callback_data=f"{self.PRODUCT_PREFIX}{p[0]}")]
            for p in products
        ]
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_main")])
        await update.callback_query.edit_message_text(
            "📥 *خروجی اکسل مشترکین*\n\nپلن را انتخاب کنید:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def handle_product(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generate excel and send back."""
        await update.callback_query.answer()
        prod_id = int(update.callback_query.data.replace(self.PRODUCT_PREFIX, ""))
        rows = self._get_subscriber_rows(prod_id)
        if not rows:
            await update.callback_query.edit_message_text("هیچ خریدی برای این پلن پیدا نشد.")
            return
        df = pd.DataFrame(rows, columns=[
            "نام کامل", "یوزرنیم", "Telegram ID", "تلفن", "ایمیل",
            "پلن", "شروع اشتراک", "پایان اشتراک", "مبلغ پرداختی", "تاریخ پرداخت"
        ])
        df.fillna('', inplace=True)
        bio = BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Subscribers")
        bio.seek(0)
        await update.callback_query.edit_message_text("در حال ارسال فایل …")
        await context.bot.send_document(
            chat_id=update.effective_user.id,
            document=bio,
            filename=f"plan_{prod_id}_subscribers.xlsx",
            caption="📊 گزارش مشترکین",
        )

    # ---------------------------------------------------------------------
    def register(self, dispatcher):
        dispatcher.add_handler(CallbackQueryHandler(self.entry, pattern=f"^{self.ENTRY_CALLBACK}$"))
        dispatcher.add_handler(CallbackQueryHandler(self.handle_product, pattern=f"^{self.PRODUCT_PREFIX}\\d+$"))

    # ---------------------------------------------------------------------
    # Database helpers
    # ---------------------------------------------------------------------
    def _run_query(self, sql: str, params: Tuple = ()) -> List[Tuple]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, params)
            return [tuple(r) for r in cur.fetchall()]

    def _get_products(self):
        return self._run_query("SELECT id, name FROM plans ORDER BY id")

    def _get_subscriber_rows(self, prod_id: int):
        query = (
            "SELECT u.full_name, IFNULL(u.username, '') AS username, u.user_id AS telegram_id, "
            "IFNULL(u.phone, '') AS phone, IFNULL(u.email, '') AS email, p.name AS plan_name, "
            "s.start_date, s.end_date, "
            "COALESCE(pay.amount, 'رایگان') AS amount_paid, "
            "COALESCE(pay.payment_date, s.start_date) AS payment_date "
            "FROM subscriptions s "
            "JOIN users u ON u.user_id = s.user_id "
            "JOIN plans p ON p.id = s.plan_id "
            "LEFT JOIN payments pay ON pay.payment_id = ( "
            "    SELECT p2.payment_id FROM payments p2 "
            "    WHERE p2.user_id = s.user_id AND p2.plan_id = s.plan_id AND p2.status = 'completed' "
            "    ORDER BY p2.payment_date DESC LIMIT 1 ) "
            "WHERE s.plan_id = ?"
        )
        return self._run_query(query, (prod_id,))
