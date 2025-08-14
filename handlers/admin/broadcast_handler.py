"""Admin broadcast handler – allows admin to send a global message with custom buttons.

Flow:
/start or callback `admin_broadcast_start` (only admins)
1. ASK_MESSAGE – admin sends text (only text supported for v1).
2. MENU – shows currently selected buttons + options to add button, send, cancel.
3. ADD_BUTTON – open categories/plans tree, admin selects category or plan -> added.
4. Back to MENU; admin can repeat or send.
5. On send, iterate over all registered user telegram_ids and send the message with InlineKeyboardMarkup.
"""
from __future__ import annotations

import os
import json

import logging
from typing import List, Dict, Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from utils.helpers import admin_only_decorator as admin_only, safe_edit_message_text
from utils.text_utils import buttonize_markdown
from database.queries import DatabaseQueries as _DB
from utils.keyboards.categories_keyboard import get_categories_keyboard
from utils.keyboards import get_subscription_plans_keyboard

# ---------- internal helpers ---------- #

def _flatten_categories(cat_nodes: list[dict]) -> list[dict]:
    """Flatten nested category tree into a simple list of dicts preserving order."""
    flat: list[dict] = []
    def _walk(nodes: list[dict]):
        for n in nodes:
            flat.append(n)
            _walk(n.get("children", []))
    _walk(cat_nodes)
    return flat

# ---------- Composite keyboard ---------- #

def _build_category_plan_keyboard(parent_id: int | None = None):
    """Return a keyboard that lists child categories (for navigation) AND plans belonging to that category.

    parent_id None means root products menu (uncategorised plans)."""
    cat_kb = get_categories_keyboard(parent_id).inline_keyboard  # list of rows
    # remove the last row (back button) to append after merging
    # cat_kb rows are tuples; convert to list for mutability
    back_row = list(cat_kb[-1]) if cat_kb else []
    cat_rows = [list(r) for r in cat_kb[:-1]] if cat_kb else []

    # Plans rows
    plans_markup = get_subscription_plans_keyboard(category_id=parent_id)
    plan_rows = plans_markup.inline_keyboard[:-1]  # skip its own back row

    # Optional: add a row to select current category itself (as button in broadcast)
    if parent_id is not None:
        from database.queries import DatabaseQueries as _DB
        cat = _DB.get_category_by_id(parent_id)
        if cat:
            rows = [[InlineKeyboardButton(f"➕ {cat['name']}", callback_data=f"addcat_{parent_id}")]] + cat_rows
    else:
        rows = cat_rows
    rows += plan_rows
    # add back row at end
    if back_row:
        rows.append(back_row)
    return InlineKeyboardMarkup(rows)

logger = logging.getLogger(__name__)

# ---------- utility ---------- #

def _ensure_buttons(context: ContextTypes.DEFAULT_TYPE) -> list[Dict[str, str]]:
    """Guarantee a mutable list stored in user_data['broadcast_buttons'] and return it."""
    if not isinstance(context.user_data.get("broadcast_buttons"), list):
        context.user_data["broadcast_buttons"] = []
    return context.user_data["broadcast_buttons"]

# States
ASK_MESSAGE, MENU, ADD_SELECT, ASK_AUDIENCE = range(4)


# ---------- Helper builders ---------- #

def _build_menu_keyboard(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    """Keyboard showing selected buttons with options to add, send or cancel."""
    selected_buttons: List[Dict[str, str]] = _ensure_buttons(context)
    rows: List[List[InlineKeyboardButton]] = []
    # Preview selected buttons (non-functional)
    preview_row: List[InlineKeyboardButton] = []
    for btn in selected_buttons:
        preview_row.append(InlineKeyboardButton(btn["text"], callback_data="noop"))
        if len(preview_row) == 2:
            rows.append(preview_row)
            preview_row = []
    if preview_row:
        rows.append(preview_row)

    # Control buttons
    rows.append([
        InlineKeyboardButton("➕ افزودن کلید", callback_data="broadcast_add"),
        InlineKeyboardButton("✅ ارسال", callback_data="broadcast_send"),
        InlineKeyboardButton("❌ لغو", callback_data="broadcast_cancel"),
    ])
    return InlineKeyboardMarkup(rows)

def _build_audience_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for choosing audience."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 کاربران فعال", callback_data="audience_active"),
            InlineKeyboardButton("👥 تمامی اعضا", callback_data="audience_all"),
        ],
        [InlineKeyboardButton("❌ لغو", callback_data="broadcast_cancel")],
    ])


