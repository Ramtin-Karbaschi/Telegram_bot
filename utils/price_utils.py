import requests
import math
import time
from typing import Optional

from config import logger, ABANTETHER_API_KEY, ABANTETHER_API_BASE_URL

# Cache variables for USDT→Toman (IRT) buy rate to avoid hitting the API more than once per minute
_cached_rate_toman: Optional[float] = None
_cache_timestamp: float = 0.0

ABANTETHER_USDT_IRR_PRICE_URL = f"{ABANTETHER_API_BASE_URL.rstrip('/')}/otc/coin-price/"

async def get_usdt_to_irr_rate(force_refresh: bool = False) -> float | None:
    """Return USDT→IRR rate.

    The value is fetched from AbanTether and cached for up to 60 seconds to respect
    API limits. If *force_refresh* is True, the cache is bypassed.
    """

    global _cached_rate_toman, _cache_timestamp

    now = time.time()
    from config import USDT_RATE_CACHE_SECONDS
    if not force_refresh and _cached_rate_toman is not None and (now - _cache_timestamp) < USDT_RATE_CACHE_SECONDS:
        return _cached_rate_toman

    try:
        headers = {}
        if ABANTETHER_API_KEY:
            headers["Authorization"] = f"Token {ABANTETHER_API_KEY}"

        response = requests.get(ABANTETHER_USDT_IRR_PRICE_URL, timeout=10, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Expected structure: {"USDT": {"usdtPrice": "1", "irtPriceBuy": "27200.0", ...}}
        if isinstance(data, dict) and "USDT" in data and isinstance(data["USDT"], dict):
            usdt_info = data["USDT"]
                        # AbanTether returns both buy/sell. To ensure the customer pays enough, use the HIGHER of the two.
            sell_str = usdt_info.get("irtPriceSell")
            buy_str = usdt_info.get("irtPriceBuy")
            try:
                sell_price = float(sell_str) if sell_str else 0.0
            except ValueError:
                sell_price = 0.0
            try:
                buy_price = float(buy_str) if buy_str else 0.0
            except ValueError:
                buy_price = 0.0

            rate_irr = max(sell_price, buy_price)
            if rate_irr > 0:
                _cached_rate_toman = rate_irr
                _cache_timestamp = now
                logger.info("Fetched USDT SELL price from AbanTether: %.0f Toman.", rate_irr)
                return rate_irr
            logger.error("AbanTether response missing valid price fields. Response: %s", data)
            return None
        logger.error("Unexpected AbanTether response structure: %s", data)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Error fetching USDT price from AbanTether: %s", e)
    except (ValueError, TypeError) as e:
        logger.error("Error parsing AbanTether API response: %s", e)
    except Exception as e:
        logger.error("Unexpected error fetching USDT price: %s", e)

    return None

def convert_usdt_to_irr(usdt_amount: float, usdt_rate_toman: float) -> int | None:
    """Convert a *usdt_amount* to Iranian **Rial** (IRR).

    1. Multiply USDT amount by the *toman* rate to obtain a value in Toman.
    2. Convert Toman to Rial by multiplying by ``10``.
    3. The result is rounded to the nearest integer Rial for gateway compatibility.
    """

    if usdt_rate_toman is None or usdt_rate_toman <= 0:
        return None

    toman_amount = usdt_amount * usdt_rate_toman  # USDT ➜ Toman
    irr_amount = int(round(toman_amount * 10))    # Toman ➜ Rial
    return irr_amount


def convert_irr_to_usdt(irr_amount: float, usdt_rate_toman: float) -> float | None:
    """Convert *irr_amount* (Rial) to USDT.

    1. مبلغ ریالی ابتدا به تومان تبدیل می‌شود (تقسیم بر ۱۰).
    2. مقدار به‌دست آمده بر نرخ تتر (بر حسب تومان) تقسیم می‌شود.
    3. برای محافظت در برابر نوسان قیمت، نتیجه به سمت بالا و تا 5 رقم اعشار (گرد کردن به بالا در رقم ششم) گرد می‌شود.
    """

    if usdt_rate_toman is None or usdt_rate_toman <= 0:
        return None

    toman_amount = irr_amount / 10  # ریال → تومان
    usdt_amount = toman_amount / usdt_rate_toman
    # گرد کردن به بالا در رقم ششم اعشار (نتیجه ۵ رقم اعشار به کاربر نمایش داده می‌شود)
    return math.ceil(usdt_amount * 100000) / 100000
