"""Admin main menu handlers for Daraei Academy Telegram bot.
Provides a simple, localized admin panel with inline keyboards
so administrators can quickly access management features
(tickets, users, payments, broadcasts, settings)."""

import logging
from typing import Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler, CommandHandler, MessageHandler, filters, ConversationHandler
)
# Import broadcast_start for custom broadcast
from handlers.admin.broadcast_handler import broadcast_start

from utils.helpers import admin_only_decorator as admin_only
from utils.helpers import is_user_in_admin_list
from utils.admin_utils import (
    is_admin_user, is_mid_level_user, is_support_user,
    has_ticket_access, has_payment_access, has_broadcast_access, has_settings_access,
    staff_required
)
from utils.invite_link_manager import InviteLinkManager
from database.free_plan_helper import ensure_free_plan
from utils.db_backup import export_database, export_database_excel

from .admin_product_handlers import AdminProductHandler
from .admin_support_handlers import SupportUserManager
from .crypto_panel_methods import CryptoPanelMethods
from .crypto_additional_methods import CryptoAdditionalMethods

from database.queries import DatabaseQueries

logger = logging.getLogger(__name__)

# States for Ban/Unban Conversation
AWAIT_USER_ID_FOR_BAN, AWAIT_BAN_CHOICE = range(2)
# State for awaiting new promo button text
AWAIT_PROMO_TEXT = 1

