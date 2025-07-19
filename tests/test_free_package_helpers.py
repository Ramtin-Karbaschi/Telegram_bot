import sys, pathlib, pytest
# Ensure project root is in sys.path
ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from handlers.free_package.free_package_handlers import _queue_position, _add_to_waitlist
from handlers.admin.free_package_admin_handlers import _build_nav_keyboard, PAGE_SIZE


def test_add_to_waitlist_and_position(tmp_path, monkeypatch):
    """Ensure adding to waitlist returns correct sequential positions."""
    # Patch database access inside helpers to use in-memory sqlite for isolation
    import sqlite3
    import handlers.free_package.free_package_handlers as fph

    # Create in-memory DB and required table
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """CREATE TABLE free_package_waitlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            position INTEGER,
            created_at TEXT
        )"""
    )

    # Monkeypatch global db connection
    # Patch the connection used inside handlers
    # Build a lightweight wrapper mimicking original db with execute/fetchone
    class _DBWrapper:
        def __init__(self, conn):
            self._conn = conn
            self._cursor = conn.cursor()
        def execute(self, *args, **kwargs):
            self._cursor = self._conn.execute(*args, **kwargs)
        def fetchone(self):
            return self._cursor.fetchone()
        def fetchall(self):
            return self._cursor.fetchall()
        def commit(self):
            self._conn.commit()
    monkeypatch.setattr(fph.db, "db", _DBWrapper(conn))

    # Add three different users
    pos1 = _add_to_waitlist(100)
    pos2 = _add_to_waitlist(101)
    pos3 = _add_to_waitlist(102)

    assert (pos1, pos2, pos3) == (1, 2, 3)
    # Existing user keeps same position
    pos1_again = _add_to_waitlist(100)
    assert pos1_again == 1


def test_build_nav_keyboard():
    total_items = 42
    total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE
    # page 0 should only have next button
    kb_first = _build_nav_keyboard("test", 0, total_pages)
    assert any(b.callback_data == "test:1" for row in kb_first.inline_keyboard for b in row)
    # middle page should have both
    kb_mid = _build_nav_keyboard("test", 1, total_pages)
    datas = [b.callback_data for row in kb_mid.inline_keyboard for b in row]
    assert "test:0" in datas and "test:2" in datas
    # last page should only have prev
    kb_last = _build_nav_keyboard("test", total_pages - 1, total_pages)
    assert any(b.callback_data == f"test:{total_pages-2}" for row in kb_last.inline_keyboard for b in row)
