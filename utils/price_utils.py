import requests
import math
import time
from typing import Optional

from config import logger, ABANTETHER_API_KEY, ABANTETHER_API_BASE_URL

# Cache variables for USDT→IRR rate to avoid hitting the API more than once per minute
_cached_rate_irr: Optional[float] = None
_cache_timestamp: float = 0.0

ABANTETHER_USDT_IRR_PRICE_URL = f"{ABANTETHER_API_BASE_URL.rstrip('/')}/otc/coin-price/"

async def get_usdt_to_irr_rate(force_refresh: bool = False) -> float | None:
    """Return USDT→IRR rate.

    The value is fetched from AbanTether and cached for up to 60 seconds to respect
    API limits. If *force_refresh* is True, the cache is bypassed.
    """

    global _cached_rate_irr, _cache_timestamp

    now = time.time()
    if not force_refresh and _cached_rate_irr is not None and (now - _cache_timestamp) < 60:
        return _cached_rate_irr

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
            price_irr_str = usdt_info.get("irtPriceBuy") or usdt_info.get("irtPriceSell")
            if price_irr_str:
                rate_irr = float(price_irr_str)
                _cached_rate_irr = rate_irr
                _cache_timestamp = now
                logger.info("Fetched USDT/IRR rate from AbanTether: %.0f IRR.", rate_irr)
                return rate_irr
            logger.error("AbanTether response missing 'irtPriceBuy'/'irtPriceSell'. Response: %s", data)
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

def convert_irr_to_usdt(irr_amount: float, usdt_rate_toman: float) -> float | None:
    """Convert *irr_amount* (Rial) to USDT.

    1. مبلغ ریالی ابتدا به تومان تبدیل می‌شود (تقسیم بر ۱۰).
    2. مقدار به‌دست آمده بر نرخ تتر (بر حسب تومان) تقسیم می‌شود.
    3. برای محافظت در برابر نوسان قیمت، نتیجه به سمت بالا و تا 4 رقم اعشار گرد می‌شود.
    """

    if usdt_rate_toman is None or usdt_rate_toman <= 0:
        return None

    toman_amount = irr_amount / 10  # ریال → تومان
    usdt_amount = toman_amount / usdt_rate_toman
    return math.ceil(usdt_amount * 10000) / 10000
