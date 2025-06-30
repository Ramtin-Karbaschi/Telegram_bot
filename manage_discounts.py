import argparse
import sys
import os
from datetime import datetime

# Add project root to path to allow imports
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from database.queries import DatabaseQueries

def create_discount(args):
    """Handler to create a new discount code."""
    start_date = args.start_date if args.start_date else None
    end_date = args.end_date if args.end_date else None
    max_uses = args.max_uses if args.max_uses else None

    # For 100% discount, value is 100 if type is 'percentage'
    value = 100 if args.percentage_100 else args.value
    discount_type = 'percentage' if args.percentage_100 else args.type

    discount_id = DatabaseQueries.create_discount(
        code=args.code,
        discount_type=discount_type,
        value=value,
        start_date=start_date,
        end_date=end_date,
        max_uses=max_uses,
        is_active=True
    )

    if discount_id:
        print(f"Successfully created discount '{args.code}' with ID: {discount_id}")
        if args.plans:
            for plan_id in args.plans:
                if DatabaseQueries.assign_discount_to_plan(discount_id, plan_id):
                    print(f"- Successfully assigned to plan ID: {plan_id}")
                else:
                    print(f"- Failed to assign to plan ID: {plan_id}")
    else:
        print(f"Failed to create discount '{args.code}'.")

def list_discounts(args):
    """Handler to list all existing discounts."""
    discounts = DatabaseQueries.get_all_discounts()
    if not discounts:
        print("No discounts found.")
        return

    print("{:<5} {:<20} {:<12} {:<10} {:<10} {:<10} {:<10}".format(
        'ID', 'Code', 'Type', 'Value', 'Active', 'Uses', 'Max Uses'
    ))
    print("-" * 80)
    for d in discounts:
        status = 'Yes' if d['is_active'] else 'No'
        max_uses = d['max_uses'] if d['max_uses'] is not None else 'N/A'
        print("{:<5} {:<20} {:<12} {:<10} {:<10} {:<10} {:<10}".format(
            d['id'], d['code'], d['type'], d['value'], status, d['uses_count'], max_uses
        ))

def toggle_discount(args):
    """Handler to activate or deactivate a discount."""
    new_status = args.status == 'activate'
    if DatabaseQueries.toggle_discount_status(args.id, new_status):
        print(f"Successfully set discount ID {args.id} to {'active' if new_status else 'inactive'}.")
    else:
        print(f"Failed to update status for discount ID {args.id}.")

def assign_plan(args):
    """Handler to assign a discount to a plan."""
    if DatabaseQueries.assign_discount_to_plan(args.discount_id, args.plan_id):
        print(f"Successfully assigned discount ID {args.discount_id} to plan ID {args.plan_id}.")
    else:
        print(f"Failed to assign discount. It might already be assigned.")

def list_plans(args):
    """Handler to list all available plans."""
    plans = DatabaseQueries.get_all_plans()
    if not plans:
        print("No plans found.")
        return
    print("{:<5} {:<30} {:<10}".format('ID', 'Name', 'Price'))
    print("-" * 50)
    for plan in plans:
        print("{:<5} {:<30} {:<10}".format(plan['id'], plan['name'], plan['price']))


def main():
    parser = argparse.ArgumentParser(description="Discount Management CLI for Daraei Academy Bot")
    subparsers = parser.add_subparsers(dest='command', required=True)

    # 'create' command
    p_create = subparsers.add_parser('create', help='Create a new discount code.')
    p_create.add_argument('code', type=str, help='The unique discount code (e.g., FREE_ACCESS).')
    p_create.add_argument('--type', type=str, default='percentage', choices=['percentage', 'fixed'], help='Type of discount.')
    p_create.add_argument('--value', type=float, help='Value of the discount (e.g., 20 for 20%). Required if not --percentage-100.')
    p_create.add_argument('--percentage-100', action='store_true', help='Create a 100% discount for free access.')
    p_create.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format.')
    p_create.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format.')
    p_create.add_argument('--max-uses', type=int, help='Maximum number of uses.')
    p_create.add_argument('--plans', nargs='+', type=int, help='List of plan IDs to assign this discount to.')
    p_create.set_defaults(func=create_discount)

    # 'list' command
    p_list = subparsers.add_parser('list', help='List all discounts.')
    p_list.set_defaults(func=list_discounts)

    # 'toggle' command
    p_toggle = subparsers.add_parser('toggle', help='Activate or deactivate a discount.')
    p_toggle.add_argument('id', type=int, help='The ID of the discount to toggle.')
    p_toggle.add_argument('status', type=str, choices=['activate', 'deactivate'], help='Set status to active or inactive.')
    p_toggle.set_defaults(func=toggle_discount)

    # 'assign' command
    p_assign = subparsers.add_parser('assign', help='Assign a discount to a plan.')
    p_assign.add_argument('discount_id', type=int, help='The ID of the discount.')
    p_assign.add_argument('plan_id', type=int, help='The ID of the plan.')
    p_assign.set_defaults(func=assign_plan)

    # 'list-plans' command
    p_list_plans = subparsers.add_parser('list-plans', help='List all available subscription plans.')
    p_list_plans.set_defaults(func=list_plans)

    args = parser.parse_args()
    
    # Ensure value is provided if not a 100% discount
    if args.command == 'create' and not args.percentage_100 and args.value is None:
        parser.error('--value is required unless --percentage-100 is used.')

    args.func(args)

if __name__ == '__main__':
    main()
