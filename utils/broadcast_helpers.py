"""Helper utilities for admin broadcast flow."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict, Set

def build_channel_select_keyboard(channels: List[Dict], selected_ids: Set[int]) -> InlineKeyboardMarkup:
    """Return an inline keyboard to multi-select channels.

    Args:
        channels: list of dicts with keys 'id' and 'title'.
        selected_ids: set of already-selected channel IDs.
    """
    keyboard = []
    row = []
    for ch in channels:
        cid = ch["id"]
        title = ch["title"]
        selected = cid in selected_ids
        text = ("✅ " if selected else "☑️ ") + title
        row.append(InlineKeyboardButton(text, callback_data=f"chpick_{cid}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    toggle_text = "انتخاب همه" if len(selected_ids) < len(channels) else "لغو همه"
    keyboard.append([
        InlineKeyboardButton(toggle_text, callback_data="chpick_all"),
        InlineKeyboardButton("✅ تأیید", callback_data="chpick_done"),
    ])
    keyboard.append([
        InlineKeyboardButton("❌ انصراف", callback_data="broadcast_cancel")
    ])
    return InlineKeyboardMarkup(keyboard)
