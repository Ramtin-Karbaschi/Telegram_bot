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
        # Ensure we always store something useful in details
        if details is None:
            details = {}
        # Attempt safe JSON serialization
        try:
            details_json = json.dumps(details, ensure_ascii=False, default=str)  # Allow non-ASCII & fallback str
        except TypeError as e:
            # Fallback: stringify the dict
            print(f"Error serializing details to JSON for user {telegram_id}, action {action_type}: {e}")
            details_json = json.dumps({"raw": str(details)[:500]})

        dbq = DatabaseQueries()

        # Auto-resolve user_db_id if missing
        if user_db_id is None:
            try:
                # users.user_id column stores Telegram ID in our schema
                if dbq.user_exists_static(telegram_id):
                    user_db_id = telegram_id
                else:
                    # Minimal insert so FK constraint passes
                    dbq.add_user(telegram_id)
                    user_db_id = telegram_id
            except Exception as fetch_exc:
                print(f"UserAction: could not resolve/save user record for {telegram_id}: {fetch_exc}")

        success = dbq.add_user_activity_log(
            telegram_id=telegram_id,
            action_type=action_type,
            details=details_json,
            user_id=user_db_id,
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
