import sqlite3
import json
import logging
from io import BytesIO

DB_PATH = "database/data/app.db"
logger = logging.getLogger(__name__)

def export_database() -> BytesIO | None:
    """
    Connects to the SQLite database, exports all tables to a JSON format,
    and returns it as a BytesIO object.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # Access columns by name
        cursor = conn.cursor()

        # Get a list of all tables in the database
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [table['name'] for table in cursor.fetchall()]

        # Export each table to a dictionary
        db_export = {}
        for table_name in tables:
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            # Convert sqlite3.Row objects to plain dictionaries
            db_export[table_name] = [dict(row) for row in rows]

        # Convert the dictionary to a JSON string
        json_data = json.dumps(db_export, indent=4, ensure_ascii=False, default=str)

        # Create a BytesIO object to send the file directly
        bio = BytesIO()
        bio.write(json_data.encode('utf-8'))
        bio.name = 'db_backup.json'
        bio.seek(0)  # Rewind the buffer to the beginning
        return bio

    except sqlite3.Error as e:
        logger.error(f"Database error during backup: {e}", exc_info=True)
        return None
    finally:
        if 'conn' in locals() and conn:
            conn.close()

"""Utility to export entire SQLite database to a single JSON blob."""

import json
import logging
import sqlite3
from io import BytesIO
from typing import Dict, List, Any

from database.models import Database
from database.schema import ALL_TABLES

logger = logging.getLogger(__name__)


def _table_name_from_sql(create_sql: str) -> str:
    """Extract table name from CREATE TABLE statement."""
    # naive parse: CREATE TABLE IF NOT EXISTS table_name (
    parts = create_sql.split()
    try:
        idx = parts.index("TABLE")
    except ValueError:
        return "unknown"
    # skip IF, NOT, EXISTS optionally
    while parts[idx + 1].upper() in {"IF", "NOT", "EXISTS"}:
        idx += 1
    return parts[idx + 1].strip("`\"")


def export_database() -> BytesIO | None:
    """Return BytesIO containing UTF-8 JSON of full DB or None on failure."""
    db = Database()
    if not db.connect():
        return None

    try:
        db.conn.row_factory = sqlite3.Row  # type: ignore[attr-defined]
        cursor = db.cursor
        data: Dict[str, List[dict[str, Any]]] = {}
        for create_sql in ALL_TABLES:
            table = _table_name_from_sql(create_sql)
            try:
                cursor.execute(f"SELECT * FROM {table}")
                rows = cursor.fetchall()
                data[table] = [dict(row) for row in rows]  # type: ignore[arg-type]
            except sqlite3.Error as exc:
                logger.error("Failed to read table %s: %s", table, exc)
                data[table] = []
        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        return BytesIO(json_bytes)
    finally:
        db.close()
