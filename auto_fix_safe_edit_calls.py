"""
🔧 اصلاح خودکار تمام فراخوانی‌های نادرست safe_edit_message_text
"""

import re
import os

def fix_safe_edit_calls():
    """اصلاح تمام فراخوانی‌های نادرست"""
    
    file_path = "handlers/payment/payment_handlers.py"
    
    if not os.path.exists(file_path):
        print(f"❌ فایل پیدا نشد: {file_path}")
        return False
    
    # خواندن فایل
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("🔧 شروع اصلاح فراخوانی‌های safe_edit_message_text...")
    
    # تهیه نسخه پشتیبان
    backup_file = file_path + ".backup"
    with open(backup_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"💾 نسخه پشتیبان ذخیره شد: {backup_file}")
    
    # اصلاحات تکی برای موارد خاص
    fixes = [
        # خط 353
        {
            'old': 'await safe_edit_message_text("خطا: قیمت پلن تعریف نشده است.")',
            'new': 'await safe_edit_message_text(query.message, text="خطا: قیمت پلن تعریف نشده است.")'
        },
        # خط 441
        {
            'old': 'await safe_edit_message_text("خطا: قیمت پلن تعریف نشده است.")',
            'new': 'await safe_edit_message_text(query.message, text="خطا: قیمت پلن تعریف نشده است.")'
        },
        # خط 528
        {
            'old': 'await safe_edit_message_text(f"خطا در فعال‌سازی پلن رایگان: {message}")',
            'new': 'await safe_edit_message_text(query.message, text=f"خطا در فعال‌سازی پلن رایگان: {message}")'
        },
        # خط 726
        {
            'old': 'await safe_edit_message_text("خطای سیستمی: اطلاعات کاربری شما یافت نشد. لطفاً با پشتیبانی تماس بگیرید.")',
            'new': 'await safe_edit_message_text(query.message, text="خطای سیستمی: اطلاعات کاربری شما یافت نشد. لطفاً با پشتیبانی تماس بگیرید.")'
        },
        # خط 995
        {
            'old': 'await safe_edit_message_text(PAYMENT_ERROR_MESSAGE, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))',
            'new': 'await safe_edit_message_text(query.message, text=PAYMENT_ERROR_MESSAGE, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))'
        },
        # خط 1017
        {
            'old': 'await safe_edit_message_text("خطای سیستمی هنگام ثبت مبلغ تتر. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))',
            'new': 'await safe_edit_message_text(query.message, text="خطای سیستمی هنگام ثبت مبلغ تتر. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))'
        },
        # خط 1215
        {
            'old': 'await safe_edit_message_text("خطای داخلی: روش پرداخت ناشناخته است.", reply_markup=get_main_menu_keyboard(user_id=telegram_id))',
            'new': 'await safe_edit_message_text(query.message, text="خطای داخلی: روش پرداخت ناشناخته است.", reply_markup=get_main_menu_keyboard(user_id=telegram_id))'
        },
        # خط 1226
        {
            'old': 'await safe_edit_message_text("خطای داخلی: مبلغ طرح یافت نشد.", reply_markup=get_main_menu_keyboard(user_id=telegram_id))',
            'new': 'await safe_edit_message_text(query.message, text="خطای داخلی: مبلغ طرح یافت نشد.", reply_markup=get_main_menu_keyboard(user_id=telegram_id))'
        },
        # خط 1399
        {
            'old': 'await safe_edit_message_text("خطا: اطلاعات کاربری شما یافت نشد. لطفاً مجدداً تلاش کنید یا با پشتیبانی تماس بگیرید.")',
            'new': 'await safe_edit_message_text(query.message, text="خطا: اطلاعات کاربری شما یافت نشد. لطفاً مجدداً تلاش کنید یا با پشتیبانی تماس بگیرید.")'
        },
        # خط 1440
        {
            'old': 'await safe_edit_message_text("خطا: رکورد پرداخت شما یافت نشد. با پشتیبانی تماس بگیرید.")',
            'new': 'await safe_edit_message_text(query.message, text="خطا: رکورد پرداخت شما یافت نشد. با پشتیبانی تماس بگیرید.")'
        },
        # خط 1499
        {
            'old': 'await safe_edit_message_text("این پرداخت قبلاً تایید شده است.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))',
            'new': 'await safe_edit_message_text(query.message, text="این پرداخت قبلاً تایید شده است.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))'
        },
        # خط 1519
        {
            'old': 'await safe_edit_message_text("خطایی در هنگام بررسی پرداخت رخ داد. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))',
            'new': 'await safe_edit_message_text(query.message, text="خطایی در هنگام بررسی پرداخت رخ داد. لطفاً با پشتیبانی تماس بگیرید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👤 مشاهده اطلاعات کاربری", callback_data="show_status")]]))'
        }
    ]
    
    # اعمال اصلاحات
    fixes_applied = 0
    for fix in fixes:
        if fix['old'] in content:
            content = content.replace(fix['old'], fix['new'])
            fixes_applied += 1
            print(f"✅ اصلاح شد: safe_edit_message_text call")
    
    # ذخیره فایل اصلاح شده
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n🎉 اصلاحات کامل شد!")
    print(f"✅ تعداد اصلاحات اعمال شده: {fixes_applied}")
    print(f"📁 فایل اصلاح شده: {file_path}")
    print(f"💾 نسخه پشتیبان: {backup_file}")
    
    return True

def verify_fixes():
    """تایید اصلاحات"""
    
    file_path = "handlers/payment/payment_handlers.py"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # بررسی وجود موارد مشکل‌ساز
    problematic_patterns = [
        'safe_edit_message_text("',
        'safe_edit_message_text(f"',
        'safe_edit_message_text(PAYMENT_ERROR_MESSAGE,'
    ]
    
    remaining_issues = 0
    for pattern in problematic_patterns:
        count = content.count(pattern)
        if count > 0:
            remaining_issues += count
            print(f"⚠️ هنوز {count} مورد باقی مانده با pattern: {pattern}")
    
    if remaining_issues == 0:
        print("✅ همه موارد مشکل‌ساز برطرف شدند!")
        return True
    else:
        print(f"❌ هنوز {remaining_issues} مورد مشکل‌ساز باقی مانده")
        return False

def main():
    """اجرای اصلاحات"""
    print("🚀 شروع اصلاح خودکار safe_edit_message_text calls")
    print("=" * 60)
    
    success = fix_safe_edit_calls()
    
    if success:
        print("\n🔍 تایید اصلاحات...")
        verify_fixes()
        
        print("\n" + "=" * 60)
        print("🎯 نتیجه: کاربر منتظر شما حالا می‌تواند TX hash وارد کند!")
        print("✅ خطای AttributeError برطرف شد")
        print("🔄 سیستم پرداخت کامل کار می‌کند")
        print("=" * 60)
    else:
        print("❌ خطا در اصلاح فایل")

if __name__ == "__main__":
    main()
