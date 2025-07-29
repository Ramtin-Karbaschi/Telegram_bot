"""
🔍 پیدا کردن فراخوانی‌های نادرست safe_edit_message_text
"""

import re
import os

def find_incorrect_safe_edit_calls():
    """پیدا کردن فراخوانی‌های نادرست"""
    
    payment_file = "handlers/payment/payment_handlers.py"
    
    if not os.path.exists(payment_file):
        print(f"❌ File not found: {payment_file}")
        return
    
    with open(payment_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print("🔍 Scanning for incorrect safe_edit_message_text calls...")
    print("=" * 60)
    
    incorrect_calls = []
    in_safe_edit_call = False
    current_call_start = 0
    
    for i, line in enumerate(lines, 1):
        line_stripped = line.strip()
        
        # Check if this line starts a safe_edit_message_text call
        if 'await safe_edit_message_text(' in line:
            in_safe_edit_call = True
            current_call_start = i
            
            # Check if the first argument appears to be a string (starts with quote)
            after_paren = line.split('await safe_edit_message_text(')[1]
            first_arg = after_paren.strip()
            
            # If it starts with a quote, it's likely incorrect
            if first_arg.startswith('"') or first_arg.startswith("'"):
                incorrect_calls.append({
                    'line_num': i,
                    'line_content': line.strip(),
                    'type': 'string_first_arg'
                })
                print(f"❌ Line {i}: String as first argument")
                print(f"   {line.strip()}")
                
        # Check for calls that don't have query.message as first arg
        elif in_safe_edit_call and ')' in line:
            in_safe_edit_call = False
    
    # Also look for specific patterns that are definitely wrong
    wrong_patterns = [
        'safe_edit_message_text(f"',
        'safe_edit_message_text("',
        "safe_edit_message_text('",
        'safe_edit_message_text(PAYMENT_ERROR_MESSAGE',
    ]
    
    for i, line in enumerate(lines, 1):
        for pattern in wrong_patterns:
            if pattern in line:
                incorrect_calls.append({
                    'line_num': i,
                    'line_content': line.strip(),
                    'type': 'wrong_pattern',
                    'pattern': pattern
                })
                print(f"❌ Line {i}: Wrong pattern '{pattern}'")
                print(f"   {line.strip()}")
    
    print(f"\n📊 Summary: Found {len(incorrect_calls)} problematic calls")
    
    if incorrect_calls:
        print("\n🔧 These need to be fixed:")
        for call in incorrect_calls:
            print(f"  • Line {call['line_num']}: {call['type']}")
    else:
        print("✅ No obvious problems found!")
    
    return incorrect_calls

if __name__ == "__main__":
    find_incorrect_safe_edit_calls()
