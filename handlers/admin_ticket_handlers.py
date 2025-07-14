import logging
from telegram import Bot as TelegramBot

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.constants import ParseMode
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from database.queries import DatabaseQueries
import config
from utils.helpers import is_admin
from utils.helpers import staff_only_decorator as staff_only

import json
from ai.model import responder
import html  # For escaping HTML entities
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

logger = logging.getLogger(__name__)

class AdminTicketHandler:
    """Handle ticket management for admins"""
    
    def __init__(self):
        """Initialize the handler and set `admin_config` required by permission decorators."""
        self.admin_config = getattr(config, "MANAGER_BOT_ADMINS_DICT", {}) or getattr(config, "ADMIN_USER_IDS", [])
        # Use the *main* bot token to reach end-users; manager bot cannot initiate chats.
        try:
            self.main_bot = TelegramBot(token=config.MAIN_BOT_TOKEN)
        except Exception as e:  # Fallback if token missing
            logger.error("Failed to create main bot instance: %s", e)
            self.main_bot = None
    
    @staff_only
    async def show_ticket_history_for_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, target_user_id: int):
        """Show recent tickets of specified user to admin/support."""
        tickets = DatabaseQueries.get_tickets_by_user(target_user_id, limit=20)
        if not tickets:
            await update.effective_message.reply_text("📭 برای این کاربر تیکتی یافت نشد.")
            return
        text_lines = [f"📄 *آخرین تیکت‌های کاربر {target_user_id}:*\n"]
        keyboard = []
        for t in tickets:
            t = dict(t)
            ticket_id = t.get('id') or t.get('ticket_id')
            subject = t.get('subject', 'بدون موضوع')
            status = (t.get('status') or '').replace('_', ' ')
            created_at = t.get('created_at', '')
            text_lines.append(f"• #{ticket_id} | {subject} | {status} | {created_at}")
            keyboard.append([InlineKeyboardButton(f"تیکت#{ticket_id}", callback_data=f"view_ticket_{ticket_id}")])
        await update.effective_message.reply_text("\n".join(text_lines), parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

    def get_ticket_conversation_handler(self):
        """Get the conversation handler for ticket management"""
        return ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.show_tickets_command, pattern="^show_tickets$"),
                CallbackQueryHandler(self.view_ticket_callback, pattern="^view_ticket_\\d+$"),
                CallbackQueryHandler(self.generate_answer_callback, pattern="^gen_answer_\\d+$"),
                CallbackQueryHandler(self.manual_answer_callback, pattern="^manual_answer_\\d+$"),
                CallbackQueryHandler(self.edit_answer_callback, pattern="^edit_answer_\\d+$"),
                CallbackQueryHandler(self.send_answer_callback, pattern="^send_answer_\\d+$"),
                CallbackQueryHandler(self.close_ticket_callback, pattern="^close_ticket_\\d+$"),
                CallbackQueryHandler(self.paginate_tickets_callback, pattern=r'^tickets_page_\d+$'),
                CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern=r'^ignore$'),
                CallbackQueryHandler(self.refresh_tickets_callback, pattern="^refresh_tickets$"),
                CallbackQueryHandler(self.refresh_all_tickets_callback, pattern="^refresh_all_tickets$")
            ],
            states={
                # Add states as needed
            },
            fallbacks=[
                CallbackQueryHandler(self.show_tickets_command, pattern="^refresh_tickets$")
            ],
            per_message=False
        )
    
    @staff_only
    async def show_tickets_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all pending tickets to admin"""
        user_id = update.effective_user.id
        
        try:
            # Get all pending tickets
            tickets = self._get_pending_tickets()
            
            if not tickets:
                await update.message.reply_text("📋 هیچ تیکت باز یافت نشد.")
                return
            
            # Create ticket list with inline keyboard
            keyboard = []
            row = []
            message_text = "📋 لیست تیکت‌های باز:\n\n"
            
            per_page = 10
            page = 0
            start = page * per_page
            end = start + per_page
            tickets_page = tickets[start:end]
            
            for ticket in tickets_page:  # Show max 10 tickets at once
                ticket = dict(ticket)  # تبدیل Row به دیکشنری
                ticket_id = ticket.get('ticket_id') or ticket.get('id')
                user_id_ticket = ticket.get('user_id')
                subject = ticket.get('subject', 'بدون موضوع')
                created_at = ticket.get('created_at', 'نامشخص')
                
                # Get user info
                user_info = self._get_user_info(user_id_ticket)
                user_display = self._format_user_info(user_info)
                
                message_text += f"تیکت #{ticket_id}\n"
                message_text += f"کاربر: {user_display}\n"
                message_text += f"موضوع: {subject}\n"
                message_text += f"تاریخ: {created_at}\n"
                message_text += "───────────────────\n\n"
                
                # Add button for this ticket to the current row
                row.append(
                    InlineKeyboardButton(
                        f"تیکت#{ticket_id}", 
                        callback_data=f"view_ticket_{ticket_id}"
                    )
                )
                
                # If row is full (3 items), add it to the keyboard and start a new row
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
            
            # Add any remaining buttons in the last row (if it's not empty)
            if row:
                keyboard.append(row)

            # Navigation row
            nav_row = []
            if end < len(tickets):
                nav_row.append(InlineKeyboardButton("بعدی »", callback_data="tickets_page_1"))
            if nav_row:
                keyboard.append(nav_row)

            # Add refresh button on its own row
            keyboard.append([
                InlineKeyboardButton("به‌روزرسانی لیست تیکت‌ها", callback_data="refresh_tickets")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                message_text,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error showing tickets: {e}")
            await update.message.reply_text("خطا در نمایش تیکت‌ها.")

    async def view_ticket_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed view of a specific ticket"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id

        # Check if user is admin
        if not self._is_admin(user_id):
            await query.edit_message_text("شما دسترسی لازم برای این عملیات را ندارید.")
            return

        try:
            # Extract ticket ID from callback data
            ticket_id = int(query.data.split('_')[-1])
            logger.info(f"DEBUG: Admin {user_id} viewing ticket with ID: {ticket_id}")

            # Get ticket details
            ticket = self._get_ticket_by_id(ticket_id)

            if not ticket:
                logger.warning(f"Ticket with ID {ticket_id} not found by _get_ticket_by_id.")
                await query.edit_message_text("تیکت یافت نشد.")
                return

            logger.info(f"DEBUG: Ticket data for display: {ticket}")

            user_id_ticket = ticket.get('user_id')
            subject = ticket.get('subject', 'بدون موضوع')
            message = ticket.get('message', 'پیام موجود نیست')
            created_at = ticket.get('created_at', 'نامشخص')
            status = ticket.get('status', 'نامشخص')



            # Get user info
            user_info = self._get_user_info(user_id_ticket)
            if not user_info:
                await query.edit_message_text("اطلاعات کاربر یافت نشد.")
                return

            user_display = html.escape(self._format_user_info(user_info))
            contact_info = html.escape(self._get_contact_info(user_info))
            subject_html = html.escape(subject)
            message_html = html.escape(message)

            # Format ticket details
            message_text = (
                f"جزئیات تیکت #{ticket_id}\n\n"
                f"کاربر: {user_display}\n"
                f"موضوع: {subject_html}\n"
                f"تاریخ ایجاد: {created_at}\n"
                f"وضعیت: {self._get_status_emoji(status)} {status}\n\n"
                f"پیام:\n{message_html}\n\n"
                f"اطلاعات تماس: {contact_info}"
            )



            # Create action buttons
            keyboard = [
                [  # First row: generate AI answer
                    InlineKeyboardButton("🔄 تولید پاسخ پیشنهادی", callback_data=f"gen_answer_{ticket_id}"),
                    InlineKeyboardButton("✍️ پاسخ دستی", callback_data=f"manual_answer_{ticket_id}")
                ],
                [  # Second row: Close ticket
                    InlineKeyboardButton("بستن تیکت", callback_data=f"close_ticket_{ticket_id}")
                ],
                [  # Third row: Back to list
                    InlineKeyboardButton("بازگشت به لیست تیکت‌ها", callback_data="refresh_tickets")
                ]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                message_text,
                reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error viewing ticket: {e}")
            await query.edit_message_text("خطا در نمایش تیکت.")

    async def generate_answer_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generate AI suggested answer on demand and update the ticket view"""
        query = update.callback_query
        await query.answer("در حال تولید پاسخ...")

        user_id = query.from_user.id
        if not self._is_admin(user_id):
            await query.edit_message_text("شما دسترسی لازم برای این عملیات را ندارید.")
            return

        ticket_id = int(query.data.split('_')[-1])
        ticket = self._get_ticket_by_id(ticket_id)
        if not ticket:
            await query.edit_message_text("تیکت یافت نشد.")
            return

        # Generate AI answer
        subject = ticket.get('subject', 'بدون موضوع')
        first_message = ticket.get('message', '')
        ai_answer = responder.answer_ticket(subject, first_message, ticket.get('user_id'))
        if not ai_answer:
            await query.edit_message_text("خطا در تولید پاسخ توسط هوش‌مصنوعی.")
            return
        context.user_data[f'ai_answer_{ticket_id}'] = ai_answer

        # Prepare updated message text (similar to view_ticket details)
        user_info = self._get_user_info(ticket.get('user_id'))
        user_display = html.escape(self._format_user_info(user_info)) if user_info else "نامشخص"
        contact_info = html.escape(self._get_contact_info(user_info)) if user_info else "-"
        subject_html = html.escape(subject)
        message_html = html.escape(first_message)
        created_at = ticket.get('created_at', 'نامشخص')
        status = ticket.get('status', 'نامشخص')

        message_text = (
            f"جزئیات تیکت #{ticket_id}\n\n"
            f"کاربر: {user_display}\n"
            f"موضوع: {subject_html}\n"
            f"تاریخ ایجاد: {created_at}\n"
            f"وضعیت: {self._get_status_emoji(status)} {status}\n\n"
            f"پیام:\n{message_html}\n\n"
            f"اطلاعات تماس: {contact_info}\n\n"
            f"پاسخ پیشنهادی هوش‌مصنوعی:\n{ai_answer}\n"
        )

        # Updated keyboard with send/edit options
        keyboard = [
            [
                InlineKeyboardButton("ارسال پاسخ پیشنهادی", callback_data=f"send_answer_{ticket_id}"),
                InlineKeyboardButton("ویرایش و ارسال پاسخ", callback_data=f"edit_answer_{ticket_id}")
            ],
            [
                InlineKeyboardButton("🔄 تولید مجدد پاسخ", callback_data=f"gen_answer_{ticket_id}")
            ],
            [
                InlineKeyboardButton("بستن تیکت", callback_data=f"close_ticket_{ticket_id}")
            ],
            [
                InlineKeyboardButton("بازگشت به لیست تیکت‌ها", callback_data="refresh_tickets")
            ]
        ]
        await query.edit_message_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def send_answer_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send the stored AI answer to the ticket owner"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        if not self._is_admin(user_id):
            await query.edit_message_text("شما دسترسی لازم برای این عملیات را ندارید.")
            return

        ticket_id = int(query.data.split('_')[-1])
        ticket = self._get_ticket_by_id(ticket_id)
        if not ticket:
            await query.edit_message_text("تیکت یافت نشد.")
            return

        target_user_id = ticket.get('user_id')
        ai_answer = context.user_data.get(f'ai_answer_{ticket_id}')
        if not ai_answer:
            await query.edit_message_text("پاسخ هوش‌مصنوعی یافت نشد.")
            return

        try:
            original_question = ticket.get('message', '') or '-'
            user_reply_text = (
                f"سوال شما:\n{original_question}\n\n"
                f"پاسخ:\n{ai_answer}"
            )
            bot_to_use = self.main_bot or context.bot
            await bot_to_use.send_message(chat_id=target_user_id, text=user_reply_text)
            DatabaseQueries.add_ticket_message(ticket_id, user_id, ai_answer, is_admin_message=True, update_status=False)
            DatabaseQueries.update_ticket_status(ticket_id, 'closed')
            await query.edit_message_text(
                f"💠 پاسخ برای کاربر ارسال شد و تیکت بسته شد.\n\nسوال:\n{original_question}\n\nپاسخ ارسال شده:\n{ai_answer}"
            )
        except Exception as e:
            logger.error(f"Error sending AI answer: {e}")
            await query.edit_message_text("خطا در ارسال پاسخ به کاربر.")

    async def edit_answer_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Provide AI answer for admin to edit manually"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        if not self._is_admin(user_id):
            await query.edit_message_text("شما دسترسی لازم برای این عملیات را ندارید.")
            return

        ticket_id = int(query.data.split('_')[-1])
        ai_answer = context.user_data.get(f'ai_answer_{ticket_id}')
        if not ai_answer:
            await query.edit_message_text("پاسخ هوش‌مصنوعی یافت نشد.")
            return

        # Ask admin to edit the answer using ForceReply
        await query.message.reply_text(
            f"لطفاً پاسخ را ویرایش کرده و ارسال کنید. پس از ارسال، ربات آن را به کاربر فوروارد خواهد کرد.\n\nمتن پیشنهادی:\n{ai_answer}",
            reply_markup=ForceReply(selective=True)
        )
        # Set state for later processing (implementation of listener not included here)
        context.user_data['editing_ticket_id'] = ticket_id

    async def manual_answer_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Prompt admin to type a manual answer without AI suggestion"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        if not self._is_admin(user_id):
            await query.edit_message_text("شما دسترسی لازم برای این عملیات را ندارید.")
            return

        ticket_id = int(query.data.split('_')[-1])
        ticket = self._get_ticket_by_id(ticket_id)
        if not ticket:
            await query.edit_message_text("تیکت یافت نشد.")
            return

        # Ask admin to reply manually
        await query.message.reply_text(
            "لطفاً پاسخ خود را بنویسید و ارسال کنید.",
            reply_markup=ForceReply(selective=True)
        )
        context.user_data['editing_ticket_id'] = ticket_id

    async def receive_edited_answer(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle admin's edited answer after ForceReply"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            return  # ignore non-admins
        ticket_id = context.user_data.pop('editing_ticket_id', None)
        if not ticket_id:
            return  # nothing to process
        ticket = self._get_ticket_by_id(ticket_id)
        if not ticket:
            await update.message.reply_text("تیکت یافت نشد.")
            return
        target_user_id = ticket.get('user_id')
        text = update.message.text
        try:
            original_question = ticket.get('message', '') or '-'
            combined_text = (
                f"❔ سوال شما:\n{original_question}\n\n"
                f"✅ پاسخ:\n{text}"
            )
            bot_to_use = self.main_bot or context.bot
            await bot_to_use.send_message(chat_id=target_user_id, text=combined_text)
            DatabaseQueries.add_ticket_message(ticket_id, user_id, text, is_admin_message=True, update_status=False)
            DatabaseQueries.update_ticket_status(ticket_id, 'closed')
            await update.message.reply_text(
                "💠 پاسخ برای کاربر ارسال شد و تیکت بسته شد.\n\n"
                f"❔ سوال:\n{original_question}\n\n✅ پاسخ ارسال شده:\n{text}"
            )
        except Exception as e:
            logger.error(f"Error forwarding edited answer: {e}")
            await update.message.reply_text("خطا در ارسال پاسخ.")

    async def close_ticket_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Close a ticket"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        # Check if user is admin
        if not self._is_admin(user_id):
            await query.edit_message_text("شما دسترسی لازم برای این عملیات را ندارید.")
            return
        
        try:
            # Extract ticket ID from callback data
            ticket_id = int(query.data.split('_')[-1])
            
            # Close the ticket
            success = self._close_ticket(ticket_id, query.from_user.id) # Pass admin_id for logging or future use
            
            if success:
                # Get ticket info to notify user
                ticket = self._get_ticket_by_id(ticket_id)
                if ticket:
                    ticket_user_id = ticket.get('user_id')
                    
                    # Try to notify the user
                    try:
                        await context.bot.send_message(
                            chat_id=ticket_user_id,
                            text=f"⭕ تیکت شما با شماره #{ticket_id} بسته شد.\n"
                                 f"پاسخ مربوطه از طریق پشتیبانی ارسال خواهد شد."
                        )
                    except Exception:
                        logger.warning(f"Could not notify user {ticket_user_id} about closed ticket")
                
                await query.edit_message_text(
                    f"تیکت #{ticket_id} با موفقیت بسته شد.\n"
                    f"کاربر در صورت امکان از بسته شدن تیکت مطلع شد."
                )
            else:
                await query.edit_message_text("خطا در بستن تیکت.")
                
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")
            await query.edit_message_text("خطا در بستن تیکت.")

    async def refresh_tickets_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Refresh the list of pending tickets (inline)."""
        query = update.callback_query
        # Show a short answering toast but don't block on it
        await query.answer("🔄 در حال به‌روزرسانی…", show_alert=False)

        # Only admins/support are allowed – reuse the same check
        if not self._is_admin(query.from_user.id):
            await query.edit_message_text("❌ شما دسترسی لازم برای این عملیات را ندارید.")
            return

        # Delegate to the inline implementation that already handles
        # the 'Message is not modified' BadRequest gracefully.
        await self._show_tickets_inline(query, page=0)

    async def paginate_tickets_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Paginate tickets"""
        query = update.callback_query
        await query.answer()

        page = int(query.data.split('_')[-1])
        await self._show_tickets_inline(query, page)

    def get_handlers(self):
        """Return all handlers for the ticket management module."""
        return [
            CommandHandler("tickets", self.show_tickets_command),
            CallbackQueryHandler(self.view_ticket_callback, pattern=r'^view_ticket_'),
            CallbackQueryHandler(self.send_answer_callback, pattern=r'^send_answer_'),
            CallbackQueryHandler(self.edit_answer_callback, pattern=r'^edit_answer_'),
            CallbackQueryHandler(self.close_ticket_callback, pattern=r'^close_ticket_'),
            CallbackQueryHandler(self.refresh_tickets_callback, pattern=r'^refresh_tickets$'),
            CallbackQueryHandler(self.paginate_tickets_callback, pattern=r'^tickets_page_\d+$'),
            MessageHandler(filters.REPLY & filters.TEXT & (~filters.COMMAND), self.receive_edited_answer),
        ]
    
    async def _show_tickets_inline(self, query, page: int = 0):
        """Show tickets in inline message"""
        try:
            # Get all pending tickets and convert rows to dicts so we can access with .get
            tickets_raw = self._get_pending_tickets()
            tickets = [dict(t) for t in tickets_raw]
            # Sort descending by ticket id (newest first) to keep ordering stable.
            tickets.sort(key=lambda t: (t.get("ticket_id") or t.get("id") or 0), reverse=True)

            if not tickets:
                await query.edit_message_text("هیچ تیکت باز یافت نشد.")
                return

            # Pagination bookkeeping
            logger.debug(f"_show_tickets_inline: total_tickets={len(tickets)}, requested_page={page}")
            per_page = 10
            total_pages = (len(tickets) - 1) // per_page + 1
            # Clamp page index to valid range to avoid empty pages if ticket count changed
            page = max(0, min(page, total_pages - 1))

            # Create ticket list with inline keyboard
            keyboard = []
            message_text = "📋 لیست تیکت‌های باز:\n\n"
            
            start = page * per_page
            end = start + per_page
            tickets_page = tickets[start:end]
            
            row = []
            for ticket in tickets_page:  # Show max 10 tickets at once
                ticket = dict(ticket)  # تبدیل Row به دیکشنری
                ticket_id = ticket.get('ticket_id') or ticket.get('id')
                user_id_ticket = ticket.get('user_id')
                subject = ticket.get('subject', 'بدون موضوع')
                created_at = ticket.get('created_at', 'نامشخص')
                
                # Get user info
                user_info = self._get_user_info(user_id_ticket)
                user_display = self._format_user_info(user_info)
                
                message_text += f"تیکت #{ticket_id}\n"
                message_text += f"کاربر: {user_display}\n"
                message_text += f"موضوع: {subject}\n"
                message_text += f"تاریخ: {created_at}\n"
                message_text += "───────────────────\n\n"
                
                # Add button to current row
                row.append(
                    InlineKeyboardButton(
                        f"تیکت#{ticket_id}",
                        callback_data=f"view_ticket_{ticket_id}"
                    )
                )
                # If row full (3 buttons), push to keyboard
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
            # leftover row
            if row:
                keyboard.append(row)
            
            # Navigation row with current page indicator
            nav_row = []
            if page > 0:
                nav_row.append(InlineKeyboardButton("« قبلی", callback_data=f"tickets_page_{page-1}"))
            nav_row.append(InlineKeyboardButton(f"صفحه {page+1}/{total_pages}", callback_data="ignore"))
            if page < total_pages - 1:
                nav_row.append(InlineKeyboardButton("بعدی »", callback_data=f"tickets_page_{page+1}"))
            if nav_row:
                keyboard.append(nav_row)

            # Add refresh button
            keyboard.append([
                InlineKeyboardButton("به‌روزرسانی", callback_data="refresh_tickets")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                message_text,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            import telegram
            if isinstance(e, telegram.error.BadRequest) and "Message is not modified" in str(e):
                logger.warning(f"Suppressed Telegram BadRequest: {e}")
                return
            logger.error(f"Error showing tickets inline: {e}")
            await query.edit_message_text("❌ خطا در نمایش تیکت‌ها.")
    
    def _is_admin(self, user_id):
        """Check if user is admin"""
        try:
            admin_config_json_str = getattr(config, 'ALL_ADMINS_CONFIG_JSON', None)
            admin_config_direct = getattr(config, 'ALL_ADMINS_CONFIG', None)

            if admin_config_direct is not None:
                admin_list = admin_config_direct
            elif admin_config_json_str is not None:
                admin_list = json.loads(admin_config_json_str)
            else:
                logger.error("Admin configuration (ALL_ADMINS_CONFIG or ALL_ADMINS_CONFIG_JSON) not found in config module.")
                return False
            
            if not isinstance(admin_list, list):
                logger.error(f"Admin configuration is not a list: {type(admin_list)}")
                return False

            for admin in admin_list:
                if isinstance(admin, dict) and admin.get('chat_id') == user_id and \
                   'manager_bot_admin' in admin.get('roles', []):
                    return True
            # Check support users table
            from database.queries import DatabaseQueries
            # Check support staff list defined in config (e.g., MAIN_BOT_SUPPORT_STAFF_LIST)
            try:
                support_staff_list = getattr(config, 'MAIN_BOT_SUPPORT_STAFF_LIST', [])
                if isinstance(support_staff_list, (list, tuple, set)) and user_id in support_staff_list:
                    return True
            except Exception as e:
                logger.warning(f"Could not read MAIN_BOT_SUPPORT_STAFF_LIST from config: {e}")

            if DatabaseQueries.is_support_user(user_id):
                return True  # Treat support users as authorized for ticket handling
            return False
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding ALL_ADMINS_CONFIG_JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Error checking admin status for user {user_id}: {e}", exc_info=True)
            return False
    
    def _get_pending_tickets(self):
        """Get pending tickets from database by calling the static method from DatabaseQueries."""
        try:
            # DatabaseQueries.get_open_tickets() (from queries.py, line ~470)
            # returns a list of dicts:
            # [{'ticket_id': ..., 'user_id': ..., 'user_name': ..., 'subject': ..., 'status': ..., 'created_at': ...}, ...]
            tickets_data = DatabaseQueries.get_open_tickets()
            logger.info(f"DEBUG: _get_pending_tickets received {len(tickets_data)} tickets.")
            return tickets_data
        except Exception as e:
            logger.error(f"Error in _get_pending_tickets: {e}", exc_info=True)
            return []
    
    def _get_ticket_by_id(self, ticket_id):
        """Get ticket by ID using appropriate static methods from DatabaseQueries."""
        try:
            logger.info(f"Fetching ticket details for ID: {ticket_id} using DatabaseQueries.get_ticket_details")
            # DatabaseQueries.get_ticket_details(ticket_id) returns a dict with ticket info and a list of messages, or None.
            # Schema of returned dict: {'ticket_id', 'user_id', 'user_name', 'subject', 'status', 'created_at', 'messages': [...]}
            ticket_details_full = DatabaseQueries.get_ticket_details(ticket_id) 
            
            if ticket_details_full:
                first_message_text = "پیام اولیه یافت نشد"
                if ticket_details_full.get('messages'):
                    # Sort messages by timestamp to get the earliest one
                    sorted_messages = sorted(ticket_details_full['messages'], key=lambda m: m.get('timestamp', ''))
                    if sorted_messages:
                        first_message_text = sorted_messages[0].get('message', first_message_text)
                
                # Construct the dictionary format expected by view_ticket_callback
                ticket_data_for_handler = {
                    'ticket_id': ticket_details_full.get('ticket_id'),
                    'user_id': ticket_details_full.get('user_id'),
                    'subject': ticket_details_full.get('subject'),
                    'message': first_message_text, # Added the first message
                    'created_at': ticket_details_full.get('created_at'),
                    'status': ticket_details_full.get('status'),
                    'user_name': ticket_details_full.get('user_name') # Keep user_name if available
                }
                logger.info(f"DEBUG: Processed ticket data for ID {ticket_id}: {ticket_data_for_handler}")
                return ticket_data_for_handler
            else:
                logger.warning(f"DatabaseQueries.get_ticket_details({ticket_id}) returned None.")
                return None
        except Exception as e:
            logger.error(f"Error in _get_ticket_by_id for ticket_id {ticket_id}: {e}", exc_info=True)
            return None
    
    def _close_ticket(self, ticket_id, admin_id): # admin_id can be used for logging or if schema changes
        """Close a ticket using DatabaseQueries.update_ticket_status."""
        try:
            # The current TICKETS_TABLE schema does not have 'closed_by' or 'closed_at'.
            # DatabaseQueries.update_ticket_status (queries.py line ~558) updates only status.
            success = DatabaseQueries.update_ticket_status(ticket_id, 'closed')
            logger.info(f"Attempted to close ticket {ticket_id} by admin {admin_id}, success: {success}")
            return success
        except Exception as e:
            logger.error(f"Error in _close_ticket for ticket_id {ticket_id}: {e}", exc_info=True)
            return False
    
    def _get_user_info(self, user_id_ticket):
        """Get user information by user_id using DatabaseQueries.get_user_details."""
        try:
            if user_id_ticket is None:
                logger.warning("Attempted to get user info with None user_id_ticket.")
                return None
            # DatabaseQueries.get_user_details(user_id) returns a sqlite3.Row or None
            user_row = DatabaseQueries.get_user_details(user_id_ticket) # from queries.py line ~53
            if user_row:
                user_data = dict(user_row) # Convert sqlite3.Row to dict
                logger.info(f"DEBUG: Retrieved user_info for user_id {user_id_ticket}: {user_data}")
                return user_data
            logger.warning(f"No user_info found for user_id {user_id_ticket}")
            return None
        except Exception as e:
            logger.error(f"Error in _get_user_info for user_id {user_id_ticket}: {e}", exc_info=True)
            return None
    
    def _format_user_info(self, user_info):
        """Format user info for display"""
        if not user_info:
            return "نامشخص"
        
        first_name = user_info.get('first_name', '')
        last_name = user_info.get('last_name', '')
        username = user_info.get('username', '')
        user_id = user_info.get('user_id', '')
        
        display_name = ""
        if first_name:
            display_name += first_name
        if last_name:
            display_name += f" {last_name}"
        
        if username:
            display_name += f" (@{username})"
        
        if not display_name.strip():
            display_name = f"User ID: {user_id}"
        
        return display_name.strip()
    
    def _get_contact_info(self, user_info):
        """Get contact information for admin"""
        if not user_info:
            return "اطلاعات تماس موجود نیست"
        
        telegram_id = user_info.get('telegram_id')
        phone = user_info.get('phone')
        username = user_info.get('username')
        
        contact_methods = []
        
        # Telegram contact
        if telegram_id:
            if username:
                contact_methods.append(f"تلگرام: @{username}")
            else:
                contact_methods.append(f"[تلگرام](tg://user?id={telegram_id})")
        
        # Phone contact
        if phone:
            contact_methods.append(f"تلفن: {phone}")
        
        if not contact_methods:
            contact_methods.append("اطلاعات تماس موجود نیست")
        
        return " | ".join(contact_methods)
    
    def _get_status_emoji(self, status):
        """Get emoji for ticket status"""
        status_emojis = {
            'open': '🟢',
            'closed': '🔴',
            'pending': '🟡',
            'in_progress': '🔵'
        }
        return status_emojis.get(status, '⚪')

    def _get_all_tickets(self):
        """Get all tickets from database."""
        try:
            tickets_data = DatabaseQueries.get_all_tickets()
            logger.info(f"DEBUG: _get_all_tickets received {len(tickets_data)} tickets.")
            return tickets_data
        except Exception as e:
            logger.error(f"Error in _get_all_tickets: {e}", exc_info=True)
            return []

    @staff_only
    async def show_all_tickets_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show all tickets history to admin"""
        user_id = update.effective_user.id  # noqa: F841 unused but kept for symmetry
        try:
            tickets = self._get_all_tickets()
            if not tickets:
                await update.message.reply_text("📋 هیچ تیکتی یافت نشد.")
                return
            keyboard = []
            message_text = "📋 لیست تمام تیکت‌ها:\n\n"
            for ticket in tickets[:10]:
                ticket = dict(ticket)
                ticket_id = ticket.get('ticket_id') or ticket.get('id')
                user_info = self._get_user_info(ticket.get('user_id'))
                user_display = self._format_user_info(user_info)
                subject = ticket.get('subject', 'بدون موضوع')
                created_at = ticket.get('created_at', '')
                status = ticket.get('status', '')
                readable_status = str(status).replace('_', ' ')
                emoji = self._get_status_emoji(status)
                message_text += f"{emoji} *تیکت #{ticket_id}* ({readable_status})\n"
                message_text += f"👤 کاربر: {user_display}\n"
                message_text += f"📝 موضوع: {subject}\n"
                message_text += f"📅 تاریخ: {created_at}\n"
                message_text += "─────────────────\n\n"
                keyboard.append([
                    InlineKeyboardButton(
                        f"📋 تیکت#{ticket_id}", callback_data=f"view_ticket_{ticket_id}")
                ])
            keyboard.append([InlineKeyboardButton("به‌روزرسانی", callback_data="refresh_all_tickets")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(message_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error showing all tickets: {e}")
            await update.message.reply_text("❌ خطا در نمایش تیکت‌ها.")

    async def paginate_tickets_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle pagination for pending tickets list"""
        query = update.callback_query
        await query.answer()
        if not self._is_admin(query.from_user.id):
            await query.edit_message_text("❌ شما دسترسی لازم برای این عملیات را ندارید.")
            return
        try:
            page = int(query.data.split('_')[-1])
        except ValueError:
            page = 0
        logger.debug(f"paginate_tickets_callback: user={query.from_user.id} requested page {page}")
        await self._show_tickets_inline(query, page=page)

    async def refresh_all_tickets_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Refresh all tickets list"""
        query = update.callback_query
        await query.answer()
        if not self._is_admin(query.from_user.id):
            await query.edit_message_text("❌ شما دسترسی لازم برای این عملیات را ندارید.")
            return
        await self._show_all_tickets_inline(query)

    async def _show_all_tickets_inline(self, query):
        """Show all tickets in inline message"""
        try:
            tickets = self._get_all_tickets()
            if not tickets:
                await query.edit_message_text("📋 هیچ تیکتی یافت نشد.")
                return

            keyboard = []
            row = []
            message_text = "📋 لیست تمام تیکت‌ها:\n\n"

            for ticket in tickets[:10]: # Limit to 10 for now to prevent message overload
                ticket = dict(ticket)
                ticket_id = ticket.get('ticket_id') or ticket.get('id')
                user_info = self._get_user_info(ticket.get('user_id'))
                user_display = self._format_user_info(user_info)
                subject = ticket.get('subject', 'بدون موضوع')
                created_at = ticket.get('created_at', '')
                status = ticket.get('status', '')
                readable_status = str(status).replace('_', ' ')
                emoji = self._get_status_emoji(status)

                message_text += f"{emoji} *تیکت #{ticket_id}* ({readable_status})\n"
                message_text += f"👤 کاربر: {user_display}\n"
                message_text += f"📝 موضوع: {subject}\n"
                message_text += f"📅 تاریخ: {created_at}\n"
                message_text += "───────────────────\n\n"

                row.append(InlineKeyboardButton(
                    f"📋 تیکت#{ticket_id}", callback_data=f"view_ticket_{ticket_id}"
                ))

                if len(row) == 3:
                    keyboard.append(row)
                    row = []

            if row:
                keyboard.append(row)

            keyboard.append([InlineKeyboardButton("به‌روزرسانی", callback_data="refresh_all_tickets")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

        except Exception as e:
            import telegram
            if isinstance(e, telegram.error.BadRequest) and "Message is not modified" in str(e):
                logger.warning(f"Suppressed Telegram BadRequest: {e}")
                return
            logger.error(f"Error showing all tickets inline: {e}")
            await query.edit_message_text("❌ خطا در نمایش تیکت‌ها.")
    
    def get_handlers(self):
        """Get all handlers for this module"""
        return [
            CommandHandler('tickets', self.show_tickets_command),
            CommandHandler('all_tickets', self.show_all_tickets_command),
            
            CallbackQueryHandler(self.view_ticket_callback, pattern=r'^view_ticket_\d+$'),
            CallbackQueryHandler(self.generate_answer_callback, pattern=r'^gen_answer_\d+$'),
            CallbackQueryHandler(self.manual_answer_callback, pattern=r'^manual_answer_\d+$'),
            CallbackQueryHandler(self.send_answer_callback, pattern=r'^send_answer_\d+$'),
            CallbackQueryHandler(self.edit_answer_callback, pattern=r'^edit_answer_\d+$'),
            CallbackQueryHandler(self.close_ticket_callback, pattern=r'^close_ticket_\d+$'),
            CallbackQueryHandler(self.refresh_tickets_callback, pattern=r'^refresh_tickets$'),
            CallbackQueryHandler(self.paginate_tickets_callback, pattern=r'^tickets_page_\d+$'),
            CallbackQueryHandler(self.refresh_all_tickets_callback, pattern=r'^refresh_all_tickets$'),
            MessageHandler(filters.TEXT & (~filters.COMMAND), self.receive_edited_answer),
        ]
