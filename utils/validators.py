#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Input validators for the Daraei Academy Telegram bot."""

import datetime

MIN_PERSIAN_BIRTH_YEAR = 1320
MAX_PERSIAN_BIRTH_YEAR = 1394 # Adjust as needed, e.g., current_shamsi_year - 18

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
