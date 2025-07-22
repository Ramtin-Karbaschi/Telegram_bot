"""Utilities for validating and normalising phone numbers.

The helper `normalize_phone_number` converts user–provided phone numbers –
which might include Persian/Arabic digits, optional leading zero, optional
country code, spaces or dashes – into the canonical E.164‐like form
`+CCXXXXXXXXX` used throughout the project/database.

Supports both Iranian and international mobile numbers.
If the input cannot be interpreted as a valid mobile number the
function returns ``None``.
"""
from __future__ import annotations

import re

from .locale_utils import fa_to_en_digits

_IR_MOBILE_REGEX = re.compile(r"^(?:\+98|0|98)?9\d{9}$")

def normalize_phone_number(raw: str | None) -> str | None:
    """Return phone number in E.164 format or *None* if invalid.

    Accepts Iranian and international variants (Persian digits also allowed):
        Iranian:
        • 09123456789
        • 9123456789
        • +989123456789
        • 98 912 345 6789
        • ۰۹۱۲۳۴۵۶۷۸۹ (Persian)
        
        International:
        • +1234567890
        • +44 20 7946 0958
        • +86 138 0013 8000

    The algorithm:
    1. Convert Persian/Arabic digits to Latin using ``fa_to_en_digits``.
    2. Strip all characters except digits and plus.
    3. Apply validation and re-format to the canonical E.164 form.
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

    # First try Iranian mobile number validation
    if _IR_MOBILE_REGEX.fullmatch((plus and "+") + cleaned_body):
        # Remove any leading + or country/zero prefixes to build canonical format
        body = cleaned_body
        if body.startswith("98"):
            body = body[2:]
        elif body.startswith("0"):
            body = body[1:]

        # Now body should start with '9' and be 10 digits
        if len(body) == 10 and body.startswith("9"):
            return "+98" + body
    
    # If not Iranian, try international format
    if plus == "+" and cleaned_body.isdigit():
        # Basic international validation: country code + number
        # Must be between 7-15 digits total (E.164 standard)
        if 7 <= len(cleaned_body) <= 15:
            return "+" + cleaned_body
    
    # If no plus but starts with country code, add plus
    if not plus and cleaned_body.isdigit() and len(cleaned_body) >= 10:
        # Common country codes that might be entered without +
        common_codes = ['1', '44', '49', '33', '39', '34', '7', '86', '81', '82', '91', '92', '93', '94', '95', '60', '62', '63', '65', '66']
        for code in sorted(common_codes, key=len, reverse=True):  # Try longer codes first
            if cleaned_body.startswith(code) and 7 <= len(cleaned_body) <= 15:
                return "+" + cleaned_body
    
    return None

__all__ = ["normalize_phone_number"]
