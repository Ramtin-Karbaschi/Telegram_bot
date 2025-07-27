"""Utility text formatting helpers for Telegram buttons/messages."""

def strikethrough(text: str) -> str:
    """Return *text* with a Unicode combining long stroke overlay on every character.

    This emulates **strikethrough** in places where Telegram markup is *not* parsed,
    such as button titles (ReplyKeyboardButton / InlineKeyboardButton).

    Example
    -------
    >>> strikethrough('150$')
    '1̶5̶0̶$̶'
    """
    return ''.join(ch + '\u0336' for ch in str(text))


import re

def _md_st_to_overlay(match: re.Match) -> str:
    """Internal helper: convert matched group to strikethrough overlay string."""
    return strikethrough(match.group(1))


def buttonize_markdown(text: str) -> str:
    """Convert limited Markdown/HTML formatting markers inside *text* to styles
    compatible with Telegram *button labels* by replacing them with Unicode
    overlay equivalents.

    Supported conversions:
    • `~text~` (MarkdownV2 strike)  -> overlay strikethrough
    • `<s>text</s>` (HTML strike)  -> overlay strikethrough

    Other formatting is left unchanged (displayed literally) because buttons
    cannot render bold/italic etc.
    """
    if not text:
        return text
    # markdownV2 strikethrough ~text~
    text = re.sub(r"~([^~]+)~", _md_st_to_overlay, text)
    # html <s>text</s>
    text = re.sub(r"<s>([^<]+)</s>", _md_st_to_overlay, text, flags=re.IGNORECASE)
    return text


def price_with_discount(old_price: str, new_price: str, prefix: str = "اشتراک یکماهه /") -> str:
    """Build a button label showing *old_price* strikethrough and *new_price* plain.

    Parameters
    ----------
    old_price : str
        Original price (e.g. '150$').
    new_price : str
        Discounted price (e.g. '70$').
    prefix : str, default 'اشتراک یکماهه /'
        Text to appear before the prices.
    """
    return f"{prefix} {strikethrough(old_price)}  {new_price}"
