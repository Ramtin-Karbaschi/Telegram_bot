"""Unit tests for database.free_plan_helper.ensure_free_plan.

These tests exercise creation and update behaviour of the helper using an
in-memory SQLite database so that the production database file is never
touched.  The `Database` singleton is reset for every test so that each
run is completely isolated.
"""

from __future__ import annotations

import sqlite3

import pytest

import sys, pathlib
# Ensure project root is on the path when tests are executed from sub-directories
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from database import models as db_models
from database.free_plan_helper import ensure_free_plan


def _setup_in_memory_db() -> db_models.Database:
    """Return a Database instance backed by a fresh in-memory SQLite DB.

    The global `db_models._instance` singleton reference is replaced so
    that calls to `Database()` inside the helper pick up the same
    in-memory connection.
    """
    # Reset the singleton before every invocation so we do not carry any
    # state between tests.
    db_models._instance = None

    # Create a new singleton instance that points to :memory:
    db = db_models.Database(":memory:")

    # Establish the schema required by `ensure_free_plan`.
    create_table_sql = """
        CREATE TABLE plans (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            name              TEXT UNIQUE,
            description       TEXT,
            price             REAL,
            original_price_irr REAL,
            days              INTEGER,
            plan_type         TEXT,
            is_active         INTEGER,
            display_order     INTEGER
        )
    """
    db.execute(create_table_sql)
    db.commit()

    return db


@pytest.fixture(autouse=True)
def _isolate_db():
    """Provide each test with a fresh in-memory database."""
    db = _setup_in_memory_db()
    try:
        yield db
    finally:
        # Close the connection explicitly just in case – the singleton's
        # `close()` method is a no-op, but calling commit ensures changes
        # are flushed for inspection before teardown.
        if db.conn is not None:
            db.commit()
            db.conn.close()
        db_models._instance = None  # Reset after test


def test_plan_created_when_missing(_isolate_db):
    """A new 20-day plan is created if none exists."""
    plan_id = ensure_free_plan()
    assert plan_id == 1  # First row should have ID = 1

    db = db_models.Database.get_instance()
    db.execute("SELECT name, days FROM plans WHERE id = ?", (plan_id,))
    name, days = db.fetchone()
    assert name == "free_20d"
    assert days == 20


def test_existing_plan_updated_to_20_days(_isolate_db):
    """An existing plan with a different duration is updated to 20 days."""
    db = db_models.Database.get_instance()
    # Insert a plan with 15-day duration first.
    db.execute(
        """
        INSERT INTO plans (name, description, price, original_price_irr, days, plan_type, is_active, display_order)
        VALUES (?, 'هدیه ۱۵ روزه', 0, 0, 15, 'subscription', 1, 0)
        """,
        ("free_20d",),
    )
    db.commit()

    # Now run the helper – it should update the plan instead of inserting
    # a new one.
    plan_id = ensure_free_plan()
    assert plan_id == 1  # Same row is reused

    db.execute("SELECT days FROM plans WHERE id = ?", (plan_id,))
    (days,) = db.fetchone()
    assert days == 20
