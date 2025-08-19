#!/usr/bin/env python3
"""
Test script to verify sales message formatting
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import jdatetime
from datetime import datetime

# Mock USDT rate for testing
MOCK_USDT_RATE = 66000  # تومان

def format_sales_message(payment_method: str, payment_amount: float, plan_name: str, user_display: str, use_rate: bool = True):
    """Format a sales message based on payment method"""
    
    # Get current Persian date
    try:
        persian_date = jdatetime.datetime.now().strftime("%Y/%m/%d")
    except Exception:
        persian_date = "تاریخ نامشخص"
    
    pm_lower = payment_method.lower()
    
    if pm_lower in ["rial", "zarinpal"]:
        # Rial payment
        price_formatted = f"{int(payment_amount):,} تومان"
        purchase_tag = "#خرید_نقدی"
        
    elif pm_lower in ["crypto", "tether", "usdt"]:
        # Crypto/Tether payment
        price_formatted = f"{payment_amount:.2f} تتر"
        purchase_tag = "#خرید_تتری"
        
        # Calculate rial equivalent
        if use_rate and MOCK_USDT_RATE > 0:
            rial_equivalent = int(payment_amount * MOCK_USDT_RATE)
            price_formatted = f"{payment_amount:.2f} تتر (معادل {rial_equivalent:,} تومان)"
            
    elif payment_amount == 0 or pm_lower in ["free", "رایگان"]:
        # Free plan
        price_formatted = "رایگان"
        purchase_tag = "#خرید_رایگان"
        
    else:
        # Unknown payment method
        price_formatted = f"{payment_amount}"
        purchase_tag = "#خرید"
    
    # Format the message
    message = (
        f"{purchase_tag}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📅 تاریخ: {persian_date}\n"
        f"👤 کاربر: {user_display}\n"
        f"📦 محصول: {plan_name}\n"
        f"💰 مبلغ: {price_formatted}\n"
        f"━━━━━━━━━━━━━━━"
    )
    
    return message

def test_messages():
    """Test different payment scenarios"""
    
    print("=" * 50)
    print("تست پیام‌های فروش اصلاح شده")
    print("=" * 50)
    
    test_cases = [
        {
            "name": "خرید نقدی (ریالی)",
            "payment_method": "zarinpal",
            "payment_amount": 250000,
            "plan_name": "اشتراک VIP یک ماهه",
            "user_display": "@ramtin_test"
        },
        {
            "name": "خرید با تتر (با معادل ریالی)",
            "payment_method": "tether",
            "payment_amount": 3.78,
            "plan_name": "اشتراک VIP یک ماهه",
            "user_display": "@crypto_buyer"
        },
        {
            "name": "خرید رایگان",
            "payment_method": "free",
            "payment_amount": 0,
            "plan_name": "بسته رایگان آزمایشی",
            "user_display": "ID:123456789"
        },
        {
            "name": "خرید با کریپتو (بدون نرخ)",
            "payment_method": "crypto",
            "payment_amount": 5.5,
            "plan_name": "اشتراک سه ماهه",
            "user_display": "@user_test"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n\n📌 تست شماره {i}: {test_case['name']}")
        print("-" * 40)
        
        # Test with rate
        message = format_sales_message(
            test_case["payment_method"],
            test_case["payment_amount"],
            test_case["plan_name"],
            test_case["user_display"],
            use_rate=True
        )
        print(message)
        
        # For crypto, also test without rate
        if test_case["payment_method"] in ["tether", "crypto", "usdt"]:
            print("\n⚠️ حالت بدون نرخ ارز:")
            message_no_rate = format_sales_message(
                test_case["payment_method"],
                test_case["payment_amount"],
                test_case["plan_name"],
                test_case["user_display"],
                use_rate=False
            )
            print(message_no_rate)
    
    print("\n" + "=" * 50)
    print("✅ تست‌ها با موفقیت انجام شد")
    print("=" * 50)
    
    # Show sample calculations
    print("\n💡 نمونه محاسبات:")
    print(f"- نرخ تتر فرضی: {MOCK_USDT_RATE:,} تومان")
    print(f"- 3.78 تتر = {int(3.78 * MOCK_USDT_RATE):,} تومان")
    print(f"- 5.5 تتر = {int(5.5 * MOCK_USDT_RATE):,} تومان")

if __name__ == "__main__":
    test_messages()
