#!/usr/bin/env python3
"""Test broadcast message flow without buttons"""

import os
import sys
import asyncio
import logging
from unittest.mock import Mock, AsyncMock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from handlers.admin.broadcast_handler import add_select_callback, menu_callback
from telegram import Update, CallbackQuery, Message, User
from telegram.ext import ContextTypes

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_broadcast_without_buttons():
    """Test that broadcast flow works without selecting any buttons"""
    
    print("\n" + "="*50)
    print("Testing Broadcast Without Buttons")
    print("="*50)
    
    # Create mock objects
    update = Mock(spec=Update)
    context = Mock(spec=ContextTypes.DEFAULT_TYPE)
    query = AsyncMock(spec=CallbackQuery)
    user = Mock(spec=User)
    
    # Setup user
    user.id = 123456789  # Admin user ID
    update.effective_user = user
    update.callback_query = query
    query.data = "broadcast_continue"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    
    # Initialize context user_data
    context.user_data = {}
    
    # Test 1: Continue without buttons
    print("\n✅ Test 1: Testing 'Continue' without selecting buttons...")
    context.user_data["broadcast_buttons"] = []  # No buttons selected
    
    with patch('utils.admin_utils.has_broadcast_access', return_value=True):
        await add_select_callback(update, context)
    
    # Check that the message was edited correctly
    assert query.edit_message_text.called, "Message should be edited"
    call_args = query.edit_message_text.call_args
    message_text = call_args[0][0] if call_args[0] else call_args.kwargs.get('text', '')
    
    print(f"Message shown: {message_text}")
    assert "هیچ دکمه‌ای انتخاب نشده" in message_text, "Should show warning about no buttons"
    assert context.user_data.get("bc_waiting_msg") == True, "Should set waiting flag"
    print("✅ Test 1 PASSED: Can continue without buttons")
    
    # Test 2: Continue with buttons
    print("\n✅ Test 2: Testing 'Continue' with buttons selected...")
    query.reset_mock()
    context.user_data["broadcast_buttons"] = [
        {"type": "category", "id": 1, "text": "Test Category"}
    ]
    
    with patch('utils.admin_utils.has_broadcast_access', return_value=True):
        await add_select_callback(update, context)
    
    call_args = query.edit_message_text.call_args
    message_text = call_args[0][0] if call_args[0] else call_args.kwargs.get('text', '')
    
    print(f"Message shown: {message_text}")
    assert "1 دکمه انتخاب شده" in message_text, "Should show button count"
    assert context.user_data.get("bc_waiting_msg") == True, "Should set waiting flag"
    print("✅ Test 2 PASSED: Works with buttons too")
    
    # Test 3: Send broadcast without buttons
    print("\n✅ Test 3: Testing 'Send' without buttons...")
    query.reset_mock()
    query.data = "broadcast_send"
    context.user_data["broadcast_buttons"] = []
    context.user_data["broadcast_text"] = "Test message"
    
    with patch('utils.admin_utils.has_broadcast_access', return_value=True):
        await menu_callback(update, context)
    
    # Should proceed to audience selection
    assert query.edit_message_text.called, "Should show audience selection"
    call_args = query.edit_message_text.call_args
    message_text = call_args[0][0] if call_args[0] else call_args.kwargs.get('text', '')
    
    print(f"Message shown: {message_text}")
    assert "انتخاب مخاطبان" in message_text, "Should show audience selection"
    assert context.user_data.get("bc_in_audience") == True, "Should set audience flag"
    print("✅ Test 3 PASSED: Can send without buttons")
    
    print("\n" + "="*50)
    print("✅ ALL TESTS PASSED!")
    print("Broadcast flow works correctly without buttons")
    print("="*50)

if __name__ == "__main__":
    asyncio.run(test_broadcast_without_buttons())
