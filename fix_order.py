#!/usr/bin/env python3

from database.altseason_queries import AltSeasonQueries

db = AltSeasonQueries()

print('=== Current Order Issues ===')
all_items = db.get_all_items_ordered()
for i, item in enumerate(all_items):
    print(f'{i+1}. Order {item["item_order"]}: {item["item_type"]} - {item["title"]} (ID: {item["id"]})')

print('\n=== Fixing Order ===')
# Re-assign sequential order numbers
for i, item in enumerate(all_items, start=1):
    new_order = i
    item_id = item["id"]
    item_type = item["item_type"]
    
    print(f'Setting {item_type} ID {item_id} to order {new_order}')
    db.update_item_order(item_id, item_type, new_order)

print('\n=== Verification ===')
all_items_fixed = db.get_all_items_ordered()
for i, item in enumerate(all_items_fixed):
    print(f'{i+1}. Order {item["item_order"]}: {item["item_type"]} - {item["title"]} (ID: {item["id"]})')

print('\n✅ Order fixed! Now the flow should work properly.')
