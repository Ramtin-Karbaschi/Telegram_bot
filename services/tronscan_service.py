# services/tronscan_service.py

import logging
import time
import requests
from datetime import datetime, timedelta
from database.models import Database
import config

logger = logging.getLogger(__name__)

# Constants for TronScan API
USDT_DECIMALS = 6
USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

class TronScanService:
    """سرویس کامل تایید پرداخت‌های تتری با استفاده از TronScan API
    
    ویژگی‌های کلیدی:
    - جستجوی خودکار تراکنش‌ها در بلاک‌چین
    - تایید 100% خودکار برای Trust Wallet
    - پشتیبانی از مبالغ دقیق و tolerance
    - امنیت بالا و جلوگیری از تقلب
    """
    
    ENDPOINT = "https://apilist.tronscanapi.com"
    
    @staticmethod
    def verify_payment_by_hash(tx_hash: str, min_amount: float, wallet_address: str) -> tuple[bool, float]:
        """تایید پرداخت با TX hash ارائه شده توسط کاربر"""
        
        if not (tx_hash and wallet_address and min_amount > 0):
            return False, 0.0
        
        # بررسی تکراری نبودن TX hash
        db = Database()
        if db.get_crypto_payment_by_transaction_id(tx_hash):
            logger.warning(f"Duplicate TX hash used: {tx_hash}")
            return False, 0.0
        
        try:
            headers = {"TRON-PRO-API-KEY": config.TRONSCAN_API_KEY} if getattr(config, "TRONSCAN_API_KEY", None) else {}
            
            # دریافت اطلاعات تراکنش
            url = f"{TronScanService.ENDPOINT}/api/transaction-info"
            params = {"hash": tx_hash}
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if not data or "contractRet" not in data:
                logger.info(f"Transaction {tx_hash} not found or invalid")
                return False, 0.0
            
            # بررسی موفقیت تراکنش
            if data.get("contractRet") != "SUCCESS":
                logger.info(f"Transaction {tx_hash} failed on-chain")
                return False, 0.0
            
            # بررسی تایید کافی (اختیاری)
            confirmations = data.get("confirmed", True)
            if not confirmations:
                logger.info(f"Transaction {tx_hash} not confirmed yet")
                return False, 0.0
            
            # بررسی سن تراکنش (حداکثر 24 ساعت)
            tx_timestamp = data.get("block_timestamp", 0) / 1000
            current_time = time.time()
            max_age_hours = getattr(config, "MAX_TX_AGE_HOURS", 24)
            
            if current_time - tx_timestamp > max_age_hours * 3600:
                logger.info(f"Transaction {tx_hash} too old")
                return False, 0.0
            
            # بررسی Transfer events برای USDT
            trc20_transfers = data.get("trc20TransferInfo", [])
            
            for transfer in trc20_transfers:
                contract_address = transfer.get("contract_address", "")
                to_address = transfer.get("to_address", "")
                amount_str = transfer.get("amount_str", "0")
                
                # بررسی کنترکت USDT و آدرس مقصد
                if (contract_address == USDT_TRC20_CONTRACT and 
                    to_address == wallet_address):
                    
                    try:
                        # محاسبه مبلغ USDT
                        raw_amount = int(amount_str)
                        usdt_amount = raw_amount / (10 ** USDT_DECIMALS)
                        
                        if usdt_amount >= min_amount:
                            logger.info(f"Valid payment: {usdt_amount:.6f} USDT in TX {tx_hash}")
                            TronScanService._log_verification(tx_hash, "success", min_amount, wallet_address, usdt_amount)
                            return True, usdt_amount
                        else:
                            logger.info(f"Insufficient amount: {usdt_amount:.6f} < {min_amount} USDT")
                            
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error parsing amount in TX {tx_hash}: {e}")
                        continue
            
            logger.info(f"No matching USDT transfer found in TX {tx_hash}")
            TronScanService._log_verification(tx_hash, "no_match", min_amount, wallet_address)
            return False, 0.0
            
        except requests.RequestException as e:
            logger.error(f"TronScan API error for TX {tx_hash}: {e}")
            return False, 0.0
        except Exception as e:
            logger.error(f"Unexpected error verifying TX {tx_hash}: {e}")
            return False, 0.0
    
    @staticmethod
    def search_payments_by_amount(wallet_address: str, expected_amount: float, 
                                 from_time: datetime, to_time: datetime) -> list[tuple[str, float]]:
        """جستجوی خودکار در بلاک‌چین برای پرداخت‌های مطابق با مبلغ مورد انتظار"""
        
        if not wallet_address or expected_amount <= 0:
            return []
        
        # محاسبه محدوده مبلغ قابل قبول (± 5% tolerance)
        db = Database()
        tolerance_percent = float(db.get_setting("crypto_tolerance_percent", "5.0"))
        min_amount = expected_amount * (1 - tolerance_percent / 100)
        max_amount = expected_amount * (1 + tolerance_percent / 100)
        
        logger.info(f"Searching USDT transfers to {wallet_address}, amount range: {min_amount:.6f}-{max_amount:.6f}")
        
        try:
            headers = {"TRON-PRO-API-KEY": config.TRONSCAN_API_KEY} if getattr(config, "TRONSCAN_API_KEY", None) else {}
            
            # تبدیل datetime به timestamp میلی‌ثانیه
            start_timestamp = int(from_time.timestamp() * 1000)
            end_timestamp = int(to_time.timestamp() * 1000)
            
            # جستجو در تراکنش‌های TRC20 ورودی
            url = f"{TronScanService.ENDPOINT}/api/token_trc20/transfers"
            params = {
                "toAddress": wallet_address,
                "contract_address": USDT_TRC20_CONTRACT,
                "start_timestamp": start_timestamp,
                "end_timestamp": end_timestamp,
                "limit": 50,
                "sort": "-timestamp"
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
            
            transfers = data.get("token_transfers", [])
            matched_transactions = []
            
            for transfer in transfers:
                try:
                    # محاسبه مبلغ USDT
                    amount_str = transfer.get("amount_str", "0")
                    raw_amount = int(amount_str)
                    usdt_amount = raw_amount / (10 ** USDT_DECIMALS)
                    
                    # بررسی مبلغ در محدوده قابل قبول
                    if min_amount <= usdt_amount <= max_amount:
                        tx_hash = transfer.get("transaction_id")
                        if tx_hash:
                            # بررسی که این TX قبلاً استفاده نشده
                            if not db.get_crypto_payment_by_transaction_id(tx_hash):
                                # تایید نهایی تراکنش
                                verified, verified_amount = TronScanService.verify_payment_by_hash(
                                    tx_hash, min_amount, wallet_address
                                )
                                if verified:
                                    matched_transactions.append((tx_hash, verified_amount))
                                    logger.info(f"Auto-matched TX: {tx_hash} with {verified_amount:.6f} USDT")
                
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Error parsing transfer data: {e}")
                    continue
            
            return matched_transactions
            
        except Exception as e:
            logger.error(f"Error searching payments: {e}")
            return []
    
    @staticmethod
    def get_address_balance(wallet_address: str) -> float:
        """دریافت موجودی USDT کیف پول"""
        try:
            headers = {"TRON-PRO-API-KEY": config.TRONSCAN_API_KEY} if getattr(config, "TRONSCAN_API_KEY", None) else {}
            
            url = f"{TronScanService.ENDPOINT}/api/account/tokens"
            params = {
                "address": wallet_address,
                "start": 0,
                "limit": 20
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            tokens = data.get("data", [])
            for token in tokens:
                if token.get("tokenId") == USDT_TRC20_CONTRACT:
                    balance_str = token.get("balance", "0")
                    raw_balance = int(balance_str)
                    usdt_balance = raw_balance / (10 ** USDT_DECIMALS)
                    return usdt_balance
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting wallet balance: {e}")
            return 0.0
    
    @staticmethod
    async def get_transaction_info(tx_hash: str) -> dict:
        """دریافت اطلاعات کامل تراکنش برای تایید پیشرفته"""
        try:
            headers = {"TRON-PRO-API-KEY": config.TRONSCAN_API_KEY} if getattr(config, "TRONSCAN_API_KEY", None) else {}
            
            url = f"{TronScanService.ENDPOINT}/api/transaction-info"
            params = {"hash": tx_hash}
            
            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                return None
            
            # استخراج اطلاعات مورد نیاز برای تحلیل امنیتی
            result = {
                'contractRet': data.get('contractRet', 'UNKNOWN'),
                'timestamp': data.get('block_timestamp', 0),
                'confirmations': 1 if data.get('confirmed', False) else 0,
                'amount': 0,  # Will be filled from TRC20 transfers
                'to_address': '',  # Will be filled from TRC20 transfers
                'from_address': data.get('ownerAddress', ''),
                'block_number': data.get('blockNumber', 0)
            }
            
            # استخراج Transfer های USDT
            trc20_transfers = data.get("trc20TransferInfo", [])
            for transfer in trc20_transfers:
                if transfer.get("contract_address") == USDT_TRC20_CONTRACT:
                    try:
                        raw_amount = int(transfer.get("amount_str", "0"))
                        # Keep raw amount for precise calculations
                        result['amount'] = raw_amount
                        result['to_address'] = transfer.get("to_address", "")
                        break
                    except (ValueError, TypeError):
                        continue
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting transaction info for {tx_hash}: {e}")
            return None
    
    @staticmethod
    def get_transaction_status(tx_hash: str) -> dict:
        """دریافت وضعیت کامل یک تراکنش"""
        try:
            headers = {"TRON-PRO-API-KEY": config.TRONSCAN_API_KEY} if getattr(config, "TRONSCAN_API_KEY", None) else {}
            
            url = f"{TronScanService.ENDPOINT}/api/transaction-info"
            params = {"hash": tx_hash}
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                return {"status": "not_found"}
            
            status_info = {
                "status": "success" if data.get("contractRet") == "SUCCESS" else "failed",
                "confirmed": data.get("confirmed", False),
                "block_number": data.get("blockNumber", 0),
                "timestamp": data.get("block_timestamp", 0),
                "from_address": data.get("ownerAddress", ""),
                "usdt_transfers": []
            }
            
            # استخراج اطلاعات Transfer های USDT
            trc20_transfers = data.get("trc20TransferInfo", [])
            for transfer in trc20_transfers:
                if transfer.get("contract_address") == USDT_TRC20_CONTRACT:
                    try:
                        raw_amount = int(transfer.get("amount_str", "0"))
                        usdt_amount = raw_amount / (10 ** USDT_DECIMALS)
                        
                        status_info["usdt_transfers"].append({
                            "from": transfer.get("from_address", ""),
                            "to": transfer.get("to_address", ""),
                            "amount": usdt_amount
                        })
                    except (ValueError, TypeError):
                        continue
            
            return status_info
            
        except Exception as e:
            logger.error(f"Error getting transaction status: {e}")
            return {"status": "error", "message": str(e)}
    
    @staticmethod
    def _log_verification(tx_hash: str, status: str, min_amount: float, wallet_address: str, actual_amount: float = 0.0):
        """ثبت لاگ تلاش‌های تایید برای audit"""
        try:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "tx_hash": tx_hash,
                "status": status,
                "expected_amount": min_amount,
                "actual_amount": actual_amount,
                "wallet_address": wallet_address,
                "service": "tronscan"
            }
            logger.info(f"Payment verification: {log_entry}")
        except Exception as e:
            logger.warning(f"Failed to log verification attempt: {e}")
