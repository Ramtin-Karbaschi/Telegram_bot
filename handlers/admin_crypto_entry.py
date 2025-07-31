"""
🚪 Admin Crypto Entry Handler
============================

Simple command handler to start the admin crypto keyboard panel.
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from utils.admin_utils import admin_required
from handlers.admin_crypto_keyboard import AdminCryptoKeyboard

logger = logging.getLogger(__name__)

@admin_required
async def admin_crypto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start admin crypto panel command"""
    
    user = update.effective_user
    logger.info(f"👑 Admin {user.id} ({user.first_name}) requested crypto admin panel")
    
    # Start the keyboard conversation
    await AdminCryptoKeyboard.start_admin_panel(update, context)

# Create command handler
admin_crypto_entry_handler = CommandHandler("admin_crypto", admin_crypto_command)
