#!/usr/bin/env python3
"""
اسکریپت تست برای بررسی API TronGrid و تراکنش‌های USDT
"""

import requests
import json
from datetime import datetime

# تنظیمات از فایل .env شما
TRONGRID_API_KEY = "dcc81955-6472-4386-a8d0-c2e4be71f02d"
CRYPTO_WALLET_ADDRESS = "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE"  # آدرس تست معتبر
USDT_TRC20_CONTRACT_ADDRESS = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

def test_trongrid_connection():
    """تست اتصال به TronGrid API"""
    print("🔍 تست اتصال به TronGrid API...")
    print(f"🔑 API Key: {TRONGRID_API_KEY[:8]}...")
    print(f"💼 آدرس: {CRYPTO_WALLET_ADDRESS}")
    
    headers = {
        "TRON-PRO-API-KEY": TRONGRID_API_KEY,
        "Content-Type": "application/json"
    }
    
    # تست اطلاعات اکانت
    url = f"https://api.trongrid.io/v1/accounts/{CRYPTO_WALLET_ADDRESS}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"📡 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ اتصال موفق!")
            print(f"📊 اطلاعات اکانت: {json.dumps(data, indent=2)}")
            return True
        else:
            print(f"❌ خطا: {response.status_code}")
            print(f"📄 پاسخ: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ خطا در اتصال: {e}")
        return False

def get_usdt_transactions():
    """دریافت تراکنش‌های USDT"""
    print(f"\n💰 بررسی تراکنش‌های USDT برای آدرس: {CRYPTO_WALLET_ADDRESS}")
    
    headers = {
        "TRON-PRO-API-KEY": TRONGRID_API_KEY,
        "Content-Type": "application/json"
    }
    
    # دریافت تراکنش‌های TRC20 (USDT)
    url = f"https://api.trongrid.io/v1/accounts/{CRYPTO_WALLET_ADDRESS}/transactions/trc20"
    params = {
        "limit": 10,  # آخرین 10 تراکنش
        "contract_address": USDT_TRC20_CONTRACT_ADDRESS
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            transactions = data.get("data", [])
            
            print(f"📈 تعداد تراکنش‌های یافت شده: {len(transactions)}")
            
            for i, tx in enumerate(transactions, 1):
                print(f"\n--- تراکنش {i} ---")
                print(f"🆔 Transaction ID: {tx.get('transaction_id')}")
                print(f"💵 مقدار: {int(tx.get('value', 0)) / 1000000} USDT")  # تبدیل از wei به USDT
                print(f"📅 زمان: {datetime.fromtimestamp(tx.get('block_timestamp', 0) / 1000)}")
                print(f"📤 از: {tx.get('from')}")
                print(f"📥 به: {tx.get('to')}")
                print(f"✅ تایید شده: {'بله' if tx.get('confirmed') else 'خیر'}")
                
            return transactions
        else:
            print(f"❌ خطا: {response.status_code}")
            print(f"📄 پاسخ: {response.text}")
            return []
            
    except Exception as e:
        print(f"❌ خطا در دریافت تراکنش‌ها: {e}")
        return []

def check_specific_transaction(tx_id):
    """بررسی یک تراکنش خاص"""
    print(f"\n🔍 بررسی تراکنش: {tx_id}")
    
    headers = {
        "TRON-PRO-API-KEY": TRONGRID_API_KEY,
        "Content-Type": "application/json"
    }
    
    url = f"https://api.trongrid.io/v1/transactions/{tx_id}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ تراکنش یافت شد!")
            print(f"📊 جزئیات: {json.dumps(data, indent=2)}")
            return data
        else:
            print(f"❌ تراکنش یافت نشد: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ خطا: {e}")
        return None

def main():
    print("🚀 شروع تست سیستم تاییدیه تراکنش‌های USDT")
    print("=" * 50)
    
    # تست اتصال
    if not test_trongrid_connection():
        print("❌ تست متوقف شد به دلیل مشکل در اتصال")
        return
    
    # دریافت تراکنش‌ها
    transactions = get_usdt_transactions()
    
    # اگر تراکنشی وجود دارد، جزئیات اولین تراکنش را نمایش بده
    if transactions:
        first_tx_id = transactions[0].get('transaction_id')
        if first_tx_id:
            check_specific_transaction(first_tx_id)
    
    print("\n" + "=" * 50)
    print("✅ تست تکمیل شد!")
    print("\n📝 نکات مهم:")
    print("1. اگر هیچ تراکنشی نمایش داده نشد، یعنی هنوز پرداختی به این آدرس نشده")
    print("2. برای تست، می‌توانید مقدار کمی USDT به آدرس خود ارسال کنید")
    print("3. تراکنش‌ها معمولاً ظرف چند دقیقه در API نمایش داده می‌شوند")
    print("4. تعداد تاییدیه‌های فعلی: 20 بلاک (حدود 1 دقیقه)")

if __name__ == "__main__":
    main()
