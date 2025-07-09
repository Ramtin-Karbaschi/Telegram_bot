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
    """Utility functions for handling TRC-20 (USDT) crypto payments using TronGrid.

    The verification flow is:
        1. Bot creates a payment request (recorded in DB) and shows the exact USDT amount.
        2. User sends the exact amount to our TRC20 wallet.
        3. When user clicks "payment_verify_crypto", handler fetches the DB record and
           invokes ``CryptoPaymentService.verify_payment``.
        4. ``verify_payment`` queries TronGrid for token transfers **to** our wallet
           starting from the request creation time, filters by:
              • contract = USDT_TRC20_CONTRACT_ADDRESS
              • to_address = our wallet
              • amount == expected_amount (string exact match up to 6 decimals)
              • transaction *confirmed*
        5. On success returns the transaction hash & block timestamp so handler can
           mark DB row paid and activate subscription.

    All network operations have 10 s timeout & proper error handling/logging.
    """

    TRONGRID_ENDPOINT = "https://api.trongrid.io"  # Mainnet; change for testnet if needed

    @staticmethod
    def _fetch_trc20_transfers(wallet_address: str, contract_address: str, min_timestamp: int, api_key: str, limit: int = 200):
        """Query TronGrid for TRC-20 transfers **to** *wallet_address* since *min_timestamp* (unix ms).

        Returns list[dict] (raw transfers). Uses pagination if more results exist.
        """
        headers = {"TRON-PRO-API-KEY": api_key} if api_key else {}
        transfers = []
        url = (
            f"{CryptoPaymentService.TRONGRID_ENDPOINT}/v1/accounts/{wallet_address}/transactions/trc20"
            f"?only_confirmed=true&limit={limit}&contract_address={contract_address}"
        )
        while url:
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                batch = data.get("data", [])
                # Filter by timestamp >= min_timestamp (TronGrid timestamp is in ms)
                batch = [t for t in batch if t.get("block_timestamp", 0) >= min_timestamp]
                transfers.extend(batch)
                # TronGrid pagination
                url = data.get("next")
            except requests.RequestException as e:
                logger.error("TronGrid request failed: %s", e)
                break
            except ValueError as e:
                logger.error("Error parsing TronGrid JSON: %s", e)
                break
        return transfers

    @staticmethod
    def verify_payment(expected_amount: float, request_created_at: datetime, wallet_address: str) -> tuple[bool, str | None]:
        """Verify if an on-chain transfer matching *expected_amount* USDT was received.

        Returns (True, tx_hash) on success, otherwise (False, None).
        """
        api_key = config.TRONGRID_API_KEY
        contract = config.USDT_TRC20_CONTRACT_ADDRESS
        if not (api_key and contract and wallet_address):
            logger.error("Missing TronGrid configuration; verification aborted.")
            return False, None

        # TronGrid uses 6 decimals for USDT values; convert float to int string with 6 decimals
        int_amount = int(round(expected_amount * (10 ** USDT_DECIMALS)))
        amount_hex = hex(int_amount)

        min_ts = int(request_created_at.timestamp() * 1000)  # ms
        transfers = CryptoPaymentService._fetch_trc20_transfers(wallet_address, contract, min_ts, api_key)
        for tr in transfers:
            # Ensure it is *to* our wallet and *value* matches
            if tr.get("to") != wallet_address:
                continue
            # `value` is hex of integer amount
            if tr.get("value") == amount_hex:
                txid = tr.get("transaction_id")
                logger.info("Matched USDT payment tx %s for amount %.6f", txid, expected_amount)
                return True, txid
        logger.info("No matching USDT payment found for amount %.6f", expected_amount)
        return False, None
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
