# services/crypto_payment_service.py

import logging
import time
import requests
from datetime import datetime, timedelta

import config

logger = logging.getLogger(__name__)

# Constants for TronGrid API
TRONGRID_API_BASE_URL = "https://api.trongrid.io"
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

    @staticmethod
    def _get_trc20_transactions(min_timestamp_ms: int = None, limit: int = 50) -> list:
        """
        Helper function to fetch TRC20 transactions for the configured wallet address.
        Filters by the USDT contract address and optionally by a minimum timestamp.
        """
        if not config.TRONGRID_API_KEY:
            logger.error("TRONGRID_API_KEY is not configured.")
            return []
        if not config.CRYPTO_WALLET_ADDRESS or config.CRYPTO_WALLET_ADDRESS == config._WALLET_NOT_SET_PLACEHOLDER:
            logger.error("CRYPTO_WALLET_ADDRESS is not configured.")
            return []
        if not config.USDT_TRC20_CONTRACT_ADDRESS or config.USDT_TRC20_CONTRACT_ADDRESS == "USDT_CONTRACT_NOT_SET_IN_ENV":
            logger.error("USDT_TRC20_CONTRACT_ADDRESS is not configured.")
            return []

        headers = {
            "Accept": "application/json",
            "TRON-PRO-API-KEY": config.TRONGRID_API_KEY
        }
        # We are interested in transactions TO our wallet
        # And only for the USDT contract
        url = f"{TRONGRID_API_BASE_URL}/v1/accounts/{config.CRYPTO_WALLET_ADDRESS}/transactions/trc20"
        params = {
            'limit': limit,
            'contract_address': config.USDT_TRC20_CONTRACT_ADDRESS,
            'only_to': 'true', # Only transactions to our wallet
            'order_by': 'block_timestamp,desc' # Get newest first
        }
        if min_timestamp_ms:
            params['min_timestamp'] = min_timestamp_ms # Transactions after this timestamp

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10) # 10s timeout
            response.raise_for_status() # Raise HTTPError for bad responses (4XX or 5XX)
            data = response.json()
            return data.get('data', [])
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching TRC20 transactions from TronGrid: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching TRC20 transactions: {e}")
        return []

    @staticmethod
    def find_usdt_payment(unique_expected_amount: float, search_start_time: datetime) -> dict | None:
        """
        Monitors the blockchain for an incoming USDT transaction matching the unique expected amount.

        Args:
            unique_expected_amount: The precise USDT amount (with unique fraction) to look for.
            search_start_time: The datetime from which to start searching for transactions.

        Returns:
            The transaction dictionary if found and confirmed, otherwise None.
        """
        min_timestamp_ms = int(search_start_time.timestamp() * 1000)
        expected_value_in_smallest_unit = int(unique_expected_amount * (10**USDT_DECIMALS))

        logger.info(
            f"Searching for USDT transaction of {unique_expected_amount} ({expected_value_in_smallest_unit} units) "
            f"to {config.CRYPTO_WALLET_ADDRESS} since {search_start_time.isoformat()}"
        )

        transactions = CryptoPaymentService._get_trc20_transactions(min_timestamp_ms=min_timestamp_ms)

        for tx in transactions:
            # TronGrid returns value as a string for TRC20, representing the smallest unit
            tx_value_str = tx.get('value')
            tx_to_address = tx.get('to')
            tx_id = tx.get('transaction_id')
            
            if tx_value_str is None or tx_to_address != config.CRYPTO_WALLET_ADDRESS:
                continue
            
            try:
                tx_value_units = int(tx_value_str)
            except ValueError:
                logger.warning(f"Could not parse transaction value: {tx_value_str} for tx_id: {tx_id}")
                continue

            # Check if the transaction amount matches the expected unique amount
            # Allow for a very small tolerance due to potential float precision issues, 
            # though direct integer comparison is better if possible.
            if tx_value_units == expected_value_in_smallest_unit:
                logger.info(f"Potential matching transaction found: {tx_id} with value {tx_value_units} units.")
                # TODO: Implement confirmation check
                # confirmed = _check_transaction_confirmations(tx_id, config.CRYPTO_PAYMENT_CONFIRMATIONS)
                # if confirmed:
                #     logger.info(f"Transaction {tx_id} confirmed.")
                #     return tx
                # else:
                logger.info(f"Potential matching transaction found: {tx_id} with value {tx_value_units} units. Checking confirmations...")
                confirmed = CryptoPaymentService._check_transaction_confirmations(tx_id, config.CRYPTO_PAYMENT_CONFIRMATIONS)
                if confirmed:
                    logger.info(f"Transaction {tx_id} is confirmed with at least {config.CRYPTO_PAYMENT_CONFIRMATIONS} confirmations.")
                    return tx
                else:
                    logger.info(f"Transaction {tx_id} found but not yet sufficiently confirmed (less than {config.CRYPTO_PAYMENT_CONFIRMATIONS} confirmations). Will check again later.")
        
        return None

    @staticmethod
    def _check_transaction_confirmations(transaction_id: str, required_confirmations: int) -> bool:
        """
        Checks if a transaction has reached the required number of confirmations.
        Placeholder: This is a complex part and needs careful implementation.
        TronGrid might offer an endpoint for transaction info including confirmations, 
        or one might need to compare block numbers.
        """
        # Example: GET https://api.trongrid.io/wallet/gettransactioninfobyid?value=<transaction_id>
        # The response might contain 'blockNumber' and current block 'block_header.raw_data.number'.
        # Confirmations = current_block_number - transaction_block_number + 1
        logger.warning(f"Confirmation check for {transaction_id} is not fully implemented. Returning True as placeholder.")
        if not config.TRONGRID_API_KEY:
            logger.error("TRONGRID_API_KEY is not configured for confirmation check.")
            return False # Cannot check without API key
        
        # This is a simplified placeholder. Real implementation needs to fetch current block height
        if not config.TRONGRID_API_KEY or config.TRONGRID_API_KEY == config._KEY_NOT_SET_PLACEHOLDER:
            logger.error("TRONGRID_API_KEY is not configured. Cannot check transaction confirmations.")
            return False

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "TRON-PRO-API-KEY": config.TRONGRID_API_KEY
        }

        # 1. Get transaction info by ID to find its block number
        tx_info_payload = {"value": transaction_id}
        tx_info_url = f"{TRONGRID_API_BASE_URL}/wallet/gettransactioninfobyid"
        try:
            response_tx_info = requests.post(tx_info_url, headers=headers, json=tx_info_payload, timeout=10)
            response_tx_info.raise_for_status()
            tx_info_data = response_tx_info.json()

            if not tx_info_data: # Empty response means transaction not found or not confirmed yet by this node
                logger.warning(f"Transaction info for {transaction_id} is empty or not found yet.")
                return False
        
            # Check for 'blockNumber' and if it's 0, it might mean it's not confirmed / in a block yet
            # Or if the transaction failed, it might not have a blockNumber.
            # Some failed TRC20 transfers might still appear in account transaction history but have no blockNumber or a 'failed' status.
            # We are primarily interested in successful, confirmed transactions.
            if 'blockNumber' not in tx_info_data or tx_info_data['blockNumber'] == 0:
                logger.info(f"Transaction {transaction_id} does not have a block number or blockNumber is 0. Not confirmed.")
                return False
        
            # Check for transaction result in receipt if available (e.g., 'SUCCESS')
            # This can vary; for TRC20, the presence in `transactions/trc20` usually implies success of the token transfer itself.
            # The `gettransactioninfobyid` might also contain a `receipt.result` or similar.
            # For example, if tx_info_data.get('receipt', {}).get('result') == 'FAILED', it's definitely not a valid payment.
            # We assume _get_trc20_transactions already filters for successful-looking transfers to some extent.

            transaction_block_number = tx_info_data['blockNumber']
            logger.info(f"Transaction {transaction_id} is in block {transaction_block_number}.")

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching transaction info for {transaction_id} from TronGrid: {e}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching transaction info for {transaction_id}: {e}")
            return False

        # 2. Get current block number (latest solidified block)
        # Using /wallet/getnowblock as it's commonly available for current block info
        # Some APIs use /walletsolidity/getnowblock for the latest solidified block
        # We'll try /wallet/getnowblock first.
        current_block_url = f"{TRONGRID_API_BASE_URL}/wallet/getnowblock"
        try:
            response_current_block = requests.post(current_block_url, headers=headers, json={}, timeout=10) # Empty payload for getnowblock
            response_current_block.raise_for_status()
            current_block_data = response_current_block.json()
            
            if 'block_header' not in current_block_data or \
               'raw_data' not in current_block_data['block_header'] or \
               'number' not in current_block_data['block_header']['raw_data']:
                logger.error("Could not parse current block number from TronGrid response.")
                return False
            
            current_block_number = current_block_data['block_header']['raw_data']['number']
            logger.info(f"Current solidified block number on TronGrid: {current_block_number}.")

        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching current block number from TronGrid: {e}")
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching current block number: {e}")
            return False

        # 3. Calculate confirmations
        confirmations = (current_block_number - transaction_block_number) + 1
        logger.info(f"Transaction {transaction_id} has {confirmations} confirmations.")

        return confirmations >= required_confirmations


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
