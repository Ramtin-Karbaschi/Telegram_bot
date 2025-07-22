#!/usr/bin/env python3

from database.altseason_queries import AltSeasonQueries

db = AltSeasonQueries()

print('=== Questions ===')
questions = db.list_questions()
for q in questions:
    print(f'Q{q["question_order"]}: {q["title"]} (ID: {q["id"]})')

print('\n=== Videos ===')  
videos = db.list_videos()
for v in videos:
    file_id_short = v["telegram_file_id"][:20] + "..." if v["telegram_file_id"] else "None"
    print(f'V{v["video_order"]}: {v["title"]} (ID: {v["id"]}) - FileID: {file_id_short}')

print('\n=== All Items Ordered ===')
all_items = db.get_all_items_ordered()
for i, item in enumerate(all_items):
    print(f'{i+1}. Order {item["item_order"]}: {item["item_type"]} - {item["title"]} (ID: {item["id"]})')

print(f'\nTotal items: {len(all_items)}')
