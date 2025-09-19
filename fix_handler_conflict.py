#!/usr/bin/env python3
"""
اصلاح تداخل handler ها
"""

import re

# خواندن فایل
file_path = r"c:\Users\ramti\Documents\GitHub\Telegram_bot\handlers\admin_menu_handlers.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# کامنت کردن conversation handler قدیمی برای invite links
# ابتدا پیدا کردن خط شروع و پایان
pattern = r'(        # Conversation handler for creating invite links\s*\n.*?handlers\.append\(invite_link_conv_handler\))'

def comment_out_block(match):
    block = match.group(1)
    lines = block.split('\n')
    commented_lines = []
    for line in lines:
        if line.strip():
            commented_lines.append('        # ' + line.lstrip())
        else:
            commented_lines.append(line)
    return '\n'.join(commented_lines)

# اعمال تغییرات
new_content = re.sub(pattern, comment_out_block, content, flags=re.DOTALL)

# نوشتن فایل
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("✅ handler قدیمی کامنت شد")

# اصلاح handler های مرتبط در admin_menu_handlers.py
# همچنین باید متدهای قدیمی را به حالت stub تبدیل کنیم
