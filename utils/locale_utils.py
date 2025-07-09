"""Utility functions for locale-aware text handling (Persian/Arabic digits)."""

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
EN_DIGITS = "0123456789"

# Build translation map: Persian+Arabic -> English
TRANS_TABLE = str.maketrans(PERSIAN_DIGITS + ARABIC_DIGITS, EN_DIGITS * 2)

def fa_to_en_digits(text: str | None) -> str | None:
    """Convert any Persian/Arabic digits in *text* to their English equivalents.

    Returns the original string if *text* is falsy (preserves None).
    """
    if not text:
        return text
    return text.translate(TRANS_TABLE)


def to_int(text: str) -> int:
    """Safely convert Persian/English digit string to int."""
    return int(fa_to_en_digits(text).strip())


def to_float(text: str) -> float:
    """Safely convert Persian/English digit string to float."""
    return float(fa_to_en_digits(text).strip())
