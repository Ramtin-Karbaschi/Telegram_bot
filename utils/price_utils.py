import requests
import math
from config import logger

NOBITEX_USDT_IRT_ORDERBOOK_URL = "https://api.nobitex.ir/v3/orderbook/USDTIRT"

async def get_usdt_to_irr_rate() -> float | None:
    """Fetches the current USDT to IRT exchange rate from Nobitex and converts it to IRR."""
    try:
        response = requests.get(NOBITEX_USDT_IRT_ORDERBOOK_URL, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        data = response.json()
        
        if data.get("status") == "ok":
            last_trade_price_toman_str = data.get("lastTradePrice")
            if last_trade_price_toman_str:
                last_trade_price_toman = float(last_trade_price_toman_str)
                rate_irr = last_trade_price_toman * 10  # Convert Toman to Rial
                logger.info(f"Successfully fetched USDT/IRT rate from Nobitex: {last_trade_price_toman} Toman. Converted to IRR: {rate_irr}")
                return rate_irr
            else:
                logger.error("Nobitex API response does not contain 'lastTradePrice'.")
                return None
        else:
            logger.error(f"Nobitex API request failed with status: {data.get('status')}. Response: {data}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching USDT price from Nobitex: {e}")
        return None
    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing Nobitex API response or converting price: {e}. Response data: {data if 'data' in locals() else 'N/A'}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching USDT price from Nobitex: {e}")
        return None

def convert_irr_to_usdt(irr_amount: float, usdt_rate: float) -> float | None:
    """Converts an IRR amount to USDT, rounding up to 3 decimal places."""
    if usdt_rate is None or usdt_rate <= 0:
        return None
    usdt_amount = irr_amount / usdt_rate
    return math.ceil(usdt_amount * 1000) / 1000
