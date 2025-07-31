"""
🔧 پچ کردن منوی اصلی برای اضافه کردن دکمه تبلیغاتی
"""

import re

def patch_main_menu_keyboard():
    """پچ کردن فایل keyboard برای اضافه کردن دکمه تبلیغاتی"""
    
    file_path = "utils/keyboards/__init__.py"
    
    # خواندن فایل
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # پچ اول: در get_main_reply_keyboard
    old_altseason_code = """        # AltSeason feature button
        try:
            from database.altseason_queries import AltSeasonQueries
            if AltSeasonQueries().is_enabled():
                keyboard_buttons.insert(0, [KeyboardButton(constants.TEXT_MAIN_MENU_ALTSEASON)])
        except Exception as e:
            logger.error(f"Unable to add AltSeason button: {e}")"""
    
    new_altseason_code = """        # Special buttons row (AltSeason + Promotional)
        special_buttons_row = []
        
        # AltSeason feature button
        try:
            from database.altseason_queries import AltSeasonQueries
            if AltSeasonQueries().is_enabled():
                special_buttons_row.append(KeyboardButton(constants.TEXT_MAIN_MENU_ALTSEASON))
        except Exception as e:
            logger.error(f"Unable to add AltSeason button: {e}")
        
        # Promotional category button
        try:
            from utils.promotional_category_utils import get_promotional_category_button
            promo_button = get_promotional_category_button()
            if promo_button:
                special_buttons_row.append(promo_button)
        except Exception as e:
            logger.error(f"Unable to add promotional category button: {e}")
        
        # Add special buttons row if it has any buttons
        if special_buttons_row:
            keyboard_buttons.insert(0, special_buttons_row)"""
    
    # اعمال پچ
    if old_altseason_code in content:
        content = content.replace(old_altseason_code, new_altseason_code)
        print("✅ Patch 1 applied: get_main_reply_keyboard")
    else:
        print("❌ Patch 1 not found in get_main_reply_keyboard")
    
    # پچ دوم: در get_main_menu_keyboard (inline version)
    old_inline_code = """            *( [InlineKeyboardButton(constants.TEXT_MAIN_MENU_ALTSEASON, callback_data="altseason_flow")] if __import__('database.altseason_queries', fromlist=['AltSeasonQueries']).AltSeasonQueries().is_enabled() else [] ), InlineKeyboardButton("📊 جایگاه صف رایگان", callback_data="freepkg_queue_pos")"""
    
    new_inline_code = """            *( [InlineKeyboardButton(constants.TEXT_MAIN_MENU_ALTSEASON, callback_data="altseason_flow")] if __import__('database.altseason_queries', fromlist=['AltSeasonQueries']).AltSeasonQueries().is_enabled() else [] ),
            *( [InlineKeyboardButton(promo_text, callback_data=f"products_menu_{promo_cat}")] if (lambda: (
                (promo_status := __import__('handlers.admin_promotional_category', fromlist=['PromotionalCategoryManager']).PromotionalCategoryManager.get_promotional_category_status()),
                promo_text := promo_status.get('button_text'),
                promo_cat := promo_status.get('category_id'),
                promo_status.get('enabled') and promo_text and promo_cat
            )[3])() else [] ),
            InlineKeyboardButton("📊 جایگاه صف رایگان", callback_data="freepkg_queue_pos")"""
    
    if old_inline_code in content:
        content = content.replace(old_inline_code, new_inline_code)
        print("✅ Patch 2 applied: get_main_menu_keyboard inline version")
    else:
        print("❌ Patch 2 not found - checking for alternative pattern")
        
        # جستجوی pattern دیگری
        pattern = r'(\*\(\s*\[InlineKeyboardButton\(constants\.TEXT_MAIN_MENU_ALTSEASON.*?\]\s*.*?\).*?)(InlineKeyboardButton\("📊 جایگاه صف رایگان")'
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(
                pattern,
                r'\1*( [InlineKeyboardButton(promo_text, callback_data=f"products_menu_{promo_cat}")] if (lambda: ((promo_status := __import__(\'handlers.admin_promotional_category\', fromlist=[\'PromotionalCategoryManager\']).PromotionalCategoryManager.get_promotional_category_status()), promo_text := promo_status.get(\'button_text\'), promo_cat := promo_status.get(\'category_id\'), promo_status.get(\'enabled\') and promo_text and promo_cat)[3])() else [] ), \2',
                content,
                flags=re.DOTALL
            )
            print("✅ Patch 2 applied with regex")
        else:
            print("❌ Patch 2 pattern not found")
    
    # ذخیره فایل
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"📁 File patched: {file_path}")

if __name__ == "__main__":
    patch_main_menu_keyboard()
    print("🎯 Main menu keyboard patching completed!")
