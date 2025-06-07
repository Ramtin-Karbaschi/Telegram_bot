import json
from database.queries import DatabaseQueries

class UserAction:
    @staticmethod
    def log_user_action(telegram_id: int, action_type: str, details: dict = None, user_db_id: int = None) -> bool:
        """
        Logs a user action to the database.

        Args:
            telegram_id: The Telegram ID of the user.
            action_type: A string describing the type of action (e.g., 'crypto_payment_request').
            details: An optional dictionary containing additional details about the action.
                     This will be stored as a JSON string.
            user_db_id: Optional. The internal database ID (primary key) of the user from the 'users' table.

        Returns:
            True if the log was successfully added, False otherwise.
        """
        details_json = None
        if details is not None:
            try:
                details_json = json.dumps(details)
            except TypeError as e:
                print(f"Error serializing details to JSON for user {telegram_id}, action {action_type}: {e}")
                # Optionally, log a simplified version or skip details
                details_json = json.dumps({'error': 'Failed to serialize details'})

        # Attempt to get user_db_id if not provided and user exists
        # This might be redundant if the caller is expected to provide it when available.
        # For now, we rely on the caller to pass user_db_id if known.
        # if user_db_id is None:
        #     user_record = DatabaseQueries.get_user_details(telegram_id) # Assuming get_user_details uses telegram_id
        #     if user_record and 'id' in user_record: # Check if 'id' is the PK column name
        #         user_db_id = user_record['id']

        success = DatabaseQueries.add_user_activity_log(
            telegram_id=telegram_id,
            action_type=action_type,
            details=details_json,
            user_id=user_db_id
        )

        if not success:
            print(f"Failed to log user action for telegram_id {telegram_id}, action_type {action_type}")
            # Potentially raise an exception or handle more robustly

        return success

# Example usage (for testing purposes, normally called from handlers):
# if __name__ == '__main__':
#     # Ensure database and tables are initialized first
#     # DatabaseQueries.init_database()
#     # Test logging
#     # Log an action for a user who might not be in the 'users' table yet, or we don't have their db id
#     UserAction.log_user_action(telegram_id=123456789, action_type='bot_start', details={'entry_point': '/start'})
#     # Log an action for a known user (assuming user_db_id 1 exists for telegram_id 987654321)
#     UserAction.log_user_action(telegram_id=987654321, user_db_id=1, action_type='profile_view', details={'profile_section': 'main'})
