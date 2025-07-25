import sqlite3
from typing import Optional

# We rely on the Database singleton that already exists in database.models
try:
    from database.models import Database  # type: ignore
except ImportError:
    # Fallback: simple connection based on default path
    import os
    DEFAULT_PATH = os.getenv("BOT_DB_PATH", "database/data/app.db")
    _fallback_conn: Optional[sqlite3.Connection] = None

    def _get_fallback_conn() -> sqlite3.Connection:
        global _fallback_conn
        if _fallback_conn is None:
            _fallback_conn = sqlite3.connect(DEFAULT_PATH, timeout=10, check_same_thread=False)
            _fallback_conn.row_factory = sqlite3.Row
        return _fallback_conn

    def get_db() -> sqlite3.Connection:  # noqa: D401
        """Return a shared SQLite connection (fallback implementation)."""
        return _get_fallback_conn()
else:

    def get_db() -> sqlite3.Connection:  # noqa: D401
        """Return the shared SQLite connection managed by the Database singleton."""
        db_instance = Database.get_instance()
        # Ensure connection is active
        if not db_instance.connect():
            raise RuntimeError("Unable to connect to SQLite database via Database singleton")
        return db_instance.conn