class AdminMenuHandler(CryptoPanelMethods, CryptoAdditionalMethods):
    """Show an interactive admin panel and dispatch to feature modules."""

    def __init__(self, db_queries: DatabaseQueries, invite_link_manager=None, admin_config=None, main_bot_app=None):
        # Store shared DatabaseQueries instance
        self.db_queries = db_queries

        # Store invite link manager class or instance
        self.invite_link_manager = invite_link_manager

        # Save admin configuration for permission checks used by @admin_only decorator
        self.admin_config = admin_config
        
        # Store main bot application for sending broadcast messages
        self.main_bot_app = main_bot_app

        # Re-use ticket handler to show lists inside this menu (no DB object required here)
        from .admin_ticket_handlers import AdminTicketHandler
        self.ticket_handler = AdminTicketHandler()

        # Product handler needs DB access as well as optional admin config
        self.product_handler = AdminProductHandler(self.db_queries, admin_config=self.admin_config)
        # Support user manager
        self.support_manager = SupportUserManager(admin_config=self.admin_config)
        
        # Export subscribers helper
        from .admin.export_subs_admin_handler import ExportSubsAdminHandler
        self.export_handler = ExportSubsAdminHandler(db_queries)

        # Simple flag for maintenance mode toggle in misc settings
        self.maintenance_mode = False
        self.search_flag = None
        self.broadcast_flag = None

        self.button_texts = {
            'users': '👥 مدیریت کاربران',
            'products': '📦 مدیریت محصولات',
            'tickets': '🎫 مدیریت تیکت‌ها',
            'payments': '💳 مدیریت پرداخت‌ها',
            'broadcast': '📢 ارسال پیام همگانی',
            'stats': '📊 آمار کلی',
            'settings': '⚙️ تنظیمات',
            'export_subs': '📤 خروجی مشترکین',
            'promo_category': '🎯 دکمه تبلیغاتی',
            'crypto': '💰 پنل کریپتو',
            'back_to_main': '🔙 بازگشت به منوی اصلی',
        }

        self.admin_buttons_map = {
            self.button_texts['crypto']: self._crypto_panel_entry,
            self.button_texts['users']: self._users_submenu,
            self.button_texts['products']: self._products_submenu,
            self.button_texts['tickets']: self._tickets_submenu,
            self.button_texts['payments']: self._payments_submenu,
            self.button_texts['broadcast']: self._broadcast_entry_direct,
            self.button_texts['stats']: self._show_stats_handler,
            self.button_texts['settings']: self._settings_submenu,
            self.button_texts['export_subs']: self._export_subs_entry,
            self.button_texts['promo_category']: self._promo_category_entry,
            self.button_texts['back_to_main']: self.show_admin_menu,
        }

    @staff_required
    async def route_admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Routes admin commands from ReplyKeyboardMarkup clicks."""
        from utils.locale_utils import fa_to_en_digits  # localized digit support
        # If crypto panel conversation is active for this user, ignore further admin menu routing
        if context.user_data.get('crypto_active'):
            return

        command_text = fa_to_en_digits(update.message.text)
        user_id = update.effective_user.id if update.effective_user else None
        
        # Check access for different commands
        if command_text == self.button_texts['tickets'] and not has_ticket_access(user_id):
            logger.info(f"DEBUG: User {user_id} denied ticket access - admin:{is_admin_user(user_id)}, mid:{is_mid_level_user(user_id)}, support:{is_support_user(user_id)}")
            await update.message.reply_text("دسترسی محدود است.")
            return
        elif command_text == self.button_texts['payments'] and not has_payment_access(user_id):
            logger.info(f"DEBUG: User {user_id} denied payment access - admin:{is_admin_user(user_id)}, mid:{is_mid_level_user(user_id)}, support:{is_support_user(user_id)}")
            await update.message.reply_text("دسترسی محدود است.")
            return
        elif command_text == self.button_texts['broadcast'] and not has_broadcast_access(user_id):
            logger.info(f"DEBUG: User {user_id} denied broadcast access - admin:{is_admin_user(user_id)}, mid:{is_mid_level_user(user_id)}, support:{is_support_user(user_id)}")
            await update.message.reply_text("دسترسی محدود است.")
            return
        elif command_text in {self.button_texts['users'], self.button_texts['products'], self.button_texts['stats'], self.button_texts['settings'], self.button_texts['export_subs'], self.button_texts['promo_category'], self.button_texts['crypto']} and not is_admin_user(user_id):
            await update.message.reply_text("دسترسی محدود است.")
            return
        elif command_text not in self.admin_buttons_map and command_text != self.button_texts['back_to_main']:
            # Unknown command, but allow it to pass through for potential future expansion
            pass
        function_to_call = self.admin_buttons_map.get(command_text)

        if not function_to_call:
            return

        # Handlers like _users_submenu expect a 'query' object.
        # Handlers like show_admin_menu expect 'update' and 'context'.
        # We create a dummy query object to bridge this gap.
        class DummyQuery:
            def __init__(self, message):
                self.message = message

            async def answer(self):
                pass  # No-op

            async def edit_message_text(self, *args, **kwargs):
                # For reply keyboards, we send a new message instead of editing.
                await self.message.reply_text(*args, **kwargs)

        # Check the function signature to decide how to call it.
        import inspect
        sig = inspect.signature(function_to_call)
        if len(sig.parameters) > 1: # Assumes (self, update, context)
            await function_to_call(update, context)
        else: # Assumes (self, query)
            await function_to_call(DummyQuery(update.message))

    async def _export_subs_entry(self, query):
        """Entry point: delegate to ExportSubsAdminHandler.entry"""
        # ExportSubsAdminHandler expects an object with .callback_query attribute like Update.
        from types import SimpleNamespace
        dummy_update = SimpleNamespace(callback_query=query)
        await self.export_handler.entry(dummy_update, None)

    async def _crypto_panel_entry(self, query):
        """Entry point for the crypto admin keyboard panel (reply keyboard version)."""
        from handlers.admin_crypto_keyboard import AdminCryptoKeyboard
        from types import SimpleNamespace

        # Acknowledge (dummy for ReplyKeyboard)
        if hasattr(query, 'answer'):
            await query.answer()

        # Ensure crypto_active flag so other admin handlers ignore messages
        from telegram.ext import ContextTypes
        if hasattr(query, 'context'):
            context = query.context
        else:
            context = ContextTypes.DEFAULT_TYPE()
            context.user_data = {}
        context.user_data['crypto_active'] = True

        # ارسال پیام خوش‌آمد و آغاز گفت‌وگو
        from types import SimpleNamespace
        from handlers.admin_crypto_keyboard import AdminCryptoKeyboard
        dummy_update = SimpleNamespace(callback_query=query)
        await AdminCryptoKeyboard.start_admin_panel(dummy_update, context)
        return

    async def _promo_category_entry(self, query):
        """Entry point for promotional category management"""
        from handlers.admin_promotional_category import show_promotional_category_admin
        from types import SimpleNamespace
        # Create a dummy update object with callback_query
        dummy_update = SimpleNamespace(callback_query=query)
        await show_promotional_category_admin(dummy_update, None)

    async def _show_stats_handler(self, query):
        """
        Display comprehensive and useful system statistics.
        Designed to be called from a reply keyboard.
        """
        try:
            from datetime import datetime, timedelta
            import sqlite3
            
            # Get current datetime for calculations
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=7)
            month_start = today_start - timedelta(days=30)
            
            # Gather comprehensive statistics
            message_text = "📊 <b>آمار جامع سیستم</b>\n\n"
            
            # === User Statistics ===
            try:
                total_users = DatabaseQueries.get_total_users_count() or 0
                active_users = DatabaseQueries.get_active_users_count() or 0
                
                # Get today's new users (if method exists)
                try:
                    today_users = DatabaseQueries.get_users_count_since(today_start.isoformat()) or 0
                except:
                    today_users = 0
                    
                message_text += "👥 <b>آمار کاربران:</b>\n"
                message_text += f"• کل کاربران: <code>{total_users:,}</code>\n"
                message_text += f"• کاربران فعال: <code>{active_users:,}</code>\n"
                if today_users > 0:
                    message_text += f"• عضویت امروز: <code>{today_users:,}</code>\n"
                if total_users > 0:
                    activity_rate = (active_users / total_users * 100)
                    message_text += f"• نرخ فعالیت: <code>{activity_rate:.1f}%</code>\n"
                message_text += "\n"
            except Exception as e:
                logger.error(f"Error getting user stats: {e}")
                message_text += "👥 <b>آمار کاربران:</b> خطا در دریافت اطلاعات\n\n"
            
            # === Subscription Statistics ===
            try:
                # Get all plans and their subscription counts
                plans = DatabaseQueries.get_all_plans() or []
                total_active_subs = 0
                total_expired_subs = 0
                plan_details = []
                
                for plan in plans:
                    if isinstance(plan, dict):
                        plan_id = plan.get('id')
                        plan_name = plan.get('name', 'نامشخص')
                    else:
                        plan_id = plan[0] if len(plan) > 0 else None
                        plan_name = plan[1] if len(plan) > 1 else 'نامشخص'
                    
                    if plan_id:
                        try:
                            active_count = DatabaseQueries.count_subscriptions_for_plan(plan_id) or 0
                            total_count = DatabaseQueries.count_total_subscriptions_for_plan(plan_id) or 0
                            expired_count = total_count - active_count
                            
                            total_active_subs += active_count
                            total_expired_subs += expired_count
                            
                            if total_count > 0:
                                plan_details.append({
                                    'name': plan_name,
                                    'active': active_count,
                                    'total': total_count
                                })
                        except:
                            continue
                
                message_text += "📋 <b>آمار اشتراک‌ها:</b>\n"
                message_text += f"• اشتراک‌های فعال: <code>{total_active_subs:,}</code>\n"
                message_text += f"• اشتراک‌های منقضی: <code>{total_expired_subs:,}</code>\n"
                
                # Show top plans
                if plan_details:
                    plan_details.sort(key=lambda x: x['active'], reverse=True)
                    message_text += "\n<b>محبوب‌ترین پلان‌ها:</b>\n"
                    for i, plan in enumerate(plan_details[:3], 1):
                        message_text += f"{i}. {plan['name']}: <code>{plan['active']}</code> فعال\n"
                
                message_text += "\n"
            except Exception as e:
                logger.error(f"Error getting subscription stats: {e}")
                message_text += "📋 <b>آمار اشتراک‌ها:</b> خطا در دریافت اطلاعات\n\n"
            
            # === Payment Statistics ===
            try:
                # Compute payment statistics directly from DB (supports both payments and crypto_payments)
                total_payments = 0
                successful_payments = 0
                total_revenue = 0.0  # IRR

                from database.models import Database
                db = Database()
                cursor = db.conn.cursor()

                # Total payment attempts
                try:
                    cursor.execute("SELECT COUNT(*) FROM payments")
                    total_payments += cursor.fetchone()[0] or 0
                except Exception:
                    pass
                try:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crypto_payments'")
                    if cursor.fetchone():
                        cursor.execute("SELECT COUNT(*) FROM crypto_payments")
                        total_payments += cursor.fetchone()[0] or 0
                except Exception:
                    pass

                # Successful payments
                try:
                    cursor.execute("SELECT COUNT(*) FROM payments WHERE status IN ('paid','completed','successful','verified')")
                    successful_payments += cursor.fetchone()[0] or 0
                except Exception:
                    pass
                try:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crypto_payments'")
                    if cursor.fetchone():
                        cursor.execute("SELECT COUNT(*) FROM crypto_payments WHERE status IN ('paid','paid-late','completed','successful','verified')")
                        successful_payments += cursor.fetchone()[0] or 0
                except Exception:
                    pass

                # Total IRR revenue
                try:
                    cursor.execute("SELECT SUM(amount) FROM payments WHERE status IN ('paid','completed','successful','verified') AND amount IS NOT NULL AND amount > 0")
                    res = cursor.fetchone()[0]
                    if res:
                        total_revenue += float(res)
                except Exception:
                    pass
                try:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='crypto_payments'")
                    if cursor.fetchone():
                        cursor.execute("SELECT SUM(rial_amount) FROM crypto_payments WHERE status IN ('paid','paid-late','completed','successful','verified') AND rial_amount IS NOT NULL AND rial_amount > 0")
                        res = cursor.fetchone()[0]
                        if res:
                            total_revenue += float(res)
                except Exception:
                    pass

                message_text += "💰 <b>آمار مالی:</b>\n"
                message_text += f"• کل پرداخت‌ها: <code>{total_payments:,}</code>\n"
                if total_payments > 0:
                    success_rate = (successful_payments / total_payments * 100)
                    message_text += f"• نرخ موفقیت: <code>{success_rate:.1f}%</code>\n"
                message_text += f"• کل درآمد: <code>{total_revenue:,.0f}</code> تومان\n"

                if total_payments > 0:
                    avg_payment = total_revenue / total_payments
                    message_text += f"• میانگین پرداخت: <code>{avg_payment:,.0f}</code> تومان\n"

                message_text += "\n"
            except Exception as e:
                logger.error(f"Error getting payment stats: {e}")
                message_text += "💰 <b>آمار مالی:</b> خطا در دریافت اطلاعات\n\n"
            
            # === Ticket Statistics ===
            try:
                pending_tickets = DatabaseQueries.get_pending_tickets_count() or 0
                total_tickets = DatabaseQueries.get_total_tickets_count() or 0
                closed_tickets = total_tickets - pending_tickets
                
                message_text += "🎫 <b>آمار تیکت‌ها:</b>\n"
                message_text += f"• در انتظار پاسخ: <code>{pending_tickets:,}</code>\n"
                message_text += f"• بسته شده: <code>{closed_tickets:,}</code>\n"
                message_text += f"• کل تیکت‌ها: <code>{total_tickets:,}</code>\n"
                
                if total_tickets > 0:
                    resolution_rate = (closed_tickets / total_tickets * 100)
                    message_text += f"• نرخ حل شده: <code>{resolution_rate:.1f}%</code>\n"
                
                message_text += "\n"
            except Exception as e:
                logger.error(f"Error getting ticket stats: {e}")
                message_text += "🎫 <b>آمار تیکت‌ها:</b> خطا در دریافت اطلاعات\n\n"
            
            # === System Health ===
            try:
                import os
                import psutil
                
                # Get system info if available
                try:
                    cpu_percent = psutil.cpu_percent(interval=1)
                    memory = psutil.virtual_memory()
                    disk = psutil.disk_usage('/')
                    
                    message_text += "⚡ <b>وضعیت سیستم:</b>\n"
                    message_text += f"• CPU: <code>{cpu_percent:.1f}%</code>\n"
                    message_text += f"• RAM: <code>{memory.percent:.1f}%</code> استفاده\n"
                    message_text += f"• دیسک: <code>{disk.percent:.1f}%</code> استفاده\n"
                    message_text += "\n"
                except ImportError:
                    # psutil not available
                    message_text += "⚡ <b>وضعیت سیستم:</b> 🟢 آنلاین\n\n"
                except:
                    message_text += "⚡ <b>وضعیت سیستم:</b> 🟢 آنلاین\n\n"
                    
            except Exception as e:
                logger.error(f"Error getting system stats: {e}")
                message_text += "⚡ <b>وضعیت سیستم:</b> 🟢 آنلاین\n\n"
            
            # === Footer ===
            message_text += f"🕐 <b>آخرین بروزرسانی:</b> {now.strftime('%H:%M:%S')}\n"
            message_text += "📱 <b>وضعیت بات:</b> 🟢 فعال"
            
            # Send the comprehensive stats
            if hasattr(query, 'message') and query.message:
                await query.message.reply_text(message_text, parse_mode="HTML")
            else:
                logger.warning("Could not send stats reply, query object lacks 'message'.")
                
        except Exception as e:
            logger.error(f"Error in _show_stats_handler: {e}")
            error_msg = (
                "❌ <b>خطا در دریافت آمار</b>\n\n"
                "ممکن است برخی از داده‌ها در دسترس نباشند.\n"
                "لطفاً دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
            )
            if hasattr(query, 'message') and query.message:
                await query.message.reply_text(error_msg, parse_mode="HTML")

    """Show an interactive admin panel and dispatch to feature modules."""

    # Callback data constants
    TICKETS_MENU = "admin_tickets_menu"
    USERS_MENU = "admin_users_menu"
    FREE20_CALLBACK = "users_free20"
    CREATE_INVITE_LINK = "users_create_invite_link"
    PAYMENTS_MENU = "admin_payments_menu"
    BROADCAST_MENU = "admin_broadcast_menu"
    EXPORT_SUBS_MENU = "admin_export_subs"
    BROADCAST_ACTIVE = "broadcast_active"
    BROADCAST_ALL = "broadcast_all"
    BROADCAST_WITH_LINK = "broadcast_with_link"
    BROADCAST_WL_ACTIVE = "broadcast_wl_active"
    BROADCAST_WL_ALL = "broadcast_wl_all"
    BROADCAST_CANCEL = "broadcast_cancel"
    SETTINGS_MENU = "admin_settings_menu"
    PRODUCTS_MENU = "admin_products_menu"
    BACKUP_CALLBACK = "settings_backup_json"
    BACKUP_XLSX_CALLBACK = "settings_backup_xlsx"
    SUPPORT_MENU = "settings_support_users"
    SUPPORT_ADD = "settings_support_add"
    SUPPORT_LIST = "settings_support_list"
    BACK_MAIN = "admin_back_main"
    TICKETS_HISTORY = "tickets_history_input"
    MAIN_MENU_CALLBACK = BACK_MAIN
    BAN_UNBAN_USER = "users_ban_unban"
    EXTEND_SUB_CALLBACK = "users_extend_subscription"
    EXTEND_SUB_ALL_CALLBACK = "users_extend_all_subscription"
    CHECK_SUB_STATUS = "users_check_subscription"

    # Conversation states
    (GET_INVITE_LINK_USER_ID,) = range(100, 101)
    (AWAIT_BROADCAST_MESSAGE, AWAIT_BROADCAST_CONFIRMATION) = range(101, 103)
    (AWAIT_FREE20_USER_ID,) = range(103, 104)
    (AWAIT_USER_ID_FOR_BAN, AWAIT_BAN_CHOICE) = range(104, 106)
    (AWAIT_EXTEND_USER_ID, AWAIT_EXTEND_DAYS) = range(106, 108)
    (AWAIT_CHECK_USER_ID,) = range(108, 109)
    (AWAIT_EXTEND_ALL_DAYS,) = range(109, 110)

    @staff_required
    async def show_admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Entry command `/admin` – show main panel."""
        user_id = update.effective_user.id if update.effective_user else None
        
        # Build keyboard based on user access level
        keyboard = []
        
        # First row: Always include tickets for all staff
        first_row = []
        if has_ticket_access(user_id):
            first_row.append(InlineKeyboardButton("🎫 مدیریت تیکت‌ها", callback_data=self.TICKETS_MENU))
        
        # Admin-only buttons in first row
        if is_admin_user(user_id):
            first_row.append(InlineKeyboardButton("👥 مدیریت کاربران", callback_data=self.USERS_MENU))
        
        if first_row:
            keyboard.append(first_row)
        
        # Second row: Payments and Products
        second_row = []
        if has_payment_access(user_id):
            second_row.append(InlineKeyboardButton("💳 مدیریت پرداخت‌ها", callback_data=self.PAYMENTS_MENU))
        
        if is_admin_user(user_id):
            second_row.append(InlineKeyboardButton("📦 مدیریت محصولات", callback_data=self.PRODUCTS_MENU))
        
        if second_row:
            keyboard.append(second_row)
        
        # Third row: Crypto panel and Broadcast (admin + mid-level)
        third_row = []
        if is_admin_user(user_id):
            third_row.append(InlineKeyboardButton("💰 پنل کریپتو", callback_data="crypto_panel"))
        
        if has_broadcast_access(user_id):
            third_row.append(InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="broadcast_custom"))
        
        if third_row:
            keyboard.append(third_row)
        
        # Fourth row: Export and Settings (admin only)
        fourth_row = []
        if is_admin_user(user_id):
            fourth_row.append(InlineKeyboardButton("📤 خروجی مشترکین", callback_data=self.EXPORT_SUBS_MENU))
            fourth_row.append(InlineKeyboardButton("⚙️ تنظیمات", callback_data=self.SETTINGS_MENU))
        
        if fourth_row:
            keyboard.append(fourth_row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Check if we are editing a message (from a callback) or sending a new one
        if update.callback_query:
            await update.callback_query.edit_message_text("⚡️ *پنل مدیریت*\nیکی از گزینه‌های زیر را انتخاب کنید:", parse_mode="Markdown", reply_markup=reply_markup)
        else:
            await update.message.reply_text("⚡️ *پنل مدیریت*\nیکی از گزینه‌های زیر را انتخاب کنید:", parse_mode="Markdown", reply_markup=reply_markup)

    # ---------- Menu callbacks ----------
    @staff_required
    async def admin_menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = query.from_user.id
        is_admin_flag = is_user_in_admin_list(user_id, self.admin_config)
        is_mid_level = is_mid_level_user(user_id)
        support_allowed_callbacks = {
            self.TICKETS_MENU, self.PAYMENTS_MENU,
            "tickets_open", "tickets_all",
            "payments_recent", "payments_stats",
            "product_sales_reports", "product_sales_list",
            self.TICKETS_HISTORY,
            self.BACK_MAIN
        }
        
        # Broadcast-related callbacks for mid-level users
        broadcast_callbacks = {
            "broadcast_custom", "broadcast_continue", "broadcast_cancel",
            self.BROADCAST_MENU, self.BROADCAST_WITH_LINK,
            self.BROADCAST_WL_ACTIVE, self.BROADCAST_WL_ALL
        }
        
        # Check if user has access to this callback
        has_access = (
            is_admin_flag or 
            data in support_allowed_callbacks or 
            data.startswith("product_sales_") or
            (is_mid_level and (
                data in broadcast_callbacks or
                data.startswith("bc_plan_") or
                data.startswith("bc_cat_") or
                data.startswith("bc_chan_") or
                data.startswith("broadcast_")
            ))
        )
        logging.info(f"DEBUG: user_id={user_id}, is_admin={is_admin_flag}, is_mid_level={is_mid_level}, data={data}, has_access={has_access}")
        if not has_access:
            await query.answer("دسترسی محدود است.", show_alert=True)
            return

        logger.debug("Admin menu callback: %s", data)
        logger.info(f"DEBUG: callback={data}, bc_flow={context.user_data.get('bc_flow')}, user_data_keys={list(context.user_data.keys())}")

        if data == self.TICKETS_MENU:
            await self._tickets_submenu(query)
        elif data == self.TICKETS_HISTORY:
            await query.edit_message_text("🔎 لطفاً شمارهٔ موبایل (مثلاً +98912...) کاربر را ارسال کنید:")
            context.user_data["awaiting_ticket_history_user"] = True
        elif data == self.USERS_MENU:
            await self._users_submenu(query)
        elif data == self.PAYMENTS_MENU:
            await self._payments_submenu(query)
        elif data == self.EXPORT_SUBS_MENU:
            await self.export_handler.entry(update, context)
        elif data.startswith("exp_prod_"):
            await self.export_handler.handle_product(update, context)
        elif data == "crypto_panel":
            await self._crypto_panel_entry(query, context)

        elif data == self.BROADCAST_MENU:
            await self._broadcast_submenu(query)
        elif data == self.BROADCAST_WITH_LINK:
            await self._broadcast_wl_choose_audience(query)
        elif data == self.BROADCAST_WL_ACTIVE:
            await self._broadcast_wl_ask_content(query, context, target="active")
        elif data == self.BROADCAST_WL_ALL:
            await self._broadcast_wl_ask_content(query, context, target="all")
        elif data.startswith("chpick_"):
            await self._broadcast_wl_picker_callback(query, context)
        elif data == self.BROADCAST_CANCEL:
            await self._broadcast_wl_cancel(query, context)
        elif data == "users_list_active":
            await self._show_active_users(query)
        elif data == self.SETTINGS_MENU:
            await self._settings_submenu(query)
        elif data == self.PRODUCTS_MENU:
            await self._products_submenu(query)
        # ----- Product submenu actions -----
        elif data == "products_list":
            await self.product_handler._show_all_plans(query)
        elif data == "products_show_all":
            await self.product_handler._show_all_plans(query)
        elif data.startswith("view_plan_"):
            plan_id = int(data.split("_")[2])
            await self.product_handler._show_single_plan(query, plan_id)
        elif data.startswith("toggle_plan_active_"):
            plan_id = int(data.rsplit("_", 1)[1])
            await self.product_handler.toggle_plan_status(query, plan_id)
        elif data.startswith("toggle_plan_public_"):
            plan_id = int(data.rsplit("_", 1)[1])
            await self.product_handler.toggle_plan_visibility(query, plan_id)
        elif data.startswith("delete_plan_confirm_"):
            # confirmation button already includes 'confirm'
            plan_id = int(data.rsplit("_", 1)[1])
            await self.product_handler.delete_plan_confirmation(query, plan_id)
        elif data.startswith("delete_plan_"):
            # initial delete request from single-plan view
            plan_id = int(data.rsplit("_", 1)[1])
            await self.product_handler.delete_plan_confirmation(query, plan_id)
        elif data.startswith("confirm_delete_plan_"):
            plan_id = int(data.rsplit("_", 1)[1])
            await self.product_handler.delete_plan(query, plan_id)
        # ----- Product sales report actions -----
        elif data == "products_sales_reports":
            await self._show_products_sales_reports(query)
        elif data.startswith("sales_report_"):
            plan_id = int(data.split("_", 2)[2])
            await self._show_product_sales_report(query, plan_id)
        elif data.startswith("sales_details_"):
            plan_id = int(data.split("_", 2)[2])
            await self._show_product_sales_details(query, plan_id)
        elif data == self.BACK_MAIN:
            await self.show_admin_menu(update, context)
        # ----- Ticket submenu actions -----
        elif data == "tickets_open":
            await self.ticket_handler._show_tickets_inline(query)
        elif data == "tickets_all":
            await self.ticket_handler._show_all_tickets_inline(query)
        # ----- Users submenu actions -----
        elif data == "users_active":
            await self._show_active_users(query)
        elif data == "users_search":
            # Ask admin for search term
            await query.edit_message_text("🔎 لطفاً نام کاربری، نام یا آیدی عددی کاربر را ارسال کنید:")
            context.user_data["awaiting_user_search_query"] = True
        elif data == self.FREE20_CALLBACK:
            # Start free 20-day activation flow
            await query.edit_message_text("🎁 لطفاً نام کاربری (بدون @) یا آیدی عددی کاربر را ارسال کنید:")
            context.user_data["awaiting_free20_user"] = True
        elif data == self.BAN_UNBAN_USER:
            await self.ban_unban_start(update, context)
        # ----- Payments submenu actions -----
        elif data == "payments_recent":
            await self._show_recent_payments_inline(query)
        elif data == "payments_stats":
            await self._show_payments_stats(query)
        elif data == "product_sales_reports":
            logging.info("DEBUG: product_sales_reports callback received")
            await self._show_product_sales_reports_menu(query)
        elif data == "product_sales_list":
            await self._show_product_sales_list(query)
        elif data.startswith("product_sales_detail_"):
            plan_id = int(data.split("_", 3)[3])
            await self._show_product_sales_detail(query, plan_id)
        elif data.startswith("payment_info_"):
            pid = data.split("_", 2)[2]
            await self._show_payment_details(query, pid)
        elif data == "payments_search":
            await query.edit_message_text("🔎 لطفاً شناسه پرداخت یا هش تراکنش را ارسال کنید:")
            context.user_data["awaiting_payment_search"] = True
            await self._show_recent_payments(query)
        elif data == "payments_export_excel":
            await self._export_payments_excel(query, context)
        elif data == "payments_stats":
            await self._show_payments_stats(query)
        # ----- Crypto panel actions -----
        elif data == "crypto_system_status":
            await self._show_crypto_system_status(query)
        elif data == "crypto_payment_stats":
            await self._show_crypto_payment_stats(query)
        elif data == "crypto_security":
            await self._show_crypto_security(query)
        elif data == "crypto_reports":
            await self._show_crypto_reports(query)
        elif data == "crypto_wallet_info":
            await self._show_crypto_wallet_info(query)
        elif data == "crypto_manual_tx":
            await self._show_crypto_manual_tx(query)
        elif data == "crypto_verify_payments":
            await self._show_crypto_verify_payments(query)
        # ----- Crypto sub-menu actions -----
        elif data == "crypto_report_daily":
            await self._show_crypto_report_daily(query)
        elif data == "crypto_report_weekly":
            await self._show_crypto_report_weekly(query)
        elif data == "crypto_report_monthly":
            await self._show_crypto_report_monthly(query)
        elif data == "crypto_payment_details":
            await self._show_crypto_payment_details(query)
        elif data == "crypto_security_logs":
            await self._show_crypto_security_logs(query)
        elif data == "crypto_wallet_history":
            await self._show_crypto_wallet_history(query)
        elif data == "crypto_verify_history":
            await self._show_crypto_verify_history(query)
        elif data == "crypto_check_txid":
            await self._show_crypto_check_txid(query)
        elif data == "crypto_test_connection":
            await self._show_crypto_test_connection(query)
        elif data == "crypto_simulate_payment":
            await self._show_crypto_simulate_payment(query)
        elif data == "crypto_validate_address":
            await self._show_crypto_validate_address(query)
        # ----- Discounts submenu actions -----
        elif data == "discounts_menu":
            await self._discounts_submenu(query)
        elif data == "discounts_add":
            # Start inline create discount flow
            context.user_data["discount_flow"] = {"mode":"create","state":"await_code","data":{}}
            await query.edit_message_text("🆕 لطفاً کد تخفیف را ارسال کنید (حروف و اعداد لاتین).")
        elif data == "discounts_list":
            await self._list_discounts(query)
        elif data.startswith("view_discount_"):
            did = int(data.split("_")[2])
            await self._show_single_discount(query, did)
        elif data.startswith("edit_discount_") or data.startswith("discounts_edit_"):
            # Support both 'edit_discount_' and legacy 'discounts_edit_' prefixes
            did = int(data.split("_")[-1])
            context.user_data["discount_flow"] = {"mode":"edit","discount_id":did,"state":"await_value","data":{}}
            await query.edit_message_text(
                "✏️ مقدار و نوع جدید را ارسال کنید به فرم 'percentage 10' یا 'fixed 50000':\n\nیا دکمه ⏭️ بدون تغییر را بزنید.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏭️ بدون تغییر", callback_data="discount_edit_skip")],
                    [InlineKeyboardButton("🔙 بازگشت", callback_data=f"view_discount_{did}")]
                ])
            )
        elif data.startswith("toggle_discount_"):
            did = int(data.split("_")[2])

            await self._toggle_discount_status(query, did)
        elif data.startswith("delete_discount_"):
            did = int(data.split("_")[2])
            await self._delete_discount_confirmation(query, did)
        elif data.startswith("planpick_") or data in ("planpick_all", "planpick_done"):
            try:
                # Extract plan ID if it exists and is numeric
                if data.startswith("planpick_") and not data in ("planpick_all", "planpick_done"):
                    parts = data.split("_")
                    if len(parts) > 1 and not parts[1].isdigit() and parts[1] not in ["all", "done"]:
                        logger.warning(f"Invalid planpick callback data: {data}")
                        await query.answer("❌ شناسه پلن نامعتبر است.", show_alert=True)
                        return
                await self._handle_plan_select_callback(query, context)
            except Exception as e:
                logger.error(f"Error in planpick callback: {e}", exc_info=True)
                await query.answer("❌ خطا در پردازش درخواست", show_alert=True)
        elif data.startswith("confirm_delete_discount_"):
            did = int(data.split("_")[3])
            await self._delete_discount(query, did)
            await self._list_discounts(query)
        elif data == "discount_edit_skip":
            # Skip edit and return to discount details
            df = context.user_data.get("discount_flow")
            if df and df.get("mode") == "edit":
                did = df.get("discount_id")
                context.user_data.pop("discount_flow", None)
                await self._show_single_discount(query, did)
            else:
                await query.answer("❌ عملیات نامعتبر", show_alert=True)
        # ----- Settings submenu actions -----
        elif data == "settings_admins":
            await self._show_admins_settings(query)
        elif data == self.BACKUP_CALLBACK:
            # generate and send JSON backup
            bio = export_database()
            if bio:
                bio.seek(0)
                await context.bot.send_document(chat_id=query.from_user.id, document=bio, filename="db_backup.json")
                await query.answer("📤 بکاپ JSON ارسال شد")
            else:
                await query.answer("❌ خطا در تهیه بکاپ JSON", show_alert=True)
        elif data == self.BACKUP_XLSX_CALLBACK:
            bio = export_database_excel()
            if bio:
                bio.seek(0)
                await context.bot.send_document(chat_id=query.from_user.id, document=bio, filename="db_backup.xlsx")
                await query.answer("📤 بکاپ اکسل ارسال شد")
            else:
                await query.answer("❌ خطا در تهیه بکاپ اکسل", show_alert=True)
        elif data == self.SUPPORT_MENU:
            await self._settings_support_submenu(query)
        elif data == self.SUPPORT_ADD:
             # Begin inline flow to add support user
             await query.edit_message_text("➕ لطفاً آیدی عددی تلگرام کاربر پشتیبان را ارسال کنید:")
             context.user_data["awaiting_support_user_id"] = True
        elif data == self.SUPPORT_LIST:
            await self._show_support_users(query)
        elif data == "settings_toggle_discount_step":
            current = DatabaseQueries.get_setting("enable_discount_code_step", "1")
            new_value = "0" if current == "1" else "1"
            DatabaseQueries.set_setting("enable_discount_code_step", new_value)
            await query.answer("به‌روزرسانی شد")
            await self._settings_submenu(query)
        elif data == "settings_misc":
            await self._settings_misc_submenu(query)
        elif data == "settings_toggle_maintenance":
            # Toggle the flag
            self.maintenance_mode = not self.maintenance_mode
            await query.answer("به‌روزرسانی شد")
            await self._settings_misc_submenu(query)
        # ----- Broadcast submenu actions -----
        elif data in (self.BROADCAST_ACTIVE, self.BROADCAST_ALL):
            # Set broadcast target and ask for content
            target_label = "کاربران فعال" if data == self.BROADCAST_ACTIVE else "تمامی کاربران ثبت‌نام‌شده"
            context.user_data["broadcast_target"] = "active" if data == self.BROADCAST_ACTIVE else "all"
            await query.edit_message_text(f"✉️ لطفاً پیام مورد نظر خود را ارسال کنید. پس از ارسال، پیام به‌صورت خودکار برای {target_label} فوروارد خواهد شد.")
            context.user_data["awaiting_broadcast_content"] = True
        elif data == self.BACK_MAIN:
            # Just recreate the main admin menu correctly
            await self.show_admin_menu(update, context)
        elif data == "broadcast_custom":
            # جریان پیام همگانی با دکمه محصول/دسته
            await query.answer()
            from handlers.admin.broadcast_handler import broadcast_start  # local import to avoid circular
            # علامت گذاری فعال بودن جریان
            context.user_data["bc_flow"] = True
            # start flow and set flag to capture next message
            await broadcast_start(update=update, context=context)
            return
        elif context.user_data.get("bc_flow") and data in {"broadcast_add", "broadcast_send", "broadcast_cancel"}:
            logger.info(f"Routing broadcast menu callback: {data}")
            from handlers.admin.broadcast_handler import menu_callback
            await menu_callback(update, context)
            return
        elif context.user_data.get("bc_flow") and (
            data.startswith("bc_cat_") or data.startswith("bc_plan_") or data.startswith("bc_chan_")
        ):
            logger.info(f"Routing broadcast add_select callback: {data}")
            from handlers.admin.broadcast_handler import add_select_callback
            await add_select_callback(update, context)
            return
        elif context.user_data.get("bc_flow") and data in {"audience_active", "audience_all"}:
            logger.info(f"Routing broadcast audience callback: {data}")
            from handlers.admin.broadcast_handler import audience_callback
            await audience_callback(update, context)
            return
        elif context.user_data.get("bc_flow"):
            # Catch-all for any other broadcast callbacks
            logger.info(f"Routing other broadcast callback: {data}")
            from handlers.admin.broadcast_handler import add_select_callback
            await add_select_callback(update, context)
            return
        else:
            await query.answer("دستور ناشناخته!", show_alert=True)

    # ---------- Helper for users ----------
    async def _show_active_users(self, query):
        """Show list of active users (simple version)."""
        try:
            users = DatabaseQueries.get_all_active_subscribers()
            if not users:
                await query.edit_message_text("📋 هیچ کاربر فعالی یافت نشد.")
                return
            message_lines = ["📋 *لیست کاربران فعال:*\n"]
            for u in users[:30]:
                # Depending on the returned row type (sqlite3.Row or tuple/dict), access safely
                try:
                    user_id = u['user_id'] if isinstance(u, dict) else u[0]
                    full_name = u.get('full_name') if isinstance(u, dict) else (u[1] if len(u) > 1 else "")
                except Exception:
                    user_id = u[0] if isinstance(u, (list, tuple)) else getattr(u, 'user_id', 'N/A')
                    full_name = getattr(u, 'full_name', '')
                line = f"• {full_name} – {user_id}"
                message_lines.append(line)
            await query.edit_message_text("\n".join(message_lines), parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error showing active users: {e}")
            await query.edit_message_text("❌ خطا در نمایش کاربران فعال.")

    # ---------- Sub-menus ----------
    async def _tickets_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("🟢 تیکت‌های منتظر پاسخ", callback_data="tickets_open"), InlineKeyboardButton("📜 همهٔ تیکت‌ها", callback_data="tickets_all")],
            [InlineKeyboardButton("🔎 تاریخچهٔ تیکت کاربر", callback_data=self.TICKETS_HISTORY), InlineKeyboardButton("📄 خروجی تیکت‌ها", callback_data="export_all_tickets")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("🎫 *مدیریت تیکت‌ها*\nگزینه مورد نظر را انتخاب کنید:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _users_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("🔗 لینک دعوت", callback_data=self.CREATE_INVITE_LINK), InlineKeyboardButton("➕ افزایش اشتراک", callback_data=self.EXTEND_SUB_CALLBACK)],
            [InlineKeyboardButton("➕ افزایش همگانی", callback_data=self.EXTEND_SUB_ALL_CALLBACK)],
            [InlineKeyboardButton("📆 مشاهده اعتبار", callback_data=self.CHECK_SUB_STATUS), InlineKeyboardButton("📋 کاربران فعال", callback_data="users_list_active")],
            [InlineKeyboardButton("🔎 جستجوی کاربر", callback_data="users_search"), InlineKeyboardButton("🛑 مسدود/آزاد کردن", callback_data=self.BAN_UNBAN_USER)],
            [InlineKeyboardButton("🎁 فعال‌سازی ۲۰ روزه رایگان", callback_data=self.FREE20_CALLBACK)],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("👥 *مدیریت کاربران*:\nچه کاری می‌خواهید انجام دهید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _payments_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("💰 تراکنش‌های اخیر", callback_data="payments_recent"), InlineKeyboardButton("🔍 جستجوی پرداخت", callback_data="payments_search")],
            [InlineKeyboardButton("📊 گزارش فروش محصولات", callback_data="product_sales_reports")],
            [InlineKeyboardButton("📤 خروجی مشترکین", callback_data=self.EXPORT_SUBS_MENU), InlineKeyboardButton("📈 آمار اشتراک‌ها", callback_data="payments_stats")],
            [InlineKeyboardButton("📤 خروجی اکسل پرداخت‌ها", callback_data="payments_export_excel")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("💳 *مدیریت پرداخت‌ها*:\nچه کاری می‌خواهید انجام دهید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _broadcast_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("✉️ ارسال پیام همگانی", callback_data="broadcast_send")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("📢 *ارسال پیام همگانی*:\nمی‌خواهید یک پیام برای همه کاربران ارسال کنید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _products_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("➕ محصول جدید", callback_data="products_add"), InlineKeyboardButton("📜 محصولات", callback_data="products_list")],
            [InlineKeyboardButton("📂 مدیریت دسته‌بندی‌ها", callback_data="manage_categories")],
            [InlineKeyboardButton("آلت‌سیزن", callback_data="altseason_admin")],
            [InlineKeyboardButton("📈 گزارش فروش محصولات", callback_data="product_sales_reports")],
            [InlineKeyboardButton("💰 پنل کریپتو", callback_data="crypto_panel")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("📦 *مدیریت محصولات*:\nچه کاری می‌خواهید انجام دهید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _discounts_submenu(self, query):
        keyboard = [
            [InlineKeyboardButton("➕ کد تخفیف جدید", callback_data="discounts_add"), InlineKeyboardButton("📜 کدهای تخفیف", callback_data="discounts_list")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("💸 *مدیریت کدهای تخفیف*:\nچه کاری می‌خواهید انجام دهید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _list_discounts(self, query):
        """Lists all discount codes with simple view."""
        discounts = DatabaseQueries.get_all_discounts()
        if not discounts:
            # query may be CallbackQuery or DummyQuery; fall back to reply_text if needed
            if hasattr(query, "edit_message_text"):
                await query.edit_message_text("هیچ کد تخفیفی یافت نشد.")
            else:
                await query.message.reply_text("هیچ کد تخفیفی یافت نشد.")
            return
        text = "📜 *لیست کدهای تخفیف*:\n"
        keyboard = []
        row = []
        for d in discounts:
            # Convert sqlite3.Row to dict properly
            if hasattr(d, 'keys'):
                d_dict = {key: d[key] for key in d.keys()}
            else:
                d_dict = dict(d)
            
            status = "🟢 فعال" if d_dict.get("is_active") else "🔴 غیرفعال"
            uses_count = d_dict.get('uses_count', 0)
            text += f"\n• {d_dict.get('code')} ({status}) - {uses_count} استفاده"
            # add button
            row.append(InlineKeyboardButton(d_dict.get('code'), callback_data=f"view_discount_{d_dict.get('id')}") )
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="discounts_menu")])
        if hasattr(query, "edit_message_text"):
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_single_discount(self, query, discount_id: int):
        d = DatabaseQueries.get_discount_by_id(discount_id) if hasattr(DatabaseQueries, 'get_discount_by_id') else None
        if not d:
            await query.edit_message_text("کد تخفیف یافت نشد.")
            return
        
        # Convert sqlite3.Row to dict properly
        if hasattr(d, 'keys'):
            d_dict = {key: d[key] for key in d.keys()}
        else:
            d_dict = dict(d)
            
        status_text = "فعال 🟢" if d_dict.get("is_active") else "غیرفعال 🔴"
        toggle_text = "🔴 غیرفعال کردن" if d_dict.get("is_active") else "🟢 فعال کردن"
        text = (
            f"جزئیات کد تخفیف {d_dict['code']}\n\n"
            f"شناسه: {d_dict['id']}\n"
            f"نوع: {d_dict['type']}\n"
            f"مقدار: {d_dict['value']}\n"
            f"وضعیت: {status_text}\n"
            f"تاریخ شروع: {d_dict.get('start_date','-')}\n"
            f"تاریخ پایان: {d_dict.get('end_date','-')}\n"
            f"حداکثر استفاده: {d_dict.get('max_uses','-')}\n"
            f"تعداد استفاده: {d_dict.get('uses_count','0')}"
        )
        keyboard = [
            [InlineKeyboardButton(toggle_text, callback_data=f"toggle_discount_{discount_id}")],
            [InlineKeyboardButton("✏️ ویرایش", callback_data=f"edit_discount_{discount_id}")],
            [InlineKeyboardButton("🗑️ حذف", callback_data=f"delete_discount_{discount_id}")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="discounts_list")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    # --------------------------------------
    # New helper methods for plan selection
    # --------------------------------------
    def _build_plan_select_keyboard(self, selected_ids: set[int], plans):
        """Return an inline keyboard for multi-selecting plans."""
        keyboard = []
        row = []
        for p in plans:
            # Handle different data types (tuple/list vs sqlite3.Row)
            if isinstance(p, (list, tuple)):
                pid = p[0]
                pname = p[1]
            else:
                # Convert sqlite3.Row to dict properly
                if hasattr(p, 'keys'):
                    p_dict = {key: p[key] for key in p.keys()}
                else:
                    p_dict = dict(p)
                pid = p_dict.get("id")
                pname = p_dict.get("name")
            selected = pid in selected_ids
            button_text = ("✅ " if selected else "☑️ ") + str(pname)
            row.append(InlineKeyboardButton(button_text, callback_data=f"planpick_{pid}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        # Control buttons
        toggle_all_text = "انتخاب همه" if len(selected_ids) < len(plans) else "لغو همه"
        keyboard.append([
            InlineKeyboardButton(toggle_all_text, callback_data="planpick_all"),
            InlineKeyboardButton("✅ تأیید", callback_data="planpick_done"),
        ])
        keyboard.append([InlineKeyboardButton("❌ انصراف", callback_data="discounts_menu")])
        return keyboard

    async def _handle_plan_select_callback(self, query, context):
        """Handle toggle/confirm actions during plan multi-select."""
        df = context.user_data.get("discount_flow")
        if not df or df.get("state") != "await_plan_inline":
            return  # Not in this flow
        data = query.data
        selected: set = df["data"].get("selected_plan_ids", set())
        plans = DatabaseQueries.get_active_plans()

        if data == "planpick_done":
            # Proceed to create discount
            plan_ids = list(selected)
            ddata = df["data"]
            new_id = DatabaseQueries.create_discount(ddata["code"], ddata["type"], ddata["value"])
            if new_id:
                if plan_ids:
                    DatabaseQueries.link_discount_to_plans(new_id, plan_ids)
                await query.edit_message_text("✅ کد تخفیف ایجاد شد.")
            else:
                await query.edit_message_text("❌ خطا در ایجاد کد تخفیف. شاید کد تکراری باشد.")
            # Clean up and show submenu
            context.user_data.pop("discount_flow", None)
            await self._discounts_submenu(query)
            return
        elif data == "planpick_all":
            if len(selected) < len(plans):
                selected = {p[0] if isinstance(p, (list, tuple)) else p.get("id") for p in plans}
            else:
                selected = set()
        elif data.startswith("planpick_"):
            try:
                # Extract the part after planpick_
                parts = data.split("_", 1)
                if len(parts) < 2 or not parts[1].isdigit():
                    logger.warning(f"Invalid planpick callback data: {data}")
                    await query.answer("❌ شناسه پلن نامعتبر است.", show_alert=True)
                    return
                    
                pid = int(parts[1])
                if pid in selected:
                    selected.remove(pid)
                else:
                    selected.add(pid)
            except (ValueError, IndexError) as e:
                logger.error(f"Error processing planpick callback: {e}", exc_info=True)
                await query.answer("❌ خطا در پردازش درخواست", show_alert=True)
                return
        else:
            return  # Unknown callback

        # Save and refresh keyboard
        df["data"]["selected_plan_ids"] = selected
        keyboard = self._build_plan_select_keyboard(selected, plans)
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    async def _toggle_discount_status(self, query, discount_id: int):
        d = DatabaseQueries.get_discount_by_id_code_or_id(discount_id) if hasattr(DatabaseQueries, 'get_discount_by_id_code_or_id') else None
        # fallback
        if d is None:
            # attempt by custom query
            pass
        d = DatabaseQueries.get_discount_by_id(discount_id) if hasattr(DatabaseQueries, 'get_discount_by_id') else None
        if not d:
            await query.answer("خطا", show_alert=True)
            return
        
        # Convert sqlite3.Row to dict properly
        if hasattr(d, 'keys'):
            d_dict = {key: d[key] for key in d.keys()}
        else:
            d_dict = dict(d)
            
        new_status = 0 if d_dict['is_active'] else 1
        DatabaseQueries.toggle_discount_status(discount_id, new_status)
        await self._show_single_discount(query, discount_id)

    async def _delete_discount_confirmation(self, query, discount_id: int):
        keyboard = [[InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"confirm_delete_discount_{discount_id}"), InlineKeyboardButton("❌ انصراف", callback_data=f"view_discount_{discount_id}")]]
        await query.edit_message_text("آیا از حذف این کد تخفیف اطمینان دارید؟", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _delete_discount(self, query, discount_id: int):
        if DatabaseQueries.delete_discount(discount_id):
            await query.answer("حذف شد")
            await self._list_discounts(query)
        else:
            await query.answer("خطا در حذف", show_alert=True)

    async def _settings_submenu(self, query):
        # Determine current status of discount code step
        discount_step_enabled = DatabaseQueries.get_setting("enable_discount_code_step", "1") == "1"
        discount_toggle_text = ("🏷️ مرحله کد تخفیف : ✅" if discount_step_enabled else "🏷️ مرحله کد تخفیف : ❌")

        keyboard = [
            [InlineKeyboardButton("🔐 مدیران", callback_data="settings_admins"), InlineKeyboardButton("👥 مدیریت پشتیبان‌ها", callback_data=self.SUPPORT_MENU)],
            [InlineKeyboardButton("🏅 مدیریت میان‌رده‌ها", callback_data="settings_mid_level"), InlineKeyboardButton("🔘 دکمه‌های تمدید", callback_data="settings_renew_buttons")],
            [InlineKeyboardButton("💸 مدیریت کدهای تخفیف", callback_data="discounts_menu"), InlineKeyboardButton(discount_toggle_text, callback_data="settings_toggle_discount_step")],
            [InlineKeyboardButton("🎯 دکمه تبلیغاتی", callback_data="promo_category_admin"), InlineKeyboardButton("⚙️ سایر تنظیمات", callback_data="settings_misc")],
            [InlineKeyboardButton("💾 بکاپ JSON دیتابیس", callback_data=self.BACKUP_CALLBACK), InlineKeyboardButton("📆 بکاپ Excel دیتابیس", callback_data=self.BACKUP_XLSX_CALLBACK)],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text("⚙️ *تنظیمات ربات*:\nکدام بخش را می‌خواهید مدیریت کنید؟", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _settings_renew_buttons_submenu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show dynamic submenu listing all active plans & root categories to toggle renew button visibility."""
        query = update.callback_query
        await query.answer()

        visibility = DatabaseQueries.get_renew_visibility()
        selected_plans = visibility["plans"]
        selected_cats = visibility["categories"]

        # Fetch active plans and full category tree (nested)
        plans = DatabaseQueries.get_active_plans()
        category_tree = DatabaseQueries.get_category_tree() or []

        keyboard: list[list[InlineKeyboardButton]] = []

        # ------------------------------------------------------------
        # Special categories (Free plans and Products)
        # ------------------------------------------------------------
        free_enabled = 0 in selected_cats
        prod_enabled = -1 in selected_cats
        free_text = ("✅ " if free_enabled else "❌ ") + "🎁 رایگان"
        prod_text = ("✅ " if prod_enabled else "❌ ") + "🛒 محصولات"
        keyboard.append([InlineKeyboardButton(free_text, callback_data="toggle_renew_cat_0")])
        keyboard.append([InlineKeyboardButton(prod_text, callback_data="toggle_renew_cat_-1")])

        # ------------------------------------------------------------
        # Helper to flatten category tree with indentation
        # ------------------------------------------------------------
        def _flatten(tree: list[dict], level: int = 0):
            flat: list[tuple[int, str]] = []
            prefix = "  " * level  # two spaces per hierarchy level for indentation
            for node in tree:
                cid = node.get("id")
                cname = node.get("name", "-")
                flat.append((cid, f"{prefix}{cname}"))
                children = node.get("children")
                if children:
                    flat.extend(_flatten(children, level + 1))
            return flat

        categories_flat = _flatten(category_tree)

        # Divider before categories
        if categories_flat:
            keyboard.append([InlineKeyboardButton("──────────", callback_data="noop")])

        # Category toggle buttons (in hierarchical order)
        for cid, cname in categories_flat:
            enabled = cid in selected_cats
            text = ("✅ " if enabled else "❌ ") + f"{cname}"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"toggle_renew_cat_{cid}")])

        # Divider before plans
        if plans:
            keyboard.append([InlineKeyboardButton("──────────", callback_data="noop")])

        # Plans
        for plan in plans:
            pid = plan["id"] if isinstance(plan, dict) else plan[0]
            pname = plan["name"] if isinstance(plan, dict) else plan[1]
            enabled = pid in selected_plans
            text = ("✅ " if enabled else "❌ ") + f"{pname}"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"toggle_renew_plan_{pid}")])

        # Back button
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=self.SETTINGS_MENU)])

        await query.edit_message_text(
            "🔘 تنظیم نمایش دکمه‌های تمدید برای هر طرح و دسته‌بندی:\nبا لمس هر مورد، وضعیت آن تغییر خواهد کرد.",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _settings_renew_toggle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        await query.answer()

        visibility = DatabaseQueries.get_renew_visibility()

        if data.startswith("toggle_renew_plan_"):
            pid = int(data.split("_")[-1])
            if pid in visibility["plans"]:
                visibility["plans"].remove(pid)
            else:
                visibility["plans"].add(pid)
            DatabaseQueries.set_renew_visibility(visibility)
        elif data.startswith("toggle_renew_cat_"):
            cid = int(data.split("_")[-1])
            if cid in visibility["categories"]:
                visibility["categories"].remove(cid)
            else:
                visibility["categories"].add(cid)
            DatabaseQueries.set_renew_visibility(visibility)
        else:
            # legacy free/products toggles – treat as special categories
            if data.endswith("_free"):
                special = 0
            else:
                special = -1
            if special in visibility["categories"]:
                visibility["categories"].remove(special)
            else:
                visibility["categories"].add(special)
            DatabaseQueries.set_renew_visibility(visibility)

        # Refresh submenu
        await self._settings_renew_buttons_submenu(update, context)

    async def _toggle_renew_button(self, query, key):
        """Toggle db setting and refresh the renew buttons submenu."""
        current = DatabaseQueries.get_setting(key, '1')
        new_val = '0' if current == '1' else '1'
        DatabaseQueries.set_setting(key, new_val)
        # Rebuild the submenu keyboard after toggle
        free_enabled = DatabaseQueries.get_setting('renew_free', '1') == '1'
        prod_enabled = DatabaseQueries.get_setting('renew_products', '1') == '1'
        free_text = ('✅' if free_enabled else '❌') + " 🎁 رایگان"
        prod_text = ('✅' if prod_enabled else '❌') + " 🛒 محصولات"
        keyboard = [
            [InlineKeyboardButton(free_text, callback_data="toggle_renew_free")],
            [InlineKeyboardButton(prod_text, callback_data="toggle_renew_products")],
            [InlineKeyboardButton("✔️ ذخیره و بازگشت", callback_data=self.SETTINGS_MENU)]
        ]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))

    async def _settings_misc_submenu(self, query):
        """Show miscellaneous settings such as maintenance toggle."""
        maintenance_status = "ON" if self.maintenance_mode else "OFF"
        keyboard = [
            [InlineKeyboardButton(f"🚧 حالت نگه‌داری: {maintenance_status}", callback_data="settings_toggle_maintenance")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.SETTINGS_MENU)],
        ]
        await query.edit_message_text(
            "⚙️ *سایر تنظیمات*:\nبرای تغییر حالت نگه‌داری دکمه زیر را فشار دهید.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _broadcast_entry_direct(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Entry point for new broadcast flow without extra submenu."""
        from handlers.admin.broadcast_handler import broadcast_start
        # Set the conversation state manually
        await broadcast_start(update=update, context=context)

    async def _broadcast_submenu(self, query):
        """Display broadcast options (active users vs all users)."""
        keyboard = [
            [InlineKeyboardButton("🟢 کاربران فعال", callback_data=self.BROADCAST_ACTIVE)],
            [InlineKeyboardButton("👥 تمامی اعضا", callback_data=self.BROADCAST_ALL)],
            [InlineKeyboardButton("🔗 پیام با دکمهٔ لینک کانال", callback_data="broadcast_with_link")],
            [InlineKeyboardButton("🛍️ پیام با دکمه‌های محصولات/دسته‌ها", callback_data="broadcast_custom")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text(
            "📢 *ارسال پیام همگانی*:\nیکی از گزینه‌های زیر را انتخاب کنید:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    # This method is handled by the comprehensive stats handler above
    # Redirect to avoid duplication
    async def _show_general_stats(self, query):
        """Legacy method - redirects to comprehensive stats handler."""
        # Use the updated comprehensive stats handler
        await self._show_stats_handler(query)

    # LEGACY minimal products submenu (kept for backwards compatibility but renamed)
    async def _products_submenu_legacy(self, query):
        """[LEGACY] Display minimal products management submenu."""
        keyboard = [
            [InlineKeyboardButton("📋 لیست محصولات", callback_data="products_list")],
            [InlineKeyboardButton("📈 گزارش فروش محصولات", callback_data="products_sales_reports")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BACK_MAIN)],
        ]
        await query.edit_message_text(
            "📦 <b>مدیریت محصولات:</b>\n\nچه کاری می‌خواهید انجام دهید؟",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _show_products_sales_reports(self, query):
        """Show products sales reports menu."""
        try:
            # Get all plans
            plans = DatabaseQueries.get_all_plans() or []
            if not plans:
                await query.edit_message_text(
                    "❌ هیچ محصولی یافت نشد.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 بازگشت", callback_data=self.PRODUCTS_MENU)]
                    ])
                )
                return

            keyboard = []
            for plan in plans:
                if isinstance(plan, dict):
                    plan_id = plan.get('id')
                    plan_name = plan.get('name', 'نامشخص')
                else:
                    plan_id = plan[0] if len(plan) > 0 else None
                    plan_name = plan[1] if len(plan) > 1 else 'نامشخص'
                
                if plan_id:
                    # Truncate long names for better display
                    display_name = plan_name[:25] + "..." if len(plan_name) > 25 else plan_name
                    keyboard.append([
                        InlineKeyboardButton(
                            f"📊 {display_name}", 
                            callback_data=f"sales_report_{plan_id}"
                        )
                    ])
            
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=self.PRODUCTS_MENU)])
            
            await query.edit_message_text(
                "📈 <b>گزارش فروش محصولات:</b>\n\nیک محصول را برای مشاهده گزارش فروش انتخاب کنید:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as e:
            logger.error(f"Error in _show_products_sales_reports: {e}")
            await query.edit_message_text(
                "❌ خطا در دریافت لیست محصولات.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت", callback_data=self.PRODUCTS_MENU)]
                ])
            )

    async def _show_product_sales_report(self, query, plan_id):
        """Show detailed sales report for a specific product."""
        try:
            from datetime import datetime, timedelta
            
            # Get plan details
            plan = DatabaseQueries.get_plan_by_id(plan_id)
            if not plan:
                await query.edit_message_text(
                    "❌ محصول یافت نشد.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 بازگشت", callback_data="products_sales_reports")]
                    ])
                )
                return
            
            if isinstance(plan, dict):
                plan_name = plan.get('name', 'نامشخص')
                plan_price = plan.get('price', 0)
            else:
                plan_name = plan[1] if len(plan) > 1 else 'نامشخص'
                plan_price = plan[3] if len(plan) > 3 else 0
            
            # Calculate time periods
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=7)
            month_start = today_start - timedelta(days=30)
            
            # Get sales data for different periods
            today_sales = DatabaseQueries.get_plan_sales_count_since(plan_id, today_start.isoformat()) or 0
            week_sales = DatabaseQueries.get_plan_sales_count_since(plan_id, week_start.isoformat()) or 0
            month_sales = DatabaseQueries.get_plan_sales_count_since(plan_id, month_start.isoformat()) or 0
            total_sales = DatabaseQueries.get_plan_sales_count(plan_id) or 0
            
            # Calculate revenues
            today_revenue = today_sales * plan_price
            week_revenue = week_sales * plan_price
            month_revenue = month_sales * plan_price
            total_revenue = total_sales * plan_price
            
            message_text = f"📊 <b>گزارش فروش: {plan_name}</b>\n\n"
            message_text += f"💰 <b>قیمت واحد:</b> {plan_price:,} تومان\n\n"
            
            message_text += "📈 <b>آمار فروش:</b>\n"
            message_text += f"• امروز: <code>{today_sales:,}</code> عدد (<code>{today_revenue:,}</code> تومان)\n"
            message_text += f"• هفته گذشته: <code>{week_sales:,}</code> عدد (<code>{week_revenue:,}</code> تومان)\n"
            message_text += f"• ماه گذشته: <code>{month_sales:,}</code> عدد (<code>{month_revenue:,}</code> تومان)\n"
            message_text += f"• کل فروش: <code>{total_sales:,}</code> عدد (<code>{total_revenue:,}</code> تومان)\n\n"
            
            # Calculate averages
            if week_sales > 0:
                daily_avg = week_sales / 7
                message_text += f"📊 <b>میانگین روزانه (هفته):</b> {daily_avg:.1f} عدد\n"
            
            if month_sales > 0:
                monthly_avg = month_sales / 30
                message_text += f"📊 <b>میانگین روزانه (ماه):</b> {monthly_avg:.1f} عدد\n"
            
            message_text += f"\n🕐 <b>آخرین بروزرسانی:</b> {now.strftime('%H:%M:%S')}"
            
            keyboard = [
                [InlineKeyboardButton("🔄 بروزرسانی", callback_data=f"sales_report_{plan_id}")],
                [InlineKeyboardButton("📋 جزئیات بیشتر", callback_data=f"sales_details_{plan_id}")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="products_sales_reports")],
            ]
            
            await query.edit_message_text(
                message_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            
        except Exception as e:
            logger.error(f"Error in _show_product_sales_report: {e}")
            await query.edit_message_text(
                "❌ خطا در دریافت گزارش فروش.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت", callback_data="products_sales_reports")]
                ])
            )

    async def _show_product_sales_details(self, query, plan_id):
        """Show detailed sales breakdown for a specific product."""
        try:
            from datetime import datetime, timedelta
            
            # Get plan details
            plan = DatabaseQueries.get_plan_by_id(plan_id)
            if not plan:
                await query.edit_message_text(
                    "❌ محصول یافت نشد.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 بازگشت", callback_data=f"sales_report_{plan_id}")]
                    ])
                )
                return
            
            if isinstance(plan, dict):
                plan_name = plan.get('name', 'نامشخص')
                plan_price = plan.get('price', 0)
            else:
                plan_name = plan[1] if len(plan) > 1 else 'نامشخص'
                plan_price = plan[3] if len(plan) > 3 else 0
            
            # Get recent sales (last 10)
            recent_sales = DatabaseQueries.get_recent_plan_sales(plan_id, limit=10) or []
            
            message_text = f"📋 <b>جزئیات فروش: {plan_name}</b>\n\n"
            
            if recent_sales:
                message_text += "🛒 <b>آخرین فروش‌ها:</b>\n"
                for i, sale in enumerate(recent_sales, 1):
                    if isinstance(sale, dict):
                        user_id = sale.get('user_id', 'نامشخص')
                        created_at = sale.get('created_at', '')
                        amount = sale.get('amount', plan_price)
                    else:
                        user_id = sale[1] if len(sale) > 1 else 'نامشخص'
                        created_at = sale[6] if len(sale) > 6 else ''
                        amount = sale[2] if len(sale) > 2 else plan_price
                    
                    # Format date
                    try:
                        if created_at:
                            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            date_str = dt.strftime('%Y/%m/%d %H:%M')
                        else:
                            date_str = 'نامشخص'
                    except:
                        date_str = 'نامشخص'
                    
                    message_text += f"{i}. کاربر {user_id} - {date_str} - {amount:,} تومان\n"
            else:
                message_text += "📝 هیچ فروشی ثبت نشده است.\n"
            
            # Get sales by payment method if available
            try:
                rial_sales = DatabaseQueries.get_plan_rial_sales_count(plan_id) or 0
                crypto_sales = DatabaseQueries.get_plan_crypto_sales_count(plan_id) or 0
                
                if rial_sales > 0 or crypto_sales > 0:
                    message_text += "\n💳 <b>روش پرداخت:</b>\n"
                    message_text += f"• ریالی: {rial_sales:,} عدد\n"
                    message_text += f"• کریپتو: {crypto_sales:,} عدد\n"
            except:
                pass  # Methods might not exist
            
            keyboard = [
                [InlineKeyboardButton("🔄 بروزرسانی", callback_data=f"sales_details_{plan_id}")],
                [InlineKeyboardButton("🔙 بازگشت به گزارش", callback_data=f"sales_report_{plan_id}")],
            ]
            
            await query.edit_message_text(
                message_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            
        except Exception as e:
            logger.error(f"Error in _show_product_sales_details: {e}")
            await query.edit_message_text(
                "❌ خطا در دریافت جزئیات فروش.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 بازگشت", callback_data=f"sales_report_{plan_id}")]
                ])
            )

    # ---------- Broadcast with link flow helpers ----------
    async def _broadcast_wl_choose_audience(self, query):
        """Ask admin to choose target audience for broadcast with link."""
        keyboard = [
            [InlineKeyboardButton("🟢 کاربران فعال", callback_data=self.BROADCAST_WL_ACTIVE)],
            [InlineKeyboardButton("👥 تمامی اعضا", callback_data=self.BROADCAST_WL_ALL)],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.BROADCAST_MENU)],
        ]
        await query.edit_message_text("📢 *پیام با دکمه کانال*\nلطفاً مخاطبین را انتخاب کنید:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _broadcast_wl_ask_content(self, query, context, target: str):
        """Prompt admin to send message content."""
        context.user_data["bw_target"] = target  # 'active' or 'all'
        context.user_data["bw_awaiting_content"] = True
        await query.edit_message_text("✏️ محتوای پیام (متن یا عکس) را ارسال کنید.")

    async def _broadcast_wl_show_channel_picker(self, message, context):
        """After receiving content, ask admin to pick channels."""
        from utils.broadcast_helpers import build_channel_select_keyboard
        from config import TELEGRAM_CHANNELS_INFO

        context.user_data["bw_selected_ids"] = set()
        keyboard = build_channel_select_keyboard(TELEGRAM_CHANNELS_INFO, set())
        await message.reply_text("🔗 لینک‌های کانال/گروه موردنظر را انتخاب کنید، سپس تأیید را بزنید:", reply_markup=keyboard)
        
        # For media messages, we need to download and re-upload via main bot since file_ids are bot-specific
        if message.text and not message.effective_attachment:
            # Plain text message - store content directly
            context.user_data["bw_draft"] = {
                "type": "text",
                "data": {
                    "text": message.text_html or message.text,
                    **({"parse_mode": "HTML"} if message.text_html else {}),
                }
            }
            logger.info("Stored text message for broadcast")
        elif message.photo or message.video or message.document:
            # For media, we'll download and re-upload via main bot during broadcast
            # Store the original message reference and let main bot handle the file transfer
            if self.main_bot_app:
                try:
                    # Send the media to main bot first so it gets its own file_id
                    from io import BytesIO
                    from telegram import InputFile

                    if message.photo:
                        # Download photo bytes
                        photo_file = await message.photo[-1].get_file()
                        bio = BytesIO()
                        await photo_file.download_to_memory(out=bio)
                        bio.seek(0)
                        input_file = InputFile(bio, filename="photo.jpg")
                        sent = await self.main_bot_app.bot.send_photo(
                            chat_id=message.from_user.id,
                            photo=input_file,
                            caption="[BROADCAST_DRAFT] ",
                            disable_notification=True,
                            parse_mode="HTML"
                        )
                        # remove temp message
                        try:
                            await self.main_bot_app.bot.delete_message(chat_id=sent.chat_id, message_id=sent.message_id)
                        except Exception:
                            pass
                        context.user_data["bw_draft"] = {
                            "type": "photo",
                            "data": {
                                "photo": sent.photo[-1].file_id,
                                "caption": message.caption_html or message.caption or "",
                                **({"parse_mode": "HTML"} if message.caption_html else {}),
                            }
                        }
                    elif message.video:
                        # Download video bytes
                        video_file = await message.video.get_file()
                        bio = BytesIO()
                        await video_file.download_to_memory(out=bio)
                        bio.seek(0)
                        input_file = InputFile(bio, filename=message.video.file_name or "video.mp4")
                        sent = await self.main_bot_app.bot.send_video(
                            chat_id=message.from_user.id,
                            video=input_file,
                            caption="[BROADCAST_DRAFT] ",
                            disable_notification=True,
                            parse_mode="HTML"
                        )
                        try:
                            await self.main_bot_app.bot.delete_message(chat_id=sent.chat_id, message_id=sent.message_id)
                        except Exception:
                            pass
                        context.user_data["bw_draft"] = {
                            "type": "video",
                            "data": {
                                "video": sent.video.file_id,
                                "caption": message.caption_html or message.caption or "",
                                **({"parse_mode": "HTML"} if message.caption_html else {}),
                            }
                        }
                    elif message.document:
                        # Download document bytes
                        doc_file = await message.document.get_file()
                        bio = BytesIO()
                        await doc_file.download_to_memory(out=bio)
                        bio.seek(0)
                        input_file = InputFile(bio, filename=message.document.file_name or "document")
                        sent = await self.main_bot_app.bot.send_document(
                            chat_id=message.from_user.id,
                            document=input_file,
                            caption="[BROADCAST_DRAFT] ",
                            disable_notification=True,
                            parse_mode="HTML"
                        )
                        try:
                            await self.main_bot_app.bot.delete_message(chat_id=sent.chat_id, message_id=sent.message_id)
                        except Exception:
                            pass
                        context.user_data["bw_draft"] = {
                            "type": "document",
                            "data": {
                                "document": sent.document.file_id,
                                "caption": message.caption_html or message.caption or "",
                                **({"parse_mode": "HTML"} if message.caption_html else {}),
                            }
                        }
                    logger.info(f"Successfully transferred media to main bot for broadcast")
                except Exception as e:
                    logger.error(f"Failed to transfer media to main bot: {e}")
                    await message.reply_text("❌ خطا در آماده‌سازی فایل برای ارسال")
                    return
            else:
                await message.reply_text("❌ ربات اصلی در دسترس نیست")
                return
        else:
            await message.reply_text("❌ نوع پیام پشتیبانی نمی‌شود")
            return

    async def _broadcast_wl_picker_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle toggle/select-all/confirm for channel picker keyboard."""
        query = update.callback_query
        if not query:
            return  # Should never happen, but guard just in case
        # Acknowledge callback to remove loading spinner
        try:
            await query.answer()
        except Exception:
            pass
        # Handle selection toggles and final confirmation for channel picker
        data = query.data
        from utils.broadcast_helpers import build_channel_select_keyboard
        from config import TELEGRAM_CHANNELS_INFO

        selected_ids: set[int] = context.user_data.get("bw_selected_ids", set())
        if data == "chpick_all":
            if len(selected_ids) < len(TELEGRAM_CHANNELS_INFO):
                selected_ids = {c['id'] for c in TELEGRAM_CHANNELS_INFO}
            else:
                selected_ids = set()
        elif data.startswith("chpick_done"):
            # Proceed to send broadcast
            await self._broadcast_wl_send(query, context, selected_ids)
            # clear bw_* keys afterwards
            for k in ["bw_selected_ids", "bw_target", "bw_draft"]:
                context.user_data.pop(k, None)
            return
        elif data.startswith("chpick_"):
            cid = int(data.split("_")[1])
            if cid in selected_ids:
                selected_ids.remove(cid)
            else:
                selected_ids.add(cid)
        logger.info("Picker update after click: %s", selected_ids)
        # Save back
        context.user_data["bw_selected_ids"] = selected_ids
        keyboard = build_channel_select_keyboard(TELEGRAM_CHANNELS_INFO, selected_ids)
        await query.message.edit_reply_markup(reply_markup=keyboard)

    async def _broadcast_wl_cancel(self, query, context):
        """Cancel the broadcast-with-link flow and clean flags."""
        for k in ["bw_selected_ids", "bw_target", "bw_draft", "bw_awaiting_content"]:
            context.user_data.pop(k, None)
        await self._broadcast_submenu(query)

    async def _broadcast_wl_send(self, query, context, selected_ids: set[int]):
        """Copy message to users and attach link buttons."""
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        from config import TELEGRAM_CHANNELS_INFO
        draft = context.user_data.get("bw_draft")
        if not draft:
            await query.answer("پیش‌نویس یافت نشد", show_alert=True)
            return
        target = context.user_data.get("bw_target", "active")
        # Build buttons
        buttons = None
        if selected_ids:
            rows = []
            for cid in selected_ids:
                ch = next((c for c in TELEGRAM_CHANNELS_INFO if c['id']==cid), None)
                if ch:
                    rows.append([InlineKeyboardButton(ch['title'], url=ch['link'])])
            buttons = InlineKeyboardMarkup(rows)
        # Determine audience list
        if target == "active":
            users_rows = DatabaseQueries.get_all_active_subscribers()
        else:
            users_rows = DatabaseQueries.get_all_registered_users()
        user_ids = [row['user_id'] if isinstance(row, dict) else row[0] for row in users_rows]
        success = 0
        total = len(user_ids)
        
        # Use main bot for sending broadcast messages to users
        bot_to_use = self.main_bot_app.bot if self.main_bot_app else context.bot
        
        draft_type = draft.get("type")
        draft_data = draft.get("data", {})
        for uid in user_ids:
            try:
                if draft_type == "text":
                    sent = await bot_to_use.send_message(chat_id=uid, **draft_data)
                elif draft_type == "photo":
                    sent = await bot_to_use.send_photo(chat_id=uid, **draft_data)
                elif draft_type == "video":
                    sent = await bot_to_use.send_video(chat_id=uid, **draft_data)
                elif draft_type == "document":
                    sent = await bot_to_use.send_document(chat_id=uid, **draft_data)
                elif draft_type == "copy":
                    sent = await bot_to_use.copy_message(chat_id=uid, from_chat_id=draft_data['chat_id'], message_id=draft_data['message_id'])
                else:
                    logger.warning("Unknown draft_type %s", draft_type)
                    continue
                if buttons:
                    await bot_to_use.edit_message_reply_markup(chat_id=uid, message_id=sent.message_id, reply_markup=buttons)
                success += 1
            except Exception as e:
                logger.warning("Broadcast send to %s failed: %s", uid, e)
        await query.edit_message_text(f"✅ ارسال به پایان رسید. موفق: {success}/{total}")

    @admin_only
    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle dynamic admin inputs based on flow flags (broadcast, user search)."""
        # If crypto panel conversation is active for this user, ignore further admin menu handling
        if context.user_data.get('crypto_active'):
            logger.info("Admin message_handler: crypto_active=True, passing to next handler")
            return False

        # Short-circuit if admin is replying to a ticket (set by AdminTicketHandler.manual_answer_callback or edit_answer_callback)
        if context.user_data.get("editing_ticket_id") is not None:
            from .admin_ticket_handlers import AdminTicketHandler  # Local import to avoid circular deps
            ticket_handler = getattr(self, "_ticket_delegate", None)
            if ticket_handler is None:
                ticket_handler = AdminTicketHandler()
                setattr(self, "_ticket_delegate", ticket_handler)
            await ticket_handler.receive_edited_answer(update, context)
            return

        logger.info("Admin message_handler triggered with text: %s | bw_content=%s | search_flag=%s", update.effective_message.text if update.effective_message else "<no message>", context.user_data.get("bw_awaiting_content"), context.user_data.get("awaiting_user_search_query"))
        message = update.effective_message
        # -------- Broadcast custom (product/category buttons) flow --------
        if context.user_data.get("bc_waiting_msg"):
            from handlers.admin.broadcast_handler import handle_message_content, MENU
            await handle_message_content(update, context)
            # if handle_message_content accepted, remove flag
            context.user_data.pop("bc_waiting_msg", None)
            return

        # -------- Broadcast-with-link content flow --------
        if context.user_data.get("bw_awaiting_content"):
            # Accept a single message (text/photo/document) as content.
            context.user_data.pop("bw_awaiting_content", None)
            await self._broadcast_wl_show_channel_picker(message, context)
            return

        # -------- Ticket history flow --------
        if context.user_data.get("awaiting_ticket_history_user"):
            text = message.text.strip()
            digits = "".join(ch for ch in text if ch.isdigit())
            if not digits:
                await message.reply_text("❌ لطفاً شمارهٔ موبایل معتبر وارد کنید.")
                return
            # اگر طول ارقام حداقل 8 باشد فرض می‌کنیم شماره موبایل است
            target_id = None
            if len(digits) >= 8:
                user_row = DatabaseQueries.get_user_by_phone(digits)
                if not user_row:
                    await message.reply_text("❌ کاربری با این شماره پیدا نشد.")
                    return
                target_id = user_row.get('user_id')
            else:
                # فرض بر این است که آیدی تلگرام است
                target_id = int(digits)
            context.user_data.pop("awaiting_ticket_history_user", None)
            # Lazy init ticket delegate
            ticket_handler = getattr(self, "_ticket_delegate_history", None)
            if ticket_handler is None:
                from .admin_ticket_handlers import AdminTicketHandler
                ticket_handler = AdminTicketHandler()
                setattr(self, "_ticket_delegate_history", ticket_handler)
            await ticket_handler.show_ticket_history_for_user(update, context, target_id)
            return

        # -------- Add-support flow --------
        if context.user_data.get("awaiting_support_user_id"):
            text = message.text.strip()
            if not text.isdigit():
                await message.reply_text("❌ آیدی باید یک عدد باشد. دوباره تلاش کنید یا /cancel را بزنید.")
                return
            tg_id = int(text)
            admin_id = update.effective_user.id
            if DatabaseQueries.add_support_user(tg_id, added_by=admin_id):
                await message.reply_text(f"✅ کاربر {tg_id} به عنوان پشتیبان ثبت شد.")
            else:
                await message.reply_text("❌ خطا در افزودن کاربر یا کاربر قبلاً پشتیبان است.")
            # Reset flag and show submenu again
            context.user_data.pop("awaiting_support_user_id", None)
            class DummyQuery:
                def __init__(self, message):
                    self.message = message
                async def edit_message_text(self,*args,**kwargs):
                    await self.message.reply_text(*args,**kwargs)
            await self._settings_support_submenu(DummyQuery(message))
            return

        # -------- Discount create/edit flow --------
        if context.user_data.get("discount_flow"):
            df = context.user_data["discount_flow"]
            mode = df.get("mode")
            state = df.get("state")
            text = message.text.strip()
            if mode == "create":
                if state == "await_code":
                    df["data"]["code"] = text
                    df["state"] = "await_value_type"
                    await message.reply_text("لطفاً نوع و مقدار را ارسال کنید به فرم 'percentage 10' یا 'fixed 50000':")
                    return
                elif state == "await_value_type":
                    parts = text.split()
                    if len(parts)!=2 or parts[0] not in ("percentage","fixed") or not parts[1].replace('.', '', 1).isdigit():
                        await message.reply_text("❌ فرمت نامعتبر است. دوباره امتحان کنید.")
                        return
                    df["data"]["type"] = "percentage" if parts[0]=="percentage" else "fixed_amount"
                    df["data"]["value"] = float(parts[1])
                    # ask plan id or 0
                    active_plans = DatabaseQueries.get_active_plans()
                    if not active_plans:
                        await message.reply_text("❌ هیچ پلن فعالی برای انتخاب وجود ندارد.")
                        # Cancel flow
                        context.user_data.pop("discount_flow", None)
                        return
                    df["state"] = "await_plan_inline"
                    df["data"]["selected_plan_ids"] = set()
                    keyboard = self._build_plan_select_keyboard(set(), active_plans)
                    await message.reply_text("لطفاً پلن‌های مورد نظر را انتخاب کنید و سپس دکمه تأیید را بزنید:", reply_markup=InlineKeyboardMarkup(keyboard))
                    return
                elif state == "await_plan":
                    plan_input = text.replace(' ','')
                    if plan_input=="0":
                        plan_ids = []
                    else:
                        ids=[pid for pid in plan_input.split(',') if pid.isdigit()]
                        if not ids:
                            await message.reply_text("❌ ورودی نامعتبر. دوباره تلاش کنید.")
                            return
                        plan_ids=[int(i) for i in ids]
                    data=df["data"]
                    new_id=DatabaseQueries.create_discount(data["code"],data["type"],data["value"])
                    if new_id:
                        if plan_ids:
                            DatabaseQueries.link_discount_to_plans(new_id,plan_ids)
                        await message.reply_text("✅ کد تخفیف ایجاد شد.")
                    else:
                        await message.reply_text("❌ خطا در ایجاد کد تخفیف. شاید کد تکراری باشد.")
                    context.user_data.pop("discount_flow",None)
                    # back to discounts submenu
                    class DummyQuery:
                        def __init__(self,m):
                            self.message=m
                        async def edit_message_text(self,*args,**kwargs):
                            await self.message.reply_text(*args,**kwargs)
                    await self._discounts_submenu(DummyQuery(message))
                    return
            elif mode=="edit":
                did=df.get("discount_id")
                parts=text.split()
                if len(parts)!=2 or parts[0] not in ("percentage","fixed") or not parts[1].replace('.', '', 1).isdigit():
                    await message.reply_text("❌ فرمت نامعتبر است. دوباره تلاش کنید.")
                    return
                new_type="percentage" if parts[0]=="percentage" else "fixed_amount"
                new_value=float(parts[1])
                ok=DatabaseQueries.update_discount(did, type=new_type, value=new_value)
                await message.reply_text("✅ به‌روزرسانی شد." if ok else "❌ خطا در به‌روزرسانی.")
                context.user_data.pop("discount_flow",None)
                class DummyQuery:
                    def __init__(self,m):
                        self.message=m
                    async def edit_message_text(self,*args,**kwargs):
                        await self.message.reply_text(*args,**kwargs)
                await self._show_single_discount(DummyQuery(message), did)
                return

        # -------- Broadcast flow --------
        if context.user_data.get("awaiting_broadcast_content"):
            # Determine target users
            target = context.user_data.get("broadcast_target", "active")
            await message.reply_text("⏳ در حال ارسال پیام به کاربران، لطفاً صبر کنید...")

            if target == "all":
                users = DatabaseQueries.get_all_registered_users()
            else:
                users = DatabaseQueries.get_all_active_subscribers()
            total = len(users)
            success = 0
            for u in users:
                try:
                    # Robustly extract user_id from different row structures
                    user_id = None
                    if isinstance(u, (list, tuple)):
                        user_id = u[0]
                    else:
                        # Try mapping style access first (works for sqlite3.Row and dict)
                        try:
                            user_id = u["user_id"]
                        except Exception:
                            user_id = u.get("user_id") if hasattr(u, "get") else None

                    # Fallback to using the raw value if still None
                    if user_id is None:
                        user_id = u

                    # Ensure user_id is an int or str representing int
                    try:
                        user_id = int(user_id)
                    except Exception:
                        logger.debug("Could not convert user_id %s to int; using as-is", user_id)

                    await context.bot.copy_message(chat_id=user_id, from_chat_id=message.chat_id, message_id=message.message_id)
                    success += 1
                except Exception as e:
                    logger.warning("Failed to send broadcast to %s: %s", user_id, e)
                    continue

            await message.reply_text(f"✅ ارسال پیام به پایان رسید. موفق: {success}/{total}")
            # Reset flags
            context.user_data.pop("awaiting_broadcast_content", None)
            context.user_data.pop("broadcast_target", None)
            return

        # --- User Search Flow ---
        elif context.user_data.get("awaiting_user_search_query"):
            search_query = update.message.text
            context.user_data["awaiting_user_search_query"] = False # Reset flag

            # Simple search logic
            users = DatabaseQueries.search_users(search_query)
            if not users:
                await update.message.reply_text(f"❌ کاربری با مشخصات `{search_query}` یافت نشد.", parse_mode="Markdown")
                return

            # Get detailed info for each user
            for user in users:
                user_id = user['user_id']
                # Get complete user details
                db_queries = DatabaseQueries()
                user_details = db_queries.get_user_details(user_id)
                
                if user_details:
                    # Build comprehensive user info message
                    # Format username properly to avoid parse_entities error
                    username_display = f"@{user_details['username']}" if user_details.get('username') else 'ندارد'
                    
                    info_lines = [
                        f"👤 **اطلاعات کامل کاربر**",
                        f"━━━━━━━━━━━━━━━━━━━━",
                        f"🆔 آیدی: `{user_details['user_id']}`",
                        f"👤 نام کامل: {user_details.get('full_name') or 'ثبت نشده'}",
                        f"📱 شماره تلفن: {user_details.get('phone') or 'ثبت نشده'}",
                        f"👥 نام کاربری: {username_display}",
                        f"📧 ایمیل: {user_details.get('email') or 'ثبت نشده'}",
                        f"🎂 تاریخ تولد: {user_details.get('birth_date') or 'ثبت نشده'}",
                        f"🎓 تحصیلات: {user_details.get('education') or 'ثبت نشده'}",
                        f"💼 شغل: {user_details.get('occupation') or 'ثبت نشده'}",
                        f"🏙 شهر: {user_details.get('city') or 'ثبت نشده'}",
                        f"📅 تاریخ ثبت نام: {user_details.get('registration_date') or 'نامشخص'}",
                        f"🕐 آخرین فعالیت: {user_details.get('last_activity') or 'نامشخص'}",
                        f"📊 وضعیت: {user_details.get('status') or 'active'}",
                    ]
                    
                    # Check subscription status
                    subscription_info = DatabaseQueries.get_user_subscription_summary(user_id)
                    if subscription_info:
                        info_lines.append(f"━━━━━━━━━━━━━━━━━━━━")
                        info_lines.append(f"💳 **وضعیت اشتراک**")
                        if subscription_info['subscription_expiration_date']:
                            info_lines.append(f"📆 انقضای اشتراک: {subscription_info['subscription_expiration_date']}")
                        if subscription_info['total_subscription_days']:
                            info_lines.append(f"📊 مجموع روزهای اشتراک: {subscription_info['total_subscription_days']} روز")
                    
                    # Check if user is banned
                    user_status = DatabaseQueries.get_user_status(user_id)
                    if user_status == 'banned':
                        info_lines.append(f"🚫 **کاربر مسدود شده است**")
                    
                    # Add action buttons
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("➕ افزایش اشتراک", callback_data=f"extend_sub_{user_id}"),
                         InlineKeyboardButton("🔗 لینک دعوت", callback_data=f"create_invite_{user_id}")],
                        [InlineKeyboardButton("🛑 مسدود/آزاد کردن", callback_data=f"ban_toggle_{user_id}"),
                         InlineKeyboardButton("📋 تاریخچه خرید", callback_data=f"purchase_history_{user_id}")],
                        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users_menu")]
                    ])
                    
                    await update.message.reply_text(
                        "\n".join(info_lines),
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                else:
                    await update.message.reply_text(
                        f"❌ خطا در دریافت جزئیات کاربر با آیدی `{user_id}`",
                        parse_mode="Markdown"
                    )

        # --- Free 30-Day Activation Flow ---
        elif context.user_data.get("awaiting_free20_user"):
            term = update.message.text.strip().lstrip("@")
            context.user_data.pop("awaiting_free20_user", None)  # Reset flag

            user_rows = DatabaseQueries.search_users(term)
            if not user_rows:
                await update.message.reply_text("❌ کاربری یافت نشد.")
                return

            # Pick the first match
            target_user_id = user_rows[0]['user_id']

            # Ensure free plan exists in the database
            plan_id = ensure_free_plan()
            if not plan_id:
                await update.message.reply_text("❌ خطا در یافتن یا ایجاد پلن رایگان در دیتابیس.")
                return

            # Add the subscription
            sub_id = DatabaseQueries.add_subscription(
                user_id=target_user_id,
                plan_id=plan_id,
                payment_id=None,  # No payment for a free plan
                plan_duration_days=20,
                amount_paid=0,
                payment_method="manual_free",
            )

            if not sub_id:
                await update.message.reply_text("❌ خطا در فعال‌سازی اشتراک رایگان برای کاربر.")
                return

            # Notify admin
            await update.message.reply_text(f"✅ اشتراک ۲۰ روزه رایگان برای کاربر `{target_user_id}` با موفقیت فعال شد. در حال ایجاد و ارسال لینک دعوت...", parse_mode="Markdown")

            # Generate and send invite links
            links = await self.invite_link_manager.ensure_one_time_links(context.bot, target_user_id)
            if not links:
                await update.message.reply_text("❌ خطا در ایجاد لینک‌های دعوت. اشتراک فعال شد اما لینک ارسال نشد.")
                return

            link_message = "🎁 سلام! اشتراک ۲۰ روزه رایگان شما فعال شد.\n\nمی‌توانید از طریق لینک‌های زیر به کانال‌ها و گروه‌های ما بپیوندید:\n"
            for channel_name, link in links.items():
                link_message += f"\n🔗 {channel_name}: {link}\n"
            link_message += "\nاین لینک‌ها یکبار مصرف هستند و فقط برای شما کار می‌کنند."

            try:
                await context.bot.send_message(chat_id=target_user_id, text=link_message)

                # Confirm to admin
                await update.message.reply_text(f"✅ لینک‌های دعوت با موفقیت برای کاربر `{target_user_id}` ارسال شد.", parse_mode="Markdown")
            except Exception as e:
                logger.error(f"Failed to send invite links to user {target_user_id}: {e}", exc_info=True)
                await update.message.reply_text(f"❌ خطا در ارسال لینک‌های دعوت به کاربر `{target_user_id}`. لطفاً به صورت دستی ارسال کنید.", parse_mode="Markdown")

        # -------- Add mid-level user flow --------
        if context.user_data.get("awaiting_mid_level_user_id"):
            text = message.text.strip()
            if not text.isdigit():
                await message.reply_text("❌ آیدی باید یک عدد باشد. دوباره تلاش کنید یا دکمه لغو را بزنید.")
                return
            
            user_id = int(text)
            admin_id = update.effective_user.id
            
            # Add mid-level user and capture success result
            success = DatabaseQueries.add_mid_level_user(user_id, alias="")
            
            # Reset flag
            context.user_data.pop("awaiting_mid_level_user_id", None)
            
            # Prepare success message
            if success:
                success_text = f"✅ کاربر {user_id} با موفقیت به لیست میان‌رده‌ها اضافه شد."
            else:
                success_text = f"❌ خطا در افزودن کاربر {user_id} یا کاربر قبلاً میان‌رده است."
            
            # Get current mid-level users from database
            mid_level_users = DatabaseQueries.get_all_mid_level_users()
            
            keyboard = [
                [InlineKeyboardButton("➕ افزودن کاربر میان‌رده", callback_data="mid_level_add")],
                [InlineKeyboardButton("📋 مشاهده لیست", callback_data="mid_level_list")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="settings")],
            ]
            
            count = len(mid_level_users)
            text = f"🏅 *مدیریت کاربران میان‌رده*\n\n"
            text += f"📊 تعداد کاربران میان‌رده: {count}\n\n"
            text += "دسترسی‌های کاربران میان‌رده:\n"
            text += "• 🎫 مدیریت تیکت‌ها\n"
            text += "• 💳 مدیریت پرداخت‌ها\n"
            text += "• 📢 ارسال پیام همگانی\n\n"
            text += success_text
            
            await message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # If no flags matched, simply ignore the message so that other handlers may process it.
        logger.debug("broadcast_message_handler: No relevant flow flag set – ignoring message.")
        return

    # ---------- Payments helpers ----------
    async def _show_recent_payments_inline(self, query):
        """Show recent payments with inline buttons for quick details."""
        payments = DatabaseQueries.get_recent_payments(20)
        if not payments:
            await query.edit_message_text("📄 پرداختی یافت نشد.")
            return
        keyboard = []
        for p in payments:
            pid = p[0] if isinstance(p, (list, tuple)) else p['id']
            amount = p[2] if isinstance(p, (list, tuple)) else p['amount_rial']
            status = p[6] if isinstance(p, (list, tuple)) else p['status']
            created_at = p[7] if isinstance(p, (list, tuple)) else p['created_at']
            text = f"#{pid} | {amount:,} | {status} | {str(created_at)[:10]}"
            keyboard.append([InlineKeyboardButton(text, callback_data=f"payment_info_{pid}")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=self.PAYMENTS_MENU)])
        await query.edit_message_text("💰 *۲۰ تراکنش اخیر:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_payment_details(self, query, payment_id: str):
        """Display details and history of a single payment."""
        db = DatabaseQueries()
        rec = db.get_payment(payment_id) or db.get_crypto_payment_by_payment_id(payment_id)
        if not rec:
            await query.edit_message_text("❌ پرداختی با این شناسه یافت نشد.")
            return
        # Build message
        lines = [f"🧾 *جزئیات پرداخت* #{payment_id}"]
        for k, v in dict(rec).items():
            lines.append(f"• {k}: {v}")
        history = db.get_payment_status_history(payment_id)
        if history:
            lines.append("\n📜 *تاریخچه وضعیت:*")
            for h in history:
                lines.append(f"→ {h['changed_at']} | {h['old_status']} ➜ {h['new_status']} | {h['note'] or ''}")
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="payments_recent")]]
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    async def _show_recent_payments(self, query):
        payments = DatabaseQueries.get_recent_payments(20)
        if not payments:
            await query.edit_message_text("📄 پرداختی یافت نشد.")
            return
        from telegram.helpers import escape_markdown
        lines = [escape_markdown("💰 ۲۰ تراکنش اخیر:", version=2) + "\n"]
        for p in payments:
            try:
                payment_id = p[0] if isinstance(p, (list, tuple)) else p['id']
                user_id = p[1] if isinstance(p, (list, tuple)) else p['user_id']
                amount = p[2] if isinstance(p, (list, tuple)) else p['amount']
                status = p[5] if isinstance(p, (list, tuple)) else p['status']
                created_at = p[6] if isinstance(p, (list, tuple)) else p['created_at']
                escaped_status = escape_markdown(str(status), version=2)
                lines.append(escape_markdown(f"• #{payment_id} – {amount} ریال – {escaped_status} – {created_at} – UID:{user_id}", version=2))
            except Exception:
                lines.append(str(p))
        await query.edit_message_text("\n".join(lines), parse_mode="MarkdownV2")

    async def _show_payments_stats(self, query):
        """Show per-plan sales & subscription stats for admins."""
        try:
            stats = DatabaseQueries.get_sales_stats_per_plan()
            if not stats:
                await query.edit_message_text(
                    "📊 هیچ آماری برای نمایش وجود ندارد.",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 بازگشت", callback_data=self.PAYMENTS_MENU)
                    ]])
                )
                return

            # Header
            lines = ["📈 <b>آمار فروش و اشتراک هر پلن</b>\n"]
            
            total_active_all = 0
            total_subs_all = 0
            total_revenue_usdt_all = 0
            total_revenue_irr_all = 0
            
            for rec in stats:
                pid = rec.get("plan_id", 0)
                name = rec.get("plan_name", "نامشخص")
                active = rec.get("active_subscriptions", 0)
                total = rec.get("total_subscriptions", 0)
                rev_r = rec.get("total_revenue_rial", 0) or 0
                rev_u = rec.get("total_revenue_usdt", 0) or 0
                
                # Calculate conversion rate
                conversion_rate = (active / total * 100) if total > 0 else 0
                
                # Add to totals
                total_active_all += active
                total_subs_all += total
                total_revenue_usdt_all += rev_u
                total_revenue_irr_all += rev_r
                
                lines.append(
                    f"🔹 <b>{name}</b> (ID: {pid})\n"
                    f"   👥 اشتراک: <code>{active:,}</code> فعال / <code>{total:,}</code> کل\n"
                    f"   💰 درآمد: <code>{rev_u:,.2f}</code> USDT | <code>{rev_r:,.0f}</code> ریال\n"
                    f"   📊 نرخ فعال: <code>{conversion_rate:.1f}%</code>\n"
                )
            
            # Add summary
            lines.append(
                f"\n📋 <b>خلاصه کل:</b>\n"
                f"👥 کل اشتراک فعال: <code>{total_active_all:,}</code>\n"
                f"📦 کل اشتراک ثبت‌شده: <code>{total_subs_all:,}</code>\n"
                f"💵 کل درآمد USDT: <code>{total_revenue_usdt_all:,.2f}</code>\n"
                f"💴 کل درآمد ریال: <code>{total_revenue_irr_all:,.0f}</code>"
            )
            
            # Create back button
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 بازگشت", callback_data=self.PAYMENTS_MENU)
            ]])
            
            await query.edit_message_text(
                "\n".join(lines), 
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"Error in _show_payments_stats: {e}")
            await query.edit_message_text(
                "❌ خطا در دریافت آمار پلن‌ها. لطفاً دوباره تلاش کنید.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 بازگشت", callback_data=self.PAYMENTS_MENU)
                ]])
            )
    
    async def _export_payments_excel(self, query, context):
        """Generate an Excel workbook with payments-related data and send it to the admin.
        Sheets: payments, crypto_payments, payment_status_history
        """
        await query.answer()
        try:
            import sqlite3
            from io import BytesIO
            from datetime import datetime
            import pandas as pd
            from database.models import Database
        except Exception as e:
            logger.error(f"Import error for payments export: {e}")
            await query.answer("❌ پیش‌نیازها نصب نیستند (pandas).", show_alert=True)
            return

        # Ensure DB connection
        db = Database()
        if not db.connect():
            await query.answer("❌ خطا در اتصال به دیتابیس.", show_alert=True)
            return

        try:
            # Make sure rows are dict-like
            db.conn.row_factory = sqlite3.Row  # type: ignore[attr-defined]
            cursor = db.cursor

            # Determine Excel engine
            try:
                import xlsxwriter  # noqa: F401
                engine_name = "xlsxwriter"
            except ImportError:
                try:
                    import openpyxl  # noqa: F401
                    engine_name = "openpyxl"
                except ImportError:
                    await query.answer("❌ هیچ‌یک از پکیج‌های xlsxwriter یا openpyxl نصب نیست.", show_alert=True)
                    return

            tables = ["payments", "crypto_payments", "payment_status_history"]
            bio = BytesIO()
            with pd.ExcelWriter(bio, engine=engine_name) as writer:
                for table in tables:
                    try:
                        cursor.execute(f"SELECT * FROM {table}")
                        rows = cursor.fetchall() or []
                        df = pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()
                        # Excel sheet names are max 31 chars
                        sheet = table[:31]
                        df.to_excel(writer, sheet_name=sheet, index=False)
                    except Exception as exc:
                        logger.error(f"Failed reading table {table}: {exc}")
                        # still create an empty sheet to indicate presence
                        pd.DataFrame().to_excel(writer, sheet_name=table[:31], index=False)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bio.name = f"payments_export_{ts}.xlsx"
            bio.seek(0)

            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=bio,
                filename=bio.name,
            )
            await query.answer("📤 فایل اکسل پرداخت‌ها ارسال شد")
        except Exception as e:
            logger.error(f"Error generating payments Excel: {e}", exc_info=True)
            await query.answer("❌ خطا در تولید فایل اکسل پرداخت‌ها.", show_alert=True)
        finally:
            db.close()
    async def _show_admins_settings(self, query):
        """Display list of configured admins. Use safe HTML formatting to avoid Markdown errors."""
        import html as _html
        if not self.admin_config:
            await query.edit_message_text("🔐 پیکربندی مدیران یافت نشد.")
            return
        lines = ["<b>🔐 فهرست مدیران:</b>"]
        if isinstance(self.admin_config, list):
            for adm in self.admin_config:
                if isinstance(adm, dict):
                    alias = _html.escape(str(adm.get('alias', '-')))
                    cid = _html.escape(str(adm.get('chat_id', '-')))
                    lines.append(f"• {alias} – {cid}")
        elif isinstance(self.admin_config, dict):
            for uid, alias in self.admin_config.items():
                alias_h = _html.escape(str(alias))
                uid_h = _html.escape(str(uid))
                lines.append(f"• {alias_h} – {uid_h}")
        await query.edit_message_text("\n".join(lines), parse_mode="HTML")

    # ---------- Public helper ----------
    # ---------- Invite Link Conversation Handlers ----------

    @admin_only
    async def start_invite_link_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Asks the admin for the user_id to create an invite link for."""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "🔗 لطفاً آیدی عددی کاربری که می‌خواهید برای او لینک دعوت بسازید را ارسال کنید.\n\n"
            "برای لغو /cancel را بزنید."
        )
        return self.GET_INVITE_LINK_USER_ID

    @admin_only
    async def create_and_send_invite_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receives user_id, creates links, sends them, and confirms."""
        admin_user = update.effective_user
        target_user_id_str = update.message.text

        if not target_user_id_str.isdigit():
            await update.message.reply_text("❌ آیدی کاربر باید یک عدد باشد. لطفاً دوباره تلاش کنید یا /cancel را بزنید.")
            return self.GET_INVITE_LINK_USER_ID

        target_user_id = int(target_user_id_str)

        await update.message.reply_text(f"⏳ در حال ایجاد لینک برای کاربر `{target_user_id}`...", parse_mode="Markdown")

        try:
            # We need to use the new method name from the manager  
            logger.info(f"DEBUG: Creating invite links for user {target_user_id}")
            links = await InviteLinkManager.ensure_one_time_links(context.bot, target_user_id)
            logger.info(f"DEBUG: Links created successfully: {len(links) if links else 0} links")

            if not links:
                await admin_user.send_message(
                    f"❌ متاسفانه ایجاد لینک برای کاربر `{target_user_id}` با خطا مواجه شد. "
                    f"ممکن است ربات دسترسی لازم در کانال‌ها را نداشته باشد. لطفاً لاگ‌ها را بررسی کنید.",
                    parse_mode="Markdown"
                )
                return ConversationHandler.END

            # Send links to the target user using main bot (not manager bot)
            link_message = "سلام! لینک‌های دعوت شما برای عضویت در کانال‌ها آماده شد:\n\n" + "\n".join(links)
            try:
                # Determine which bot instance to use - prioritize main bot
                if self.main_bot_app:
                    # Check if main_bot_app has 'application' attribute (for Application object)
                    if hasattr(self.main_bot_app, "application") and hasattr(self.main_bot_app.application, "bot"):
                        bot_to_use = self.main_bot_app.application.bot
                    # Check if main_bot_app has direct 'bot' attribute
                    elif hasattr(self.main_bot_app, "bot"):
                        bot_to_use = self.main_bot_app.bot
                    else:
                        logger.warning("main_bot_app does not have expected bot attribute structure, falling back to manager bot")
                        bot_to_use = context.bot
                else:
                    logger.warning("main_bot_app not available, using manager bot (may fail)")
                    bot_to_use = context.bot
                
                # Send without parse_mode to avoid entity parsing issues
                await bot_to_use.send_message(chat_id=target_user_id, text=link_message, parse_mode=None)

                # Confirm to admin
                await admin_user.send_message(
                    f"✅ لینک‌های دعوت با موفقیت برای کاربر `{target_user_id}` ارسال شد.",
                    parse_mode="Markdown"
                )
            except Exception as e:
                from telegram.error import BadRequest, Forbidden, TelegramError
                
                # More specific error handling for Telegram errors
                error_str = str(e).lower()
                
                if isinstance(e, Forbidden):
                    if "bot was blocked by the user" in error_str:
                        error_msg = (
                            f"🚫 **کاربر `{target_user_id}` بات را بلاک کرده**\n\n"
                            "از کاربر بخواهید بات را unblock کرده و `/start` بزند.\n\n"
                            "**لینک‌های ایجاد شده:**\n" + "\n".join(links)
                        )
                    else:
                        error_msg = (
                            f"🚫 **دسترسی محدود به کاربر `{target_user_id}`**\n\n"
                            f"**دلیل:** {str(e)}\n\n"
                            "**لینک‌های ایجاد شده:**\n" + "\n".join(links)
                        )
                elif isinstance(e, BadRequest):
                    if "chat not found" in error_str:
                        error_msg = (
                            f"❌ **کاربر `{target_user_id}` یافت نشد**\n\n"
                            "**دلایل احتمالی:**\n"
                            "• کاربر اکانت خود را حذف کرده\n"
                            "• کاربر هنوز با بات چت شروع نکرده (/start نزده)\n\n"
                            "**راه‌حل:** از کاربر بخواهید ابتدا `/start` را در بات بزند.\n\n"
                            "**لینک‌های ایجاد شده:**\n" + "\n".join(links)
                        )
                    elif "can't parse entities" in error_str:
                        error_msg = (
                            f"⚠️ **خطای قالب‌بندی پیام برای کاربر `{target_user_id}`**\n\n"
                            "مشکل در قالب‌بندی متن پیام وجود دارد.\n\n"
                            "**لینک‌های ایجاد شده:**\n" + "\n".join(links)
                        )
                    else:
                        error_msg = (
                            f"❌ **درخواست نامعتبر برای کاربر `{target_user_id}`**\n\n"
                            f"**جزئیات:** {str(e)}\n\n"
                            "**لینک‌های ایجاد شده:**\n" + "\n".join(links)
                        )
                else:
                    error_msg = (
                        f"⚠️ **خطای غیرمنتظره در ارسال به کاربر `{target_user_id}`**\n\n"
                        f"**نوع خطا:** {type(e).__name__}\n"
                        f"**جزئیات:** {str(e)}\n\n"
                        "**لینک‌های ایجاد شده:**\n" + "\n".join(links)
                    )
                
                logger.error(f"Failed to send invite links to user {target_user_id}: {e}")
                try:
                    await admin_user.send_message(error_msg, parse_mode="Markdown")
                except Exception as parse_error:
                    # Fallback: send without markdown if parse fails
                    logger.warning(f"Markdown parse failed, sending plain text: {parse_error}")
                    await admin_user.send_message(error_msg.replace("**", "").replace("*", ""))

        except Exception as e:
            logger.error(f"Error in ensure_one_time_links for user {target_user_id}: {e}", exc_info=True)
            await admin_user.send_message(f"❌ یک خطای پیش‌بینی نشده در ایجاد لینک رخ داد: {e}")

        return ConversationHandler.END

    async def cancel_invite_link_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancels the invite link creation conversation."""
        await update.message.reply_text("عملیات ایجاد لینک دعوت لغو شد.")
        # To improve UX, we could show the main menu again, but this is sufficient.
        return ConversationHandler.END

    # --- Ban/Unban User Handlers ---
    async def ban_unban_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            text="لطفاً شناسه کاربری (User ID) کاربر مورد نظر را برای مسدود/آزاد کردن ارسال کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("لغو عملیات", callback_data='cancel_ban_unban')]])
        )
        return AWAIT_USER_ID_FOR_BAN

    async def ban_unban_receive_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id_str = update.message.text
        if not user_id_str.isdigit():
            await update.message.reply_text("شناسه کاربری نامعتبر است. لطفاً یک عدد ارسال کنید.")
            return AWAIT_USER_ID_FOR_BAN

        user_id = int(user_id_str)
        user = DatabaseQueries.get_user_by_telegram_id(user_id)

        if not user:
            await update.message.reply_text(
                f"کاربری با شناسه {user_id} یافت نشد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("لغو عملیات", callback_data='cancel_ban_unban')]])
            )
            return AWAIT_USER_ID_FOR_BAN

        status = DatabaseQueries.get_user_status(user_id)
        status_text = "مسدود 🛑" if status == 'banned' else "فعال ✅"

        keyboard = [
            [InlineKeyboardButton("مسدود کردن کاربر", callback_data=f'ban_user_{user_id}')],
            [InlineKeyboardButton("آزاد کردن کاربر", callback_data=f'unban_user_{user_id}')],
            [InlineKeyboardButton("لغو عملیات", callback_data='cancel_ban_unban')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"کاربر: {user['full_name'] or user_id}\nوضعیت فعلی: {status_text}\n\nلطفاً اقدام مورد نظر را انتخاب کنید:",
            reply_markup=reply_markup
        )
        return AWAIT_BAN_CHOICE

    async def ban_unban_set_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        action, _, user_id_str = query.data.partition('_user_')
        user_id = int(user_id_str)
        new_status = 'banned' if action == 'ban' else 'active'
        
        # Pass bot instance for chat history deletion when banning
        bot_instance = context.bot if new_status == 'banned' else None
        if DatabaseQueries.set_user_status(user_id, new_status, bot_instance):
            status_text = "مسدود شد" if new_status == 'banned' else "آزاد شد"
            await query.edit_message_text(f"کاربر با شناسه {user_id} با موفقیت {status_text}.")
        else:
            await query.edit_message_text("خطایی در به‌روزرسانی وضعیت کاربر رخ داد.")

        # Return to the main users menu
        await self._users_submenu(query)
        return ConversationHandler.END

    async def ban_unban_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("عملیات مسدود/آزاد کردن لغو شد.")
        await self._users_submenu(query)
        return ConversationHandler.END

    # --- Ban/Unban User Handlers ---
    async def ban_unban_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            text="لطفاً شناسه کاربری (User ID) کاربر مورد نظر را برای مسدود/آزاد کردن ارسال کنید.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("لغو عملیات", callback_data='cancel_ban_unban')]])
        )
        return self.AWAIT_USER_ID_FOR_BAN

    async def ban_unban_receive_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id_str = update.message.text
        if not user_id_str.isdigit():
            await update.message.reply_text("شناسه کاربری نامعتبر است. لطفاً یک عدد ارسال کنید.")
            return self.AWAIT_USER_ID_FOR_BAN

        user_id = int(user_id_str)
        user = DatabaseQueries.get_user_by_telegram_id(user_id)

        if not user:
            await update.message.reply_text(
                f"کاربری با شناسه {user_id} یافت نشد.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("لغو عملیات", callback_data='cancel_ban_unban')]])
            )
            return self.AWAIT_USER_ID_FOR_BAN

        status = DatabaseQueries.get_user_status(user_id)
        status_text = "مسدود 🛑" if status == 'banned' else "فعال ✅"

        keyboard = [
            [InlineKeyboardButton("مسدود کردن کاربر", callback_data=f'ban_user_{user_id}')],
            [InlineKeyboardButton("آزاد کردن کاربر", callback_data=f'unban_user_{user_id}')],
            [InlineKeyboardButton("لغو عملیات", callback_data='cancel_ban_unban')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"کاربر: {user['full_name'] or user_id}\nوضعیت فعلی: {status_text}\n\nلطفاً اقدام مورد نظر را انتخاب کنید:",
            reply_markup=reply_markup
        )
        return self.AWAIT_BAN_CHOICE

    async def ban_unban_set_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        action, _, user_id_str = query.data.partition('_user_')
        user_id = int(user_id_str)
        new_status = 'banned' if action == 'ban' else 'active'
        
        # Pass bot instance for chat history deletion when banning
        bot_instance = context.bot if new_status == 'banned' else None
        if DatabaseQueries.set_user_status(user_id, new_status, bot_instance):
            status_text = "مسدود شد" if new_status == 'banned' else "آزاد شد"
            await query.edit_message_text(f"کاربر با شناسه {user_id} با موفقیت {status_text}.")
        else:
            await query.edit_message_text("خطایی در به‌روزرسانی وضعیت کاربر رخ داد.")

        # Return to the main users menu
        await self._users_submenu(query)
        return ConversationHandler.END

    async def ban_unban_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("عملیات مسدود/آزاد کردن لغو شد.")
        await self._users_submenu(query)
        return ConversationHandler.END

    async def _settings_support_submenu(self, query):
        """Support users management submenu"""
        keyboard = [
            [InlineKeyboardButton("➕ افزودن پشتیبان", callback_data=self.SUPPORT_ADD)],
            [InlineKeyboardButton("📋 فهرست پشتیبان‌ها", callback_data=self.SUPPORT_LIST)],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.SETTINGS_MENU)],
        ]
        await query.edit_message_text("👥 *مدیریت پشتیبان‌ها*:\nگزینه مورد نظر را انتخاب کنید.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_support_users(self, query):
        rows = DatabaseQueries.get_all_support_users()
        if not rows:
            await query.edit_message_text("👥 هیچ کاربر پشتیبانی تعریف نشده است.")
            return
        lines = ["👥 *فهرست پشتیبان‌ها:*\n"]
        keyboard = []
        for row in rows:
            if isinstance(row, (list, tuple)):
                tg_id = row[0]
                added_at = row[2] if len(row) > 2 else None
            else:
                tg_id = row["telegram_id"] if "telegram_id" in row.keys() else row[0]
                added_at = row["added_at"] if "added_at" in row.keys() else (row[2] if len(row) > 2 else None)
            lines.append(f"• {tg_id} – {added_at}")
            keyboard.append([InlineKeyboardButton(f"❌ حذف {tg_id}", callback_data=f"remove_support_{tg_id}")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data=self.SUPPORT_MENU)])
        await query.edit_message_text("\n".join(lines), parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    # ---- Extend Subscription Duration (Single User) Flow ----
    @staff_required
    async def start_extend_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Entry point: ask admin for target user identifier (username or Telegram ID)."""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "لطفاً شناسه عددی یا نام کاربری (بدون @) کاربر مورد نظر را ارسال کنید:\n\nبرای لغو /cancel را بزنید.",
            parse_mode="Markdown",
        )
        return self.AWAIT_EXTEND_USER_ID

    async def receive_extend_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        identifier = (update.message.text or "").strip()
        user_id = None
        # Convert Persian digits to English if helper exists
        try:
            from utils.locale_utils import fa_to_en_digits
            identifier = fa_to_en_digits(identifier)
        except Exception:
            pass

        if identifier.isdigit():
            user_id = int(identifier)
        else:
            # strip leading @ if present
            if identifier.startswith("@"):
                identifier = identifier[1:]
            # Search user by username
            results = DatabaseQueries.search_users(identifier)
            if results:
                # Take first match
                row = results[0]
                user_id = row["user_id"] if isinstance(row, dict) else row[0]
        if not user_id:
            await update.message.reply_text("کاربر یافت نشد. دوباره تلاش کنید یا /cancel را بزنید.")
            return self.AWAIT_EXTEND_USER_ID

        context.user_data["extend_target_user_id"] = user_id
        await update.message.reply_text("تعداد روزهایی که می‌خواهید به اشتراک کاربر اضافه شود را وارد کنید:")
        return self.AWAIT_EXTEND_DAYS

    async def receive_extend_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        days_str = (update.message.text or "").strip()
        try:
            days = int(days_str)
        except ValueError:
            await update.message.reply_text("لطفاً یک عدد معتبر وارد کنید.")
            return self.AWAIT_EXTEND_DAYS
        if days <= 0:
            await update.message.reply_text("تعداد روز باید بیشتر از ۰ باشد.")
            return self.AWAIT_EXTEND_DAYS

        user_id = context.user_data.get("extend_target_user_id")
        if not user_id:
            await update.message.reply_text("خطا: شناسه کاربر در حافظه یافت نشد. لطفاً از ابتدا دوباره تلاش کنید.")
            return ConversationHandler.END

        success = DatabaseQueries.extend_subscription_duration(user_id, days)
        if success:
            await update.message.reply_text(f"✅ اشتراک کاربر {user_id} به‌مدت {days} روز تمدید شد.")
            # Notify the user in the main bot (if we have access to bot instance)
            if self.main_bot_app:
                try:
                    # Check if main_bot_app has 'application' attribute (for Application object)
                    if hasattr(self.main_bot_app, "application") and hasattr(self.main_bot_app.application, "bot"):
                        await self.main_bot_app.application.bot.send_message(
                            chat_id=user_id,
                            text=f"اشتراک شما به‌مدت {days} روز تمدید شد. از همراهی شما سپاسگزاریم!"
                        )
                    # Check if main_bot_app has direct 'bot' attribute
                    elif hasattr(self.main_bot_app, "bot"):
                        await self.main_bot_app.bot.send_message(
                            chat_id=user_id,
                            text=f"اشتراک شما به‌مدت {days} روز تمدید شد. از همراهی شما سپاسگزاریم!"
                        )
                    else:
                        logger.warning("main_bot_app does not have expected bot attribute structure")
                except Exception as e:
                    logger.warning("Failed to notify user %s about extension: %s", user_id, e)
        else:
            await update.message.reply_text("❌ تمدید اشتراک ناموفق بود. کاربر ممکن است اشتراک فعالی نداشته باشد.")
        # After completion, show users submenu again
        class _DummyQuery:
            def __init__(self, message):
                self.message = message
            async def edit_message_text(self, *args, **kwargs):
                await self.message.reply_text(*args, **kwargs)
        await self._users_submenu(_DummyQuery(update.message))
        return ConversationHandler.END

    async def cancel_extend_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("عملیات لغو شد.")
        # Create a DummyQuery wrapper for _users_submenu
        class _DummyQuery:
            def __init__(self, message):
                self.message = message
            async def edit_message_text(self, *args, **kwargs):
                await self.message.reply_text(*args, **kwargs)
        await self._users_submenu(_DummyQuery(update.message))
        return ConversationHandler.END

    # ---- Extend Subscription Duration for All Users (Bulk) ----
    @staff_required
    async def start_extend_subscription_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "🔔 لطفاً تعداد روزهایی که می‌خواهید به تمام کاربران فعال اضافه شود را وارد کنید:\n\nبرای لغو /cancel را بزنید.",
            parse_mode="Markdown",
        )
        return self.AWAIT_EXTEND_ALL_DAYS

    async def receive_extend_all_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        days_str = (update.message.text or "").strip()
        try:
            days = int(days_str)
        except ValueError:
            await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید.")
            return self.AWAIT_EXTEND_ALL_DAYS
        if days <= 0:
            await update.message.reply_text("❌ تعداد روز باید بیشتر از ۰ باشد.")
            return self.AWAIT_EXTEND_ALL_DAYS

        updated = DatabaseQueries.extend_subscription_duration_all(days)
        await update.message.reply_text(f"✅ اشتراک {updated} کاربر به‌مدت {days} روز تمدید شد.")

        # Notify each active subscriber
        if self.main_bot_app:
            try:
                users = DatabaseQueries.get_all_active_subscribers()
                bot_instance = None
                
                # Determine the correct bot instance
                if hasattr(self.main_bot_app, "application") and hasattr(self.main_bot_app.application, "bot"):
                    bot_instance = self.main_bot_app.application.bot
                elif hasattr(self.main_bot_app, "bot"):
                    bot_instance = self.main_bot_app.bot
                
                if bot_instance:
                    for row in users:
                        # Handle sqlite3.Row objects properly
                        if hasattr(row, 'keys'):  # sqlite3.Row
                            uid = row[0] if len(row) > 0 else None
                        elif isinstance(row, (list, tuple)):
                            uid = row[0]
                        elif isinstance(row, dict):
                            uid = row.get("user_id")
                        else:
                            uid = None
                        
                        if not uid:
                            continue
                        try:
                            await bot_instance.send_message(
                                chat_id=uid,
                                text=f"اشتراک شما به‌مدت {days} روز تمدید شد. از همراهی شما سپاسگزاریم!"
                            )
                        except Exception:
                            pass  # Ignore failures for individual users
                else:
                    logger.warning("Could not find bot instance in main_bot_app")
            except Exception as e:
                logger.warning("Failed to broadcast extension notification: %s", e)

        class _DummyQuery:
            def __init__(self, message):
                self.message = message
            async def edit_message_text(self, *args, **kwargs):
                await self.message.reply_text(*args, **kwargs)

        await self._users_submenu(_DummyQuery(update.message))
        return ConversationHandler.END

    async def cancel_extend_subscription_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("عملیات لغو شد.")
        # Create a DummyQuery wrapper for _users_submenu
        class _DummyQuery:
            def __init__(self, message):
                self.message = message
            async def edit_message_text(self, *args, **kwargs):
                await self.message.reply_text(*args, **kwargs)
        await self._users_submenu(_DummyQuery(update.message))
        return ConversationHandler.END

    # ---- Check Subscription Status Flow ----
    @staff_required
    async def start_check_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("لطفاً شناسه عددی یا نام کاربری کاربر را وارد کنید:")
        return self.AWAIT_CHECK_USER_ID

    async def receive_check_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        identifier = (update.message.text or "").strip()
        try:
            from utils.locale_utils import fa_to_en_digits
            identifier = fa_to_en_digits(identifier)
        except Exception:
            pass
        user_id = None
        if identifier.isdigit():
            user_id = int(identifier)
        else:
            if identifier.startswith("@"):
                identifier = identifier[1:]
            results = DatabaseQueries.search_users(identifier)
            if results:
                # Take first match
                row = results[0]
                user_id = row["user_id"] if isinstance(row, dict) else row[0]
        if not user_id:
            await update.message.reply_text("کاربر یافت نشد. دوباره تلاش کنید یا /cancel.")
            return self.AWAIT_CHECK_USER_ID

        sub_row = DatabaseQueries.get_user_active_subscription(user_id)
        if not sub_row:
            await update.message.reply_text("این کاربر اشتراک فعالی ندارد.")
            # Create a DummyQuery wrapper for _users_submenu
            class _DummyQuery:
                def __init__(self, message):
                    self.message = message
                async def edit_message_text(self, *args, **kwargs):
                    await self.message.reply_text(*args, **kwargs)
            await self._users_submenu(_DummyQuery(update.message))
            return ConversationHandler.END

        end_date_str = sub_row["end_date"] if isinstance(sub_row, dict) else sub_row[5]  # assuming column order
        try:
            from datetime import datetime
            end_dt = datetime.fromisoformat(end_date_str)
        except Exception:
            from datetime import datetime
            try:
                end_dt = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                end_dt = None
        if end_dt:
            from zoneinfo import ZoneInfo
            iran_tz = ZoneInfo("Asia/Tehran")
            # ensure both datetimes Tehran tz
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=iran_tz)
            else:
                end_dt = end_dt.astimezone(iran_tz)
            now = datetime.now(tz=iran_tz)
            delta = end_dt - now
            if delta.total_seconds() <= 0:
                # Possibly incorrect record; attempt to find a future subscription
                other_active = DatabaseQueries.get_user_active_subscriptions(user_id) if hasattr(DatabaseQueries, 'get_user_active_subscriptions') else None
                if other_active:
                    # Expect list of rows sorted by end_date DESC; pick first with future end_date
                    for row in other_active:
                        end_str = row['end_date'] if isinstance(row, dict) else row[5]
                        try:
                            alt_dt = datetime.fromisoformat(end_str)
                        except Exception:
                            try:
                                alt_dt = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S")
                            except Exception:
                                continue
                        if alt_dt.tzinfo is None:
                            alt_dt = alt_dt.replace(tzinfo=iran_tz)
                        else:
                            alt_dt = alt_dt.astimezone(iran_tz)
                        if alt_dt > now:
                            end_dt = alt_dt
                            delta = end_dt - now
                            break
                if delta.total_seconds() <= 0:
                    msg = "اشتراک کاربر منقضی شده است."
                else:
                    # fallthrough to human_rem below
                    pass
            if delta.total_seconds() > 0:
                days = delta.days
                hours = delta.seconds // 3600
                minutes = (delta.seconds % 3600) // 60
                human_rem = f"{days} روز"
                if hours or minutes:
                    human_rem += f" و {hours} ساعت و {minutes} دقیقه"
                msg = (
                    f"اعتبار اشتراک کاربر تا تاریخ {end_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                    f"(حدود {human_rem} باقی مانده)"
                )
        else:
            msg = f"تاریخ پایان اشتراک: {end_date_str}"
        await update.message.reply_text(msg)

        # Wrap message in a lightweight DummyQuery so _users_submenu works
        class _DummyQuery:
            def __init__(self, message):
                self.message = message
            async def edit_message_text(self, *args, **kwargs):
                await self.message.reply_text(*args, **kwargs)
        await self._users_submenu(_DummyQuery(update.message))
        return ConversationHandler.END

    def get_handlers(self):
        """Return telegram.ext handlers to register in the dispatcher."""
        handlers = [
            CommandHandler("admin", self.show_admin_menu),
        ]

        # Conversation handler for creating invite links
        invite_link_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_invite_link_creation, pattern=f"^{self.CREATE_INVITE_LINK}$")],
            states={
                self.GET_INVITE_LINK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.create_and_send_invite_link)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_invite_link_creation)],
            per_user=True,
            per_chat=True,
        )
        handlers.append(invite_link_conv_handler)

        # Conversation handler for extending subscription duration
        extend_sub_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_extend_subscription, pattern=f'^{self.EXTEND_SUB_CALLBACK}$')],
            states={
                self.AWAIT_EXTEND_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_extend_user_id)],
                self.AWAIT_EXTEND_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_extend_days)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel_extend_subscription)],
            per_user=True,
            per_chat=True,
        )
        handlers.append(extend_sub_conv_handler)

        # Conversation handler for checking subscription status
        check_sub_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_check_subscription, pattern=f'^{self.CHECK_SUB_STATUS}$')],
            states={
                self.AWAIT_CHECK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_check_user_id)],
            },
            fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)],
            per_user=True,
            per_chat=True,
        )
        handlers.append(check_sub_conv_handler)
        ban_unban_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.ban_unban_start, pattern=f'^{self.BAN_UNBAN_USER}$')],
            states={
                self.AWAIT_USER_ID_FOR_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.ban_unban_receive_user_id)],
                self.AWAIT_BAN_CHOICE: [CallbackQueryHandler(self.ban_unban_set_status, pattern=r'^(ban|unban)_user_')]
            },
            fallbacks=[
                CallbackQueryHandler(self.ban_unban_cancel, pattern='^cancel_ban_unban$'),
                CommandHandler('cancel', self.ban_unban_cancel)
                ],
            # Since this is a nested conversation, we don't map to parent, but end it.
            # The parent handler will catch the back-to-menu callbacks.
        )
        handlers.append(ban_unban_handler)

        # Channel multi-select picker for broadcast with link
        handlers.append(CallbackQueryHandler(self._broadcast_wl_picker_callback, pattern=r"^(chpick_.*|chpick_all|chpick_done)$"))

        # ---- Renew buttons settings handlers ----
        handlers.append(CallbackQueryHandler(self._settings_renew_buttons_submenu, pattern='^settings_renew_buttons$'))
        handlers.append(CallbackQueryHandler(self._settings_renew_toggle_callback, pattern=r'^toggle_renew_(free|products)$'))
        handlers.append(CallbackQueryHandler(self._settings_renew_toggle_callback, pattern=r'^toggle_renew_(cat|plan)_-?\d+$'))

        # Conversation handler for extend all subscriptions
        extend_all_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_extend_subscription_all, pattern=f'^{self.EXTEND_SUB_ALL_CALLBACK}$')],
            states={
                self.AWAIT_EXTEND_ALL_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_extend_all_days)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel_extend_subscription_all)],
        )
        handlers.append(extend_all_conv_handler)

    async def _crypto_panel_entry(self, query, context):
        """Handle crypto panel entry from admin menu"""
        await query.answer()
        
        # Create inline keyboard with crypto panel options
        keyboard = [
            [InlineKeyboardButton("🏥 وضعیت سیستم", callback_data="crypto_system_status"), InlineKeyboardButton("📊 آمار پرداخت‌ها", callback_data="crypto_payment_stats")],
            [InlineKeyboardButton("🔒 امنیت سیستم", callback_data="crypto_security"), InlineKeyboardButton("📈 گزارش‌ها", callback_data="crypto_reports")],
            [InlineKeyboardButton("💰 اطلاعات کیف پول", callback_data="crypto_wallet_info"), InlineKeyboardButton("🔍 تست TX دستی", callback_data="crypto_manual_tx")],
            [InlineKeyboardButton("✅ تایید پرداخت‌ها", callback_data="crypto_verify_payments")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.PAYMENTS_MENU)]
        ]
        
        await query.edit_message_text(
            "👑 **پنل مدیریت کریپتو** 👑\n\n"
            "به پنل مدیریت سیستم پرداخت USDT خوش آمدید!\n\n"
            "🔧 **امکانات در دسترس:**\n"
            "• نظارت بر وضعیت سیستم\n"
            "• مشاهده آمار و گزارش‌ها\n"
            "• مدیریت امنیت\n"
            "• تست دستی تراکنش‌ها\n\n"
            "برای شروع، یکی از گزینه‌های زیر را انتخاب کنید:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    def get_handlers(self):
        """Return telegram.ext handlers to register in the dispatcher."""
        handlers = [
            CommandHandler("admin", self.show_admin_menu),
        ]

        # Conversation handler for creating invite links
        invite_link_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_invite_link_creation, pattern=f"^{self.CREATE_INVITE_LINK}$")],
            states={
                self.GET_INVITE_LINK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.create_and_send_invite_link)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_invite_link_creation)],
            per_user=True,
            per_chat=True,
        )
        handlers.append(invite_link_conv_handler)

        # Conversation handler for extending subscription duration
        extend_sub_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_extend_subscription, pattern=f'^{self.EXTEND_SUB_CALLBACK}$')],
            states={
                self.AWAIT_EXTEND_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_extend_user_id)],
                self.AWAIT_EXTEND_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_extend_days)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel_extend_subscription)],
            per_user=True,
            per_chat=True,
        )
        handlers.append(extend_sub_conv_handler)

        # Conversation handler for checking subscription status
        check_sub_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_check_subscription, pattern=f'^{self.CHECK_SUB_STATUS}$')],
            states={
                self.AWAIT_CHECK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_check_user_id)],
            },
            fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)],
            per_user=True,
            per_chat=True,
        )
        handlers.append(check_sub_conv_handler)

        # Conversation handler for ban/unban user
        ban_unban_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.ban_unban_start, pattern=f'^{self.BAN_UNBAN_USER}$')],
            states={
                self.AWAIT_USER_ID_FOR_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.ban_unban_receive_user_id)],
                self.AWAIT_BAN_CHOICE: [CallbackQueryHandler(self.ban_unban_set_status, pattern=r'^(ban|unban)_user_')]
            },
            fallbacks=[
                CallbackQueryHandler(self.ban_unban_cancel, pattern='^cancel_ban_unban$'),
                CommandHandler('cancel', self.ban_unban_cancel)
            ],
        )
        handlers.append(ban_unban_handler)

        # Conversation handler for extend all subscriptions
        extend_all_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_extend_subscription_all, pattern=f'^{self.EXTEND_SUB_ALL_CALLBACK}$')],
            states={
                self.AWAIT_EXTEND_ALL_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_extend_all_days)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel_extend_subscription_all)],
        )
        handlers.append(extend_all_conv_handler)

        # Channel multi-select picker for broadcast with link
        handlers.append(CallbackQueryHandler(self._broadcast_wl_picker_callback, pattern=r"^(chpick_.*|chpick_all|chpick_done)$"))

        # ---- Renew buttons settings handlers ----
        handlers.append(CallbackQueryHandler(self._settings_renew_buttons_submenu, pattern='^settings_renew_buttons$'))
        handlers.append(CallbackQueryHandler(self._settings_renew_toggle_callback, pattern=r'^toggle_renew_(free|products)$'))
        handlers.append(CallbackQueryHandler(self._settings_renew_toggle_callback, pattern=r'^toggle_renew_(cat|plan)_-?\d+$'))

        # ---- Support user management handlers ----
        handlers.extend(self.support_manager.get_handlers())
        
        # ---- Export subscribers handlers ----
        handlers.append(CallbackQueryHandler(self.export_handler.entry, pattern=f'^{self.EXPORT_SUBS_MENU}$'))
        handlers.append(CallbackQueryHandler(self.export_handler.handle_product, pattern=r'^exp_prod_\d+$'))

        # This is the main handler for all other admin menu callbacks
        # Note: The invite link and ban/unban callbacks are handled by their respective ConversationHandlers.
        handlers.append(CallbackQueryHandler(self.admin_menu_callback, pattern="^(admin_|users_|tickets_|payments_|broadcast_|bc_cat_|bc_plan_|bc_chan_|audience_|broadcast_continue$|broadcast_cancel$|settings_(?!mid_level)|products_|discounts_|view_discount_|edit_discount_|discount_edit_|toggle_discount_|delete_discount_|confirm_delete_discount_|view_plan_|toggle_plan_|delete_plan_|confirm_delete_plan_|planpick_|crypto_panel|crypto_|product_sales_)"))

        # ---- Promotional category handlers ----
        from handlers.admin_promotional_category import (
            show_promotional_category_admin, show_category_selection,
            set_promotional_category_handler, set_promotional_product_handler, toggle_promotional_category_handler,
            prompt_promotional_change_text_handler, receive_new_promo_text_message,
            manage_existing_buttons_handler, toggle_promotional_button_handler, delete_promotional_button_handler,
            edit_button_text_handler, receive_new_button_text
        )
        handlers.append(CallbackQueryHandler(show_promotional_category_admin, pattern="^promo_category_admin$"))
        handlers.append(CallbackQueryHandler(show_category_selection, pattern="^promo_select_category$"))
        handlers.append(CallbackQueryHandler(set_promotional_category_handler, pattern="^promo_set_category_\d+$"))
        handlers.append(CallbackQueryHandler(set_promotional_product_handler, pattern="^promo_set_product_\d+$"))
        handlers.append(CallbackQueryHandler(toggle_promotional_category_handler, pattern="^promo_toggle$"))
        
        # New handlers for multiple promotional buttons
        handlers.append(CallbackQueryHandler(manage_existing_buttons_handler, pattern="^manage_existing_buttons$"))
        handlers.append(CallbackQueryHandler(toggle_promotional_button_handler, pattern="^toggle_button_\d+$"))
        handlers.append(CallbackQueryHandler(delete_promotional_button_handler, pattern="^delete_button_\d+$"))

        # Conversation handler for changing promotional button text
        promo_text_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(prompt_promotional_change_text_handler, pattern="^promo_change_text$")],
            states={
                AWAIT_PROMO_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_promo_text_message)],
            },
            fallbacks=[CallbackQueryHandler(show_promotional_category_admin, pattern="^promo_category_admin$")],
            per_user=True,
            per_chat=True,
        )
        handlers.append(promo_text_conv_handler)
        
        # Button text editing conversation handler
        AWAIT_BUTTON_TEXT = 1
        button_text_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(edit_button_text_handler, pattern="^edit_button_text_\d+$")],
            states={
                AWAIT_BUTTON_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_button_text)],
            },
            fallbacks=[CallbackQueryHandler(manage_existing_buttons_handler, pattern="^manage_existing_buttons$")],
            per_user=True,
            per_chat=True,
        )
        handlers.append(button_text_conv_handler)

        # ---- Mid-level user management handlers ----
        handlers.append(CallbackQueryHandler(self._settings_mid_level_submenu, pattern='^settings_mid_level$'))
        handlers.append(CallbackQueryHandler(self._mid_level_add_user_prompt, pattern='^mid_level_add$'))
        handlers.append(CallbackQueryHandler(self._mid_level_remove_user, pattern=r'^mid_level_remove_(\d+)$'))
        handlers.append(CallbackQueryHandler(self._mid_level_list_users, pattern='^mid_level_list$'))
        
        return handlers

    # ---- Mid-level user management methods ----
    async def _settings_mid_level_submenu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show mid-level user management submenu"""
        query = update.callback_query
        await query.answer()
        
        # Get current mid-level users from database
        mid_level_users = DatabaseQueries.get_all_mid_level_users()
        
        keyboard = [
            [InlineKeyboardButton("➕ افزودن کاربر میان‌رده", callback_data="mid_level_add")],
            [InlineKeyboardButton("📋 مشاهده لیست", callback_data="mid_level_list")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="settings")],
        ]
        
        count = len(mid_level_users)
        text = f"🏅 *مدیریت کاربران میان‌رده*\n\n"
        text += f"📊 تعداد کاربران میان‌رده: {count}\n\n"
        text += "دسترسی‌های کاربران میان‌رده:\n"
        text += "• 🎫 مدیریت تیکت‌ها\n"
        text += "• 💳 مدیریت پرداخت‌ها\n"
        text += "• 📢 ارسال پیام همگانی"
        
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def _mid_level_add_user_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt admin to enter user ID for mid-level access"""
        query = update.callback_query
        await query.answer()
        
        text = "➕ *افزودن کاربر میان‌رده*\n\n"
        text += "لطفاً ID کاربر را وارد کنید:\n\n"
        text += "⚠️ توجه: ID عددی کاربر را وارد کنید نه username"
        
        keyboard = [[InlineKeyboardButton("❌ لغو", callback_data="settings_mid_level")]]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Set a flag to handle the next message as user ID
        context.user_data['awaiting_mid_level_user_id'] = True
    
    async def _mid_level_list_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show list of current mid-level users with option to remove"""
        query = update.callback_query
        await query.answer()
        
        mid_level_users = DatabaseQueries.get_all_mid_level_users()
        
        if not mid_level_users:
            text = "📋 *لیست کاربران میان‌رده*\n\n😔 هیچ کاربر میان‌رده‌ای یافت نشد."
            keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="settings_mid_level")]]
        else:
            text = f"📋 *لیست کاربران میان‌رده* ({len(mid_level_users)})\n\n"
            
            keyboard = []
            for user in mid_level_users:
                user_id = user.get('telegram_id')
                alias = user.get('alias', '')
                created_at = user.get('created_at', '')
                
                display_text = f"👤 {user_id}"
                if alias:
                    display_text += f" ({alias})"
                
                text += f"{display_text}\n• تاریخ اضافه: {created_at[:10] if created_at else 'N/A'}\n\n"
                
                keyboard.append([InlineKeyboardButton(
                    f"❌ حذف {user_id}", 
                    callback_data=f"mid_level_remove_{user_id}"
                )])
            
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="settings_mid_level")])
        
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def _mid_level_remove_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove a user from mid-level access"""
        query = update.callback_query
        await query.answer()
        
        # Extract user ID from callback data
        user_id = int(query.data.split('_')[-1])
        
        success = DatabaseQueries.remove_mid_level_user(user_id)
        
        if success:
            text = f"✅ کاربر {user_id} با موفقیت از لیست میان‌رده‌ها حذف شد."
        else:
            text = f"❌ خطا در حذف کاربر {user_id}."
        
        keyboard = [
            [InlineKeyboardButton("📋 بازگشت به لیست", callback_data="mid_level_list")],
            [InlineKeyboardButton("🔙 منوی میان‌رده", callback_data="settings_mid_level")]
        ]
        
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    # ========================================
    # Product Sales Report Methods
    # ========================================
    
    async def _show_product_sales_reports_menu(self, query):
        """Show main menu for product sales reports."""
        keyboard = [
            [InlineKeyboardButton("📊 لیست محصولات", callback_data="product_sales_list")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=self.PAYMENTS_MENU)],
        ]
        text = "📊 *گزارش فروش محصولات*\n\nلطفاً یکی از گزینه‌ها را انتخاب کنید:"
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def _show_product_sales_list(self, query):
        """Show list of products with sales data for selection."""
        try:
            plans = self.db_queries.get_all_plans_with_sales_data()
            
            if not plans:
                text = "😔 *هیچ محصولی یافت نشد*\n\nهنوز هیچ محصولی تعریف نشده است."
                keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="product_sales_reports")]]
                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                return
            
            text = "📊 *لیست محصولات*\n\n"
            keyboard = []
            
            for plan in plans:
                plan_id = plan['id']
                plan_name = plan['name']
                total_sales = plan['total_sales']
                price_irr = plan['price_irr']
                price_usdt = plan['price_usdt']
                
                # Format price display
                price_text = ""
                if price_irr > 0:
                    price_text += f"{price_irr:,.0f} ریال"
                if price_usdt > 0:
                    if price_text:
                        price_text += " / "
                    price_text += f"{price_usdt} USDT"
                
                text += f"📾 **{plan_name}**\n"
                text += f"• قیمت: {price_text}\n"
                text += f"• کل فروش: {total_sales} عدد\n\n"
                
                keyboard.append([InlineKeyboardButton(
                    f"📈 گزارش {plan_name}", 
                    callback_data=f"product_sales_detail_{plan_id}"
                )])
            
            keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="product_sales_reports")])
            
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            
        except Exception as e:
            logging.error(f"Error showing product sales list: {e}")
            text = "❌ خطا در نمایش لیست محصولات."
            keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="product_sales_reports")]]
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    async def _show_product_sales_detail(self, query, plan_id):
        """Show detailed sales report for a specific product."""
        try:
            # Get plan info
            plan = self.db_queries.get_plan_by_id(plan_id)
            if not plan:
                text = "❌ محصول یافت نشد."
                keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="product_sales_list")]]
                await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
                return
            
            plan_name = plan['name']
            
            # Get sales data for different periods
            today_sales = self.db_queries.get_plan_sales_count(plan_id=plan_id, days=1)
            week_sales = self.db_queries.get_plan_sales_count(plan_id=plan_id, days=7)
            month_sales = self.db_queries.get_plan_sales_count(plan_id=plan_id, days=30)
            total_sales = self.db_queries.get_plan_sales_count(plan_id=plan_id)
            
            # Get recent sales
            recent_sales = self.db_queries.get_recent_plan_sales(plan_id=plan_id, limit=5)
            
            # Get payment method breakdown
            payment_breakdown = self.db_queries.get_payment_method_breakdown(plan_id=plan_id)
            
            # Build the report
            text = f"📈 *گزارش تفصیلی فروش*\n📾 **{plan_name}**\n\n"
            
            # Sales summary
            text += "📊 *خلاصه فروش:*\n"
            text += f"• امروز: {today_sales['count']} عدد\n"
            text += f"• هفته گذشته: {week_sales['count']} عدد\n"
            text += f"• ماه گذشته: {month_sales['count']} عدد\n"
            text += f"• کل فروش: {total_sales['count']} عدد\n\n"
            
            # Revenue summary
            text += "💰 *خلاصه درآمد:*\n"
            if total_sales['revenue_irr'] > 0:
                text += f"• درآمد ریالی: {total_sales['revenue_irr']:,.0f} ریال\n"
            if total_sales['revenue_usdt'] > 0:
                text += f"• درآمد تتری: {total_sales['revenue_usdt']:.2f} USDT\n"
            text += "\n"
            
            # Payment method breakdown
            text += "💳 *تفکیک روش پرداخت:*\n"
            text += f"• پرداخت ریالی: {payment_breakdown['rial']} عدد\n"
            text += f"• پرداخت کریپتو: {payment_breakdown['crypto']} عدد\n\n"
            
            # Recent sales
            if recent_sales:
                text += "🕐 *فروش‌های اخیر:*\n"
                for sale in recent_sales[:3]:  # Show only first 3
                    user_name = sale['user_name']
                    created_at = sale['created_at'][:16] if sale['created_at'] else 'نامشخص'
                    amount = sale['amount_irr'] if sale['amount_irr'] > 0 else sale['amount_usdt']
                    currency = 'ریال' if sale['amount_irr'] > 0 else 'USDT'
                    text += f"• {user_name} - {amount:,.0f} {currency} ({created_at})\n"
                text += "\n"
            else:
                text += "😔 هیچ فروشی ثبت نشده.\n\n"
            
            # Average calculations
            if week_sales['count'] > 0:
                daily_avg_week = week_sales['count'] / 7
                text += f"📉 میانگین روزانه (هفته): {daily_avg_week:.1f} عدد\n"
            
            if month_sales['count'] > 0:
                daily_avg_month = month_sales['count'] / 30
                text += f"📉 میانگین روزانه (ماه): {daily_avg_month:.1f} عدد\n"
            
            keyboard = [
                [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="product_sales_list")],
                [InlineKeyboardButton("🔙 منوی اصلی", callback_data="product_sales_reports")]
            ]
            
            await query.edit_message_text(text[:4096], parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
            
        except Exception as e:
            logging.error(f"Error showing product sales detail: {e}")
            text = "❌ خطا در نمایش گزارش فروش."
            keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="product_sales_list")]]
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
