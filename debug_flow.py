#!/usr/bin/env python3

from database.altseason_queries import AltSeasonQueries

db = AltSeasonQueries()
all_items = db.get_all_items_ordered()

print('=== Flow Simulation ===')
for i, item in enumerate(all_items):
    print(f'Step {i+1}: {item["item_type"]} - {item["title"]} (Order: {item["item_order"]})')
    if item['item_type'] == 'video':
        file_id_short = item["telegram_file_id"][:30] + "..." if item["telegram_file_id"] else "None"
        print(f'  Video file_id: {file_id_short}')
        print(f'  Origin: chat_id={item.get("origin_chat_id")}, msg_id={item.get("origin_message_id")}')

print('\n=== Problem Analysis ===')
print('The issue is that multiple items have the same order number!')
print('This causes unpredictable sorting behavior.')

# Group by order
from collections import defaultdict
by_order = defaultdict(list)
for item in all_items:
    by_order[item["item_order"]].append(item)

for order in sorted(by_order.keys()):
    items = by_order[order]
    if len(items) > 1:
        print(f'⚠️  Order {order} has {len(items)} items:')
        for item in items:
            print(f'   - {item["item_type"]}: {item["title"]} (ID: {item["id"]})')
