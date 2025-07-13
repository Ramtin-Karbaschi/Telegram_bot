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
    def verify_payment_by_hash(tx_hash: str, min_amount: float, wallet_address: str) -> tuple[bool, float]:
        """Validate a single transaction by its hash.

        Args:
            tx_hash: Transaction hash provided by the user.
            min_amount: Minimum USDT amount that should have been transferred.
            wallet_address: Our destination wallet address.

        Returns
        -------
        (True, amount) if the hash is valid, sent **to** our wallet, and *amount >= min_amount*.
        Otherwise returns (False, 0.0).
        """
        if not (tx_hash and wallet_address and min_amount > 0):
            logger.warning("verify_payment_by_hash called with invalid arguments")
            return False, 0.0

        headers = {"TRON-PRO-API-KEY": config.TRONGRID_API_KEY} if getattr(config, "TRONGRID_API_KEY", None) else {}
        url = f"{CryptoPaymentService.TRONGRID_ENDPOINT}/v1/transactions/{tx_hash}/events"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            events = resp.json().get("data", [])
        except requests.RequestException as e:
            logger.error("TronGrid tx lookup failed: %s", e)
            return False, 0.0
        except ValueError:
            logger.error("Invalid JSON from TronGrid when fetching tx %s", tx_hash)
            return False, 0.0

        contract_addr = config.USDT_TRC20_CONTRACT_ADDRESS
        for ev in events:
            if ev.get("event_name") != "Transfer":
                continue
            res = ev.get("result", {})
            if res.get("contract_address") != contract_addr:
                continue
            if res.get("to") != wallet_address:
                continue
            try:
                raw_val = int(res.get("value", "0"))
                amount = raw_val / (10 ** USDT_DECIMALS)
            except (TypeError, ValueError):
                continue
            if amount >= min_amount:
                logger.info("Tx %s valid: %.6f USDT to our wallet", tx_hash, amount)
                return True, amount
        logger.info("Tx %s not matched or insufficient amount", tx_hash)
        return False, 0.0

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
    def get_final_usdt_payment_amount(base_usdt_amount_rounded_to_3_decimals: float, payment_request_id: str | int) -> float:
        """Return a **unique** USDT amount for this payment request.

        Args:
            base_usdt_amount_rounded_to_3_decimals: Plan price already rounded to 3 decimals (e.g. ``97.000``).
            payment_request_id: Primary-key/UUID of the row returned by ``create_crypto_payment_request``.

        Strategy
        ---------
        • Add یک افست کوچک (≤ 0.00099) به مبلغ پایه؛ این افست از شناسهٔ رکورد مشتق می‌شود و تا 5 رقم اعشار نگه داشته می‌شود.
        • بدین ترتیب هر تراکنش عدد متمایز دارد و می‌توان آن را با دقت کامل روی بلاک‌چین تطبیق داد.
        • خروجی نهایتاً تا ``USDT_DECIMALS`` رقم اعشار (پیش‌فرض 6) گرد می‌شود.
        """
        if base_usdt_amount_rounded_to_3_decimals <= 0:
            logger.error("Base USDT amount must be positive: %s", base_usdt_amount_rounded_to_3_decimals)
            return 0.0

        # Derive a deterministic numeric seed from the request id (works for int PK or UUID string)
        try:
            if isinstance(payment_request_id, int):
                numeric_id = payment_request_id
            else:
                # UUID or str: take last 6 hex chars -> int
                numeric_id = int(str(payment_request_id).replace("-", "")[-6:], 16)
        except (ValueError, TypeError):
            numeric_id = int(time.time())  # fallback to current seconds, still reasonably unique

        # Map to 1-99 then to 0.00001-0.00099
        offset_index = (numeric_id % 99) + 1  # 1 → 99 inclusive
        unique_offset = round(offset_index / 100_000, 5)  # five-decimal offset

        final_amount = round(base_usdt_amount_rounded_to_3_decimals + unique_offset, USDT_DECIMALS)
        logger.info(
            "Computed unique USDT amount %.6f (base %.3f + offset %.5f) for payment_request_id=%s",
            final_amount,
            base_usdt_amount_rounded_to_3_decimals,
            unique_offset,
            payment_request_id,
        )
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
