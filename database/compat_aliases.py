"""Compatibility aliases for DatabaseQueries static convenience methods.

This small module patches the DatabaseQueries class so that legacy code which
calls `DatabaseQueries.user_exists(user_id)` or
`DatabaseQueries.is_registered(user_id)` without instantiating the class keeps
working.  Importing this module once (e.g., in bot entrypoint) is enough.
"""
from database.queries import DatabaseQueries  # pylint: disable=wrong-import-position

# Assign staticmethods as class-level callables for backward compatibility
DatabaseQueries.user_exists = staticmethod(DatabaseQueries.user_exists_static)
DatabaseQueries.is_registered = staticmethod(DatabaseQueries.is_registered_static)

# Safe convenience wrappers to let code call certain methods at class-level
# without instantiating DatabaseQueries. We capture the ORIGINAL instance
# methods before wrapping to avoid recursion.
# and call the corresponding instance methods.

def _with_instance(fn_name):
    def _wrapper(*args, **kwargs):
        from database.models import Database  # local import to avoid circular
        db = Database()
        try:
            dq = DatabaseQueries(db)
            return getattr(dq, fn_name)(*args, **kwargs)
        finally:
            if db.conn:
                db.close()
    return _wrapper

from database.models import Database

# Capture originals
_orig_add_user = DatabaseQueries.add_user
_orig_update_user_profile = DatabaseQueries.update_user_profile
_orig_update_user_activity = DatabaseQueries.update_user_activity
_orig_get_user_details = DatabaseQueries.get_user_details
_orig_search_users = DatabaseQueries.search_users

def _wrapper(func):
    def _inner(*args, **kwargs):
        db = Database()
        try:
            dq = DatabaseQueries(db)
            return func(dq, *args, **kwargs)
        finally:
            if db.conn:
                db.close()
    return _inner

DatabaseQueries.add_user = staticmethod(_wrapper(_orig_add_user))
DatabaseQueries.update_user_profile = staticmethod(_wrapper(_orig_update_user_profile))
DatabaseQueries.update_user_activity = staticmethod(_wrapper(_orig_update_user_activity))
DatabaseQueries.get_user_details = staticmethod(_wrapper(_orig_get_user_details))
DatabaseQueries.search_users = staticmethod(_wrapper(_orig_search_users))
