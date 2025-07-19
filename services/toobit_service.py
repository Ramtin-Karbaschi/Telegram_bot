"""Service wrapper for Toobit.com API operations used by the Free Package flow.

This module centralises every call we need to make to Toobit so that the rest
of the bot can remain decoupled from HTTP / auth details.  If the exchange
changes its API in the future, we only need to touch this file.

IMPORTANT: The actual REST endpoints that are hit here are **assumptions**
because we do not yet have official documentation.  Replace the placeholder
URLs once Toobit provides the production API.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import requests

import config

logger = logging.getLogger(__name__)


class ToobitServiceError(Exception):
    """Raised whenever the exchange returns an error or the HTTP request fails."""


class ToobitService:  # pylint: disable=too-few-public-methods
    """Light-weight synchronous API wrapper.

    It only implements the small subset of functionality that we need for the
    *Free Package* feature:

    1. Verify that a UID has signed up using **our** referral code.
    2. Fetch the user's cumulative trading volume.
    3. Fetch the timestamp of their last trade (for inactivity checks).
    """

    _DEFAULT_HEADERS = {
        "Accept": "application/json",
        "User-Agent": "DaraeiAcademyBot/1.0 (+https://t.me/Daraei_Academy_bot)",
    }

    def __init__(self, *, base_url: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.base_url: str = base_url or config.TOOBIT_API_BASE_URL
        self.api_key: str = api_key or config.TOOBIT_API_KEY

        if not self.api_key:
            logger.error("TOOBIT_API_KEY is missing. Free Package flow will not work until it is set in .env")
        self._session = requests.Session()
        # Ensure header values are ASCII-only to prevent UnicodeEncodeError
        headers = dict(self._DEFAULT_HEADERS)
        if self.api_key and self.api_key.isascii():
            headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            if self.api_key:
                logger.warning("TOOBIT_API_KEY contains non-ASCII characters; Authorization header skipped to avoid encoding error.")
        self._session.headers.update(headers)

    # ---------------------------------------------------------------------
    # Public helpers used by bot flows
    # ---------------------------------------------------------------------
    def is_user_referred_by_us(self, uid: str) -> bool:
        """Return True **iff** *uid* registered with our referral code."""
        try:
            from urllib.parse import quote
            safe_uid = quote(uid, safe="")
            resp = self._get(f"/v1/users/{safe_uid}/referral")
            return resp.get("referral_code") == config.TOOBIT_REF_CODE
        except ToobitServiceError as exc:
            logger.warning("Toobit referral check failed: %s", exc)
            return False

    def get_user_total_volume(self, uid: str) -> float:
        """Return the cumulative traded *USD* volume for the user.

        If something goes wrong we conservatively return 0 which will fail the
        eligibility check.
        """
        try:
            from urllib.parse import quote
            safe_uid = quote(uid, safe="")
            data = self._get(f"/v1/users/{safe_uid}/trading-volume")
            # Expected payload: {"volume_usd": 1234.56}
            return float(data.get("volume_usd", 0))
        except ToobitServiceError as exc:
            logger.warning("Toobit volume fetch failed: %s", exc)
            return 0.0
        except (TypeError, ValueError):
            return 0.0

    def get_last_trade_time(self, uid: str) -> Optional[datetime]:
        """Return the timestamp of the latest *filled* order for inactivity checks."""
        try:
            from urllib.parse import quote
            safe_uid = quote(uid, safe="")
            data = self._get(f"/v1/users/{safe_uid}/last-trade")
            # Expected payload: {"executed_at": "2025-07-15T10:15:30Z"}
            ts: str | None = data.get("executed_at")
            return datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
        except ToobitServiceError as exc:
            logger.warning("Toobit last-trade fetch failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        try:
            res = self._session.get(url, timeout=10)
        except requests.RequestException as exc:
            raise ToobitServiceError(f"Network error when calling {url}: {exc}") from exc

        if res.status_code >= 400:
            raise ToobitServiceError(f"API error {res.status_code}: {res.text}")

        try:
            return res.json()
        except ValueError as exc:
            raise ToobitServiceError(f"Invalid JSON response from {url}") from exc
