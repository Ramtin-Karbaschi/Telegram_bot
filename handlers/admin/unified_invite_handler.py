"""
Unified Invite Link Handler
یک handler یکپارچه برای ارسال لینک دعوت با قابلیت انتخاب کانال
"""

import logging
from typing import List, Dict, Optional
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, 
    CallbackQueryHandler, MessageHandler, filters, CommandHandler
)
from telegram.error import Forbidden, BadRequest, TelegramError
import asyncio

from database.queries import DatabaseQueries
from utils.invite_link_manager import InviteLinkManager
import config

logger = logging.getLogger(__name__)

# Conversation states
GET_USER_INFO, SELECT_CHANNELS = range(2)


class UnifiedInviteHandler:
    """Handler for creating and sending invite links with channel selection"""
    
    def __init__(self, db_queries=None, main_bot_app=None):
        self.db_queries = db_queries or DatabaseQueries()
        self.main_bot_app = main_bot_app
        
    async def start_invite_process(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """شروع فرآیند ارسال لینک دعوت"""
        query = update.callback_query
        if query:
            await query.answer()
            
        # Check if called from user search (has user_id in callback data)
        user_id = None
        if query and query.data.startswith('create_invite_'):
            try:
                user_id = int(query.data.split('_')[-1])
            except (ValueError, IndexError):
                pass
        
        if user_id:
            # Store user_id and go to channel selection
            context.user_data['invite_target_user_id'] = user_id
            return await self.show_channel_selection(update, context)
        else:
            # Ask for user ID
            message = (
                "🔗 لطفاً آیدی عددی کاربری که می‌خواهید برای او لینک دعوت بسازید را ارسال کنید.\n\n"
                "برای لغو /cancel را بزنید."
            )
            
            if query:
                try:
                    await query.edit_message_text(message)
                except Exception as e:
                    # If message content is same, just send a new message
                    logger.warning(f"Could not edit message: {e}")
                    await query.message.reply_text(message)
            else:
                await update.message.reply_text(message)
            
            return GET_USER_INFO
    
    async def receive_user_info(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """دریافت اطلاعات کاربر"""
        user_input = update.message.text.strip()
        
        # Try to parse as user_id
        try:
            user_id = int(user_input)
        except ValueError:
            await update.message.reply_text(
                "❌ آیدی کاربر باید یک عدد باشد.\n"
                "برای انصراف: /cancel"
            )
            return GET_USER_INFO
        
        # Store user_id
        context.user_data['invite_target_user_id'] = user_id
        
        # Show channel selection
        return await self.show_channel_selection(update, context)
    
    async def show_channel_selection(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """نمایش لیست کانال‌ها برای انتخاب"""
        user_id = context.user_data.get('invite_target_user_id')
        
        # Get user info for display
        user_info = self.db_queries.get_user_details(user_id)
        if user_info:
            user_display = user_info.get('full_name') or user_info.get('username') or f"ID: {user_id}"
        else:
            user_display = f"ID: {user_id}"
        
        # Get all configured channels
        channels = config.TELEGRAM_CHANNELS_INFO if hasattr(config, 'TELEGRAM_CHANNELS_INFO') else []
        
        if not channels:
            message = "❌ هیچ کانالی در سیستم تعریف نشده است."
            if update.callback_query:
                await update.callback_query.edit_message_text(message)
            else:
                await update.message.reply_text(message)
            return ConversationHandler.END
        
        # Initialize selected channels if not exists
        if 'selected_channels' not in context.user_data:
            context.user_data['selected_channels'] = []
        
        selected = context.user_data['selected_channels']
        
        # Build keyboard with channels
        keyboard = []
        
        message_lines = [
            "📋 انتخاب کانال‌ها برای ارسال لینک دعوت",
            f"👤 کاربر: {user_display}",
            "━━━━━━━━━━━━━━━━━━━━━",
            "کانال‌های مورد نظر را انتخاب کنید:",
            ""
        ]
        
        for channel in channels:
            channel_id = channel.get('id')
            channel_title = channel.get('title', f'Channel {channel_id}')
            
            # Check if selected
            is_selected = channel_id in selected
            checkbox = "☑️" if is_selected else "⬜"
            
            # Create button
            button_text = f"{checkbox} {channel_title}"
            callback_data = f"inv_toggle_ch_{channel_id}"
            
            keyboard.append([
                InlineKeyboardButton(button_text, callback_data=callback_data)
            ])
            
            # Add to message
            status = "✅" if is_selected else "⭕"
            message_lines.append(f"  {status} {channel_title}")
        
        # Add action buttons
        keyboard.append([
            InlineKeyboardButton("🚀 ارسال همه لینک‌ها", callback_data="inv_send_all"),
            InlineKeyboardButton("✅ ارسال انتخابی", callback_data="inv_send_selected")
        ])
        keyboard.append([
            InlineKeyboardButton("❌ انصراف", callback_data="inv_cancel")
        ])
        
        # Count selected
        if selected:
            message_lines.append("")
            message_lines.append(f"📊 تعداد انتخاب شده: {len(selected)} از {len(channels)}")
        
        # Send or update message
        reply_markup = InlineKeyboardMarkup(keyboard)
        message_text = "\n".join(message_lines)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=message_text,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                text=message_text,
                reply_markup=reply_markup
            )
        
        return SELECT_CHANNELS
    
    async def handle_channel_selection(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """مدیریت انتخاب کانال‌ها"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "inv_cancel":
            await query.edit_message_text("❌ عملیات لغو شد.")
            context.user_data.pop('invite_target_user_id', None)
            context.user_data.pop('selected_channels', None)
            return ConversationHandler.END
        
        if data == "inv_send_all":
            # Send links for all channels
            return await self.send_invite_links(update, context, send_all=True)
        
        if data == "inv_send_selected":
            # Check if any channel selected
            selected = context.user_data.get('selected_channels', [])
            if not selected:
                await query.answer("⚠️ لطفاً حداقل یک کانال را انتخاب کنید", show_alert=True)
                return SELECT_CHANNELS
            
            return await self.send_invite_links(update, context, send_all=False)
        
        # Toggle specific channel
        if data.startswith('inv_toggle_ch_'):
            try:
                channel_id = int(data.replace('inv_toggle_ch_', ''))
                
                selected = context.user_data.get('selected_channels', [])
                if channel_id in selected:
                    selected.remove(channel_id)
                else:
                    selected.append(channel_id)
                
                context.user_data['selected_channels'] = selected
                
                # Refresh display
                return await self.show_channel_selection(update, context)
                
            except (ValueError, IndexError):
                await query.answer("❌ خطا در پردازش انتخاب")
                return SELECT_CHANNELS
        
        return SELECT_CHANNELS
    
    async def send_invite_links(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE,
        send_all: bool = False
    ) -> int:
        """ارسال لینک‌های دعوت"""
        query = update.callback_query
        await query.answer()
        
        user_id = context.user_data.get('invite_target_user_id')
        
        # Get channels to send
        if send_all:
            channels = config.TELEGRAM_CHANNELS_INFO if hasattr(config, 'TELEGRAM_CHANNELS_INFO') else []
            message = f"⏳ در حال ایجاد و ارسال لینک برای همه {len(channels)} کانال..."
        else:
            selected_ids = context.user_data.get('selected_channels', [])
            all_channels = config.TELEGRAM_CHANNELS_INFO if hasattr(config, 'TELEGRAM_CHANNELS_INFO') else []
            channels = [ch for ch in all_channels if ch['id'] in selected_ids]
            message = f"⏳ در حال ایجاد و ارسال {len(channels)} لینک انتخاب شده..."
        
        await query.edit_message_text(message)
        
        try:
            # Generate links
            links = await InviteLinkManager.ensure_one_time_links(
                context.bot, 
                user_id,
                channels_info=channels if not send_all else None
            )
            
            if not links:
                await query.edit_message_text(
                    "❌ خطا در ایجاد لینک‌های دعوت.\n"
                    "ممکن است ربات دسترسی ادمین در کانال‌ها نداشته باشد."
                )
                return ConversationHandler.END
            
            # Prepare message with channel names and links
            message_parts = ["🎉 لینک‌های دعوت شما آماده شد:\n"]
            for channel, link in zip(channels, links):
                message_parts.append(f"\n📍 {channel['title']}:\n{link}")
            
            invite_message = "\n".join(message_parts)
            
            # Send to user
            try:
                # Determine which bot to use
                if self.main_bot_app:
                    if hasattr(self.main_bot_app, "application") and hasattr(self.main_bot_app.application, "bot"):
                        bot_to_use = self.main_bot_app.application.bot
                    elif hasattr(self.main_bot_app, "bot"):
                        bot_to_use = self.main_bot_app.bot
                    else:
                        bot_to_use = context.bot
                else:
                    bot_to_use = context.bot
                
                # Send message (without parse_mode to avoid entity errors)
                await bot_to_use.send_message(
                    chat_id=user_id,
                    text=invite_message,
                    parse_mode=None,
                    disable_web_page_preview=True
                )
                
                # Success message to admin
                await query.edit_message_text(
                    f"✅ {len(links)} لینک دعوت با موفقیت برای کاربر {user_id} ارسال شد."
                )
                
            except Forbidden as e:
                error_str = str(e).lower()
                if "bot was blocked by the user" in error_str:
                    error_msg = (
                        f"🚫 کاربر بات را بلاک کرده\n\n"
                        "لینک‌های ایجاد شده:\n"
                    )
                else:
                    error_msg = f"🚫 خطای دسترسی: {str(e)}\n\nلینک‌ها:\n"
                
                for channel, link in zip(channels, links):
                    error_msg += f"\n{channel['title']}:\n{link}\n"
                
                await query.edit_message_text(error_msg)
                
            except BadRequest as e:
                error_str = str(e).lower()
                if "chat not found" in error_str:
                    error_msg = (
                        f"❌ کاربر یافت نشد\n\n"
                        "کاربر باید ابتدا `/start` را در بات بزند.\n\n"
                        "لینک‌های ایجاد شده:\n"
                    )
                else:
                    error_msg = f"❌ خطا: {str(e)}\n\nلینک‌ها:\n"
                
                for channel, link in zip(channels, links):
                    error_msg += f"\n{channel['title']}:\n{link}\n"
                
                await query.edit_message_text(error_msg)
                
            except Exception as e:
                logger.error(f"Error sending invite links: {e}")
                error_msg = f"❌ خطا: {str(e)}\n\nلینک‌ها:\n"
                
                for channel, link in zip(channels, links):
                    error_msg += f"\n{channel['title']}:\n{link}\n"
                
                await query.edit_message_text(error_msg)
                
        except Exception as e:
            logger.error(f"Error creating invite links: {e}")
            await query.edit_message_text(f"❌ خطا در ایجاد لینک‌ها: {str(e)}")
        
        # Clear context
        context.user_data.pop('invite_target_user_id', None)
        context.user_data.pop('selected_channels', None)
        
        return ConversationHandler.END
    
    async def cancel_operation(
        self, 
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """لغو عملیات"""
        # Clear context
        context.user_data.pop('invite_target_user_id', None)
        context.user_data.pop('selected_channels', None)
        
        await update.message.reply_text("❌ عملیات لغو شد.")
        return ConversationHandler.END
    
    def get_conversation_handler(self):
        """بازگرداندن ConversationHandler برای این قابلیت"""
        return ConversationHandler(
            entry_points=[
                # From main menu
                CallbackQueryHandler(
                    self.start_invite_process, 
                    pattern='users_create_invite_link'
                ),
                # From user search
                CallbackQueryHandler(
                    self.start_invite_process,
                    pattern=r'^create_invite_\d+$'
                )
            ],
            states={
                GET_USER_INFO: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, 
                        self.receive_user_info
                    )
                ],
                SELECT_CHANNELS: [
                    CallbackQueryHandler(
                        self.handle_channel_selection,
                        pattern=r'^inv_(toggle_ch_|send_all|send_selected|cancel)'
                    )
                ]
            },
            fallbacks=[
                CommandHandler("cancel", self.cancel_operation),
                CallbackQueryHandler(
                    self.cancel_operation,
                    pattern='^inv_cancel$'
                )
            ],
            per_user=True,
            per_chat=True,
            allow_reentry=True
        )
