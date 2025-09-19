"""
Database queries for the Daraei Academy Telegram bot
"""

import sqlite3
from datetime import datetime, timedelta
from database.models import Database
from database.schema import ALL_TABLES
import logging

# Migration to add custom_caption column if missing
# Migration to add origin_chat_id/origin_message_id columns to videos table if missing
def _ensure_custom_caption_column():
    """Ensure custom_caption column exists in plan_videos table."""
    db = Database()
    if not db.connect():
        return False
    
    try:
        cursor = db.conn.cursor()
        # Check if column exists
        cursor.execute("PRAGMA table_info(plan_videos)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'custom_caption' not in columns:
            logging.info("Adding custom_caption column to plan_videos table")
            cursor.execute("ALTER TABLE plan_videos ADD COLUMN custom_caption TEXT")
            db.conn.commit()
            logging.info("Successfully added custom_caption column")
        
        return True
    except Exception as e:
        logging.error(f"Error adding custom_caption column: {e}")
        return False
    finally:
        db.close()

# ---------------------------------------------------------------------------
# Migration to ensure category_id column exists in plans table
# ---------------------------------------------------------------------------

def _ensure_video_origin_columns():
    """Ensure origin_chat_id and origin_message_id columns exist in videos table."""
    db = Database()
    if not db.connect():
        return False
    try:
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(videos)")
        cols = [row[1] for row in cursor.fetchall()]
        added = False
        if 'origin_chat_id' not in cols:
            logging.info("Adding origin_chat_id column to videos table")
            cursor.execute("ALTER TABLE videos ADD COLUMN origin_chat_id INTEGER")
            added = True
        if 'origin_message_id' not in cols:
            logging.info("Adding origin_message_id column to videos table")
            cursor.execute("ALTER TABLE videos ADD COLUMN origin_message_id INTEGER")
            added = True
        if added:
            db.conn.commit()
            logging.info("Successfully ensured origin columns in videos table")
        return True
    except Exception as e:
        logging.error(f"Error ensuring origin columns: {e}")
        return False
    finally:
        db.close()

def _ensure_category_id_column():
    """Ensure category_id column exists in plans table."""
    db = Database()
    if not db.connect():
        return False
    try:
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(plans)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'category_id' not in columns:
            logging.info("Adding category_id column to plans table")
            cursor.execute("ALTER TABLE plans ADD COLUMN category_id INTEGER NULL REFERENCES categories(id)")
            db.conn.commit()
            logging.info("Successfully added category_id column")
        return True
    except Exception as e:
        logging.error(f"Error adding category_id column: {e}")
        return False
    finally:
        db.close()

# ---------------------------------------------------------------------------
# Migration to ensure root category exists
# ---------------------------------------------------------------------------

def _ensure_root_category():
    """Create a root '🛒 محصولات' category if it does not exist."""
    db = Database()
    if not db.connect():
        return False
    try:
        cursor = db.conn.cursor()
        cursor.execute("SELECT id FROM categories WHERE path = ?", ("🛒 محصولات",))
        row = cursor.fetchone()
        if not row:
            logging.info("Creating root category '🛒 محصولات'")
            cursor.execute(
                "INSERT INTO categories (parent_id, name, path, display_order) VALUES (NULL, ?, ?, 0)",
                ("🛒 محصولات", "🛒 محصولات"),
            )
            db.conn.commit()
        return True
    except Exception as e:
        logging.error(f"Error ensuring root category: {e}")
        return False
    finally:
        db.close()

# Run migrations on import
_ensure_custom_caption_column()
_ensure_category_id_column()
_ensure_video_origin_columns()
_ensure_root_category()

import logging
from typing import Optional, Any
from database.models import Database
from database.schema import ALL_TABLES
from utils.helpers import get_current_time  # ensure Tehran-tz aware now

class DatabaseQueries:
    # --- Global bot settings helpers ---
    @staticmethod
    def _ensure_settings_table():
        from database.connection import get_db
        db = get_db()
        db.execute("CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT)")
        db.commit()

    # ------------------------------------------------------------------
    # Renew buttons visibility helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Renew buttons visibility helpers (JSON based)
    # ------------------------------------------------------------------

    @staticmethod
    def _migrate_renew_visibility():
        """Migrate legacy renew settings (renew_free/renew_products/renew_plan_ids) -> JSON config."""
        existing = DatabaseQueries.get_setting("renew_visibility_json", None)
        if existing is not None:
            return  # Already migrated

        plans: set[int] = set()
        categories: set[int] = set()

        # Legacy comma-separated plan IDs
        legacy_csv = DatabaseQueries.get_setting("renew_plan_ids", "")
        if legacy_csv:
            try:
                plans.update(int(x) for x in legacy_csv.split(",") if x.strip().isdigit())
            except Exception:
                pass

        # Very old boolean flags – keep old semantics: free=true → show all free plans, products=true → show root products category id=1 maybe.
        renew_free = DatabaseQueries.get_setting("renew_free", None)
        renew_products = DatabaseQueries.get_setting("renew_products", None)
        if renew_free == "1":
            # Convention: use special category id 0 to denote "Free plans"
            categories.add(0)
        if renew_products == "1":
            categories.add(-1)  # -1 → all products/category root

        DatabaseQueries.set_renew_visibility({"plans": list(plans), "categories": list(categories)})

    @staticmethod
    def get_renew_visibility() -> dict[str, set[int]]:
        """Return a dict with 'plans' and 'categories' sets representing IDs to show renew buttons for."""
        DatabaseQueries._migrate_renew_visibility()
        import json
        raw = DatabaseQueries.get_setting("renew_visibility_json", "")
        if not raw:
            return {"plans": set(), "categories": set()}
        try:
            data = json.loads(raw)
            return {
                "plans": set(map(int, data.get("plans", []))),
                "categories": set(map(int, data.get("categories", []))),
            }
        except Exception:
            logging.exception("Failed to parse renew_visibility_json; falling back to empty sets")
            return {"plans": set(), "categories": set()}

    @staticmethod
    def set_renew_visibility(visibility: dict[str, set[int] | list[int]]):
        """Persist visibility dict to bot_settings as JSON. Accepts sets or lists for values."""
        import json
        data = {
            "plans": list(visibility.get("plans", [])),
            "categories": list(visibility.get("categories", [])),
        }
        DatabaseQueries.set_setting("renew_visibility_json", json.dumps(data, separators=(",", ":")))

    # ------------------------------------------------------------------
    # Legacy wrapper helpers (keep external API stable)
    # ------------------------------------------------------------------

    @staticmethod
    def get_renew_plan_ids() -> set[int]:
        return DatabaseQueries.get_renew_visibility()["plans"]

    @staticmethod
    def set_renew_plan_ids(ids: set[int]):
        vis = DatabaseQueries.get_renew_visibility()
        vis["plans"] = set(ids)
        DatabaseQueries.set_renew_visibility(vis)

    @staticmethod
    def get_setting(key: str, default: str | None = None):
        DatabaseQueries._ensure_settings_table()
        from database.connection import get_db
        db = get_db()
        cur = db.execute("SELECT value FROM bot_settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    @staticmethod
    def set_setting(key: str, value: str):
        DatabaseQueries._ensure_settings_table()
        from database.connection import get_db
        db = get_db()
        db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?,?)", (key, value))
        db.commit()

    """Class for handling database operations"""

    # ---------------------------------------------------------------------
    # CATEGORY MANAGEMENT HELPERS
    # ---------------------------------------------------------------------
    @staticmethod
    def get_category_by_id(category_id: int) -> dict | None:
        """Return a single category row as dict or None."""
        from database.connection_pool import get_pool
        try:
            with get_pool().get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM categories WHERE id = ?", (category_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logging.error(f"Error fetching category {category_id}: {e}")
            # Fallback to old method if pool fails
            db = Database()
            if not db.connect():
                return None
            try:
                cursor = db.conn.cursor()
                cursor.execute("SELECT * FROM categories WHERE id = ?", (category_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
            except Exception as e2:
                logging.error(f"Fallback also failed for category {category_id}: {e2}")
                return None
            finally:
                db.close()

    @staticmethod
    def get_children_categories(parent_id: int | None = None) -> list[dict]:
        """Return direct children of a parent category (root if None)."""
        from database.connection_pool import get_pool
        try:
            with get_pool().get_connection() as conn:
                cursor = conn.cursor()
                if parent_id is None:
                    cursor.execute("SELECT * FROM categories WHERE parent_id IS NULL ORDER BY display_order, id")
                else:
                    cursor.execute("SELECT * FROM categories WHERE parent_id = ? ORDER BY display_order, id", (parent_id,))
                return [dict(r) for r in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error fetching children for parent {parent_id}: {e}")
            # Fallback to old method if pool fails
            db = Database()
            if not db.connect():
                return []
            try:
                cursor = db.conn.cursor()
                if parent_id is None:
                    cursor.execute("SELECT * FROM categories WHERE parent_id IS NULL ORDER BY display_order, id")
                else:
                    cursor.execute("SELECT * FROM categories WHERE parent_id = ? ORDER BY display_order, id", (parent_id,))
                return [dict(r) for r in cursor.fetchall()]
            except Exception as e2:
                logging.error(f"Fallback also failed for parent {parent_id}: {e2}")
                return []
            finally:
                db.close()

    @staticmethod
    def create_category(name: str, parent_id: int | None = None, display_order: int = 0) -> int | None:
        """Create a new category; returns new id or None."""
        db = Database()
        if not db.connect():
            return None
        try:
            # Build path: parent's path + '/' + name
            cursor = db.conn.cursor()
            if parent_id is None:
                parent_path = None
            else:
                cursor.execute("SELECT path FROM categories WHERE id = ?", (parent_id,))
                row = cursor.fetchone()
                if not row:
                    logging.error("Parent category %s not found", parent_id)
                    return None
                parent_path = row[0] if isinstance(row, (tuple, list)) else row["path"]
            path = name if parent_path is None else f"{parent_path}/{name}"
            cursor.execute(
                "INSERT INTO categories (parent_id, name, path, display_order) VALUES (?, ?, ?, ?)",
                (parent_id, name, path, display_order),
            )
            db.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError as ie:
            logging.warning("Category create integrity error: %s", ie)
            return None
        except Exception as e:
            logging.error(f"Error creating category: {e}")
            return None
        finally:
            db.close()

    @staticmethod
    def update_category(category_id: int, name: str | None = None, display_order: int | None = None, is_active: bool | None = None) -> bool:
        """Update basic fields of a category."""
        if name is None and display_order is None and is_active is None:
            return False
        db = Database()
        if not db.connect():
            return False
        try:
            fields = []
            params = []
            if name is not None:
                fields.append("name = ?")
                params.append(name)
            if display_order is not None:
                fields.append("display_order = ?")
                params.append(display_order)
            if is_active is not None:
                fields.append("is_active = ?")
                params.append(1 if is_active else 0)
            fields.append("updated_at = CURRENT_TIMESTAMP")
            sql = f"UPDATE categories SET {', '.join(fields)} WHERE id = ?"
            params.append(category_id)
            db.execute(sql, tuple(params))
            db.commit()
            return db.cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Error updating category {category_id}: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def delete_category(category_id: int) -> bool:
        """Delete a category if it has no children and no linked plans."""
        db = Database()
        if not db.connect():
            return False
        try:
            cursor = db.conn.cursor()
            # Check children
            cursor.execute("SELECT COUNT(*) FROM categories WHERE parent_id = ?", (category_id,))
            if cursor.fetchone()[0] > 0:
                logging.warning("Cannot delete category %s: has subcategories", category_id)
                return False
            # Check plans
            cursor.execute("SELECT COUNT(*) FROM plans WHERE category_id = ?", (category_id,))
            if cursor.fetchone()[0] > 0:
                logging.warning("Cannot delete category %s: linked plans exist", category_id)
                return False
            cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            db.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Error deleting category {category_id}: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def get_category_tree() -> list[dict]:
        """Return full category tree as nested dict list."""
        db = Database()
        if not db.connect():
            return []
        try:
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM categories ORDER BY path")
            rows = [dict(r) for r in cursor.fetchall()]
            # Build tree via id->node map
            id_map: dict[int, dict] = {}
            roots: list[dict] = []
            for row in rows:
                row["children"] = []
                id_map[row["id"]] = row
            for row in rows:
                pid = row["parent_id"]
                if pid is None:
                    roots.append(row)
                else:
                    parent = id_map.get(pid)
                    if parent:
                        parent["children"].append(row)
            return roots
        except Exception as e:
            logging.error(f"Error building category tree: {e}")
            return []
        finally:
            db.close()

    # --- VIDEO MANAGEMENT HELPERS --------------------------------------------
    @staticmethod
    def get_all_videos():
        """Get all videos from the database."""
        db = Database()
        if not db.connect():
            return []
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT id, filename, display_name, file_path, file_size, 
                       duration, telegram_file_id, origin_chat_id, origin_message_id, is_active
                FROM videos 
                WHERE is_active = 1
                ORDER BY display_name
            """)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting videos: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def add_video(
        filename: str,
        display_name: str,
        file_path: str,
        file_size: int | None = None,
        duration: int | None = None,
        telegram_file_id: str | None = None,
        origin_chat_id: int | None = None,
        origin_message_id: int | None = None,
    ) -> int | None:
        """Add a new video to the database.

        Args:
            filename: Saved filename on disk.
            display_name: Human-friendly display title.
            file_path: Absolute path on disk.
            file_size: Size of the file in bytes.
            duration: Video duration in seconds (optional).
            telegram_file_id: Original Telegram **file_id** for faster re-sending / caching (optional).
            origin_chat_id: Source channel ID if video copied from private channel (optional).
            origin_message_id: Source message ID for copy_message fallback (optional).

        Returns:
            Newly-created *video.id* or ``None`` on failure.
        """
        db = Database()
        if not db.connect():
            return None

        try:
            cursor = db.conn.cursor()
            cursor.execute(
                """
                INSERT INTO videos (
                    filename,
                    display_name,
                    file_path,
                    file_size,
                    duration,
                    telegram_file_id,
                    origin_chat_id,
                    origin_message_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    filename,
                    display_name,
                    file_path,
                    file_size,
                    duration,
                    telegram_file_id,
                    origin_chat_id,
                    origin_message_id,
                ),
            )
            db.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logging.error(f"Error adding video: {e}")
            return None
        finally:
            db.close()

    @staticmethod
    def get_video_by_id(video_id: int):
        """Get a video by its ID."""
        db = Database()
        if not db.connect():
            return None
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT id, filename, display_name, file_path, file_size, 
                       duration, telegram_file_id, origin_chat_id, origin_message_id, is_active
                FROM videos 
                WHERE id = ? AND is_active = 1
            """, (video_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
        except Exception as e:
            logging.error(f"Error getting video by id: {e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def update_video_telegram_file_id(video_id: int, telegram_file_id: str):
        """Update the Telegram file ID for a video (for caching)."""
        db = Database()
        if not db.connect():
            return False
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                UPDATE videos 
                SET telegram_file_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (telegram_file_id, video_id))
            db.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Error updating video telegram file ID: {e}")
            return False
        finally:
            db.close()

    # -----------------------------------------------------------------
    # Statistics helper methods
    # -----------------------------------------------------------------

    @staticmethod
    def get_total_users_count() -> int:
        """Return total number of registered users."""
        db = Database()
        if not db.connect():
            return 0
        try:
            cursor = db.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0]
        except Exception as e:
            logging.error(f"Error fetching total users count: {e}")
            return 0
        finally:
            db.close()

    @staticmethod
    def get_active_users_count() -> int:
        """Return number of active subscribers (users with active plan)."""
        db = Database()
        if not db.connect():
            return 0
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id)
                FROM subscriptions
                WHERE status = 'active' AND datetime(end_date) > datetime('now')
            """)
            return cursor.fetchone()[0]
        except Exception as e:
            logging.error(f"Error fetching active users count: {e}")
            return 0
        finally:
            db.close()

    @staticmethod
    def get_all_plans() -> list[dict]:
        """Return list of all plans with id, name, price."""
        db = Database()
        if not db.connect():
            return []
        try:
            cursor = db.conn.cursor()
            cursor.execute("SELECT id, name, price FROM plans WHERE is_active = 1")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logging.error(f"Error fetching plans: {e}")
            return []
        finally:
            db.close()

    @staticmethod
    def get_plan_sales_count(plan_id: int) -> int:
        """Return count of successful payments for given plan."""
        db = Database()
        if not db.connect():
            return 0
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM payments
                WHERE plan_id = ? AND status = 'paid'
            """, (plan_id,))
            return cursor.fetchone()[0]
        except Exception as e:
            logging.error(f"Error fetching sales count for plan {plan_id}: {e}")
            return 0
        finally:
            db.close()

    @staticmethod
    def get_pending_tickets_count() -> int:
        db = Database()
        if not db.connect():
            return 0
        try:
            cursor = db.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tickets WHERE status = 'pending'")
            return cursor.fetchone()[0]
        except Exception as e:
            logging.error(f"Error fetching pending tickets count: {e}")
            return 0
        finally:
            db.close()

    @staticmethod
    def get_total_tickets_count() -> int:
        db = Database()
        if not db.connect():
            return 0
        try:
            cursor = db.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tickets")
            return cursor.fetchone()[0]
        except Exception as e:
            logging.error(f"Error fetching total tickets count: {e}")
            return 0
        finally:
            db.close()

    # -----------------------------------------------------------------
    # NEW: keep DB paths in sync when we discover a better local path
    # -----------------------------------------------------------------

    @staticmethod
    def update_video_file_path(video_id: int, new_file_path: str) -> bool:
        """
        Update the local file_path of a video record.
        """
        if not new_file_path:
            return False
        db = Database()
        if not db.connect():
            return False
        try:
            cursor = db.conn.cursor()
            cursor.execute(
                """
                UPDATE videos
                SET file_path = ?
                WHERE id = ?
                """,
                (new_file_path, video_id)
            )
            db.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Error updating video telegram file ID: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def delete_video(video_id: int) -> bool:
        """
        Delete a video and its plan associations from the database.
        1. Remove all plan_videos links for this video.
        2. Delete the video record from videos table.
        Returns True if video was deleted (even if no plan links existed).
        """
        db = Database()
        if not db.connect():
            return False
        try:
            cursor = db.conn.cursor()
            # Remove from plan_videos
            cursor.execute(
                "DELETE FROM plan_videos WHERE video_id = ?",
                (video_id,)
            )
            # Remove from videos
            cursor.execute(
                "DELETE FROM videos WHERE id = ?",
                (video_id,)
            )
            db.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Error deleting video {video_id}: {e}")
            return False
        finally:
            db.close()
        """Update the local file_path of a video record.

        This is useful when a video was forwarded from another chat and its original
        `file_path` was not known at the time of insertion, or if the absolute path
        has changed due to a move/rename. We keep DB in sync so subsequent sends can
        reuse the correct path without another lookup.
        """
        if not new_file_path:
            return False
        db = Database()
        if not db.connect():
            return False
        try:
            cursor = db.conn.cursor()
            cursor.execute(
                """
                UPDATE videos
                SET file_path = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_file_path, video_id),
            )
            db.conn.commit()
            return cursor.rowcount > 0
        except Exception as exc:
            logging.error("Error updating video file_path: %s", exc)
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_plan_videos(plan_id: int):
        """Get all videos associated with a plan."""
        db = Database()
        if not db.connect():
            return []
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT v.id, v.filename, v.display_name, v.file_path, v.file_size, 
                       v.duration, v.telegram_file_id, v.origin_chat_id, v.origin_message_id, v.is_active, pv.display_order, pv.custom_caption
                FROM videos v
                JOIN plan_videos pv ON v.id = pv.video_id
                WHERE pv.plan_id = ? AND v.is_active = 1
                ORDER BY pv.display_order, v.display_name
            """, (plan_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting plan videos: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def add_video_to_plan(plan_id: int, video_id: int, display_order: int = 0, custom_caption: str | None = None):
        """Associate a video with a plan with optional custom caption."""
        db = Database()
        if not db.connect():
            return False
        
        try:
            cursor = db.conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO plan_videos (plan_id, video_id, display_order, custom_caption)
                VALUES (?, ?, ?, ?)
                """,
                (plan_id, video_id, display_order, custom_caption)
            )
            db.conn.commit()
            return True
        except Exception as e:
            logging.error(f"Error adding video to plan: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def remove_video_from_plan(plan_id: int, video_id: int):
        """Remove a video from a plan."""
        db = Database()
        if not db.connect():
            return False
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                DELETE FROM plan_videos 
                WHERE plan_id = ? AND video_id = ?
            """, (plan_id, video_id))
            db.conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Error removing video from plan: {e}")
            return False
        finally:
            db.close()
    
    # --- SURVEY MANAGEMENT HELPERS -------------------------------------------
    @staticmethod
    def create_survey(plan_id: int, title: str, description: str = None):
        """Create a new survey for a plan."""
        db = Database()
        if not db.connect():
            return None
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                INSERT INTO surveys (plan_id, title, description)
                VALUES (?, ?, ?)
            """, (plan_id, title, description))
            db.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logging.error(f"Error creating survey: {e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def add_survey_question(survey_id: int, question_text: str, question_type: str = 'text', 
                           options: str = None, is_required: bool = True, display_order: int = 0):
        """Add a question to a survey."""
        db = Database()
        if not db.connect():
            return None
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                INSERT INTO survey_questions (survey_id, question_text, question_type, 
                                            options, is_required, display_order)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (survey_id, question_text, question_type, options, int(is_required), display_order))
            db.conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logging.error(f"Error adding survey question: {e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_plan_survey(plan_id: int):
        """Get the survey associated with a plan."""
        db = Database()
        if not db.connect():
            return None
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT id, plan_id, title, description, created_at
                FROM surveys 
                WHERE plan_id = ?
                ORDER BY created_at DESC
                LIMIT 1
            """, (plan_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
        except Exception as e:
            logging.error(f"Error getting plan survey: {e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_survey_by_id(survey_id: int):
        """Get a survey by its ID."""
        db = Database()
        if not db.connect():
            return None
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT id, plan_id, title, description, created_at
                FROM surveys 
                WHERE id = ?
            """, (survey_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
        except Exception as e:
            logging.error(f"Error getting survey by id: {e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_survey_questions(survey_id: int):
        """Get all questions for a survey."""
        db = Database()
        if not db.connect():
            return []
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT id, question_text, question_type, options, is_required, display_order
                FROM survey_questions 
                WHERE survey_id = ?
                ORDER BY display_order, id
            """, (survey_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting survey questions: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def save_survey_response(user_id: int, survey_id: int, question_id: int, response_text: str):
        """Save a user's response to a survey question."""
        db = Database()
        if not db.connect():
            return False
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO survey_responses 
                (user_id, survey_id, question_id, response_text)
                VALUES (?, ?, ?, ?)
            """, (user_id, survey_id, question_id, response_text))
            db.conn.commit()
            return True
        except Exception as e:
            logging.error(f"Error saving survey response: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def mark_survey_completed(user_id: int, survey_id: int, plan_id: int):
        """Mark a survey as completed by a user."""
        db = Database()
        if not db.connect():
            return False
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO user_survey_completions 
                (user_id, survey_id, plan_id)
                VALUES (?, ?, ?)
            """, (user_id, survey_id, plan_id))
            db.conn.commit()
            return True
        except Exception as e:
            logging.error(f"Error marking survey completed: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def has_user_completed_survey(user_id: int, survey_id: int):
        """Check if a user has completed a survey."""
        db = Database()
        if not db.connect():
            return False
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT 1 FROM user_survey_completions 
                WHERE user_id = ? AND survey_id = ?
            """, (user_id, survey_id))
            return cursor.fetchone() is not None
        except Exception as e:
            logging.error(f"Error checking survey completion: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_user_survey_responses(user_id: int, survey_id: int):
        """Get all responses from a user for a survey."""
        db = Database()
        if not db.connect():
            return []
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT sr.response_text, sq.question_text, sq.question_type
                FROM survey_responses sr
                JOIN survey_questions sq ON sr.question_id = sq.id
                WHERE sr.user_id = ? AND sr.survey_id = ?
                ORDER BY sq.display_order, sq.id
            """, (user_id, survey_id))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting user survey responses: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def get_plan_videos(plan_id: int):
        """Get all videos associated with a plan."""
        db = Database()
        if not db.connect():
            return []
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT v.id, v.filename, v.display_name, v.file_path, v.duration
                FROM videos v
                JOIN plan_videos pv ON v.id = pv.video_id
                WHERE pv.plan_id = ?
                ORDER BY pv.display_order, v.display_name
            """, (plan_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting plan videos: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def get_video_by_id(video_id: int):
        """Get video details by ID."""
        db = Database()
        if not db.connect():
            return None
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT id, filename, display_name, file_path, duration
                FROM videos
                WHERE id = ?
            """, (video_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
        except Exception as e:
            logging.error(f"Error getting video by ID: {e}")
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_video_plans(video_id: int):
        """Get all plans that include a specific video."""
        db = Database()
        if not db.connect():
            return []
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT pv.plan_id, p.name as plan_name
                FROM plan_videos pv
                JOIN plans p ON pv.plan_id = p.id
                WHERE pv.video_id = ?
            """, (video_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting video plans: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def get_user_active_subscriptions(user_id: int):
        """Get all active subscriptions for a user."""
        db = Database()
        if not db.connect():
            return []
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT s.id, s.plan_id, s.status, s.start_date, s.end_date,
                       p.name as plan_name
                FROM subscriptions s
                JOIN plans p ON s.plan_id = p.id
                WHERE s.user_id = ? AND s.status = 'active'
                ORDER BY s.start_date DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting user active subscriptions: {e}")
            return []
        finally:
            db.close()
    
    # --- SALES STATS HELPERS -------------------------------------------------
    @staticmethod
    def get_sales_stats_per_plan(only_active: bool = True):
        """Return sales statistics per subscription plan.

        For each plan we calculate:
        • total_subscriptions   – total number of subscriptions ever purchased for the plan
        • active_subscriptions  – current active subscriptions
        • total_revenue_rial    – total IRR revenue (payments.amount) linked to the plan with status = 'paid'
        • total_revenue_usdt    – total USDT revenue (payments.usdt_amount_requested *or* crypto_payments.usdt_amount_requested)

        Note: because our schema has two payment sources (payments & crypto_payments) and
        may not always store plan_id in crypto_payments, we only aggregate what is reliably
        available.
        """
        db = Database()
        stats: list[dict] = []
        if not db.connect():
            return stats

        try:
            now_str = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
            # Build base plans query
            plan_cond = "WHERE p.is_active = 1" if only_active else ""
            # SQL aggregates using correlated sub-queries for clarity & SQLite compatibility
            sql = f"""
                SELECT
                    p.id                                         AS plan_id,
                    p.name                                       AS plan_name,
                    (
                        SELECT COUNT(*) FROM subscriptions s
                        WHERE s.plan_id = p.id
                    )                                            AS total_subscriptions,
                    (
                        SELECT COUNT(*) FROM subscriptions s
                        WHERE s.plan_id = p.id AND s.status = 'active' AND datetime(s.end_date) > datetime(?)
                    )                                            AS active_subscriptions,
                    COALESCE((
                        SELECT SUM(amount) FROM payments pay
                        WHERE pay.plan_id = p.id AND pay.status IN ('paid','completed','successful','verified')
                    ), 0)                                         AS total_revenue_rial,
                    COALESCE((
                        SELECT SUM(usdt_amount_requested) FROM payments pay2
                        WHERE pay2.plan_id = p.id AND pay2.usdt_amount_requested IS NOT NULL AND pay2.status IN ('paid','completed','successful','verified')
                    ), 0)                                         AS total_revenue_usdt
                FROM plans p
                {plan_cond}
                ORDER BY p.display_order, p.id
            """
            db.execute(sql, (now_str,))
            rows = db.fetchall()
            if rows:
                # Convert to list of dicts for easier consumption
                col_names = [desc[0] for desc in db.cursor.description]
                for row in rows:
                    stats.append(dict(zip(col_names, row)))
        except sqlite3.Error as e:
            logging.error("SQLite error in get_sales_stats_per_plan: %s", e)
        finally:
            db.close()
        return stats
    def __init__(self, db: Database | None = None):
        # Allow passing None to use singleton Database.get_instance() or create default
        from database.models import Database as DBModel
        self.db = db or DBModel.get_instance()

    def init_database(self):
        """Initialize the database and create tables if they don't exist."""
        if self.db.connect():
            # Add is_active and is_public to plans table if they don't exist
            try:
                self.db.execute("PRAGMA table_info(plans)")
                columns = [column['name'] for column in self.db.fetchall()]

                # Add duration_days column if missing
                if 'duration_days' not in columns:
                    self.db.execute("ALTER TABLE plans ADD COLUMN duration_days INTEGER")
                    # If legacy 'days' column exists, copy data across
                    if 'days' in columns:
                        try:
                            self.db.execute("UPDATE plans SET duration_days = days WHERE duration_days IS NULL OR duration_days = 0")
                        except sqlite3.Error as copy_err:
                            logging.error(f"Error migrating days to duration_days: {copy_err}")

                # Ensure is_active / is_public & capacity columns exist
                    self.db.execute("ALTER TABLE plans ADD COLUMN auto_delete_links BOOLEAN DEFAULT 1")
                # Add base_currency TEXT column for specifying the base currency (IRR or USDT)
                if 'base_currency' not in columns:
                    self.db.execute("ALTER TABLE plans ADD COLUMN base_currency TEXT DEFAULT 'IRR'")
                # Add base_price REAL column for storing the base price in the base currency
                if 'base_price' not in columns:
                    self.db.execute("ALTER TABLE plans ADD COLUMN base_price REAL")
                self.db.commit()
            except sqlite3.Error as e:
                logging.error(f"Error checking/adding columns to plans table: {e}")

            # Ensure 'usdt_amount_requested' column in payments table
            try:
                self.db.execute("PRAGMA table_info(payments)")
                pay_cols = [c['name'] for c in self.db.fetchall()]
                # Add missing columns for crypto payments
                if 'usdt_amount_requested' not in pay_cols:
                    self.db.execute("ALTER TABLE payments ADD COLUMN usdt_amount_requested REAL")
                if 'wallet_address' not in pay_cols:
                    self.db.execute("ALTER TABLE payments ADD COLUMN wallet_address TEXT")
                if 'expires_at' not in pay_cols:
                    self.db.execute("ALTER TABLE payments ADD COLUMN expires_at TEXT")
            except sqlite3.Error as col_err:
                logging.error(f"Error ensuring usdt_amount_requested column: {col_err}")

            # Add subscription management improvements
            try:
                # Add category_id to subscriptions table if not exists
                self.db.execute("PRAGMA table_info(subscriptions)")
                sub_cols = [c['name'] for c in self.db.fetchall()]
                
                if 'category_id' not in sub_cols:
                    logging.info("Adding category_id column to subscriptions table...")
                    self.db.execute("ALTER TABLE subscriptions ADD COLUMN category_id INTEGER REFERENCES categories(id)")
                    logging.info("Successfully added category_id column")
                
                # Create subscription_history table
                self.db.execute("""
                    CREATE TABLE IF NOT EXISTS subscription_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        subscription_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        plan_id INTEGER NOT NULL,
                        category_id INTEGER,
                        action TEXT NOT NULL,
                        old_end_date TEXT,
                        new_end_date TEXT,
                        days_added INTEGER,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        created_by INTEGER,
                        notes TEXT,
                        FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
                        FOREIGN KEY (user_id) REFERENCES users(user_id),
                        FOREIGN KEY (plan_id) REFERENCES plans(id),
                        FOREIGN KEY (category_id) REFERENCES categories(id)
                    )
                """)
                
                # Create indexes for better performance
                self.db.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_category ON subscriptions(user_id, category_id, status)")
                self.db.execute("CREATE INDEX IF NOT EXISTS idx_subscription_history_user ON subscription_history(user_id, created_at DESC)")
                
                logging.info("Subscription management migrations completed")
            except sqlite3.Error as e:
                logging.error(f"Error in subscription management migration: {e}")
            
            self.db.commit()
            return self.db.create_tables(ALL_TABLES)
        return False

    # -----------------------------------
    # Survey Management
    # -----------------------------------
    @staticmethod
    def upsert_plan_survey(plan_id: int, questions: list[dict[str, any]]):
        """Create or replace survey and questions for plan."""
        db = Database()
        if not db.connect():
            return False
        import json, sqlite3, logging
        try:
            cur = db.conn.cursor()
            # Remove existing survey (cascade will delete questions)
            cur.execute("DELETE FROM surveys WHERE plan_id = ?", (plan_id,))
            # Insert new survey
            cur.execute("INSERT INTO surveys (plan_id, title) VALUES (?, ?)", (plan_id, f'Plan {plan_id} Survey'))
            survey_id = cur.lastrowid
            # Insert questions
            for order, q in enumerate(questions, 1):
                opts_json = json.dumps(q.get('options')) if q.get('options') else None
                cur.execute(
                    """INSERT INTO survey_questions (survey_id, question_text, question_type, options, display_order)
                    VALUES (?,?,?,?,?)""",
                    (survey_id, q['text'], q.get('type', 'text'), opts_json, order)
                )
            db.conn.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error upserting plan survey: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def get_plan_survey(plan_id: int):
        db = Database()
        if not db.connect():
            return None
        try:
            cur = db.conn.cursor()
            cur.execute("SELECT * FROM surveys WHERE plan_id = ? AND is_active = 1 LIMIT 1", (plan_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logging.error(f"Error get_plan_survey: {e}")
            return None
        finally:
            db.close()

    @staticmethod
    def get_survey_questions(survey_id: int):
        db = Database()
        if not db.connect():
            return []
        import json
        try:
            cur = db.conn.cursor()
            cur.execute("SELECT * FROM survey_questions WHERE survey_id = ? ORDER BY display_order", (survey_id,))
            rows = [dict(r) for r in cur.fetchall()]
            for r in rows:
                if r.get('options'):
                    try:
                        r['options'] = json.loads(r['options'])
                    except Exception:
                        pass
            return rows
        except Exception as e:
            logging.error(f"Error get_survey_questions: {e}")
            return []
        finally:
            db.close()

    @staticmethod
    def has_user_completed_survey(user_id: int, survey_id: int) -> bool:
        db = Database()
        if not db.connect():
            return False
        try:
            cur = db.conn.cursor()
            cur.execute("SELECT COUNT(*) cnt FROM survey_questions WHERE survey_id = ?", (survey_id,))
            total = cur.fetchone()['cnt']
            cur.execute("SELECT COUNT(DISTINCT question_id) cnt FROM survey_responses WHERE user_id = ? AND survey_id = ?", (user_id, survey_id))
            answered = cur.fetchone()['cnt']
            return answered >= total and total > 0
        except Exception as e:
            logging.error(f"Error has_user_completed_survey: {e}")
            return False
        finally:
            db.close()

    @staticmethod
    def add_survey_response(user_id: int, survey_id: int, question_id: int, response_text: str):
        db = Database()
        if not db.connect():
            return False
        import sqlite3
        try:
            cur = db.conn.cursor()
            cur.execute("""INSERT OR REPLACE INTO survey_responses (user_id, survey_id, question_id, response_text)
                          VALUES (?,?,?,?)""", (user_id, survey_id, question_id, response_text))
            db.conn.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error add_survey_response: {e}")
            return False
        finally:
            db.close()

    # -----------------------------------
    # Product Management
    # -----------------------------------
    def add_plan(self, name: str, price: float | None, duration_days: int, description: str | None = None, *, capacity: int | None = None, price_tether: float | None = None, original_price_irr: float | None = None, original_price_usdt: float | None = None, channels_json: str | None = None, auto_delete_links: bool = True, is_active: bool = True, is_public: bool = True, base_currency: str = 'IRR', base_price: float | None = None, category_id: int | None = None):
        """Add a new plan to the database with active and public status."""
        try:
            # Determine if legacy 'days' column exists
            self.db.execute("PRAGMA table_info(plans)")
            columns = [col['name'] for col in self.db.fetchall()]
            column_names = ["name"]
            values: list[Any] = [name]

            # Handle IRR price (legacy) if provided
            if price is not None:
                column_names.append("price")
                values.append(price)

            # Duration column
            duration_col = "duration_days" if "duration_days" in columns else "days"
            column_names.append(duration_col)
            values.append(duration_days)

            # If legacy 'days' column exists, keep it in sync
            if 'days' in columns:
                column_names.append("days")
                values.append(duration_days)

            # Description may be optional
            column_names.append("description")
            values.append(description)

            # Capacity if supported
            if 'capacity' in columns:
                column_names.append("capacity")
                values.append(capacity)

            # channels_json if supported
            if 'channels_json' in columns and channels_json is not None:
                column_names.append("channels_json")
                values.append(channels_json)

            # auto_delete_links if supported
            if 'auto_delete_links' in columns:
                column_names.append("auto_delete_links")
                values.append(auto_delete_links)

            # USDT pricing columns if present in schema and provided
            if 'price_tether' in columns and price_tether is not None:
                column_names.append("price_tether")
                values.append(price_tether)
            if 'original_price_irr' in columns and original_price_irr is not None:
                column_names.append("original_price_irr")
                values.append(original_price_irr)
            if 'original_price_usdt' in columns and original_price_usdt is not None:
                column_names.append("original_price_usdt")
                values.append(original_price_usdt)

            # Base currency and price fields
            if 'base_currency' in columns:
                column_names.append("base_currency")
                values.append(base_currency)
            if 'base_price' in columns and base_price is not None:
                column_names.append("base_price")
                values.append(base_price)

            # Category ID if supported
            if 'category_id' in columns and category_id is not None:
                column_names.append("category_id")
                values.append(category_id)

            # Activation & visibility flags
            column_names.extend(["is_active", "is_public"])
            values.extend([is_active, is_public])

            placeholders = ", ".join(["?" for _ in column_names])
            columns_sql = ", ".join(column_names)
            sql = f"INSERT INTO plans ({columns_sql}) VALUES ({placeholders})"
            params = tuple(values)
            self.db.execute(sql, params)
            self.db.commit()
            return self.db.cursor.lastrowid
        except sqlite3.Error as e:
            logging.error(f"SQLite error in add_plan: {e}")
            return None

    def get_all_plans(self, public_only=False):
        """Retrieve plans from the database. Can filter for public-only plans."""
        query = "SELECT id, name, price, duration_days, description, is_active, is_public FROM plans ORDER BY id"
        params = ()
        if public_only:
            query = "SELECT id, name, price, duration_days, description, is_active, is_public FROM plans WHERE is_public = ? AND is_active = ? ORDER BY id"
            params = (True, True)
        try:
            self.db.execute(query, params)
            return self.db.fetchall()
        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_all_plans: {e}")
            return []

    def get_plan_by_id(self, plan_id: int):
        """Retrieve a single plan by its ID."""
        try:
            self.db.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
            row = self.db.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_plan_by_id: {e}")
            return None

    def update_plan(self, plan_id: int, *, name: str | None = None, price: float | None = None, duration_days: int | None = None, capacity: int | None = None, description: str | None = None, price_tether: float | None = None, original_price_irr: float | None = None, original_price_usdt: float | None = None, channels_json: str | None = None, auto_delete_links: bool | None = None, base_currency: str | None = None, base_price: float | None = None, category_id: int | None = None):
        """Update an existing plan's details."""
        try:
            # Ensure both duration_days and legacy days are updated if applicable
            self.db.execute("PRAGMA table_info(plans)")
            cols = [c['name'] for c in self.db.fetchall()]
            set_clauses: list[str] = []
            params: list[Any] = []

            def add_field(field_name: str, value):
                if value is not None:
                    set_clauses.append(f"{field_name} = ?")
                    params.append(value)

            add_field("name", name)
            add_field("price", price)
            if duration_days is not None:
                if 'duration_days' in cols:
                    add_field("duration_days", duration_days)
                elif 'days' in cols:
                    add_field("days", duration_days)
            add_field("description", description)
            if 'capacity' in cols:
                # None means leave unchanged; explicit value (including 0) sets.
                if capacity is not None:
                    add_field("capacity", capacity)
            if 'price_tether' in cols:
                add_field("price_tether", price_tether)
            if 'original_price_irr' in cols:
                add_field("original_price_irr", original_price_irr)
            if 'original_price_usdt' in cols:
                add_field("original_price_usdt", original_price_usdt)
            if 'channels_json' in cols:
                add_field("channels_json", channels_json)
            if 'auto_delete_links' in cols:
                add_field("auto_delete_links", auto_delete_links)
            if 'base_currency' in cols:
                add_field("base_currency", base_currency)
            if 'base_price' in cols:
                add_field("base_price", base_price)
            if 'category_id' in cols:
                add_field("category_id", category_id)

            if not set_clauses:
                return False  # Nothing to update

            set_sql = ", ".join(set_clauses)
            sql = f"UPDATE plans SET {set_sql} WHERE id = ?"
            params.append(plan_id)
            self.db.execute(sql, params)
            self.db.commit()
            return self.db.cursor.rowcount > 0
        except sqlite3.Error as e:
            logging.error(f"SQLite error in update_plan: {e}")
            return False

    def set_plan_visibility(self, plan_id: int, is_public: bool | None = None):
        """Set the public visibility of a plan."""
        try:
            # If is_public is None, toggle the current value
            if is_public is None:
                self.db.execute("SELECT is_public FROM plans WHERE id = ?", (plan_id,))
                row = self.db.fetchone()
                if row is None:
                    return False
                is_public = not bool(row[0] if isinstance(row, tuple) else row['is_public'])
            self.db.execute("UPDATE plans SET is_public = ? WHERE id = ?", (is_public, plan_id))
            self.db.commit()
            return self.db.cursor.rowcount > 0
        except sqlite3.Error as e:
            logging.error(f"SQLite error in set_plan_visibility: {e}")
            return False

    def set_plan_activation(self, plan_id: int, is_active: bool | None = None):
        """Set the activation status of a plan."""
        try:
            # If is_active is None, toggle the current value
            if is_active is None:
                self.db.execute("SELECT is_active FROM plans WHERE id = ?", (plan_id,))
                row = self.db.fetchone()
                if row is None:
                    return False
                is_active = not bool(row[0] if isinstance(row, tuple) else row['is_active'])
            self.db.execute("UPDATE plans SET is_active = ? WHERE id = ?", (is_active, plan_id))
            self.db.commit()
            return self.db.cursor.rowcount > 0
        except sqlite3.Error as e:
            logging.error(f"SQLite error in set_plan_activation: {e}")
            return False

    @staticmethod
    def count_subscribers_for_plan(plan_id: int) -> int:
        """Counts the number of active subscribers for a given plan."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT COUNT(id) FROM subscriptions WHERE plan_id = ? AND status = 'active'"
                if db.execute(query, (plan_id,)):
                    result = db.fetchone()
                    return result[0] if result else 0
            except sqlite3.Error as e:
                logging.error(f"SQLite error in count_subscribers_for_plan: {e}")
            finally:
                db.close()
        return 0

    # ------------------------------------------------------------------
    # Capacity helpers
    # ------------------------------------------------------------------
    @staticmethod
    def decrement_plan_capacity(plan_id: int, amount: int = 1) -> bool:
        """Decrements remaining capacity for a plan by the given amount.

        The update is only applied if the plan has a non-NULL capacity value
        and the resulting capacity would not become negative.
        Returns True if a row was updated (capacity decremented), otherwise False.
        """
        if amount <= 0:
            return False
        db = Database()
        if db.connect():
            try:
                db.execute(
                    """
                    UPDATE plans
                    SET capacity = capacity - ?
                    WHERE id = ?
                      AND capacity IS NOT NULL
                      AND capacity >= ?
                    """,
                    (amount, plan_id, amount),
                )
                db.commit()
                return db.cursor.rowcount > 0
            except sqlite3.Error as exc:
                logging.error("SQLite error in decrement_plan_capacity: %s", exc)
                return False
            finally:
                db.close()
        return False

    def delete_plan(self, plan_id: int):
        """Delete a plan from the database."""
        try:
            self.db.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
            self.db.commit()
            return self.db.cursor.rowcount > 0
        except sqlite3.Error as e:
            logging.error(f"SQLite error in delete_plan: {e}")
            return False

    # ... (rest of the methods converted similarly) ...

    def search_users(self, term: str):
        """Search users by user_id, username, or full_name."""
        results = []
        try:
            if term.isdigit():
                self.db.execute("SELECT user_id, full_name, username FROM users WHERE user_id = ?", (int(term),))
            else:
                like_term = f"%{term}%"
                self.db.execute("SELECT user_id, full_name, username FROM users WHERE username LIKE ? OR full_name LIKE ?", (like_term, like_term))
            results = self.db.fetchall()
        except sqlite3.Error as e:
            logging.error(f"SQLite error in search_users: {e}")
        return results

    @staticmethod
    def get_recent_payments(limit: int = 20):
        """Return recent payment records."""
        payments = []
        db = Database()
        if db.connect():
            try:
                sql = f"""
                    SELECT payment_id AS id, user_id, amount AS amount_rial, 'rial' AS payment_type, payment_method, plan_id, status, created_at
                    FROM payments
                    UNION ALL
                    SELECT id AS id, user_id, rial_amount AS amount_rial, 'crypto' AS payment_type, 'crypto' AS payment_method, NULL as plan_id, status, created_at
                    FROM crypto_payments
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                db.execute(sql, (limit,))
                payments = db.fetchall()
            except sqlite3.Error as e:
                logging.error(f"SQLite error in get_recent_payments: {e}")
            finally:
                db.close()
        return payments

    def _ensure_video_table(self):
        """Ensure the video_files table exists and has the correct schema."""
        create_sql = """
            CREATE TABLE IF NOT EXISTS video_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT UNIQUE,
                telegram_file_id TEXT
            );
        """
        self.db.execute(create_sql)
        try:
            self.db.execute("PRAGMA table_info(video_files)")
            columns_info = self.db.fetchall()
            existing_columns = {row['name'] for row in columns_info}
            if "telegram_file_id" not in existing_columns:
                self.db.execute("ALTER TABLE video_files ADD COLUMN telegram_file_id TEXT")
            self.db.commit()
        except sqlite3.Error as e:
            logging.error(f"Error ensuring video table schema: {e}")

    def get_video_file_id(self, file_name: str):
        """Return cached telegram_file_id for a video filename."""
        try:
            self._ensure_video_table()
            self.db.execute("SELECT telegram_file_id FROM video_files WHERE file_name = ?", (file_name,))
            row = self.db.fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            logging.error(f"Error getting video file id: {e}")
            return None

    def save_video_file_id(self, file_name: str, file_id: str):
        """Upsert telegram_file_id for a video filename."""
        try:
            self._ensure_video_table()
            self.db.execute(
                "INSERT OR REPLACE INTO video_files (file_name, telegram_file_id) VALUES (?, ?)",
                (file_name, file_id),
            )
            self.db.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error saving video file_id for {file_name}: {e}")
            return False

    # ------------------------------------------------------------------
    # User existence / registration helpers (instance + static versions)
    # ------------------------------------------------------------------
    def user_exists(self, user_id):
        """Instance method: check if a user exists."""
        try:
            self.db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
            return self.db.fetchone() is not None
        except sqlite3.Error as e:
            logging.error(f"Error checking if user exists: {e}")
            return False

    @staticmethod
    def user_exists_static(user_id):
        """Static helper so that code can call DatabaseQueries.user_exists(user_id)."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
                return db.fetchone() is not None
            except sqlite3.Error as e:
                logging.error(f"SQLite error in user_exists_static: {e}")
            finally:
                db.close()
        return False


    def add_user(self, user_id, username=None):
        """Add a new user."""
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute(
                "INSERT INTO users (user_id, username, registration_date, last_activity) VALUES (?, ?, ?, ?)",
                (user_id, username, now, now)
            )
            self.db.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error adding user: {e}")
            return False

    def update_user_activity(self, user_id):
        """Update user's last activity timestamp."""
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.execute(
                "UPDATE users SET last_activity = ? WHERE user_id = ?",
                (now, user_id)
            )
            self.db.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error updating user activity: {e}")
            return False

    def get_user_details(self, user_id):
        """Get user details."""
        try:
            self.db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = self.db.fetchone()
            # Convert Row to dictionary for easier access
            return dict(row) if row else None
        except sqlite3.Error as e:
            logging.error(f"Error getting user details: {e}")
            return None

    def update_user_profile(self, user_id, **kwargs):
        """Update user profile information."""
        allowed_fields = ['full_name', 'phone', 'email', 'education', 'city', 'age', 'occupation', 'birth_date']
        updates = []
        params = []
        for key, value in kwargs.items():
            if key in allowed_fields and value is not None:
                updates.append(f"{key} = ?")
                params.append(value)
        
        if not updates:
            return False

        query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
        params.append(user_id)
        try:
            self.db.execute(query, tuple(params))
            self.db.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"Error updating user profile: {e}")
            return False

    @staticmethod
    def update_user_single_field(user_id: int, field_name: str, value):
        """Update a single field for a user.

        This method was converted to a static method so that callers can invoke it
        directly via ``DatabaseQueries.update_user_single_field`` without needing to
        manually instantiate ``DatabaseQueries`` with an already-connected
        ``Database`` instance.  Internally it takes care of opening a connection,
        executing the update, committing and finally closing the connection.
        """
        allowed_fields = [
            'full_name', 'phone', 'email', 'education', 'city', 'age', 'occupation', 'birth_date'
        ]
        if field_name not in allowed_fields:
            logging.warning(f"Attempted to update disallowed field '{field_name}'.")
            return False

        db = Database()
        if db.connect():
            try:
                db.execute(f"UPDATE users SET {field_name} = ? WHERE user_id = ?", (value, user_id))
                db.commit()
                return db.cursor.rowcount > 0
            except sqlite3.Error as e:
                logging.error(f"SQLite error when updating single field {field_name}: {e}")
                return False
            finally:
                db.close()
        return False

    def add_user_activity_log(self, telegram_id: int, action_type: str, details: str = None, user_id: int = None):
        """Add a user activity log."""
        now = datetime.now().isoformat()
        try:
            self.db.execute(
                "INSERT INTO user_activity_logs (user_id, telegram_id, action_type, timestamp, details) VALUES (?, ?, ?, ?, ?)",
                (user_id, telegram_id, action_type, now, details)
            )
            self.db.commit()
            return True
        except sqlite3.Error as e:
            logging.error(f"SQLite error when adding user activity log: {e}")
            return False

    def is_registered(self, user_id):
        """Instance method: check if a user has completed registration."""
        try:
            self.db.execute("SELECT full_name, phone FROM users WHERE user_id = ?", (user_id,))
            result = self.db.fetchone()
            if result:
                full_name_present = result['full_name'] is not None and str(result['full_name']).strip() != ""
                phone_present = result['phone'] is not None and str(result['phone']).strip() != ""
                return full_name_present and phone_present
        except (sqlite3.Error, IndexError, KeyError) as e:
            logging.error(f"Error checking registration status for user {user_id}: {e}")
        return False

    @staticmethod
    def get_user_by_phone(phone: str):
        """Return user row dict for given phone digits. Accepts phone with +98 or 0 prefix; only digits are compared."""
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) < 8:
            return None
        db = Database()
        if db.connect():
            try:
                # Use LIKE to match ending digits (handles country codes)
                db.execute("SELECT * FROM users WHERE REPLACE(REPLACE(phone, '+', ''), ' ', '') LIKE ? LIMIT 1", (f"%{digits}",))
                row = db.fetchone()
                return dict(row) if row else None
            except sqlite3.Error as e:
                logging.error(f"SQLite error in get_user_by_phone: {e}")
            finally:
                db.close()
        return None

    @staticmethod
    def is_registered_static(user_id):
        """Static helper so that code can call DatabaseQueries.is_registered(user_id)."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT full_name, phone FROM users WHERE user_id = ?", (user_id,))
                result = db.fetchone()
                if result:
                    full_name_present = result['full_name'] is not None and str(result['full_name']).strip() != ""
                    phone_present = result['phone'] is not None and str(result['phone']).strip() != ""
                    return full_name_present and phone_present
            except (sqlite3.Error, IndexError, KeyError) as e:
                logging.error(f"SQLite error in is_registered_static for user {user_id}: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def create_crypto_payment_request(
        user_id: int,
        rial_amount: float,
        usdt_amount_requested: float | None = None,
        wallet_address: str | None = None,
        expires_at: datetime | None = None,
        plan_id: int | None = None,
        discount_id: int | None = None,
        description: str = "Crypto payment",
    ):
        """Create a new *pending* crypto payment request in `crypto_payments` table.

        This wrapper keeps old callers intact while migrating the implementation
        to the dedicated `crypto_payments` table managed by the `database.models`
        module.  A UUID *payment_id* (TEXT) is generated and returned so the
        calling code can later use it for look-ups and verifications.
        """
        # We delegate the heavy-lifting to the Database singleton from
        # `database.models` to avoid duplicating SQL and make sure that the record
        # is created in **crypto_payments** (not in the legacy `payments` table).
        try:
            from database.models import Database as DBModel

            db_instance = DBModel.get_instance()

            if expires_at is None:
                # fall back to 24 hours from now if no explicit expiry provided
                expires_at = datetime.now() + timedelta(hours=24)

            payment_id = db_instance.create_crypto_payment_request(
                user_id=user_id,
                rial_amount=rial_amount,
                usdt_amount_requested=usdt_amount_requested or 0,
                wallet_address=wallet_address or "",
                expires_at=expires_at,
                plan_id=plan_id,
                discount_id=discount_id,
            )
            return payment_id
        except Exception as exc:
            logging.error(
                "create_crypto_payment_request wrapper failure: %s", exc, exc_info=True
            )
            return None

    @staticmethod
    def update_crypto_payment_request_with_amount(payment_request_id: str, usdt_amount: float) -> bool:
        """Update requested USDT amount for a pending crypto payment."""
        """Update the *requested* USDT amount for a pending crypto payment.

        Works on the `crypto_payments` table. Returns *True* when exactly one row
        was updated, otherwise *False*.
        """
        from database.models import Database as DBModel

        db = DBModel.get_instance()
        try:
            query = (
                "UPDATE crypto_payments "
                "SET usdt_amount_requested = ?, updated_at = ? "
                "WHERE payment_id = ? AND status = 'pending'"
            )
            params = (usdt_amount, datetime.now(), payment_request_id)
            if db.execute(query, params):
                db.commit()
                return db.cursor.rowcount == 1
        except Exception as exc:
            logging.error(
                "SQLite error in update_crypto_payment_request_with_amount: %s", exc
            )
        return False

    # -----------------------------------------------------------------------
    #  Helper: detect duplicate unique amount
    # -----------------------------------------------------------------------
    @staticmethod
    def crypto_payment_exists_with_amount(usdt_amount: float) -> bool:
        """Check if a *pending* crypto payment already uses *usdt_amount*."""
        from database.models import Database as DBModel
        db = DBModel.get_instance()
        try:
            query = (
                "SELECT 1 FROM crypto_payments "
                "WHERE status = 'pending' AND ABS(usdt_amount_requested - ?) < 0.000001 "
                "LIMIT 1"
            )
            if db.execute(query, (usdt_amount,)):
                return db.fetchone() is not None
        except Exception as exc:
            logging.error("SQLite error in crypto_payment_exists_with_amount: %s", exc)
        return False

    @staticmethod
    def update_crypto_payment_on_success(payment_id: str, transaction_id: str, usdt_amount_received: float, late: bool = False) -> bool:
        """Wrapper delegating to the singleton Database implementation for compatibility."""
        try:
            from database.models import Database as DBModel
            db_instance = DBModel.get_instance()
            return db_instance.update_crypto_payment_on_success(payment_id, transaction_id, usdt_amount_received, late=late)
        except Exception as exc:
            logging.error("Error in update_crypto_payment_on_success wrapper: %s", exc, exc_info=True)
            return False

    @staticmethod
    def update_payment_transaction_id(payment_id: int, transaction_id: str, status: str = "pending_verification"):
        """
        Updates the transaction ID and status of a payment record.
        Typically used for Zarinpal payments after getting an authority.
        """
        db = Database()
        if db.connect():
            try:
                # now_iso = datetime.now().isoformat() # Temporarily removed for updated_at
                db.execute(
                    "UPDATE payments SET transaction_id = ?, status = ? WHERE payment_id = ?",
                    (transaction_id, status, payment_id) # Temporarily removed now_iso
                )
                db.commit()
                return db.cursor.rowcount > 0  # Corrected to use db.cursor.rowcount
            except sqlite3.Error as e:
                config.logger.error(f"SQLite error in update_payment_transaction_id for payment_id {payment_id}: {e}")
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def get_payment_by_authority(authority: str):
        """
        Retrieves payment details from the database using the Zarinpal authority code.
        Args:
            authority: The Authority code provided by Zarinpal.
        Returns:
            A dictionary containing payment details (payment_id, user_id, plan_id, amount, status)
            if found, otherwise None.
        """
        db = Database()
        if db.connect():
            try:
                # Assuming 'transaction_id' stores the Zarinpal Authority and 'plan_id' column exists.
                # Also assuming 'payments' table has 'payment_method' to distinguish zarinpal payments
                db.execute(
                    """SELECT p.payment_id, p.user_id, p.plan_id, p.amount, p.status, p.discount_id
                       FROM payments p
                       WHERE p.transaction_id = ? AND p.payment_method = 'zarinpal'""",
                    (authority,)
                )
                result = db.fetchone()
                # Convert tuple to dict if result is not None
                if result:
                    columns = [desc[0] for desc in db.cursor.description]
                    return dict(zip(columns, result))
                return None
            except sqlite3.Error as e:
                config.logger.error(f"Database error in get_payment_by_authority for authority {authority}: {e}")
                return None
            finally:
                db.close()
        return None

    @staticmethod
    def update_payment_verification_status(payment_id: int, new_status: str, zarinpal_ref_id: str = None):
        """
        Updates the status of a payment after verification attempt and stores Zarinpal's RefID.
        Args:
            payment_id: The ID of the payment record.
            new_status: The new status (e.g., 'completed', 'failed', 'already_verified').
            zarinpal_ref_id: Zarinpal's final reference ID after successful verification.
                               Assumes a 'gateway_ref_id' column exists in the 'payments' table.
        """
        db = Database()
        if db.connect():
            try:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if zarinpal_ref_id:
                    db.execute(
                        """UPDATE payments
                           SET status = ?, gateway_ref_id = ?, updated_at = ?
                           WHERE payment_id = ?""",
                        (new_status, zarinpal_ref_id, now, payment_id)
                    )
                else:
                    db.execute(
                        """UPDATE payments
                           SET status = ?, updated_at = ?
                           WHERE payment_id = ?""",
                        (new_status, now, payment_id)
                    )
                db.commit()
                # Check if the update was successful
                return db.cursor.rowcount > 0
            except sqlite3.Error as e:
                config.logger.error(f"Database error in update_payment_verification_status for payment_id {payment_id}: {e}")
                return False
            finally:
                db.close()
        return False

    # Plan-related queries
    @staticmethod
    def get_active_plans():
        """Get all active subscription plans, ordered by display_order."""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT id, name, description, price, original_price_irr, price_tether, original_price_usdt, days, features, display_order, capacity, category_id FROM plans WHERE is_active = 1 ORDER BY display_order ASC, id ASC"
            )
            result = db.fetchall()
            db.close()
            return result
        return []

    @staticmethod
    def get_plan_by_id(plan_id):
        """Get plan details by its ID."""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT id, name, description, price, original_price_irr, price_tether, original_price_usdt, days, features, is_active, display_order FROM plans WHERE id = ?",
                (plan_id,)
            )
            result = db.fetchone()
            db.close()
            return result
        return None
    
    # Subscription-related queries
    @staticmethod
    def get_all_active_subscribers():
        """Get all users with an active subscription."""
        db = Database()
        if db.connect():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                "SELECT user_id FROM subscriptions WHERE status = 'active' AND end_date > ?",
                (now,)
            )
            result = db.fetchall()
            db.close()
            return result
        return []

    @staticmethod
    def get_subscription_stats():
        """Calculates and returns subscription statistics."""
        db = Database()
        if not db.connect():
            return {
                "total_users": 0,
                "active_subscribers": 0,
                "expired_subscribers": 0,
                "total_revenue_usdt": 0,
                "total_revenue_irr": 0,
            }
        
        try:
            cursor = db.conn.cursor()
            
            # Get current timestamp
            current_time = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
            
            # Total registered users
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            # Active subscribers (with time-based filtering)
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) FROM subscriptions 
                WHERE status = 'active' AND datetime(end_date) > datetime(?)
            """, (current_time,))
            active_subscribers = cursor.fetchone()[0]

            # Expired subscribers (includes both status and time)
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) FROM subscriptions 
                WHERE status != 'active' OR datetime(end_date) <= datetime(?)
            """, (current_time,))
            expired_subscribers = cursor.fetchone()[0]

            # Calculate total revenue properly
            total_revenue_usdt = 0.0
            total_revenue_irr = 0.0
            
            try:
                # USDT revenue from multiple sources
                # 1. From crypto_payments table (if exists and has data)
                try:
                    cursor.execute("""
                        SELECT SUM(usdt_amount_received) FROM crypto_payments 
                        WHERE status IN ('paid', 'completed', 'successful', 'verified')
                        AND usdt_amount_received IS NOT NULL
                    """)
                    result = cursor.fetchone()[0]
                    if result:
                        total_revenue_usdt += float(result)
                except sqlite3.OperationalError:
                    logging.debug("crypto_payments table not found or no usdt_amount_received column")
                
                # 2. From payments table USDT amounts (crypto payments recorded here)
                try:
                    cursor.execute("""
                        SELECT SUM(usdt_amount_requested) FROM payments
                        WHERE status IN ('paid', 'completed', 'successful', 'verified')
                        AND payment_method = 'crypto'
                        AND usdt_amount_requested IS NOT NULL
                    """)
                    result = cursor.fetchone()[0]
                    if result:
                        total_revenue_usdt += float(result)
                except sqlite3.OperationalError:
                    logging.debug("payments table usdt_amount_requested column not found")
                
                # IRR revenue from payments table
                # This includes both regular IRR payments and IRR equivalent of crypto payments
                try:
                    cursor.execute("""
                        SELECT SUM(amount) FROM payments 
                        WHERE status IN ('paid', 'completed', 'successful', 'verified')
                        AND amount IS NOT NULL
                        AND amount > 0
                    """)
                    result = cursor.fetchone()[0]
                    if result:
                        total_revenue_irr = float(result)
                except sqlite3.OperationalError:
                    logging.debug("payments table amount column not found")
                    
                # Also check crypto_payments for IRR amounts
                try:
                    cursor.execute("""
                        SELECT SUM(rial_amount) FROM crypto_payments
                        WHERE status IN ('paid', 'completed', 'successful', 'verified')
                        AND rial_amount IS NOT NULL
                        AND rial_amount > 0
                    """)
                    result = cursor.fetchone()[0]
                    if result:
                        total_revenue_irr += float(result)
                except sqlite3.OperationalError:
                    logging.debug("crypto_payments table rial_amount column not found")
                    
            except Exception as e:
                logging.error(f"Error calculating revenue: {e}")
                pass

            return {
                "total_users": total_users,
                "active_subscribers": active_subscribers,
                "expired_subscribers": expired_subscribers,
                "total_revenue_usdt": total_revenue_usdt,
                "total_revenue_irr": total_revenue_irr,
            }
            
        except sqlite3.Error as e:
            logging.error(f"SQLite error in get_subscription_stats: {e}")
            return {
                "total_users": 0,
                "active_subscribers": 0,
                "expired_subscribers": 0,
                "total_revenue_usdt": 0,
                "total_revenue_irr": 0,
            }
        finally:
            db.close()

    @staticmethod
    def get_all_registered_users():
        """Fetch all users that have ever registered (row exists in users table). Returns list of rows with at least user_id column."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT user_id FROM users")
                result = db.fetchall()
                db.close()
                return result
            except sqlite3.Error as exc:
                logging.error("SQLite error in get_all_registered_users: %s", exc)
                if db.conn:
                    db.conn.rollback()
                db.close()
                return []
        return []

    @staticmethod
    def has_active_subscription(user_id: int) -> bool:
        """Check if a user has an active, non-expired subscription."""
        db = Database()
        if db.connect():
            try:
                # Use current time that is timezone-aware
                current_time = get_current_time()
                query = """
                    SELECT 1 FROM subscriptions
                    WHERE user_id = ? AND end_date > ? AND status = 'active'
                    LIMIT 1
                """
                db.execute(query, (user_id, current_time))
                result = db.fetchone()
                return result is not None
            except sqlite3.Error as e:
                logging.error(f"Database error in has_active_subscription for user {user_id}: {e}")
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def get_users_with_non_active_subscription_records():
        """Get users with non-active (expired, cancelled, etc.) subscription records."""
        db = Database()
        if db.connect():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                "SELECT user_id, status FROM subscriptions WHERE status != 'active' OR end_date <= ?",
                (now,)
            )
    @staticmethod
    def _update_existing_subscription(subscription_id, plan_id, payment_id, new_end_date_str, amount_paid, payment_method, status='active'):
        """
        Helper function to update an existing subscription record.
        This is typically called when a user renews or extends an active subscription.
        """
        db = Database()
        if db.connect():
            try:
                db.execute(
                    """UPDATE subscriptions
                       SET plan_id = ?,
                           payment_id = ?,
                           end_date = ?,
                           amount_paid = ?,
                           payment_method = ?,
                           status = ?,
                           updated_at = ?
                       WHERE id = ?""",
                    (plan_id, payment_id, new_end_date_str, amount_paid, payment_method, status, 
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"), subscription_id)
                )
                db.commit()
                return True
            except sqlite3.Error as e:
                print(f"Error updating subscription {subscription_id}: {e}")
                return False
            except Exception as e:
                print(f"Unexpected error updating subscription {subscription_id}: {e}")
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def count_total_subs(plan_id: int) -> int:
        """Return total number of active subscription records for the specified plan."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT COUNT(*) FROM subscriptions WHERE plan_id = ? AND status = 'active'"
                if db.execute(query, (plan_id,)):
                    result = db.fetchone()
                    return result[0] if result else 0
            except sqlite3.Error as e:
                print(f"SQLite error in count_total_subs: {e}")
            finally:
                db.close()
        return 0

    # -----------------------------------
    # Additional subscription helpers
    # -----------------------------------
    @staticmethod
    def get_user_active_subscription(user_id: int):
        """Return the currently active subscription row for a user, or None."""
        db = Database()
        if db.connect():
            try:
                query = """
                    SELECT * FROM subscriptions
                     WHERE user_id = ? AND status = 'active'
                  ORDER BY end_date DESC LIMIT 1
                """
                db.execute(query, (user_id,))
                return db.fetchone()
            except sqlite3.Error as exc:
                logging.error("SQLite error in get_user_active_subscription: %s", exc)
            finally:
                db.close()
        return None

    @staticmethod
    def get_all_active_subscribers():
        """Return list of users that have at least one active subscription."""
        db = Database()
        if db.connect():
            try:
                query = """
                    SELECT DISTINCT u.user_id, u.full_name, u.username
                      FROM users u
                      JOIN subscriptions s ON u.user_id = s.user_id
                     WHERE s.status = 'active' AND datetime(s.end_date) > datetime('now')
                """
                if db.execute(query):
                    return db.fetchall()
            except sqlite3.Error as exc:
                logging.error("SQLite error in get_all_active_subscribers: %s", exc)
            finally:
                db.close()
        return []

    @staticmethod
    def get_active_plans():
        """Return list of plans that are marked active."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT id, name FROM plans WHERE is_active = 1 ORDER BY display_order"
                if db.execute(query):
                    return db.fetchall()
            except sqlite3.Error as exc:
                logging.error("SQLite error in get_active_plans: %s", exc)
            finally:
                db.close()
        return []

    @staticmethod
    def add_subscription(user_id: int, plan_id: int, payment_id: int, 
                     plan_duration_days: int, amount_paid: float, 
                     payment_method: str, status: str = 'active'):
        """
        Adds a new subscription or extends an existing active one for a user.
        If an active subscription exists, its end_date is extended.
        Otherwise, a new subscription record is created.

        Args:
            user_id: The ID of the user.
            plan_id: The ID of the subscription plan.
            payment_id: The ID of the payment record associated with this subscription/renewal.
            plan_duration_days: The duration of the plan in days.
            amount_paid: The amount paid for this specific transaction.
            payment_method: The method used for this payment (e.g., 'rial', 'tether').
            status: The status of the subscription, defaults to 'active'.

        Returns:
            The ID of the created or updated subscription record, or None on failure.
        """
        # Check 120-day limit before adding subscription if enabled
        limit_enabled = DatabaseQueries.get_setting("enable_120_day_limit", "1") == "1"
        if limit_enabled:
            current_remaining_days = DatabaseQueries.get_user_remaining_subscription_days(user_id)
            total_days_after_purchase = current_remaining_days + plan_duration_days
            
            if total_days_after_purchase > 120:
                logging.error(f"add_subscription blocked for user {user_id}: would exceed 120-day limit. Current: {current_remaining_days}, Plan: {plan_duration_days}, Total: {total_days_after_purchase}")
                return None
        
        db = Database()
        if not db.connect():
            print(f"Failed to connect to database in add_subscription for user {user_id}")
            return None

        try:
            print(f"DEBUG: add_subscription called with user_id={user_id}, plan_id={plan_id}, payment_id={payment_id}")
            
            current_active_sub = DatabaseQueries.get_user_active_subscription(user_id) 
            print(f"DEBUG: Current active subscription: {current_active_sub}")
            
            now_dt = datetime.now()
            
            if current_active_sub:
                current_end_date_str = current_active_sub['end_date']
                try:
                    current_end_date_dt = datetime.strptime(current_end_date_str, "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError) as e:
                    print(f"Error parsing current_end_date '{current_end_date_str}' for user {user_id}: {e}. Treating as no active sub.")
                    current_active_sub = None

                if current_active_sub and current_end_date_dt > now_dt:
                    start_point_for_new_duration = current_end_date_dt
                else:
                    start_point_for_new_duration = now_dt
                
                new_end_date_dt = start_point_for_new_duration + timedelta(days=plan_duration_days)
                new_end_date_str = new_end_date_dt.strftime("%Y-%m-%d %H:%M:%S")

                print(f"DEBUG: Updating existing subscription {current_active_sub['id']} with new end date {new_end_date_str}")
                
                if DatabaseQueries._update_existing_subscription(
                    subscription_id=current_active_sub['id'],
                    plan_id=plan_id,
                    payment_id=payment_id,
                    new_end_date_str=new_end_date_str,
                    amount_paid=amount_paid,
                    payment_method=payment_method,
                    status=status
                ):
                    print(f"DEBUG: Successfully updated subscription {current_active_sub['id']}")
                    return current_active_sub['id']
                else:
                    print(f"Failed to update existing subscription for user {user_id}.")
                    return None
            else:
                start_date_dt = now_dt
                end_date_dt = start_date_dt + timedelta(days=plan_duration_days)
                
                start_date_str = start_date_dt.strftime("%Y-%m-%d %H:%M:%S")
                end_date_str = end_date_dt.strftime("%Y-%m-%d %H:%M:%S")

                print(f"DEBUG: Creating new subscription - start: {start_date_str}, end: {end_date_str}")

                db.execute(
                    """INSERT INTO subscriptions 
                       (user_id, plan_id, payment_id, start_date, end_date, amount_paid, status, payment_method, created_at, updated_at) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (user_id, plan_id, payment_id, start_date_str, end_date_str, amount_paid, status, 
                     payment_method, now_dt.strftime("%Y-%m-%d %H:%M:%S"), now_dt.strftime("%Y-%m-%d %H:%M:%S"))
                )
                subscription_id = db.cursor.lastrowid
                print(f"DEBUG: Inserted new subscription with ID: {subscription_id}")
                
                db.commit()
                print(f"DEBUG: Committed transaction for subscription {subscription_id}")
                
                return subscription_id
        except sqlite3.Error as e:
            print(f"Database error in add_subscription for user {user_id}: {e}")
            if db.conn:
                db.conn.rollback()  # Use the connection object for rollback
            return None
        except Exception as e:
            print(f"Unexpected error in add_subscription for user {user_id}: {e}")
            if db.conn:
                db.conn.rollback()  # Use the connection object for rollback
            return None
        finally:
            db.close()
    
    @staticmethod
    def get_subscription(subscription_id):
        """Get subscription details"""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT * FROM subscriptions WHERE id = ?",
                (subscription_id,)
            )
            result = db.fetchone()
            db.close()
            return result
        return None

    # ---- Free Plan Helper Methods ----
    @staticmethod
    def has_user_used_free_plan(user_id: int, plan_id: int) -> bool:
        """Return True if the user has already subscribed to the given plan (whether active or expired)."""
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "SELECT 1 FROM subscriptions WHERE user_id = ? AND plan_id = ? LIMIT 1",
                    (user_id, plan_id),
                )
                return db.fetchone() is not None
            except sqlite3.Error as e:
                logging.error(f"SQLite error in has_user_used_free_plan: {e}")
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def count_total_subscriptions_for_plan(plan_id: int) -> int:
        """Return total number of subscription records for the specified plan."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT COUNT(*) AS cnt FROM subscriptions WHERE plan_id = ?", (plan_id,))
                row = db.fetchone()
                return (row['cnt'] if isinstance(row, sqlite3.Row) else row[0]) if row else 0
            except sqlite3.Error as e:
                logging.error(f"SQLite error in count_total_subscriptions_for_plan: {e}")
                return 0
            finally:
                db.close()
        return 0

    @staticmethod
    def deactivate_plan(plan_id: int) -> bool:
        """Set is_active = 0 for the given plan. Returns True if a row was affected."""
        db = Database()
        if db.connect():
            try:
                db.execute("UPDATE plans SET is_active = 0 WHERE id = ?", (plan_id,))
                db.commit()
                return db.cursor.rowcount > 0
            except sqlite3.Error as e:
                logging.error(f"SQLite error in deactivate_plan: {e}")
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def get_plan_by_id(plan_id: int):
        """Fetch a plan row by its ID."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
                result = db.fetchone()
                db.close()
                return dict(result) if result else None
            except sqlite3.Error as e:
                logging.error(f"SQLite error in get_plan_by_id: {e}")
                return None
            finally:
                db.close()
        return None

    # ------------------------------------------------------------------
    # Support users helpers
    # ------------------------------------------------------------------
    @staticmethod
    def get_all_support_users():
        """Return list of rows for all registered support users."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT telegram_id FROM support_users")
                fetched = db.fetchall()
                db.close()
                # Convert to simple list[int] regardless of row factory
                ids: list[int] = []
                for item in fetched or []:
                    try:
                        if isinstance(item, (tuple, list)):
                            ids.append(int(item[0]))
                        else:
                            # sqlite3.Row or dict-like
                            ids.append(int(item["telegram_id"]))
                    except (KeyError, IndexError, TypeError, ValueError):
                        continue
                return ids
            except Exception as exc:
                logging.error("SQLite error in get_all_support_users: %s", exc)
                return []
            finally:
                db.close()
        return []

    @staticmethod
    def add_support_user(telegram_id: int, added_by: int | None = None) -> bool:
        """Add a support user to the DB. Returns True if a new row was inserted."""
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "INSERT OR IGNORE INTO support_users (telegram_id, added_by) VALUES (?, ?)",
                    (telegram_id, added_by),
                )
                db.commit()
                affected = db.cursor.rowcount  # 1 if inserted, 0 if already existed
                db.close()
                return affected > 0
            except Exception as exc:
                logging.error("SQLite error in add_support_user: %s", exc)
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def remove_support_user(telegram_id: int) -> bool:
        """Remove support user. Returns True if a row was deleted."""
        db = Database()
        if db.connect():
            try:
                db.execute("DELETE FROM support_users WHERE telegram_id = ?", (telegram_id,))
                db.commit()
                affected = db.cursor.rowcount
                db.close()
                return affected > 0
            except Exception as exc:
                logging.error("SQLite error in remove_support_user: %s", exc)
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def is_support_user(telegram_id: int) -> bool:
        """Return True if telegram_id exists in support_users table and is active."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT 1 FROM support_users WHERE telegram_id = ?", (telegram_id,))
                result = db.fetchone()
                db.close()
                return bool(result)
            except Exception as exc:
                logging.error("SQLite error in is_support_user: %s", exc)
                return False
            finally:
                db.close()
        return False
    
    @staticmethod
    def is_mid_level_user(telegram_id: int) -> bool:
        """Return True if telegram_id exists in mid_level_users table and is active."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT 1 FROM mid_level_users WHERE telegram_id = ?", (telegram_id,))
                result = db.fetchone()
                db.close()
                return bool(result)
            except Exception as exc:
                logging.error("SQLite error in is_mid_level_user: %s", exc)
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def add_mid_level_user(telegram_id: int, alias: str = "") -> bool:
        """Add a user to mid_level_users table."""
        db = Database()
        if not db.connect():
            return False
        try:
            # First check if user already exists
            db.execute("SELECT 1 FROM mid_level_users WHERE telegram_id = ?", (telegram_id,))
            if db.fetchone():
                logging.info(f"User {telegram_id} is already a mid-level user")
                return True
            
            # Add the user
            current_time = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                "INSERT INTO mid_level_users (telegram_id, alias, created_at) VALUES (?, ?, ?)",
                (telegram_id, alias, current_time)
            )
            db.commit()
            logging.info(f"Added user {telegram_id} as mid-level user")
            return True
        except Exception as exc:
            logging.error(f"Error adding mid-level user {telegram_id}: {exc}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def remove_mid_level_user(telegram_id: int) -> bool:
        """Remove a user from mid_level_users table."""
        db = Database()
        if not db.connect():
            return False
        try:
            db.execute("DELETE FROM mid_level_users WHERE telegram_id = ?", (telegram_id,))
            db.commit()
            deleted = db.cursor.rowcount > 0
            if deleted:
                logging.info(f"Removed user {telegram_id} from mid-level users")
            else:
                logging.info(f"User {telegram_id} was not a mid-level user")
            return True
        except Exception as exc:
            logging.error(f"Error removing mid-level user {telegram_id}: {exc}")
            return False
        finally:
            db.close()

    @staticmethod
    def get_all_mid_level_users() -> list:
        """Get all mid-level users."""
        db = Database()
        if not db.connect():
            return []
        try:
            db.execute("SELECT telegram_id, alias, created_at FROM mid_level_users ORDER BY created_at DESC")
            return [dict(row) for row in db.fetchall()]
        except Exception as exc:
            logging.error(f"Error getting mid-level users: {exc}")
            return []
        finally:
            db.close()

    # ---- User Subscription Summary Helpers ----
    @staticmethod
    def get_plan(plan_id: int):
        """Return a single plan row (dict) by its ID or None."""
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
                row = db.fetchone()
                db.close()
                return row
            except Exception as exc:
                logging.error("SQLite error in get_plan: %s", exc)
            finally:
                db.close()
        return None

    @staticmethod
    def _ensure_user_summary_columns():
        """Ensures that `users` table has the summary columns. If not, add them with ALTER TABLE."""
        db = Database()
        if not db.connect():
            return False
        try:
            db.execute("PRAGMA table_info(users)")
            cols = [row['name'] for row in db.fetchall()]
            needed = []
            if 'total_subscription_days' not in cols:
                needed.append("ALTER TABLE users ADD COLUMN total_subscription_days INTEGER DEFAULT 0")
            if 'subscription_expiration_date' not in cols:
                needed.append("ALTER TABLE users ADD COLUMN subscription_expiration_date TEXT")
            for stmt in needed:
                db.execute(stmt)
            if needed:
                db.commit()
        except sqlite3.Error as e:
            logging.error(f"SQLite error ensuring user summary columns: {e}")
        finally:
            db.close()
        return True

    @staticmethod
    def get_user_subscription_summary(user_id: int):
        """Return total days and expiration date for a user from `users` table (may return None)."""
        DatabaseQueries._ensure_user_summary_columns()
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT total_subscription_days, subscription_expiration_date FROM users WHERE user_id = ?", (user_id,))
                return db.fetchone()
            except sqlite3.Error as e:
                logging.error(f"SQLite error in get_user_subscription_summary: {e}")
                return None
            finally:
                db.close()
        return None

    @staticmethod
    def update_user_subscription_summary(user_id: int, total_days: int, expiration_date: str) -> bool:
        """Update summary columns for user."""
        DatabaseQueries._ensure_user_summary_columns()
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "UPDATE users SET total_subscription_days = ?, subscription_expiration_date = ? WHERE user_id = ?",
                    (total_days, expiration_date, user_id),
                )
                db.commit()
                return db.cursor.rowcount > 0
            except sqlite3.Error as e:
                logging.error(f"SQLite error in update_user_subscription_summary: {e}")
                return False
            finally:
                db.close()
        return False

    def get_user_active_subscription(user_id):
        """Get user's active subscription.
           Returns the one with the latest end_date if multiple somehow exist.
        """
        db = Database()
        if db.connect():
            # Use Tehran timezone aware "now" to avoid offset issues
            now_str = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
            
            try:
                db.execute(
                    """SELECT s.id, s.user_id, s.plan_id, s.payment_id, 
                              s.start_date, s.end_date, s.amount_paid, s.payment_method, 
                              s.status, s.created_at, s.updated_at,
                              p.name as plan_name, p.days as plan_duration_config_days
                       FROM subscriptions s
                       JOIN plans p ON s.plan_id = p.id
                       WHERE s.user_id = ? AND s.status = 'active' AND s.end_date > ?
                       ORDER BY s.end_date DESC LIMIT 1""",
                    (user_id, now_str)
                )
                result = db.fetchone()
                return result
            except sqlite3.Error as e:
                print(f"Database error in get_user_active_subscription for user {user_id}: {e}")
                return None
            finally:
                db.close()
        return None

    @staticmethod
    def get_user_remaining_subscription_days(user_id: int):
        """Calculate total remaining subscription days for a user.
        Returns the number of days from now until the latest subscription end date.
        Returns 0 if no active subscription.
        """
        db = Database()
        if db.connect():
            from datetime import datetime
            now_str = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
            
            try:
                # Get the latest active subscription end date
                db.execute(
                    """SELECT MAX(end_date) as latest_end_date
                       FROM subscriptions 
                       WHERE user_id = ? AND status = 'active' AND end_date > ?""",
                    (user_id, now_str)
                )
                result = db.fetchone()
                
                if result and result['latest_end_date']:
                    # Calculate days between now and end date
                    end_date = datetime.strptime(result['latest_end_date'], "%Y-%m-%d %H:%M:%S")
                    now = datetime.strptime(now_str, "%Y-%m-%d %H:%M:%S")
                    remaining_days = (end_date - now).days
                    return max(0, remaining_days)  # Return 0 if negative
                return 0
            except sqlite3.Error as e:
                logging.error(f"Error calculating remaining subscription days for user {user_id}: {e}")
                return 0
            finally:
                db.close()
        return 0

    @staticmethod
    def get_open_tickets():
        """Fetch all tickets with 'open' or 'pending_admin_reply' status."""
        db = Database()
        tickets = []
        if db.connect():
            try:
                # Query to fetch tickets and join with users table to get full_name
                # Adjust column names (t.message, u.full_name) as per your actual schema
                query = """
                    SELECT t.id as ticket_id, t.user_id, u.full_name as user_name, 
                           t.subject as subject, t.status, t.created_at
                    FROM tickets t
                    JOIN users u ON t.user_id = u.user_id
                    WHERE t.status IN ('open', 'pending_admin_reply')
                    ORDER BY t.created_at ASC;
                """
                db.execute(query)
                rows = db.fetchall()
                if rows:
                    column_names = [desc[0] for desc in db.cursor.description]
                    for row in rows:
                        tickets.append(dict(zip(column_names, row)))
            except sqlite3.Error as e:
                print(f"SQLite error in get_open_tickets: {e}")
                # Log error
            finally:
                db.close()
        return tickets

    @staticmethod
    def get_all_tickets():
        """Fetch all tickets regardless of status for admin view."""
        db = Database()
        tickets = []
        if db.connect():
            try:
                query = """
                    SELECT t.id as ticket_id, t.user_id, u.full_name as user_name,
                           t.subject as subject, t.status, t.created_at
                    FROM tickets t
                    JOIN users u ON t.user_id = u.user_id
                    ORDER BY t.created_at DESC;
                """
                db.execute(query)
                rows = db.fetchall()
                if rows:
                    column_names = [desc[0] for desc in db.cursor.description]
                    for row in rows:
                        tickets.append(dict(zip(column_names, row)))
            except sqlite3.Error as e:
                print(f"SQLite error in get_all_tickets: {e}")
            finally:
                db.close()
        return tickets

    @staticmethod
    def get_ticket_details(ticket_id):
        """Fetch details for a specific ticket, including its messages."""
        db = Database()
        ticket_data = None
        if db.connect():
            try:
                # Fetch ticket main info
                db.execute("""
                    SELECT t.id as ticket_id, t.user_id, u.full_name as user_name, 
                           t.subject, t.status, t.created_at
                    FROM tickets t
                    JOIN users u ON t.user_id = u.user_id
                    WHERE t.id = ?;
                """, (ticket_id,))
                main_info_row = db.fetchone()
                
                if main_info_row:
                    ticket_data = {}
                    column_names = [desc[0] for desc in db.cursor.description]
                    ticket_data = dict(zip(column_names, main_info_row))

                    # Fetch ticket messages
                    db.execute("""
                        SELECT tm.id as message_id, tm.user_id, tm.message, tm.timestamp, tm.is_admin
                        FROM ticket_messages tm
                        WHERE tm.ticket_id = ?
                        ORDER BY tm.timestamp ASC;
                    """, (ticket_id,))
                    
                    messages_rows = db.fetchall()
                    messages = []
                    if messages_rows:
                        msg_column_names = [desc[0] for desc in db.cursor.description]
                        for msg_row in messages_rows:
                            messages.append(dict(zip(msg_column_names, msg_row)))
                    ticket_data['messages'] = messages

            except sqlite3.Error as e:
                print(f"SQLite error in get_ticket_details for ticket_id {ticket_id}: {e}")
                ticket_data = None # Indicate failure
            finally:
                db.close()
        return ticket_data

    @staticmethod
    def add_ticket_message(ticket_id, user_id, message, is_admin_message=False, update_status=True):
        """Adds a message to a ticket and optionally updates ticket's status and updated_at."""
        db = Database()
        success = False
        if db.connect():
            try:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                db.execute("""
                    INSERT INTO ticket_messages (ticket_id, user_id, message, timestamp, is_admin)
                    VALUES (?, ?, ?, ?, ?);
                """, (ticket_id, user_id, message, now, 1 if is_admin_message else 0))
                
                if update_status:
                    new_status = 'pending_user_reply' if is_admin_message else 'pending_admin_reply'
                    db.execute("UPDATE tickets SET status = ? WHERE id = ?;", (new_status, ticket_id))

                db.commit()
                success = True
            except sqlite3.Error as e:
                print(f"SQLite error in add_ticket_message for ticket_id {ticket_id}: {e}")
                if db.conn:
                    db.conn.rollback()  # Use the connection object for rollback
            finally:
                db.close()
        return success
        return success

    @staticmethod
    def update_ticket_status(ticket_id, new_status):
        """Updates the status of a ticket."""
        db = Database()
        success = False
        if db.connect():
            try:
                # now = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # If also updating updated_at
                # db.execute("UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?;", 
                #            (new_status, now, ticket_id))
                db.execute("UPDATE tickets SET status = ? WHERE id = ?;", (new_status, ticket_id))
                db.commit()
                success = True
            except sqlite3.Error as e:
                print(f"SQLite error in update_ticket_status for ticket_id {ticket_id}: {e}")
                if db.conn:
                    db.conn.rollback()
            finally:
                db.close()
        return success

    @staticmethod
    def get_all_active_subscribers():
        """Get all users with active subscriptions"""
        db = Database()
        if db.connect():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                """SELECT u.user_id, u.full_name, u.username, u.phone, s.start_date, s.end_date, p.name as plan_name
                FROM subscriptions s
                JOIN users u ON s.user_id = u.user_id
                JOIN plans p ON s.plan_id = p.id
                WHERE s.status = 'active' AND s.end_date > ?
                ORDER BY s.end_date ASC""",
                (now,)
            )
            result = db.fetchall()
            db.close()
            return result
        return []
    
    # Payment-related queries
    @staticmethod
    def add_payment(user_id, amount, payment_method, description=None, transaction_id=None, status="pending", plan_id=None, discount_id: int | None = None, *, expires_at: datetime | None = None):
        """Add a new payment record.

        Args:
            user_id: ID of the purchaser (telegram_id).
            amount: Amount in IRR to be paid.
            payment_method: e.g. 'zarinpal', 'crypto'.
            description: Optional textual description.
            transaction_id: Gateway authority / pre-payment token if available.
            status: Initial status, default 'pending'.
            plan_id: Related subscription plan.
            expires_at: Optional expiration `datetime`.  When provided it will be stored in the
                        `expires_at` column so that verification handlers can enforce link
                        expiration.
        """
        db = Database()
        if db.connect():
            now_iso = datetime.now().isoformat()
            expires_at_iso = expires_at.isoformat() if expires_at else None
            # Use explicit column list for forward-compatibility.
            db.execute(
                """INSERT INTO payments 
                    (user_id, plan_id, amount, discount_id, payment_date, payment_method, transaction_id, description, status, expires_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    plan_id,
                    amount,
                    discount_id,
                    now_iso,            # payment_date
                    payment_method,
                    transaction_id,
                    description,
                    status,
                    expires_at_iso,
                    now_iso,            # created_at
                    now_iso,            # updated_at
                ),
            )
            payment_id = db.cursor.lastrowid
            db.commit()
            db.close()
            return payment_id
        return None
    
    @staticmethod
    def create_payment(user_id: int, plan_id: int, amount: float, payment_method: str, status: str = "pending", description: str = None, transaction_id: str = None):
        """Backwards compatible alias expected by some handlers."""
        return DatabaseQueries.add_payment(
            user_id=user_id,
            amount=amount,
            payment_method=payment_method,
            description=description,
            transaction_id=transaction_id,
            status=status,
            plan_id=plan_id,
        )

    @staticmethod
    def get_payment(payment_id):
        """Get payment details by its primary key `payment_id`. (Legacy alias for `get_payment_by_id`.)"""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT * FROM payments WHERE payment_id = ?",
                (payment_id,)
            )
            result = db.fetchone()
            db.close()
            # Convert Row to dictionary for .get() method compatibility
            return dict(result) if result else None
        return None
    
    @staticmethod
    def get_payment_by_id(payment_id):
        """Alias for `get_payment` so existing handlers calling this name work."""
        return DatabaseQueries.get_payment(payment_id)
    
    @staticmethod
    def update_payment_expires_at(payment_id: int, expires_at: datetime):
        """Set/Update the *expires_at* timestamp for a payment row."""
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "UPDATE payments SET expires_at = ?, updated_at = ? WHERE payment_id = ?",
                    (expires_at.isoformat(), datetime.now().isoformat(), payment_id),
                )
                db.commit()
                return db.cursor.rowcount > 0
            except sqlite3.Error as e:
                config.logger.error(f"SQLite error in update_payment_expires_at for payment_id {payment_id}: {e}")
                return False
            finally:
                db.close()
        return False

    @staticmethod
    def update_payment_status(payment_id, status, transaction_id=None, error_message=None):
        """Update payment status and optionally an error message in description."""
        db = Database()
        if db.connect():
            sql_query = "UPDATE payments SET status = ?"
            params = [status]

            if transaction_id:
                sql_query += ", transaction_id = ?"
                params.append(transaction_id)
        
            if error_message:
                sql_query += ", description = ?"
                params.append(error_message)
        
            sql_query += " WHERE payment_id = ?"
            params.append(payment_id)

            db.execute(sql_query, tuple(params))
            db.commit()
            db.close()
            return True
        return False
    # Plan-related queries

    @staticmethod
    def get_active_plans():
        """Get all active subscription plans, ordered by display_order."""
        db = Database()
        if db.connect():
            now_str = get_current_time().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                """
                SELECT * FROM plans 
                WHERE is_active = 1 
                AND (expiration_date IS NULL OR expiration_date = '' OR expiration_date > ?)
                ORDER BY display_order
                """,
                (now_str,)
            )
            result = db.fetchall()
            db.close()
            return result
        return []

    @staticmethod
    def count_subscriptions_for_plan(plan_id):
        """Count the number of active subscriptions for a given plan."""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT COUNT(id) FROM subscriptions WHERE plan_id = ? AND status = 'active'",
                (plan_id,)
            )
            count = db.fetchone()[0]
            db.close()
            return count
        return 0

    @staticmethod
    def has_user_subscribed_to_plan(user_id, plan_id):
        """Check if a user has an active subscription to a specific plan."""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT 1 FROM subscriptions WHERE user_id = ? AND plan_id = ? AND status = 'active'",
                (user_id, plan_id)
            )
            result = db.fetchone()
            db.close()
            return result is not None
        return False

    # Support ticket queries
    @staticmethod
    def create_ticket(user_id, subject, message):
        """Create a new support ticket"""
# ... (rest of the code remains the same)
        db = Database()
        if db.connect():
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                """INSERT INTO tickets 
                (user_id, subject, created_at, status) 
                VALUES (?, ?, ?, 'open')""",
                (user_id, subject, now)
            )
            ticket_id = db.cursor.lastrowid
            
            # Add initial message
            db.execute(
                """INSERT INTO ticket_messages 
                (ticket_id, user_id, message, timestamp, is_admin) 
                VALUES (?, ?, ?, ?, 0)""",
                (ticket_id, user_id, message, now)
            )
            
            db.commit()
            db.close()
            return ticket_id
        return None
    
    @staticmethod
    def get_user_tickets(user_id):
        """Get all tickets created by a user"""
        db = Database()
        if db.connect():
            db.execute(
                """SELECT * FROM tickets 
                WHERE user_id = ? 
                ORDER BY created_at DESC""",
                (user_id,)
            )
            result = db.fetchall()
            db.close()
            return result
        return []
    
    @staticmethod
    def get_ticket(ticket_id):
        """Get ticket details"""
        db = Database()
        if db.connect():
            db.execute(
                "SELECT * FROM tickets WHERE id = ?",
                (ticket_id,)
            )
            result = db.fetchone()
            db.close()
            return result
        return None
    
    @staticmethod
    def get_ticket_messages(ticket_id):
        """Get all messages for a ticket"""
        db = Database()
        if db.connect():
            db.execute(
                """SELECT tm.*, u.full_name, u.username 
                FROM ticket_messages tm
                LEFT JOIN users u ON tm.user_id = u.user_id
                WHERE tm.ticket_id = ? 
                ORDER BY tm.timestamp ASC""",
                (ticket_id,)
            )
            result = db.fetchall()
            db.close()
            return result
        return []
    

    
    @staticmethod
    def update_ticket_status(ticket_id, status):
        """Update ticket status"""
        db = Database()
        if db.connect():
            db.execute(
                "UPDATE tickets SET status = ? WHERE id = ?",
                (status, ticket_id)
            )
            db.commit()
            db.close()
            return True
        return False
    
    @staticmethod
    def has_user_used_free_plan(user_id, plan_id):
        """Check if the user has ever had a subscription for a specific free plan."""
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "SELECT 1 FROM subscriptions WHERE user_id = ? AND plan_id = ?",
                    (user_id, plan_id)
                )
                result = db.fetchone()
                return result is not None
            finally:
                db.close()
        return False

    @staticmethod
    def count_total_subscriptions_for_plan(plan_id):
        """Count the total number of subscriptions ever created for a given plan."""
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "SELECT COUNT(id) FROM subscriptions WHERE plan_id = ?",
                    (plan_id,)
                )
                count = db.fetchone()[0]
                return count
            finally:
                db.close()
        return 0

    @staticmethod
    def deactivate_plan(plan_id):
        """Deactivates a plan by setting its is_active flag to False."""
        db = Database()
        if db.connect():
            try:
                db.execute(
                    "UPDATE plans SET is_active = 0 WHERE id = ?",
                    (plan_id,)
                )
                db.commit()
                return True
            finally:
                db.close()
        return False

    @staticmethod
    def get_open_tickets():
        """Get all open tickets"""
        db = Database()
        if db.connect():
            db.execute(
                """SELECT t.*, u.full_name, u.username, u.phone
                FROM tickets t
                JOIN users u ON t.user_id = u.user_id
                WHERE t.status = 'open'
                ORDER BY t.created_at ASC"""
            )
            result = db.fetchall()
            db.close()
            return result
        return []
        


    @staticmethod
    def get_users_with_non_active_subscription_records():
        """Fetches users with non-active (e.g., expired, cancelled) subscription records."""
        db = Database()
        users = []
        if db.connect():
            try:
                # Assuming 'active' is the status for an active subscription.
                # Adjust the query if your status column or 'active' value is different.
                # This query selects distinct user_ids to avoid processing the same user multiple times
                # if they have multiple non-active records.
                # It also ensures status is not NULL or empty.
                query = """
                    SELECT DISTINCT u.user_id,
                           COALESCE(s.status, 'no_subscription') AS status
                    FROM users u
                    LEFT JOIN subscriptions s
                          ON s.user_id = u.user_id
                          AND s.status = 'active'
                          AND s.end_date > ?
                    WHERE s.user_id IS NULL          -- user has no active subscription
                       OR s.status IS NULL           -- safety check
                       OR s.status != 'active'
                       OR s.end_date <= ?
                """
                # Note: If a user has NO record in the subscriptions table at all,
                # they won't be caught by this query. This query targets users
                # who HAD a subscription that is now in a non-active state.
                # To catch users in the 'users' table but not in 'subscriptions',
                # a more complex query (e.g., LEFT JOIN) would be needed.
                
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                db.execute(query, (current_time, current_time))
                records = db.fetchall()
                for row in records:
                    users.append({'user_id': row[0], 'status': row[1]})
                # self.logger.debug(f"DB: Found {len(users)} users with non-active subscriptions.") # Use logger if available
            except sqlite3.Error as e:
                # Consider using a logger here instead of print for consistency
                print(f"SQLite error in get_users_with_non_active_subscription_records: {e}")
            finally:
                db.close()
        return users
    



        
    @staticmethod
    def close_ticket(ticket_id, admin_id):
        db = Database()
        if db.connect():
            try:
                query = """
                UPDATE tickets 
                SET status = 'closed', closed_at = datetime('now'), closed_by = ?
                WHERE ticket_id = ?
                """
                if db.execute(query, (admin_id, ticket_id)):
                    db.commit()
                    return True
            except sqlite3.Error as e:
                print(f"SQLite error in close_ticket: {e}")
            finally:
                db.close()
        return False

    # --- Discount Management ---

    @staticmethod
    def create_discount(code: str, discount_type: str, value: float, start_date: str = None, end_date: str = None, max_uses: int = None, is_active: bool = True, single_use_per_user: bool = False) -> int:
        """Creates a new discount code and returns its ID."""
        db = Database()
        if db.connect():
            try:
                query = """INSERT INTO discounts 
                    (code, type, value, start_date, end_date, max_uses, is_active, single_use_per_user) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
                params = (code, discount_type, value, start_date, end_date, max_uses, is_active, single_use_per_user)
                if db.execute(query, params):
                    db.commit()
                    return db.cursor.lastrowid
            except sqlite3.Error as e:
                print(f"SQLite error in create_discount: {e}")
            finally:
                db.close()
        return None

    @staticmethod
    def get_discount_by_id(discount_id: int):
        """Retrieves a discount by its unique ID."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT * FROM discounts WHERE id = ?"
                if db.execute(query, (discount_id,)):
                    return db.fetchone()
            except sqlite3.Error as e:
                print(f"SQLite error in get_discount_by_id: {e}")
            finally:
                db.close()
        return None

    @staticmethod
    def get_discount_by_code(code: str):
        """Retrieves a discount by its code."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT * FROM discounts WHERE code = ?"
                if db.execute(query, (code,)):
                    return db.fetchone()
            except sqlite3.Error as e:
                print(f"SQLite error in get_discount_by_code: {e}")
            finally:
                db.close()
        return None

    @staticmethod
    def get_all_discounts():
        """Retrieves all discounts from the database."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT * FROM discounts ORDER BY id DESC"
                if db.execute(query):
                    return db.fetchall()
            except sqlite3.Error as e:
                print(f"SQLite error in get_all_discounts: {e}")
            finally:
                db.close()
        return []

    @staticmethod
    def toggle_discount_status(discount_id: int, is_active: bool) -> bool:
        """Activates or deactivates a discount."""
        db = Database()
        if db.connect():
            try:
                query = "UPDATE discounts SET is_active = ? WHERE id = ?"
                if db.execute(query, (is_active, discount_id)):
                    db.commit()
                    return True
            except sqlite3.Error as e:
                print(f"SQLite error in toggle_discount_status: {e}")
            finally:
                db.close()
        return False

    # NEW METHODS FOR DISCOUNT CRUD
    @staticmethod
    def update_discount(discount_id: int, **kwargs) -> bool:
        """Update fields of a discount. Pass column=value pairs via kwargs."""
        if not kwargs:
            return False
        db = Database()
        if db.connect():
            try:
                set_clause = ", ".join([f"{col} = ?" for col in kwargs.keys()])
                params = list(kwargs.values()) + [discount_id]
                query = f"UPDATE discounts SET {set_clause} WHERE id = ?"
                if db.execute(query, params):
                    db.commit()
                    return True
            except sqlite3.Error as e:
                print(f"SQLite error in update_discount: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def delete_discount(discount_id: int) -> bool:
        """Deletes a discount and its plan associations."""
        db = Database()
        if db.connect():
            try:
                db.execute("DELETE FROM discounts WHERE id = ?", (discount_id,))
                db.execute("DELETE FROM plan_discounts WHERE discount_id = ?", (discount_id,))
                db.commit()
                return True
            except sqlite3.Error as e:
                print(f"SQLite error in delete_discount: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def assign_discount_to_plan(discount_id: int, plan_id: int) -> bool:
        """Assigns a discount to a specific plan."""
        db = Database()
        if db.connect():
            try:
                query = "INSERT INTO plan_discounts (discount_id, plan_id) VALUES (?, ?)"
                if db.execute(query, (discount_id, plan_id)):
                    db.commit()
                    return True
            except sqlite3.Error as e:
                print(f"SQLite error in assign_discount_to_plan: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def link_discount_to_plans(discount_id: int, plan_ids: list) -> bool:
        """Links a discount to one or more plans."""
        db = Database()
        if db.connect():
            try:
                query = "INSERT INTO plan_discounts (discount_id, plan_id) VALUES (?, ?)"
                params_list = [(discount_id, plan_id) for plan_id in plan_ids]
                if db.executemany(query, params_list):
                    db.commit()
                    return True
            except sqlite3.Error as e:
                print(f"SQLite error in link_discount_to_plans: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def get_plans_for_discount(discount_id: int) -> list:
        """Returns a list of plan records associated with a discount."""
        db = Database()
        if db.connect():
            try:
                query = """
                    SELECT p.id, p.name FROM plans p
                    JOIN plan_discounts pd ON p.id = pd.plan_id
                    WHERE pd.discount_id = ?
                """
                if db.execute(query, (discount_id,)):
                    return db.fetchall()
            except sqlite3.Error as e:
                print(f"SQLite error in get_plans_for_discount: {e}")
            finally:
                db.close()
        return []

    # ---------- Ticket helper ----------

    @staticmethod
    def get_tickets_by_user(user_id: int, limit: int = 20):
        """Fetch recent tickets for a given user id ordered by newest."""
        db = Database()
        rows = []
        if db.connect():
            try:
                sql = "SELECT id, subject, status, created_at FROM tickets WHERE user_id = ? ORDER BY created_at DESC LIMIT ?"
                db.execute(sql, (user_id, limit))
                rows = db.fetchall()
            except Exception as e:
                logging.error(f"SQLite error in get_tickets_by_user: {e}")
            finally:
                db.close()
        return rows

    # ---------- Support Users ----------
    @staticmethod
    def add_support_user(telegram_id: int, added_by: int = None) -> bool:
        """Add a new support staff user."""
        db = Database()
        if db.connect():
            try:
                query = "INSERT OR IGNORE INTO support_users (telegram_id, added_by) VALUES (?, ?)"
                if db.execute(query, (telegram_id, added_by)):
                    db.commit()
                    return True
            except Exception as e:
                logging.error(f"SQLite error in add_support_user: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def remove_support_user(telegram_id: int) -> bool:
        db = Database()
        if db.connect():
            try:
                if db.execute("DELETE FROM support_users WHERE telegram_id = ?", (telegram_id,)):
                    db.commit()
                    return True
            except Exception as e:
                logging.error(f"SQLite error in remove_support_user: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def is_support_user(telegram_id: int) -> bool:
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT 1 FROM support_users WHERE telegram_id = ? LIMIT 1", (telegram_id,))
                return db.fetchone() is not None
            except Exception as e:
                logging.error(f"SQLite error in is_support_user: {e}")
            finally:
                db.close()
        return False

    @staticmethod
    def get_all_support_users():
        db = Database()
        if db.connect():
            try:
                db.execute("SELECT telegram_id, added_by, added_at FROM support_users")
                return db.fetchall()
            except Exception as e:
                logging.error(f"SQLite error in get_all_support_users: {e}")
            finally:
                db.close()
        return []

    @staticmethod
    def increment_discount_usage(discount_id: int) -> bool:
        """Increments the usage count of a discount."""
        db = Database()
        if db.connect():
            try:
                query = "UPDATE discounts SET uses_count = COALESCE(uses_count, 0) + 1 WHERE id = ?"
                if db.execute(query, (discount_id,)):
                    db.commit()
                    return True
            except sqlite3.Error as e:
                print(f"SQLite error in increment_discount_usage: {e}")
            finally:
                db.close()
        return False
    
    @staticmethod
    def has_user_used_discount(user_id: int, discount_id: int) -> bool:
        """Check if a user has already used a specific discount code."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT id FROM discount_usage_history WHERE user_id = ? AND discount_id = ?"
                if db.execute(query, (user_id, discount_id)):
                    result = db.fetchone()
                    return result is not None
            except sqlite3.Error as e:
                print(f"SQLite error in has_user_used_discount: {e}")
            finally:
                db.close()
        return False
    
    @staticmethod
    def record_discount_usage(user_id: int, discount_id: int, plan_id: int = None, payment_id: int = None, amount_discounted: float = None, payment_method: str = None) -> bool:
        """Record that a user has used a discount code."""
        db = Database()
        if db.connect():
            try:
                query = """INSERT INTO discount_usage_history 
                    (user_id, discount_id, plan_id, payment_id, amount_discounted, payment_method) 
                    VALUES (?, ?, ?, ?, ?, ?)"""
                params = (user_id, discount_id, plan_id, payment_id, amount_discounted, payment_method)
                if db.execute(query, params):
                    db.commit()
                    return True
            except sqlite3.IntegrityError:
                # This means the user has already used this discount (UNIQUE constraint)
                print(f"User {user_id} has already used discount {discount_id}")
                return False
            except sqlite3.Error as e:
                print(f"SQLite error in record_discount_usage: {e}")
            finally:
                db.close()
        return False
    
    @staticmethod
    def get_discount_usage_history(discount_id: int = None, user_id: int = None) -> list:
        """Get discount usage history, optionally filtered by discount_id or user_id."""
        db = Database()
        if db.connect():
            try:
                query = """SELECT duh.*, u.username, u.full_name, d.code as discount_code, p.name as plan_name
                    FROM discount_usage_history duh
                    LEFT JOIN users u ON duh.user_id = u.user_id
                    LEFT JOIN discounts d ON duh.discount_id = d.id
                    LEFT JOIN plans p ON duh.plan_id = p.id
                    WHERE 1=1"""
                params = []
                
                if discount_id:
                    query += " AND duh.discount_id = ?"
                    params.append(discount_id)
                
                if user_id:
                    query += " AND duh.user_id = ?"
                    params.append(user_id)
                
                query += " ORDER BY duh.used_at DESC"
                
                if db.execute(query, params):
                    return db.fetchall()
            except sqlite3.Error as e:
                print(f"SQLite error in get_discount_usage_history: {e}")
            finally:
                db.close()
        return []

    @staticmethod
    def get_all_plans():
        """Retrieves all subscription plans."""
        db = Database()
        if db.connect():
            try:
                query = "SELECT id, name, description, price, original_price_irr, price_tether, original_price_usdt, days, features, display_order, capacity, category_id, is_active, is_public FROM plans ORDER BY display_order"
                if db.execute(query):
                    return db.fetchall()
            except sqlite3.Error as e:
                print(f"SQLite error in get_all_plans: {e}")
            finally:
                db.close()
        return []

    @staticmethod
    def get_user_by_telegram_id(telegram_id):
        """Get user by telegram ID"""
        db = Database()
        if db.connect():
            db.execute("SELECT * FROM users WHERE user_id = ?", (telegram_id,))
            result = db.fetchone()
            db.close()
            return result
        return None

    @staticmethod
    def get_user_status(user_id: int) -> Optional[str]:
        """Get the status of a user (e.g., 'active', 'banned')."""
        db = Database()
        if not db.connect():
            return None
            
        try:
            cursor = db.conn.cursor()
            sql = "SELECT status FROM users WHERE user_id = ?"
            cursor.execute(sql, (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None
        except sqlite3.Error as e:
            logger.error(f"Database error in get_user_status for user {user_id}: {e}")
            return None
        finally:
            db.close()

    @staticmethod
    def set_user_status(user_id: int, status: str, bot_instance=None) -> bool:
        """Set the status of a user (e.g., 'active', 'banned').
        
        Args:
            user_id: Telegram user ID
            status: New status ('active' or 'banned')
            bot_instance: Optional bot instance to delete chat history when banning
        """
        if status not in ['active', 'banned']:
            logger.warning(f"Invalid status '{status}' provided for set_user_status.")
            return False
            
        db = Database()
        if not db.connect():
            return False
            
        try:
            cursor = db.conn.cursor()
            sql = "UPDATE users SET status = ? WHERE user_id = ?"
            cursor.execute(sql, (status, user_id))
            db.conn.commit()
            success = cursor.rowcount > 0
            
            # If successfully banned and bot instance provided, delete chat history
            if success and status == 'banned' and bot_instance:
                try:
                    import asyncio
                    asyncio.create_task(DatabaseQueries.delete_user_chat_history(user_id, bot_instance))
                except Exception as e:
                    logger.error(f"Failed to delete chat history for banned user {user_id}: {e}")
            
            return success
        except sqlite3.Error as e:
            logger.error(f"Database error in set_user_status for user {user_id}: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    async def delete_user_chat_history(user_id: int, bot):
        """Delete all chat history with a banned user.
        
        Args:
            user_id: Telegram user ID
            bot: Bot instance to use for deletion
        """
        try:
            # Delete all messages from/to this user in private chat
            # Note: Telegram API doesn't provide a bulk delete for private chats
            # We can only delete messages the bot has sent
            logger.info(f"Attempting to delete chat history for banned user {user_id}")
            
            # Try to delete any active conversations/keyboards
            try:
                from telegram import ReplyKeyboardRemove
                await bot.send_message(
                    chat_id=user_id,
                    text=".",  # Send minimal message
                    reply_markup=ReplyKeyboardRemove(remove_keyboard=True)
                )
                # Immediately delete the message we just sent
                sent_msg = await bot.send_message(chat_id=user_id, text=".")
                await bot.delete_message(chat_id=user_id, message_id=sent_msg.message_id)
            except Exception:
                pass  # User may have blocked the bot
            
            logger.info(f"Chat history cleanup completed for banned user {user_id}")
            
        except Exception as e:
            logger.error(f"Error deleting chat history for user {user_id}: {e}")

    @staticmethod
    def extend_subscription_duration(user_id: int, additional_days: int) -> bool:
        """Extend a single user's subscription as before (existing method)."""
        # (existing implementation remains unchanged)

    # ------------------------------------------------------------------
    # BULK SUBSCRIPTION EXTENSION
    # ------------------------------------------------------------------
    @staticmethod
    def extend_subscription_duration_all(additional_days: int) -> int:
        """Extend subscription end_date for ALL active users.

        Args:
            additional_days: Number of days to add.
        Returns:
            Number of subscriptions updated (int). Returns 0 on error or if none updated.
        """
        if additional_days <= 0:
            return 0
        db = Database()
        if not db.connect():
            return 0
        try:
            now_ts = get_current_time()
            # Ensure timezone-naive for comparison with DB dates
            if now_ts.tzinfo is not None:
                now_ts_naive = now_ts.replace(tzinfo=None)
            else:
                now_ts_naive = now_ts
            now_str = now_ts_naive.strftime("%Y-%m-%d %H:%M:%S")
            cursor = db.conn.cursor()
            # Fetch all active subscriptions (status='active')
            cursor.execute("SELECT id, end_date FROM subscriptions WHERE status = 'active'")
            rows = cursor.fetchall()
            updated_count = 0
            for row in rows:
                sub_id = row[0] if not isinstance(row, dict) else row['id']
                end_date_str = row[1] if not isinstance(row, dict) else row['end_date']
                try:
                    base_date = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    # Skip malformed dates
                    continue
                if base_date < now_ts_naive:
                    base_date = now_ts
                new_end = base_date + timedelta(days=additional_days)
                new_end_str = new_end.strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    "UPDATE subscriptions SET end_date = ?, updated_at = ? WHERE id = ?",
                    (new_end_str, now_str, sub_id),
                )
                if cursor.rowcount > 0:
                    updated_count += 1
            db.conn.commit()
            return updated_count
        except sqlite3.Error as exc:
            logging.error("SQLite error in extend_subscription_duration_all: %s", exc)
            return 0
        finally:
            db.close()
        """Extend a user's active subscription by the given number of additional days.

        If the user has an active subscription, its `end_date` is advanced. If the
        stored `end_date` is in the past, the extension starts from *now* so that
        even already-expired but still marked *active* records are handled.
        Returns True on success, False on failure or when no active subscription
        exists for the user.
        """
        if additional_days <= 0:
            logging.warning("extend_subscription_duration called with non-positive days: %s", additional_days)
            return False
        
        # Check 120-day limit before extension if enabled
        limit_enabled = Database.get_setting("enable_120_day_limit", "1") == "1"
        if limit_enabled:
            current_remaining_days = Database.get_user_remaining_subscription_days(user_id)
            total_days_after_extension = current_remaining_days + additional_days
            
            if total_days_after_extension > 120:
                logging.warning(f"User {user_id} extension blocked: would exceed 120-day limit. Current: {current_remaining_days}, Extension: {additional_days}, Total: {total_days_after_extension}")
                return False

        db = Database()
        if not db.connect():
            return False
        try:
            db.execute(
                "SELECT id, end_date FROM subscriptions WHERE user_id = ? AND status = 'active' ORDER BY end_date DESC LIMIT 1",
                (user_id,),
            )
            row = db.fetchone()
            if not row:
                logging.info("No active subscription found for user %s – cannot extend.", user_id)
                return False

            sub_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
            end_date_str = row[1] if isinstance(row, (tuple, list)) else row["end_date"]

            # Parse end_date safely.
            try:
                current_end = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    current_end = datetime.fromisoformat(end_date_str)
                except Exception:
                    current_end = get_current_time()

            # Ensure both datetimes are timezone-aware in Tehran tz
            from pytz import timezone as _tz
            tehran_tz = _tz(config.TEHRAN_TIMEZONE)
            if current_end.tzinfo is None:
                current_end = tehran_tz.localize(current_end)
            else:
                current_end = current_end.astimezone(tehran_tz)
            now_ts = get_current_time()  # already Tehran tz
            base_date = current_end if current_end > now_ts else now_ts
            new_end = base_date + timedelta(days=additional_days)
            new_end_str = new_end.strftime("%Y-%m-%d %H:%M:%S")
            updated_at_str = now_ts.strftime("%Y-%m-%d %H:%M:%S")

            db.execute(
                "UPDATE subscriptions SET end_date = ?, updated_at = ? WHERE id = ?",
                (new_end_str, updated_at_str, sub_id),
            )
            db.commit()
            return db.cursor.rowcount > 0
        except sqlite3.Error as exc:
            logging.error("SQLite error in extend_subscription_duration: %s", exc)
            return False
        finally:
            db.close()
    
    @staticmethod
    def has_user_used_free_plan(user_id: int, plan_id: int) -> bool:
        """Check if user has already used this specific free plan."""
        db = Database()
        if not db.connect():
            return False
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM subscriptions 
                WHERE user_id = ? AND plan_id = ? AND payment_method = 'free'
            """, (user_id, plan_id))
            count = cursor.fetchone()[0]
            return count > 0
        except Exception as e:
            logging.error(f"Error checking if user {user_id} used free plan {plan_id}: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_plan_videos(plan_id: int):
        """Get all videos associated with a plan."""
        db = Database()
        if not db.connect():
            return []
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT v.id, v.filename, v.display_name, v.file_path, v.file_size, 
                       v.duration, v.telegram_file_id, v.origin_chat_id, v.origin_message_id, v.is_active, pv.display_order, pv.custom_caption
                FROM videos v
                JOIN plan_videos pv ON v.id = pv.video_id
                WHERE pv.plan_id = ? AND v.is_active = 1
                ORDER BY pv.display_order, v.display_name
            """, (plan_id,))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error getting videos for plan {plan_id}: {e}")
            return []
        finally:
            db.close()

    # ====================================================================
    # Product Sales Report Methods
    # ====================================================================
    
    @staticmethod
    def get_plan_sales_count(plan_id=None, days=None):
        """Get sales count for a specific plan within a time period.
        
        Args:
            plan_id: The plan ID to filter by (if None, includes all plans)
            days: Number of days back to look (if None, returns all time)
            
        Returns:
            dict with sales data including count and revenue
        """
        db = Database()
        if not db.connect():
            return {'count': 0, 'revenue_irr': 0, 'revenue_usdt': 0}
            
        try:
            cursor = db.conn.cursor()
            
            # Build the base query
            base_query = """
                SELECT COUNT(*) as count,
                       SUM(COALESCE(p.amount, 0)) as revenue_irr,
                       SUM(COALESCE(p.usdt_amount_requested, 0)) as revenue_usdt
                FROM payments p
                WHERE p.status IN ('paid', 'completed', 'successful', 'verified')
            """
            
            params = []
            
            # Add plan filter if specified
            if plan_id is not None:
                base_query += " AND p.plan_id = ?"
                params.append(plan_id)
                
            # Add time filter if specified
            if days is not None:
                base_query += " AND p.created_at >= datetime('now', '-{} days')".format(int(days))
                
            cursor.execute(base_query, params)
            result = cursor.fetchone()
            
            if result:
                return {
                    'count': result[0] or 0,
                    'revenue_irr': float(result[1] or 0),
                    'revenue_usdt': float(result[2] or 0)
                }
            else:
                return {'count': 0, 'revenue_irr': 0, 'revenue_usdt': 0}
                
        except Exception as e:
            logging.error(f"Error getting plan sales count: {e}")
            return {'count': 0, 'revenue_irr': 0, 'revenue_usdt': 0}
        finally:
            db.close()
    
    @staticmethod
    def get_recent_plan_sales(plan_id=None, limit=10):
        """Get recent sales for a specific plan.
        
        Args:
            plan_id: The plan ID to filter by (if None, includes all plans)
            limit: Maximum number of recent sales to return
            
        Returns:
            list of recent sales with user info and timestamps
        """
        db = Database()
        if not db.connect():
            return []
            
        try:
            cursor = db.conn.cursor()
            
            query = """
                SELECT p.payment_id, p.user_id, p.amount, p.usdt_amount_requested,
                       p.payment_method, p.created_at, u.full_name, u.username,
                       pl.name as plan_name
                FROM payments p
                LEFT JOIN users u ON p.user_id = u.user_id
                LEFT JOIN plans pl ON p.plan_id = pl.id
                WHERE p.status IN ('paid', 'completed', 'successful', 'verified')
            """
            
            params = []
            
            # Add plan filter if specified
            if plan_id is not None:
                query += " AND p.plan_id = ?"
                params.append(plan_id)
                
            query += " ORDER BY p.created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            # Convert to list of dictionaries
            sales = []
            for row in results:
                sales.append({
                    'payment_id': row[0],
                    'user_id': row[1],
                    'amount_irr': float(row[2] or 0),
                    'amount_usdt': float(row[3] or 0),
                    'payment_method': row[4],
                    'created_at': row[5],
                    'user_name': row[6] or 'نامشخص',
                    'username': row[7] or '',
                    'plan_name': row[8] or 'نامشخص'
                })
                
            return sales
            
        except Exception as e:
            logging.error(f"Error getting recent plan sales: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def get_payment_method_breakdown(plan_id=None, days=None):
        """Get breakdown of payment methods for plan sales.
        
        Args:
            plan_id: The plan ID to filter by (if None, includes all plans)
            days: Number of days back to look (if None, returns all time)
            
        Returns:
            dict with payment method breakdown
        """
        db = Database()
        if not db.connect():
            return {'rial': 0, 'crypto': 0}
            
        try:
            cursor = db.conn.cursor()
            
            query = """
                SELECT p.payment_method, COUNT(*) as count
                FROM payments p
                WHERE p.status IN ('paid', 'completed', 'successful', 'verified')
            """
            
            params = []
            
            # Add plan filter if specified
            if plan_id is not None:
                query += " AND p.plan_id = ?"
                params.append(plan_id)
                
            # Add time filter if specified
            if days is not None:
                query += " AND p.created_at >= datetime('now', '-{} days')".format(int(days))
                
            query += " GROUP BY p.payment_method"
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            breakdown = {'rial': 0, 'crypto': 0}
            for row in results:
                method = row[0]
                count = row[1]
                if method in ['zarinpal', 'rial']:
                    breakdown['rial'] += count
                elif method in ['crypto', 'tether', 'usdt']:
                    breakdown['crypto'] += count
                    
            return breakdown
            
        except Exception as e:
            logging.error(f"Error getting payment method breakdown: {e}")
            return {'rial': 0, 'crypto': 0}
        finally:
            db.close()
    
    @staticmethod
    def get_all_plans_with_sales_data():
        """Get all plans with basic sales data for product selection.
        
        Returns:
            list of plans with sales count
        """
        db = Database()
        if not db.connect():
            return []
            
        try:
            cursor = db.conn.cursor()
            
            query = """
                SELECT p.id, p.name, p.description, p.price, p.price_tether,
                       COUNT(pay.payment_id) as total_sales
                FROM plans p
                LEFT JOIN payments pay ON p.id = pay.plan_id 
                    AND pay.status IN ('paid', 'completed', 'successful', 'verified')
                WHERE p.is_active = 1
                GROUP BY p.id, p.name, p.description, p.price, p.price_tether
                ORDER BY p.display_order, p.name
            """
            
            cursor.execute(query)
            results = cursor.fetchall()
            
            plans = []
            for row in results:
                plans.append({
                    'id': row[0],
                    'name': row[1],
                    'description': row[2] or '',
                    'price_irr': float(row[3] or 0),
                    'price_usdt': float(row[4] or 0),
                    'total_sales': row[5] or 0
                })
                
            return plans
            
        except Exception as e:
            logging.error(f"Error getting plans with sales data: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def get_user_purchased_products(user_id: int):
        """Get all products purchased by a user with active subscriptions.
        
        Args:
            user_id: The user ID to check
            
        Returns:
            list of plan/product IDs that the user has active subscriptions for
        """
        db = Database()
        if not db.connect():
            return []
            
        try:
            cursor = db.conn.cursor()
            query = """
                SELECT DISTINCT s.plan_id
                FROM subscriptions s
                WHERE s.user_id = ? 
                AND s.status = 'active'
                AND (s.end_date IS NULL OR s.end_date > datetime('now'))
            """
            cursor.execute(query, (user_id,))
            results = cursor.fetchall()
            return [row[0] for row in results]
            
        except Exception as e:
            logging.error(f"Error getting user purchased products: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def get_product_channels(plan_id: int):
        """Get all channel IDs associated with a specific product/plan.
        
        Args:
            plan_id: The plan/product ID
            
        Returns:
            list of channel IDs that this product grants access to
        """
        db = Database()
        if not db.connect():
            return []
            
        try:
            import json
            cursor = db.conn.cursor()
            query = "SELECT channels_json FROM plans WHERE id = ?"
            cursor.execute(query, (plan_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                try:
                    channels_data = json.loads(result[0])
                    # Extract channel IDs from the JSON structure
                    channel_ids = []
                    if isinstance(channels_data, list):
                        for channel in channels_data:
                            if isinstance(channel, dict) and 'id' in channel:
                                channel_ids.append(channel['id'])
                    elif isinstance(channels_data, dict):
                        # Handle single channel as dict
                        if 'id' in channels_data:
                            channel_ids.append(channels_data['id'])
                    return channel_ids
                except json.JSONDecodeError:
                    logging.error(f"Invalid JSON in channels_json for plan {plan_id}")
                    return []
            return []
            
        except Exception as e:
            logging.error(f"Error getting product channels: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def user_has_access_to_channel(user_id: int, channel_id: int) -> bool:
        """
        Check if a user has access to a specific channel through their purchased products.
        Uses the new SubscriptionManager for better category-based checking.
        
        Args:
            user_id: The user ID to check
            channel_id: The channel ID to check access for
            
        Returns:
            bool: True if user has access, False otherwise
        """
        try:
            # Use the new SubscriptionManager for more accurate checking
            from database.subscription_manager import SubscriptionManager
            has_access, category_name = SubscriptionManager.check_user_access_to_channel(user_id, channel_id)
            return has_access
        except ImportError:
            # Fallback to old method if SubscriptionManager not available
            pass
        
        db = Database()
        if not db.connect():
            return False
            
        try:
            import json
            cursor = db.conn.cursor()
            
            # First check if user exists in database (is a bot member)
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            user_exists = cursor.fetchone()
            if not user_exists:
                # User is not in our database - deny access
                return False
            
            # Check if channels_json column exists
            cursor.execute("PRAGMA table_info(plans)")
            columns = [col[1] for col in cursor.fetchall()]
            has_channels_json = 'channels_json' in columns
            
            if not has_channels_json:
                # Legacy mode: if channels_json doesn't exist, 
                # allow access if user has ANY active subscription
                query = """
                    SELECT COUNT(*)
                    FROM subscriptions s
                    JOIN plans p ON s.plan_id = p.id
                    WHERE s.user_id = ? 
                    AND s.status = 'active'
                    AND (s.end_date IS NULL OR s.end_date > datetime('now'))
                """
                cursor.execute(query, (user_id,))
                count = cursor.fetchone()[0]
                return count > 0
            else:
                # New mode: check channels_json for specific channel access
                query = """
                    SELECT p.channels_json
                    FROM subscriptions s
                    JOIN plans p ON s.plan_id = p.id
                    WHERE s.user_id = ? 
                    AND s.status = 'active'
                    AND (s.end_date IS NULL OR s.end_date > datetime('now'))
                """
                cursor.execute(query, (user_id,))
                results = cursor.fetchall()
                
                # If user has active subscriptions but no channels defined,
                # allow access (backward compatibility)
                has_any_subscription = len(results) > 0
                has_channel_definitions = False
                
                # Check if any of the user's products grant access to this channel
                for row in results:
                    if row[0]:  # channels_json exists
                        has_channel_definitions = True
                        try:
                            channels_data = json.loads(row[0])
                            if isinstance(channels_data, list):
                                for channel in channels_data:
                                    if isinstance(channel, dict) and channel.get('id') == channel_id:
                                        return True
                            elif isinstance(channels_data, dict):
                                if channels_data.get('id') == channel_id:
                                    return True
                        except json.JSONDecodeError:
                            continue
                
                # If user has active subscription but no channel definitions, allow access
                # This protects legacy users
                if has_any_subscription and not has_channel_definitions:
                    return True
                    
            return False
            
        except Exception as e:
            logging.error(f"Error checking user channel access: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def get_users_with_channel_access(channel_id: int):
        """Get all users who have valid access to a specific channel through their purchases.
        
        Args:
            channel_id: The channel ID to check
            
        Returns:
            list of user IDs who have valid access to this channel
        """
        db = Database()
        if not db.connect():
            return []
            
        try:
            import json
            cursor = db.conn.cursor()
            
            # First check if channels_json column exists
            cursor.execute("PRAGMA table_info(plans)")
            columns = [col[1] for col in cursor.fetchall()]
            has_channels_json = 'channels_json' in columns
            
            if not has_channels_json:
                # Legacy mode: return ALL users with active subscriptions
                query = """
                    SELECT DISTINCT s.user_id
                    FROM subscriptions s
                    JOIN plans p ON s.plan_id = p.id
                    WHERE s.status = 'active'
                    AND (s.end_date IS NULL OR s.end_date > datetime('now'))
                """
                cursor.execute(query)
                results = cursor.fetchall()
                authorized_users = [row[0] for row in results]
                
                # Also check SpotPlayer purchases
                spotplayer_query = """
                    SELECT DISTINCT user_id
                    FROM spotplayer_purchases
                    WHERE status = 'completed'
                    AND subscription_end > datetime('now')
                """
                cursor.execute(spotplayer_query)
                spotplayer_results = cursor.fetchall()
                authorized_users.extend([row[0] for row in spotplayer_results])
                
                return list(set(authorized_users))  # Remove duplicates
            else:
                # New mode: check channels_json
                query = """
                    SELECT s.user_id, p.channels_json
                    FROM subscriptions s
                    JOIN plans p ON s.plan_id = p.id
                    WHERE s.status = 'active'
                    AND (s.end_date IS NULL OR s.end_date > datetime('now'))
                """
                cursor.execute(query)
                results = cursor.fetchall()
                
                authorized_users = set()
                legacy_users = set()  # Users with subscriptions but no channel definitions
                
                for user_id, channels_json in results:
                    if channels_json:
                        try:
                            channels_data = json.loads(channels_json)
                            # Check if this product grants access to the specified channel
                            if isinstance(channels_data, list):
                                for channel in channels_data:
                                    if isinstance(channel, dict) and channel.get('id') == channel_id:
                                        authorized_users.add(user_id)
                                        break
                            elif isinstance(channels_data, dict):
                                if channels_data.get('id') == channel_id:
                                    authorized_users.add(user_id)
                        except json.JSONDecodeError:
                            # If JSON is invalid, treat as legacy user
                            legacy_users.add(user_id)
                    else:
                        # No channels defined = legacy user with access
                        legacy_users.add(user_id)
                
                # Also check SpotPlayer purchases for this specific channel
                spotplayer_query = """
                    SELECT DISTINCT sp.user_id, spp.channel_id
                    FROM spotplayer_purchases sp
                    JOIN spotplayer_products spp ON sp.product_id = spp.product_id
                    WHERE sp.status = 'completed'
                    AND sp.subscription_end > datetime('now')
                    AND spp.channel_id = ?
                """
                cursor.execute(spotplayer_query, (str(channel_id),))
                spotplayer_results = cursor.fetchall()
                for user_id, _ in spotplayer_results:
                    authorized_users.add(user_id)
                
                # Combine both authorized users and legacy users
                all_authorized = authorized_users.union(legacy_users)
                return list(all_authorized)
            
        except Exception as e:
            logging.error(f"Error getting users with channel access: {e}")
            return []
        finally:
            db.close()
    
    @staticmethod
    def get_channel_kick_settings():
        """Get kick settings for all channels."""
        db = Database()
        if not db.connect():
            return {}
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT channel_id, channel_title, kick_enabled, last_modified, modified_by
                FROM channel_kick_settings
            """)
            rows = cursor.fetchall()
            
            settings = {}
            for row in rows:
                settings[row[0]] = {
                    'channel_id': row[0],
                    'channel_title': row[1],
                    'kick_enabled': bool(row[2]),
                    'last_modified': row[3],
                    'modified_by': row[4]
                }
            return settings
            
        except Exception as e:
            logging.error(f"Error getting channel kick settings: {e}")
            return {}
        finally:
            db.close()
    
    @staticmethod
    def is_kick_enabled_for_channel(channel_id: int) -> bool:
        """Check if kick is enabled for a specific channel."""
        db = Database()
        if not db.connect():
            return True  # Default to enabled if can't check
        
        try:
            cursor = db.conn.cursor()
            cursor.execute("""
                SELECT kick_enabled FROM channel_kick_settings 
                WHERE channel_id = ?
            """, (channel_id,))
            row = cursor.fetchone()
            
            if row:
                return bool(row[0])
            else:
                # If no setting exists, default to enabled
                return True
                
        except Exception as e:
            logging.error(f"Error checking kick status for channel {channel_id}: {e}")
            return True  # Default to enabled on error
        finally:
            db.close()
    
    @staticmethod
    def update_channel_kick_setting(channel_id: int, channel_title: str, enabled: bool, modified_by: int):
        """Update or insert kick setting for a channel."""
        db = Database()
        if not db.connect():
            return False
        
        try:
            cursor = db.conn.cursor()
            now = datetime.now().isoformat()
            
            # Use INSERT OR REPLACE to handle both insert and update
            cursor.execute("""
                INSERT OR REPLACE INTO channel_kick_settings 
                (channel_id, channel_title, kick_enabled, last_modified, modified_by)
                VALUES (?, ?, ?, ?, ?)
            """, (channel_id, channel_title, 1 if enabled else 0, now, modified_by))
            
            db.conn.commit()
            return True
            
        except Exception as e:
            logging.error(f"Error updating kick setting for channel {channel_id}: {e}")
            return False
        finally:
            db.close()
    
    @staticmethod
    def initialize_channel_kick_settings(channels_info):
        """Initialize kick settings for all configured channels."""
        db = Database()
        if not db.connect():
            return False
        
        try:
            cursor = db.conn.cursor()
            
            for channel_info in channels_info:
                channel_id = channel_info.get('id')
                channel_title = channel_info.get('title', f"Channel {channel_id}")
                
                # Check if setting already exists
                cursor.execute("""
                    SELECT channel_id FROM channel_kick_settings 
                    WHERE channel_id = ?
                """, (channel_id,))
                
                if not cursor.fetchone():
                    # Insert default setting (enabled)
                    cursor.execute("""
                        INSERT INTO channel_kick_settings 
                        (channel_id, channel_title, kick_enabled, last_modified)
                        VALUES (?, ?, 1, datetime('now'))
                    """, (channel_id, channel_title))
            
            db.conn.commit()
            return True
            
        except Exception as e:
            logging.error(f"Error initializing channel kick settings: {e}")
            return False
        finally:
            db.close()
