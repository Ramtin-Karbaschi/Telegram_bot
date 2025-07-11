"""Utilities for validating and normalising Iranian phone numbers.

The helper `normalize_phone_number` converts user–provided phone numbers –
which might include Persian/Arabic digits, optional leading zero, optional
country code, spaces or dashes – into the canonical E.164‐like form
`+989XXXXXXXXX` used throughout the project/database.

If the input cannot be interpreted as a valid Iranian mobile number the
function returns ``None``.
"""
from __future__ import annotations

import re

from .locale_utils import fa_to_en_digits

_IR_MOBILE_REGEX = re.compile(r"^(?:\+98|0|98)?9\d{9}$")

def normalize_phone_number(raw: str | None) -> str | None:
    """Return phone number in `+989xxxxxxxxx` format or *None* if invalid.

    Accepts the following variants (Persian digits also allowed):
        • 09123456789
        • 9123456789
        • +989123456789
        • 98 912 345 6789
        • ۰۹۱۲۳۴۵۶۷۸۹ (Persian)

    The algorithm:
    1. Convert Persian/Arabic digits to Latin using ``fa_to_en_digits``.
    2. Strip all characters except digits and plus.
    3. Apply regex validation and re-format to the canonical form.
    """
    if not raw or not isinstance(raw, str):
        return None

    # Convert locale digits to EN and remove common separators/spaces
    cleaned = fa_to_en_digits(raw)
    cleaned = re.sub(r"[\s\-()]+", "", cleaned)

    # Ensure only leading plus is allowed in the remaining string
    if cleaned.startswith("+"):
        plus = "+"
        cleaned_body = cleaned[1:]
    else:
        plus = ""
        cleaned_body = cleaned

    # After stripping the plus, validate allowed pattern for Iranian mobile numbers
    if not _IR_MOBILE_REGEX.fullmatch((plus and "+") + cleaned_body):
        return None

    # Remove any leading + or country/zero prefixes to build canonical format
    # Remove leading plus if present for processing
    body = cleaned_body
    if body.startswith("98"):
        body = body[2:]
    elif body.startswith("0"):
        body = body[1:]

    # Now body should start with '9' and be 10 digits
    if len(body) != 10 or not body.startswith("9"):
        return None

    return "+98" + body

__all__ = ["normalize_phone_number"]