# ---------- Channel helper ---------- #

def _get_available_channels() -> list[dict]:
    """Fetch available channel buttons from environment.

    Priority:
    1. `BROADCAST_CHANNELS_JSON` – expected to be a JSON list with keys
       `id | name | url` (flexible: `title` or `link` are accepted aliases).
    2. Fallback to legacy `TELEGRAM_CHANNELS_INFO` already present in the
       project. Converts each dict to the canonical format.
    Returns a list of dicts with keys: id, name, url
    """
    raw = os.getenv("BROADCAST_CHANNELS_JSON")
    if not raw:
        # Legacy fallback
        raw = os.getenv("TELEGRAM_CHANNELS_INFO")
    if not raw:
        return []
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            raise ValueError("Channels json must be a list")
        canonical: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            chan_id = item.get("id") or item.get("channel_id")
            name = item.get("name") or item.get("title")
            url = item.get("url") or item.get("link")
            if chan_id is None or name is None or url is None:
                continue
            canonical.append({"id": chan_id, "name": name, "url": url})
        return canonical
    except Exception as e:
        logger.warning("Invalid channel info JSON – %s", e)
        return []

# ---------- Conversation entry ---------- #

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start broadcast flow - show all products and categories for selection"""
    # Check access permissions
    from utils.admin_utils import has_broadcast_access
    user_id = update.effective_user.id if update.effective_user else None
    if not has_broadcast_access(user_id):
        if update.callback_query:
            await update.callback_query.answer("دسترسی محدود است.", show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text("دسترسی محدود است.")
        return
    
    # Initialize broadcast data
    if "broadcast_buttons" not in context.user_data or not isinstance(context.user_data["broadcast_buttons"], list):
        context.user_data["broadcast_buttons"] = []
    context.user_data["bc_flow"] = True

    # Show selection UI
    await _refresh_selection_message(update, context)
    
    # Build selection message helper
async def _refresh_selection_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Render the selection page using current buttons list without resetting state."""
    db = _DB()
    plans = db.get_active_plans()
    categories = _flatten_categories(_DB.get_category_tree())
    channels = _get_available_channels()

    keyboard: list[list[InlineKeyboardButton]] = []
    # Channels header
    if channels:
        keyboard.append([InlineKeyboardButton("🔗 کانال‌ها:", callback_data="header_channels")])
        for ch in channels:
            selected = any(b.get("type") == "channel" and str(b.get("id")) == str(ch.get("id")) for b in context.user_data.get("broadcast_buttons", []))
            prefix = "✅ " if selected else "🔗 "
            keyboard.append([
                InlineKeyboardButton(f"{prefix}{ch.get('name')}", callback_data=f"bc_chan_{ch.get('id')}")
            ])
    # Separator between channels and categories
    if channels and (categories or plans):
        keyboard.append([InlineKeyboardButton("━━━━━━━━━━━━━━━━━━━━", callback_data="sep_ch_cat")])

    # Categories header
    if categories:
        keyboard.append([InlineKeyboardButton("📂 دسته‌بندی‌ها:", callback_data="header_categories")])
        for cat in categories:
            selected = any(b.get("type") == "category" and b.get("id") == cat["id"] for b in context.user_data.get("broadcast_buttons", []))
            prefix = "✅ " if selected else "📁 "
            keyboard.append([
                InlineKeyboardButton(f"{prefix}{cat['name']}", callback_data=f"bc_cat_{cat['id']}")
            ])
    # Separator
    if categories and plans:
        keyboard.append([InlineKeyboardButton("━━━━━━━━━━━━━━━━━━━━", callback_data="separator")])
    # Plans header/products
    if plans:
        keyboard.append([InlineKeyboardButton("🛍️ محصولات:", callback_data="header_products")])
        for plan in plans:
            selected = any(b.get("type") == "plan" and b.get("id") == plan["id"] for b in context.user_data.get("broadcast_buttons", []))
            prefix = "✅ " if selected else "🎯 "
            keyboard.append([
                InlineKeyboardButton(f"{prefix}{plan['name']}", callback_data=f"bc_plan_{plan['id']}")
            ])
    # Controls
    keyboard.append([InlineKeyboardButton("━━━━━━━━━━━━━━━━━━━━", callback_data="separator2")])
    keyboard.append([
        InlineKeyboardButton("✅ ادامه", callback_data="broadcast_continue"),
        InlineKeyboardButton("❌ لغو", callback_data="broadcast_cancel")
    ])

    # Send or edit message
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                "🎯 انتخاب دکمه‌های پیام همگانی\n\n"
                "دسته‌بندی‌ها و محصولاتی که می‌خواهید به عنوان دکمه در پیام نمایش داده شوند را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            if "Message is not modified" in str(e):
                # Message content is the same, just answer the callback
                await update.callback_query.answer()
            else:
                logger.error(f"Error editing broadcast selection message: {e}")
                # Try to answer the callback anyway
                try:
                    await update.callback_query.answer()
                except:
                    pass
    else:
        await update.message.reply_text(
            "🎯 **انتخاب دکمه‌های پیام همگانی**\n\n"
            "دسته‌بندی‌ها و محصولاتی که می‌خواهید به عنوان دکمه در پیام نمایش داده شوند را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )




# ---------- Message content handler (admin sends actual message) ---------- #
async def handle_message_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive the admin's actual message content for broadcast and show a preview with selected buttons."""
    # Only handle if we're waiting for broadcast message
    if not context.user_data.get("bc_waiting_msg"):
        return
    
    # Check access permissions
    from utils.admin_utils import has_broadcast_access
    user_id = update.effective_user.id if update.effective_user else None
    if not has_broadcast_access(user_id):
        await update.effective_message.reply_text("دسترسی محدود است.")
        return
    
    message = update.effective_message
    buttons_data = context.user_data.get("broadcast_buttons", [])

    # Build inline keyboard for preview (URL placeholders – they will be filled before sending)
    from utils.text_utils import buttonize_markdown
    keyboard: list[list[InlineKeyboardButton]] = []
    for b in buttons_data:
        label = buttonize_markdown(b.get("text", "-"))
        if b.get("type") == "channel":
            keyboard.append([InlineKeyboardButton(label, url=b.get("url"))])
        else:
            keyboard.append([InlineKeyboardButton(label, callback_data="ignore")])

    # Send preview
    await message.reply_text(
        "🔎 پیش‌نمایش پیام همگانی:",
    )
    if keyboard:
        await message.copy(
            chat_id=message.chat_id,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await message.copy(chat_id=message.chat_id)

    # Save draft for later (for actual broadcast step handled elsewhere)
    context.user_data["bc_draft_message_id"] = message.message_id
    context.user_data["bc_draft_chat_id"] = message.chat_id
    context.user_data["bc_draft_obj"] = message
    # Store draft descriptor compatible with existing sender logic
    # Save draft details and the Message object itself for later sending via main bot
    context.user_data["bc_draft"] = {
        "type": "copy",
        "data": {"chat_id": message.chat_id, "message_id": message.message_id}
    }
    # Keep original message object (only kept in-memory for this session)
    context.user_data["bc_draft_obj"] = message

    # Clear waiting flag
    context.user_data.pop("bc_waiting_msg", None)
    
    # Offer menu
    await message.reply_text(
        "منو:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 ارسال به همه", callback_data="broadcast_send")],
            [InlineKeyboardButton("➕ افزودن دکمه", callback_data="broadcast_add")],
            [InlineKeyboardButton("❌ لغو", callback_data="broadcast_cancel")],
        ])
    )

