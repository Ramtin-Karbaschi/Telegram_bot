#!/usr/bin/env python3

import asyncio
from database.altseason_queries import AltSeasonQueries
from handlers.altseason_handler import AltSeasonHandler

async def test_video_logic():
    db = AltSeasonQueries()
    handler = AltSeasonHandler()
    
    print('=== Testing Video Send Logic ===')
    videos = db.list_videos()
    
    for video in videos:
        print(f'\n--- Testing Video: {video["title"]} ---')
        print(f'File ID: {video["telegram_file_id"]}')
        print(f'Origin Chat: {video.get("origin_chat_id")}')
        print(f'Origin Message: {video.get("origin_message_id")}')
        
        # Test the logic without actually sending
        origin_chat_id = video.get('origin_chat_id')
        origin_message_id = video.get('origin_message_id')
        
        if origin_chat_id and origin_message_id:
            print('✅ Has origin info - would try copy_message first')
        else:
            print('⚠️  No origin info - would try send_video with file_id')
            
        # Check if file_id looks valid
        file_id = video['telegram_file_id']
        if file_id and len(file_id) > 20:
            print('✅ File ID looks valid')
        else:
            print('❌ File ID looks invalid or too short')

if __name__ == '__main__':
    asyncio.run(test_video_logic())
