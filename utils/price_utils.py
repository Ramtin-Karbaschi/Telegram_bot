import requests
import math
import time
from typing import Optional

from config import logger, NOBITEX_API_KEY, NOBITEX_API_BASE_URL

# Cache variables for USDT→IRR rate to avoid hitting the API more than once per minute
_cached_rate_irr: Optional[float] = None
_cache_timestamp: float = 0.0

NOBITEX_USDT_IRT_ORDERBOOK_URL = f"{NOBITEX_API_BASE_URL.rstrip('/')}/v3/orderbook/USDTIRT"

async def get_usdt_to_irr_rate(force_refresh: bool = False) -> float | None:
    """Return USDT→IRR rate.

    The value is fetched from Nobitex and cached for up to 60 seconds to respect API
    limits. If *force_refresh* is True, the cache is bypassed.
    """

    global _cached_rate_irr, _cache_timestamp

    now = time.time()
    if not force_refresh and _cached_rate_irr is not None and (now - _cache_timestamp) < 60:
        return _cached_rate_irr

    try:
        headers = {}
        if NOBITEX_API_KEY:
            headers["Authorization"] = f"Bearer {NOBITEX_API_KEY}"

        response = requests.get(NOBITEX_USDT_IRT_ORDERBOOK_URL, timeout=10, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Nobitex returns data["lastTradePrice"] in TOMAN when status == "ok"
        if data.get("status") == "ok":
            last_trade_price_toman_str = data.get("lastTradePrice") or data.get("lastTradePrice", data.get("lastTradePriceToman"))
            if last_trade_price_toman_str:
                last_trade_price_toman = float(last_trade_price_toman_str)
                rate_irr = last_trade_price_toman * 10  # toman→rial
                _cached_rate_irr = rate_irr
                _cache_timestamp = now
                logger.info(
                    "Fetched USDT/IRT rate from Nobitex: %.0f toman (%.0f IRR).", last_trade_price_toman, rate_irr
                )
                return rate_irr
            logger.error("Nobitex API response missing 'lastTradePrice'. Response: %s", data)
            return None
        logger.error("Nobitex API request failed. Response: %s", data)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Error fetching USDT price from Nobitex: %s", e)
    except (ValueError, TypeError) as e:
        logger.error("Error parsing Nobitex API response: %s", e)
    except Exception as e:
        logger.error("Unexpected error fetching USDT price: %s", e)

    return None

def convert_irr_to_usdt(irr_amount: float, usdt_rate: float) -> float | None:
    """Convert *irr_amount* (Rial) to USDT.

    The amount is rounded **upwards** to 3 decimal places to protect against price
    fluctuations (e.g., 12.3451 → 12.346).
    """
    if usdt_rate is None or usdt_rate <= 0:
        return None

    usdt_amount = irr_amount / usdt_rate
    return math.ceil(usdt_amount * 1000) / 1000
