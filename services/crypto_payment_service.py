# services/crypto_payment_service.py

import logging
import time
import requests
from datetime import datetime, timedelta

import config

logger = logging.getLogger(__name__)

# Constants for TronGrid API
# USDT on TRON typically has 6 decimal places
USDT_DECIMALS = 6 

class CryptoPaymentService:
    @staticmethod
    def get_final_usdt_payment_amount(base_usdt_amount_rounded_to_3_decimals: float) -> float:
        """
        Returns the final USDT amount to be paid by the user.
        This is typically the base USDT amount for the plan, already converted from Rial 
        and rounded up to 3 decimal places.
        No unique offset is added here as per the new requirement.
        The amount is returned rounded to USDT_DECIMALS (e.g., 6) for consistency, 
        but the value itself will effectively be the 3-decimal rounded input.
        Example: input 0.061 -> output 0.061000 (if USDT_DECIMALS is 6)
        """
        if base_usdt_amount_rounded_to_3_decimals <= 0:
            logger.error("Base USDT amount must be positive: %s", base_usdt_amount_rounded_to_3_decimals)
            # Consider raising ValueError if this is an unrecoverable state
            return 0.0
        
        # Ensure the final amount is represented with USDT_DECIMALS, even if it's just padding zeros
        # For example, if base is 0.061 and USDT_DECIMALS is 6, this returns 0.061000.
        # This maintains consistency in how amounts are stored or processed downstream if they expect USDT_DECIMALS precision.
        final_amount = round(base_usdt_amount_rounded_to_3_decimals, USDT_DECIMALS)
        logger.info(f"Final USDT payment amount determined: {final_amount} from base: {base_usdt_amount_rounded_to_3_decimals}")
        return final_amount

# Example usage (for testing purposes, normally called from bot handlers)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Testing crypto_payment_service...")

    # Test exchange rate
    rate = CryptoPaymentService.get_usdt_to_rial_exchange_rate()
    logger.info(f"Current USDT to RIAL (placeholder): {rate}")

    # Test unique amount calculation
    test_rial_amount = 2500000 # 2,500,000 Rials
    test_payment_id = 123
    unique_usdt = CryptoPaymentService.calculate_unique_usdt_amount(test_rial_amount, test_payment_id)
    logger.info(f"For {test_rial_amount} RIAL and payment ID {test_payment_id}, unique USDT amount: {unique_usdt}")

    # Test finding a payment (this will likely not find anything without a real transaction)
    # Set a search start time, e.g., 30 minutes ago
    # search_from = datetime.now() - timedelta(minutes=30)
    # found_tx = find_usdt_payment(unique_expected_amount=unique_usdt, search_start_time=search_from)
    
    # if found_tx:
    #     logger.info(f"Found test transaction: {found_tx}")
    # else:
    #     logger.info("No matching test transaction found (as expected without a real payment).")
    
    # To test find_usdt_payment effectively, you would need to:
    # 1. Ensure your .env has correct CRYPTO_WALLET_ADDRESS, TRONGRID_API_KEY, USDT_TRC20_CONTRACT_ADDRESS.
    # 2. Manually send a USDT (TRC20) transaction to your CRYPTO_WALLET_ADDRESS with the exact 'unique_usdt' amount.
    # 3. Run this script shortly after the transaction is broadcast.
    logger.info("To test find_usdt_payment, uncomment the section and make a real test transaction.")