# ---------- Menu callbacks ---------- #

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast menu actions (add, send, cancel)"""
    query = update.callback_query
    await query.answer()
    
    # Check access permissions
    from utils.admin_utils import has_broadcast_access
    user_id = update.effective_user.id if update.effective_user else None
    if not has_broadcast_access(user_id):
        await query.answer("دسترسی محدود است.", show_alert=True)
        return
    
    data = query.data
    logger.info(f"Broadcast menu_callback: {data}")
    
    buttons = _ensure_buttons(context)
    
    if data == "broadcast_add":
        # Show product/category selection page
        await _refresh_selection_message(update, context)
        
    elif data == "broadcast_send":
        # Allow sending without buttons - just show a warning
        if not buttons:
            await query.answer("⚠️ پیام بدون دکمه ارسال خواهد شد", show_alert=False)
            
        # Show audience selection
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 کاربران فعال", callback_data="audience_active")],
            [InlineKeyboardButton("👥 تمامی کاربران", callback_data="audience_all")],
            [InlineKeyboardButton("❌ لغو", callback_data="broadcast_cancel")]
        ])
        
        try:
            await query.edit_message_text(
                "👥 **انتخاب مخاطبان**\n\n"
                "پیام برای چه کسانی ارسال شود؟",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        except Exception as e:
            if "Message is not modified" in str(e):
                # Message content is identical, just answer the callback
                await query.answer()
            else:
                logger.error(f"Error editing message in menu_callback: {e}")
                await query.answer("خطا در بروزرسانی پیام", show_alert=True)
        context.user_data["bc_in_audience"] = True
        
    elif data == "broadcast_cancel":
        # Cancel and return to admin menu
        context.user_data.pop("bc_flow", None)
        context.user_data.pop("broadcast_buttons", None)
        context.user_data.pop("bc_waiting_msg", None)
        context.user_data.pop("bc_in_menu", None)
        context.user_data.pop("bc_in_add_select", None)
        context.user_data.pop("bc_in_audience", None)
        
        # Clear all broadcast flags
        for key in list(context.user_data.keys()):
            if key.startswith("bc_"):
                context.user_data.pop(key, None)
        
        # Show cancellation message and return to admin menu
        await query.edit_message_text("❌ ارسال پیام همگانی لغو شد.")
        
        from handlers.admin_menu_handlers import AdminMenuHandler
        admin_handler = AdminMenuHandler()
        await admin_handler.show_admin_menu(update, context)
        return



# ---------- Audience selection ---------- #
async def audience_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle audience choice (active / all) and start broadcast send logic placeholder."""
    query = update.callback_query
    data = query.data
    await query.answer()

    if data == "audience_active":
        context.user_data["bc_audience"] = "active"
    elif data == "audience_all":
        context.user_data["bc_audience"] = "all"
    else:
        await query.answer("گزینه نامعتبر", show_alert=True)
        return

    # Send the broadcast to chosen audience
    draft = context.user_data.get("bc_draft")
    if not draft:
        await query.answer("پیش‌نویس یافت نشد", show_alert=True)
        return

    from database.queries import DatabaseQueries
    buttons_data = context.user_data.get("broadcast_buttons", [])
    # We'll build the inline keyboard after we know the main-bot username
    keyboard = None

    if context.user_data["bc_audience"] == "active":
        users_rows = DatabaseQueries.get_all_active_subscribers()
    else:
        users_rows = DatabaseQueries.get_all_registered_users()
    user_ids = [row['user_id'] if isinstance(row, dict) else row[0] for row in users_rows]

    # Use main bot if available, else fallback to current bot
    from telegram import Bot
    from utils.text_utils import buttonize_markdown
    import re
    try:
        from config import MAIN_BOT_TOKEN, SHARED_CHANNEL_ID
    except ImportError:
        MAIN_BOT_TOKEN = None
        SHARED_CHANNEL_ID = None
    # Always send از طریق ربات اصلی؛ اگر شیء آن در bot_data موجود نباشد، با توکن مستقل ساخته می‌شود.
    # Always enforce sending via main bot. Manager/aux bots must NOT send broadcast directly.
    if context.application.bot_data.get("main_bot_bot"):
        bot_to_use = context.application.bot_data["main_bot_bot"]
    elif MAIN_BOT_TOKEN:
        bot_to_use = Bot(token=MAIN_BOT_TOKEN)
        # Cache for subsequent calls
        context.application.bot_data["main_bot_bot"] = bot_to_use
    else:
        await query.answer("❌ ارسال لغو شد: توکن ربات اصلی (MAIN_BOT_TOKEN) پیکربندی نشده است.", show_alert=True)
        return
    # Build keyboard with deep links to the main bot if buttons exist
    if buttons_data:
        me = await bot_to_use.get_me()
        bot_username = me.username
        rows = []
        for b in buttons_data:
            label = buttonize_markdown(b.get('text', '-'))
            if b.get('type') == 'plan':
                rows.append([InlineKeyboardButton(label, callback_data=f"plan_{b.get('id')}")])
            elif b.get('type') == 'category':
                # Use products_menu_ prefix to trigger category browsing in main bot
                rows.append([InlineKeyboardButton(label, callback_data=f"products_menu_{b.get('id')}")])
            elif b.get('type') == 'channel':
                rows.append([InlineKeyboardButton(label, url=b.get('url'))])
        keyboard = InlineKeyboardMarkup(rows)
    draft_msg = context.user_data.get("bc_draft_obj")
    
    # First, forward message to shared channel if it has media
    shared_message_id = None
    if draft_msg and (draft_msg.photo or draft_msg.video or draft_msg.document or draft_msg.audio or getattr(draft_msg, 'voice', None)) and SHARED_CHANNEL_ID:
        try:
            # Forward to shared channel using manager bot
            forwarded = await context.bot.forward_message(
                chat_id=SHARED_CHANNEL_ID,
                from_chat_id=draft_msg.chat_id,
                message_id=draft_msg.message_id
            )
            shared_message_id = forwarded.message_id
        except Exception as e:
            logger.warning(f"Failed to forward to shared channel: {e}")
    success = 0
    for uid in user_ids:
        try:
            if draft_msg and draft_msg.text and not any([draft_msg.photo, draft_msg.document, draft_msg.video, draft_msg.audio, getattr(draft_msg, 'voice', None)]):
                # Text message
                formatted = re.sub(r"~([^~]+)~", r"<s>\1</s>", draft_msg.text)
                await bot_to_use.send_message(chat_id=uid, text=formatted, reply_markup=keyboard, parse_mode="HTML")
            elif shared_message_id and SHARED_CHANNEL_ID:
                # Copy from shared channel using main bot (preserves content). Telegram Bot API
                # may not accept inline keyboards directly in copy_message across all versions,
                # therefore we first copy the message and then attach the keyboard in a second
                # step via edit_message_reply_markup.
                sent_msg = await bot_to_use.copy_message(
                    chat_id=uid,
                    from_chat_id=SHARED_CHANNEL_ID,
                    message_id=shared_message_id
                )
                if keyboard:
                    try:
                        await bot_to_use.edit_message_reply_markup(
                            chat_id=uid,
                            message_id=sent_msg.message_id,
                            reply_markup=keyboard
                        )
                    except Exception as em:
                        logger.warning("Failed to attach keyboard to copied message for %s: %s", uid, em)
            else:
                # Fallback for other message types - send as text
                await bot_to_use.send_message(
                    chat_id=uid,
                    text="پیام همگانی",
                    reply_markup=keyboard
                )
            success += 1
        except Exception as e:
            # If formatting/parsing error occurs, try copying the original message (keeps entities as-is)
            try:
                from telegram.error import BadRequest
                if isinstance(e, BadRequest) and "parse entities" in str(e).lower():
                    # Fallback – send without HTML parsing
                    if draft_msg and draft_msg.text:
                        await bot_to_use.send_message(chat_id=uid, text=draft_msg.text, reply_markup=keyboard)
                    elif shared_message_id and SHARED_CHANNEL_ID:
                        sent_msg = await bot_to_use.copy_message(chat_id=uid, from_chat_id=SHARED_CHANNEL_ID, message_id=shared_message_id)
                        if keyboard:
                            try:
                                await bot_to_use.edit_message_reply_markup(chat_id=uid, message_id=sent_msg.message_id, reply_markup=keyboard)
                            except Exception as em:
                                logger.warning("Fallback: failed to attach keyboard to copied message for %s: %s", uid, em)
                    else:
                        await bot_to_use.send_message(chat_id=uid, text="پیام همگانی", reply_markup=keyboard)
                    success += 1
                else:
                    logger.warning("Broadcast send to %s failed: %s", uid, e)
            except Exception as copy_err:
                logger.warning("Broadcast fallback copy to %s failed: %s", uid, copy_err)
    # Clean up: remove temporary message from shared channel
    if shared_message_id and SHARED_CHANNEL_ID:
        try:
            await bot_to_use.delete_message(chat_id=SHARED_CHANNEL_ID, message_id=shared_message_id)
        except Exception as e:
            logger.info("Could not delete temp shared message: %s", e)

    await query.edit_message_text(f"✅ ارسال به پایان رسید. موفق: {success}/{len(user_ids)}")

    # Clear flow flags
    for k in ["bc_flow", "bc_in_audience", "broadcast_buttons", "bc_draft", "bc_draft_message_id", "bc_draft_chat_id"]:
        context.user_data.pop(k, None)

