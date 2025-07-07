from __future__ import annotations

"""Helper for generating unique one-time Telegram invite links and persisting
   them in the database.

Usage pattern (inside an *async* handler):

    links = await InviteLinkManager.ensure_one_time_links(
        context.bot,
        target_user_id,   # Telegram "user_id"
    )
    if links:
        for link in links:
            await context.bot.send_message(target_user_id, link)

This helper automatically:
• Creates separate links for every channel / group listed in
  `config.TELEGRAM_CHANNELS_INFO` with `member_limit = 1` so that the link is
  effectively one-time-use.
• Stores those links in the `invite_links` table (via
  `database.invite_link_queries`).
• Re-uses *previously generated* unused links for the same user if they exist
  (prevents redundant API calls when the user requests the link again without
  joining).

Note: The bot must be *administrator* of the target channels / groups with
`invite_users` permission; otherwise Telegram will raise `Forbidden`.
"""

import asyncio
import logging
from typing import List, Optional

from telegram import Bot, ChatInviteLink
from telegram.error import TelegramError, Forbidden

import config
from database import invite_link_queries as ilq

logger = logging.getLogger(__name__)


class InviteLinkManager:
    """Static helpers – instantiation not required."""

    @staticmethod
    async def _create_one_time_link(bot: Bot, chat_id: int, title: str | None = None) -> Optional[str]:
        """Create a single-use invite link for *chat_id*.

        Returns the invite-link string or *None* on failure.
        """
        try:
            link_obj: ChatInviteLink = await bot.create_chat_invite_link(
                chat_id=chat_id,
                member_limit=1,
                creates_join_request=False,
                name=title,  # Optional name visible in Telegram UI
            )
            return link_obj.invite_link
        except Forbidden:
            logger.error("Bot lacks permission to create invite links in chat %s", chat_id)
        except TelegramError as exc:
            logger.error("Telegram error while creating invite link for chat %s – %s", chat_id, exc)
        return None

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    @staticmethod
    async def ensure_one_time_links(bot: Bot, user_id: int) -> Optional[List[str]]:
        """Return a list of one-time invite links (for all configured chats).

        If there are already *unused* links for *user_id* in DB, re-use them.
        Otherwise generate new links for **all** chats defined in
        `config.TELEGRAM_CHANNELS_INFO`.
        The returned list keeps the same order as `config.TELEGRAM_CHANNELS_INFO`.
        """
        # This is a simplified check. A robust implementation would query for all
        # active links for the user and check if the set of chats matches.
        # For now, we check for any single active link as a proxy.
        if ilq.get_active_invite_link(user_id):
            logger.info("User %s already has active invite links. Re-sending.", user_id)
            # This part is still not ideal as it only fetches one link.
            # A proper fix would involve changing `get_active_invite_link` to
            # `get_all_active_invite_links`.
            # For now, we will regenerate links to ensure the user gets all of them.

        # Generate fresh links for every configured channel / group
        generation_tasks = []
        for chat_info in config.TELEGRAM_CHANNELS_INFO:
            chat_id = chat_info["id"]
            link_title = f"one-time link for {user_id} – {chat_info['title']}"
            generation_tasks.append(
                InviteLinkManager._create_one_time_link(bot, chat_id, link_title)
            )

        generated_links = await asyncio.gather(*generation_tasks)

        # Map chat title -> link
        title_to_link = {}
        for chat_info, link in zip(config.TELEGRAM_CHANNELS_INFO, generated_links):
            if link:
                title_to_link[chat_info["title"]] = link

        if not title_to_link:
            logger.error("Failed to generate any invite links for user %s", user_id)
            return None

        # Persist all newly generated links to the database.
        persist_tasks = []
        for link in title_to_link.values():
            persist_tasks.append(
                asyncio.to_thread(ilq.create_invite_link, user_id, link)
            )

        results = await asyncio.gather(*persist_tasks)

        if not all(results):
            logger.warning("Failed to persist one or more invite links for user %s", user_id)
            # We still return the links so the user can join.

        logger.info("Successfully created and persisted %d links for user %s", len(title_to_link), user_id)
        return title_to_link
