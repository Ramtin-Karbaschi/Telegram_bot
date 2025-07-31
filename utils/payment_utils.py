"""Utility helpers related to crypto (USDT) payments.

This module currently provides one public helper:

    generate_unique_crypto_amount

which combines a *base_amount* (integer or Decimal) and the UUID *payment_id*
into a unique USDT amount with 2-decimal precision that can be used to
uniquely map an on-chain payment to a pending payment request.

If the initially generated amount already exists in the database for another
*pending* payment, the helper will iterate – deterministically but quickly –
through alternative suffixes until an unused amount is found, up to
``10 ** precision - 1`` tries. With 2-digit precision we have 99 unique slots
for each integer amount which is more than enough under normal load. The
code is database-agnostic; the caller needs to pass in a callable
`is_amount_taken(amount: Decimal) -> bool` that returns ``True`` if the amount
is already used by a *pending* payment.
"""
from __future__ import annotations

import hashlib
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable

logger = logging.getLogger(__name__)

_PRECISION = 2  # digits after decimal point
_MAX_TRIES = 99  # maximum different suffixes with 2-digit precision


def _suffix_from_uuid(payment_id: str, counter: int = 0, precision: int = _PRECISION) -> Decimal:
    """Return a Decimal suffix like Decimal('0.23') derived from *payment_id*.

    The *counter* allows generating a different suffix if the first choice was
    already taken.
    """
    # Use sha256 of the UUID + counter to get plenty of entropy
    digest = hashlib.sha256(f"{payment_id}-{counter}".encode()).hexdigest()
    # Take last <precision*2> hex chars → convert to int → mod range 1-99
    raw_int = int(digest[-precision * 2 :], 16) % (10**precision - 1) + 1
    fmt = f"{{:0{precision}d}}"  # e.g. precision=2 → "{:02d}"
    suffix_str = fmt.format(raw_int)
    return Decimal(f"0.{suffix_str}")


def generate_unique_crypto_amount(
    base_amount: Decimal | int | float,
    payment_id: str,
    is_amount_taken: Callable[[Decimal], bool],
    precision: int = _PRECISION,
) -> Decimal:
    """Return a unique Decimal(`base_amount + suffix`) not colliding with **pending** payments.

    Parameters
    ----------
    base_amount : Decimal | int | float
        The original (plan) price in USDT.
    payment_id : str
        UUID for this payment request – used as entropy.
    is_amount_taken : Callable[[Decimal], bool]
        Function that returns *True* if the candidate amount already exists in
        *pending* payments.
    precision : int, optional
        Number of decimal places used for uniqueness (default 2).
    """
    base = Decimal(str(base_amount)).quantize(Decimal("1."))  # ensure no decimals in base

    for attempt in range(_MAX_TRIES):
        suffix = _suffix_from_uuid(payment_id, counter=attempt, precision=precision)
        candidate = (base + suffix).quantize(Decimal(f"1.{precision * '0'}"), ROUND_HALF_UP)
        if not is_amount_taken(candidate):
            logger.debug(
                "Unique crypto amount generated: base=%s, suffix=%s → %s (attempt %d)",
                base,
                suffix,
                candidate,
                attempt,
            )
            return candidate
    # In the unlikely event that all suffixes are taken, fall back to base
    logger.warning("All unique suffixes taken for base_amount %s. Returning base amount.", base)
    return Decimal(str(base_amount))