# ---------- Category / Plan selection ---------- #

async def add_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle product/category selection for broadcast buttons"""
    query = update.callback_query
    await query.answer()
    
    # Check access permissions
    from utils.admin_utils import has_broadcast_access
    user_id = update.effective_user.id if update.effective_user else None
    if not has_broadcast_access(user_id):
        await query.answer("دسترسی محدود است.", show_alert=True)
        return
    
    data = query.data
    logger.info(f"Broadcast add_select_callback: {data}")
    
    # Ensure buttons list exists
    buttons = _ensure_buttons(context)
    
    try:
        if data.startswith("bc_cat_"):
            # Category selection - add to broadcast buttons
            category_id = int(data.split("_")[2])
            db = _DB()
            category = db.get_category_by_id(category_id)
            
            if category:
                # Check if already added
                existing = next((b for b in buttons if b.get("type") == "category" and b.get("id") == category_id), None)
                if not existing:
                    buttons.append({
                        "type": "category",
                        "id": category_id,
                        "text": category["name"],
                        "url": None  # Will be set during broadcast
                    })
                    await query.answer(f"✅ دسته '{category['name']}' انتخاب شد", show_alert=False)
                else:
                    # Remove if already exists
                    buttons[:] = [b for b in buttons if not (b.get("type") == "category" and b.get("id") == category_id)]
                    await query.answer(f"❌ دسته '{category['name']}' حذف شد", show_alert=False)
            
            # Refresh the selection page
            await _refresh_selection_message(update, context)
            
        elif data.startswith("bc_chan_"):
            logger.info("Channel selection tapped: %s", data)
            chan_id = data.split("_", 2)[2]
            channels = _get_available_channels()
            ch_obj = next((c for c in channels if str(c.get("id")) == chan_id), None)
            if ch_obj:
                existing = next((b for b in buttons if b.get("type") == "channel" and str(b.get("id")) == chan_id), None)
                if not existing:
                    buttons.append({
                        "type": "channel",
                        "id": chan_id,
                        "text": ch_obj.get("name"),
                        "url": ch_obj.get("url")
                    })
                    await query.answer(f"✅ کانال '{ch_obj.get('name')}' انتخاب شد", show_alert=False)
                else:
                    buttons[:] = [b for b in buttons if not (b.get("type") == "channel" and str(b.get("id")) == chan_id)]
                    await query.answer(f"❌ کانال '{ch_obj.get('name')}' حذف شد", show_alert=False)
            await _refresh_selection_message(update, context)

        elif data.startswith("bc_plan_"):
            # Product selection - add to broadcast buttons
            plan_id = int(data.split("_")[2])
            db = _DB()
            plan = db.get_plan_by_id(plan_id)
            
            if plan:
                # Check if already added
                existing = next((b for b in buttons if b.get("type") == "plan" and b.get("id") == plan_id), None)
                if not existing:
                    buttons.append({
                        "type": "plan",
                        "id": plan_id,
                        "text": plan["name"],
                        "url": None  # Will be set during broadcast
                    })
                    await query.answer(f"✅ محصول '{plan['name']}' انتخاب شد", show_alert=False)
                else:
                    # Remove if already exists
                    buttons[:] = [b for b in buttons if not (b.get("type") == "plan" and b.get("id") == plan_id)]
                    await query.answer(f"❌ محصول '{plan['name']}' حذف شد", show_alert=False)
            
            # Refresh the selection page
            await _refresh_selection_message(update, context)
            
        elif data == "broadcast_continue":
            # Continue to message input
            await query.edit_message_text(
                "📝 حالا پیام مورد نظر خود را ارسال کنید:"
            )
            context.user_data["bc_waiting_msg"] = True
            
        elif data == "broadcast_cancel":
            # Cancel broadcast
            context.user_data.pop("bc_flow", None)
            context.user_data.pop("broadcast_buttons", None)
            context.user_data.pop("bc_waiting_msg", None)
            
            from handlers.admin_menu_handlers import AdminMenuHandler
            admin_handler = AdminMenuHandler()
            await admin_handler.show_admin_menu(update, context)
            
    except Exception as e:
        logger.error(f"Error in add_select_callback: {e}", exc_info=True)
        await query.answer("❌ خطا در پردازش درخواست")


# ---------- Send ---------- #

async def _broadcast_send(query, context):
    text = context.user_data.get("broadcast_text")
    if not text:
        await query.edit_message_text("متن پیام یافت نشد. ابتدا متن را ارسال کنید.")
        return MENU

    buttons = context.user_data.get("broadcast_buttons", [])
    markup = None
    if buttons:
        # two buttons per row
        rows = []
        current = []
        for btn in buttons:
            current.append(InlineKeyboardButton(btn["text"], callback_data=btn["callback_data"]))
            if len(current) == 2:
                rows.append(current)
                current = []
        if current:
            rows.append(current)
        markup = InlineKeyboardMarkup(rows)

    # Determine audience
    audience = context.user_data.get("audience", "all")
    db = _DB()
    if audience == "active" and hasattr(db, "get_active_subscribers"):
        user_rows = db.get_active_subscribers()
    elif audience == "active":
        # fallback filter
        user_rows = [u for u in db.get_all_registered_users() if u.get("is_active")]
    else:
        user_rows = db.get_all_registered_users()
    success = 0
    failed = 0
    bot = query.bot
    for row in user_rows:
        try:
            await bot.send_message(chat_id=row["telegram_id"], text=text, reply_markup=markup)
            success += 1
        except Exception as e:
            logger.warning("Failed to broadcast to %s: %s", row, e)
            failed += 1
    await query.edit_message_text(f"✅ پیام به {success} کاربر ارسال شد. ❌ ناموفق: {failed}")


# ---------- Canceller ---------- #

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ارسال پیام همگانی لغو شد.")
    return ConversationHandler.END


# ---------- ConversationHandler factory ---------- #

def get_broadcast_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("broadcast", broadcast_start),
            CallbackQueryHandler(broadcast_start, pattern=r"^broadcast_custom$"),
            MessageHandler(filters.Text(["📢 ارسال پیام همگانی"]), broadcast_start)
        ],
        states={
            ASK_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message_content)],
            MENU: [CallbackQueryHandler(menu_callback)],
            ADD_SELECT: [
                CallbackQueryHandler(add_select_callback, pattern=r"^(bc_cat_|bc_plan_|bc_chan_|broadcast_continue|broadcast_cancel)")
            ],
            ASK_AUDIENCE: [CallbackQueryHandler(audience_callback)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="broadcast_handler",
        persistent=False,
    )
