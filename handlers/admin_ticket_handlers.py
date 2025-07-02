import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from database.queries import DatabaseQueries
import config
from utils.helpers import admin_only_decorator as admin_only
import json
from ai.model import responder

logger = logging.getLogger(__name__)

class AdminTicketHandler:
    """Handle ticket management for admins"""
    
    def __init__(self):
        # self.db_queries = DatabaseQueries() # This instance is not strictly needed if all calls are static
        pass
    
    @admin_only
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
            message_text = "📋 *لیست تیکت‌های باز:*\n\n"
            
            for ticket in tickets[:10]:  # Show max 10 tickets at once
                ticket = dict(ticket)  # تبدیل Row به دیکشنری
                ticket_id = ticket.get('ticket_id') or ticket.get('id')
                user_id_ticket = ticket.get('user_id')
                subject = ticket.get('subject', 'بدون موضوع')
                created_at = ticket.get('created_at', 'نامشخص')
                
                # Get user info
                user_info = self._get_user_info(user_id_ticket)
                user_display = self._format_user_info(user_info)
                
                message_text += f"🎫 *تیکت #{ticket_id}*\n"
                message_text += f"👤 کاربر: {user_display}\n"
                message_text += f"📝 موضوع: {subject}\n"
                message_text += f"📅 تاریخ: {created_at}\n"
                message_text += "─────────────────\n\n"
                
                # Add button for this ticket
                keyboard.append([
                    InlineKeyboardButton(
                        f"📋 مشاهده تیکت #{ticket_id}", 
                        callback_data=f"view_ticket_{ticket_id}"
                    )
                ])
            
            # Add refresh button
            keyboard.append([
                InlineKeyboardButton("🔄 به‌روزرسانی", callback_data="refresh_tickets")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                message_text, 
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error showing tickets: {e}")
            await update.message.reply_text("❌ خطا در نمایش تیکت‌ها.")
    
    async def view_ticket_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show detailed view of a specific ticket"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id

        # Check if user is admin
        if not self._is_admin(user_id):
            await query.edit_message_text("❌ شما دسترسی لازم برای این عملیات را ندارید.")
            return

        try:
            # Extract ticket ID from callback data
            ticket_id = int(query.data.split('_')[-1])
            logger.info(f"DEBUG: Admin {user_id} viewing ticket with ID: {ticket_id}")

            # Get ticket details
            ticket = self._get_ticket_by_id(ticket_id)

            if not ticket:
                logger.warning(f"Ticket with ID {ticket_id} not found by _get_ticket_by_id.")
                await query.edit_message_text("❌ تیکت یافت نشد.")
                return

            logger.info(f"DEBUG: Ticket data for display: {ticket}")

            user_id_ticket = ticket.get('user_id')
            subject = ticket.get('subject', 'بدون موضوع')
            message = ticket.get('message', 'پیام موجود نیست')
            created_at = ticket.get('created_at', 'نامشخص')
            status = ticket.get('status', 'نامشخص')

            # Generate AI suggested answer for the specific user
            ticket_owner_id = ticket.get('user_id')
            ai_answer = responder.answer_ticket(subject, message, ticket_owner_id)
            context.user_data[f'ai_answer_{ticket_id}'] = ai_answer

            # Get user info
            user_info = self._get_user_info(user_id_ticket)
            if not user_info:
                await query.edit_message_text("❌ اطلاعات کاربر یافت نشد.")
                return

            user_display = self._format_user_info(user_info)
            contact_info = self._get_contact_info(user_info)

            # Format ticket details
            message_text = f"🎫 *جزئیات تیکت #{ticket_id}*\n\n"
            message_text += f"👤 *کاربر:* {user_display}\n"
            message_text += f"📞 *اطلاعات تماس:* {contact_info}\n"
            message_text += f"📝 *موضوع:* {subject}\n"
            message_text += f"📅 *تاریخ ایجاد:* {created_at}\n"
            message_text += f"📊 *وضعیت:* {self._get_status_emoji(status)} {status}\n\n"
            message_text += f"💬 *پیام:*\n{message}\n\n"
            message_text += "─────────────────\n"
            message_text += "📋 *راهنما برای ادمین:*\n"
            message_text += f"• برای پاسخ به کاربر، از طریق {contact_info} با او تماس بگیرید\n"
            message_text += "• پس از حل مشکل، تیکت را بسته کنید"

            # Append AI suggested answer to message
            message_text += f"🤖 *پاسخ پیشنهادی هوش‌مصنوعی:*\n{ai_answer}\n\n"

            # Create action buttons
            keyboard = [
                [
                    InlineKeyboardButton("📤 ارسال پاسخ به کاربر", callback_data=f"send_answer_{ticket_id}"),
                    InlineKeyboardButton("✏️ ویرایش پاسخ", callback_data=f"edit_answer_{ticket_id}")
                ],
                [
                    InlineKeyboardButton("✅ بستن تیکت", callback_data=f"close_ticket_{ticket_id}")
                ],
                [
                    InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="refresh_tickets")
                ]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                message_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error viewing ticket: {e}")
            await query.edit_message_text("❌ خطا در نمایش تیکت.")

    async def send_answer_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send the stored AI answer to the ticket owner"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        if not self._is_admin(user_id):
            await query.edit_message_text("❌ شما دسترسی لازم برای این عملیات را ندارید.")
            return

        ticket_id = int(query.data.split('_')[-1])
        ticket = self._get_ticket_by_id(ticket_id)
        if not ticket:
            await query.edit_message_text("❌ تیکت یافت نشد.")
            return

        target_user_id = ticket.get('user_id')
        ai_answer = context.user_data.get(f'ai_answer_{ticket_id}')
        if not ai_answer:
            await query.edit_message_text("❌ پاسخ هوش‌مصنوعی یافت نشد.")
            return

        try:
            await context.bot.send_message(chat_id=target_user_id, text=ai_answer)
            await query.edit_message_text(
                f"✅ پاسخ برای کاربر ارسال شد:\n\n{ai_answer}"
            )
        except Exception as e:
            logger.error(f"Error sending AI answer: {e}")
            await query.edit_message_text("❌ خطا در ارسال پاسخ به کاربر.")

    async def edit_answer_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Provide AI answer for admin to edit manually"""
        query = update.callback_query
        await query.answer()

        user_id = query.from_user.id
        if not self._is_admin(user_id):
            await query.edit_message_text("❌ شما دسترسی لازم برای این عملیات را ندارید.")
            return

        ticket_id = int(query.data.split('_')[-1])
        ai_answer = context.user_data.get(f'ai_answer_{ticket_id}')
        if not ai_answer:
            await query.edit_message_text("❌ پاسخ هوش‌مصنوعی یافت نشد.")
            return

        # Ask admin to edit the answer using ForceReply
        await query.message.reply_text(
            f"✏️ لطفاً پاسخ را ویرایش کرده و ارسال کنید. پس از ارسال، ربات آن را به کاربر فوروارد خواهد کرد.\n\nمتن پیشنهادی:\n{ai_answer}",
            reply_markup=ForceReply(selective=True)
        )
        # Set state for later processing (implementation of listener not included here)
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
            await update.message.reply_text("❌ تیکت یافت نشد.")
            return
        target_user_id = ticket.get('user_id')
        text = update.message.text
        try:
            await context.bot.send_message(chat_id=target_user_id, text=text)
            await update.message.reply_text("✅ پاسخ ویرایش‌شده برای کاربر ارسال شد.")
        except Exception as e:
            logger.error(f"Error forwarding edited answer: {e}")
            await update.message.reply_text("❌ خطا در ارسال پاسخ.")

    async def close_ticket_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Close a ticket"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        # Check if user is admin
        if not self._is_admin(user_id):
            await query.edit_message_text("❌ شما دسترسی لازم برای این عملیات را ندارید.")
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
                            text=f"✅ تیکت شما با شماره #{ticket_id} بسته شد.\n"
                                 f"پاسخ مربوطه از طریق پشتیبانی ارسال خواهد شد."
                        )
                    except Exception:
                        logger.warning(f"Could not notify user {ticket_user_id} about closed ticket")
                
                await query.edit_message_text(
                    f"✅ تیکت #{ticket_id} با موفقیت بسته شد.\n"
                    f"کاربر در صورت امکان از بسته شدن تیکت مطلع شد."
                )
            else:
                await query.edit_message_text("❌ خطا در بستن تیکت.")
                
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")
            await query.edit_message_text("❌ خطا در بستن تیکت.")
    
    async def refresh_tickets_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Refresh tickets list"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        # Check if user is admin
        if not self._is_admin(user_id):
            await query.edit_message_text("❌ شما دسترسی لازم برای این عملیات را ندارید.")
            return
        
        # Simulate the show_tickets_command but for callback
        await self._show_tickets_inline(query)
    
    async def _show_tickets_inline(self, query):
        """Show tickets in inline message"""
        try:
            # Get all pending tickets
            tickets = self._get_pending_tickets()
            
            if not tickets:
                await query.edit_message_text("📋 هیچ تیکت باز یافت نشد.")
                return
            
            # Create ticket list with inline keyboard
            keyboard = []
            message_text = "📋 *لیست تیکت‌های باز:*\n\n"
            
            for ticket in tickets[:10]:  # Show max 10 tickets at once
                ticket = dict(ticket)  # تبدیل Row به دیکشنری
                ticket_id = ticket.get('ticket_id') or ticket.get('id')
                user_id_ticket = ticket.get('user_id')
                subject = ticket.get('subject', 'بدون موضوع')
                created_at = ticket.get('created_at', 'نامشخص')
                
                # Get user info
                user_info = self._get_user_info(user_id_ticket)
                user_display = self._format_user_info(user_info)
                
                message_text += f"🎫 *تیکت #{ticket_id}*\n"
                message_text += f"👤 کاربر: {user_display}\n"
                message_text += f"📝 موضوع: {subject}\n"
                message_text += f"📅 تاریخ: {created_at}\n"
                message_text += "─────────────────\n\n"
                
                # Add button for this ticket
                keyboard.append([
                    InlineKeyboardButton(
                        f"📋 مشاهده تیکت #{ticket_id}", 
                        callback_data=f"view_ticket_{ticket_id}"
                    )
                ])
            
            # Add refresh button
            keyboard.append([
                InlineKeyboardButton("🔄 به‌روزرسانی", callback_data="refresh_tickets")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                message_text, 
                parse_mode='Markdown',
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
    
    def get_handlers(self):
        """Get all handlers for this module"""
        return [
            CommandHandler('tickets', self.show_tickets_command),
            CallbackQueryHandler(self.view_ticket_callback, pattern=r'^view_ticket_\d+$'),
            CallbackQueryHandler(self.send_answer_callback, pattern=r'^send_answer_\d+$'),
            CallbackQueryHandler(self.edit_answer_callback, pattern=r'^edit_answer_\d+$'),
            CallbackQueryHandler(self.close_ticket_callback, pattern=r'^close_ticket_\d+$'),
            CallbackQueryHandler(self.refresh_tickets_callback, pattern=r'^refresh_tickets$'),
            MessageHandler(filters.TEXT & (~filters.COMMAND), self.receive_edited_answer),
        ]
