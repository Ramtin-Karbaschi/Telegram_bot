#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Input validators for the Daraei Academy Telegram bot."""

import datetime
import re

MIN_PERSIAN_BIRTH_YEAR = 1320
MAX_PERSIAN_BIRTH_YEAR = 1386  # Adjust as needed, e.g., current_shamsi_year - 18


def _convert_persian_digits_to_latin(s: str) -> str:
    """Convert Persian/Arabic digits in *s* to Latin digits."""
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"
    trans_table = str.maketrans(persian_digits + arabic_digits, "0123456789" * 2)
    return s.translate(trans_table)


def parse_persian_birth_date(date_str: str) -> str | None:
    """Parse a flexible Persian birth-date string and return normalized ``YYYY/MM/DD``.

    Accepted variants (examples):
        - "1371/6/01" or "۱۳۷۱/۰۶/۰۱"
        - "01-06-1371" or "۰۱-۰۶-۱۳۷۱"
        - "01 06 1371"
        - Order irrelevant: "1371-06-01" or "06-01-1371"

    Rules enforced:
    1. Year must be between *MIN_PERSIAN_BIRTH_YEAR* and *MAX_PERSIAN_BIRTH_YEAR*.
    2. Month may be 1–12, one or two digits.
    3. Day must be 1–31, **two digits required** (e.g., 01, 31). Single-digit day is rejected per requirements.
    4. Mixed Persian/Latin digits allowed; stored result uses Latin digits.

    Returns the normalized date string or *None* if invalid.
    """
    if not date_str or not isinstance(date_str, str):
        return None

    # Normalise separators to '/'
    cleaned = re.sub(r"[\-\s]+", "/", date_str.strip())
    cleaned = _convert_persian_digits_to_latin(cleaned)

    parts = cleaned.split("/")
    if len(parts) != 3:
        return None

    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None

    # Identify year (the only 4-digit part or value >= 1300)
    year_idx = None
    for i, n in enumerate(nums):
        if n >= MIN_PERSIAN_BIRTH_YEAR and n <= MAX_PERSIAN_BIRTH_YEAR and (len(parts[i]) == 4 or year_idx is None):
            year_idx = i
    if year_idx is None:
        return None

    year = nums[year_idx]
    # Remaining two elements are month & day but order could vary
    md = [nums[i] for i in range(3) if i != year_idx]
    if len(md) != 2:
        return None

    # First assume month/day order
    month, day = md
    # If month is >12 swap
    if month > 12 and day <= 12:
        month, day = day, month

    # Validate month/day ranges
    if not (1 <= month <= 12):
        return None
    if not (1 <= day <= 31):
        return None

    # Day must be two-digit in original token (requirement 1 & 3)
    original_day_token = parts[[i for i in range(3) if i != year_idx][md.index(day)]]
    if len(original_day_token) != 2:
        return None

    # Use jdatetime for strict validity
    try:
        import jdatetime
        jdatetime.date(year, month, day)
    except Exception:
        return None

    return f"{year:04d}/{month:02d}/{day:02d}"


def is_valid_persian_birth_date(date_str: str) -> bool:
    """Validate a Persian (Shamsi) birth date in ``YYYY/MM/DD`` format.

    The function checks:
    1. The string matches the expected pattern of four‐digit year, two‐digit
       month and two‐digit day separated by slashes, e.g. ``1370/01/15``.
    2. The year component is within the allowed range defined above.
    3. The resulting jdatetime.date is constructible (catches invalid day /
       month combinations such as 1399/13/01).
    """
    return parse_persian_birth_date(date_str) is not None

def is_valid_persian_birth_year(year_str: str) -> bool:
    """Checks if the given string is a valid Persian birth year."""
    if not year_str:
        return False
    if not year_str.isdigit():
        return False
    try:
        year = int(year_str)
        # Basic range check for a Persian (Shamsi) year
        # You might want to get the current Shamsi year dynamically for MAX_PERSIAN_BIRTH_YEAR
        if MIN_PERSIAN_BIRTH_YEAR <= year <= MAX_PERSIAN_BIRTH_YEAR:
            return True
        return False
    except ValueError:
        return False

if __name__ == '__main__':
    # Test cases
    print(f"1370: {is_valid_persian_birth_year('1370')}") # True
    print(f"1319: {is_valid_persian_birth_year('1319')}") # False
    print(f"1395: {is_valid_persian_birth_year('1395')}") # False (based on current MAX_PERSIAN_BIRTH_YEAR)
    print(f"abcd: {is_valid_persian_birth_year('abcd')}") # False
    print(f"137: {is_valid_persian_birth_year('137')}")   # False
    print(f"13700: {is_valid_persian_birth_year('13700')}") # False
    print(f"   : {is_valid_persian_birth_year('   ')}") # False
    print(f"None: {is_valid_persian_birth_year(None)}") # False
