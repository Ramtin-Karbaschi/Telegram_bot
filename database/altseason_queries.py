"""AltSeason feature specific DB helpers and migrations."""

import logging
from datetime import datetime
from database.models import Database

logger = logging.getLogger(__name__)


class AltSeasonQueries:
    """Encapsulate all database interactions for the Alt-Season flow."""

    def __init__(self):
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema migration helpers
    # ------------------------------------------------------------------
    def _ensure_schema(self):
        db = Database()
        if not db.connect():
            return
        try:
            cur = db.conn.cursor()
            # questions table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS altseason_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_order INTEGER NOT NULL,
                poll_id TEXT NOT NULL,
                poll_chat_id INTEGER,
                poll_message_id INTEGER,
                title TEXT,
                display_timing TEXT DEFAULT 'before_videos',
                poll_data TEXT,
                is_active INTEGER DEFAULT 1
                )
                """
            )
            # Ensure new columns exist for legacy databases
            existing_cols = [row[1] for row in cur.execute("PRAGMA table_info(altseason_questions)")]
            if 'poll_chat_id' not in existing_cols:
                cur.execute("ALTER TABLE altseason_questions ADD COLUMN poll_chat_id INTEGER")
            if 'poll_message_id' not in existing_cols:
                cur.execute("ALTER TABLE altseason_questions ADD COLUMN poll_message_id INTEGER")
            if 'display_timing' not in existing_cols:
                cur.execute("ALTER TABLE altseason_questions ADD COLUMN display_timing TEXT DEFAULT 'before_videos'")
            if 'title' not in existing_cols:
                cur.execute("ALTER TABLE altseason_questions ADD COLUMN title TEXT")
            if 'poll_data' not in existing_cols:
                cur.execute("ALTER TABLE altseason_questions ADD COLUMN poll_data TEXT")
            # videos table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS altseason_videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_order INTEGER NOT NULL,
                    telegram_file_id TEXT NOT NULL,
                    origin_chat_id INTEGER,
                    origin_message_id INTEGER,
                    caption TEXT,
                    title TEXT
                )
                """
            )
            # Ensure new columns exist for legacy video tables
            existing_v_cols = [row[1] for row in cur.execute("PRAGMA table_info(altseason_videos)")]
            if 'title' not in existing_v_cols:
                cur.execute("ALTER TABLE altseason_videos ADD COLUMN title TEXT")
            if 'origin_chat_id' not in existing_v_cols:
                cur.execute("ALTER TABLE altseason_videos ADD COLUMN origin_chat_id INTEGER")
            if 'origin_message_id' not in existing_v_cols:
                cur.execute("ALTER TABLE altseason_videos ADD COLUMN origin_message_id INTEGER")
            # users table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS altseason_users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    last_name TEXT,
                    phone TEXT,
                    started_at TEXT
                )
                """
            )
            # answers table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS altseason_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    question_id INTEGER NOT NULL,
                    option_id INTEGER NOT NULL,
                    answered_at TEXT,
                    FOREIGN KEY(user_id) REFERENCES altseason_users(user_id),
                    FOREIGN KEY(question_id) REFERENCES altseason_questions(id)
                )
                """
            )
            # settings table (single-row flag)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS altseason_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    is_enabled INTEGER DEFAULT 0
                )
                """
            )
            # ensure single row exists
            cur.execute("INSERT OR IGNORE INTO altseason_settings(id, is_enabled) VALUES (1, 0)")
            db.conn.commit()
        except Exception as e:
            logger.error("AltSeason schema migration failed: %s", e)
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------
    def is_enabled(self) -> bool:
        db = Database()
        if not db.connect():
            return False
        try:
            row = db.conn.execute("SELECT is_enabled FROM altseason_settings WHERE id = 1").fetchone()
            return bool(row[0]) if row else False
        finally:
            db.close()

    def set_enabled(self, flag: bool):
        db = Database()
        if not db.connect():
            return
        try:
            db.conn.execute("UPDATE altseason_settings SET is_enabled = ? WHERE id = 1", (1 if flag else 0,))
            db.conn.commit()
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Question / video CRUD (admin side)
    # ------------------------------------------------------------------
    def list_questions(self):
        db = Database()
        if not db.connect():
            return []
        try:
            cur = db.conn.cursor()
            cur.execute("SELECT * FROM altseason_questions WHERE is_active = 1 ORDER BY question_order")
            return [dict(r) for r in cur.fetchall()]
        finally:
            db.close()

    def add_question(self, order: int, poll_id: str, poll_chat_id: int, poll_message_id: int, title: str = None, display_timing: str = 'before_videos', poll_data: dict = None):
        db = Database()
        if not db.connect():
            return None
        try:
            cur = db.conn.cursor()
            import json
            poll_data_json = json.dumps(poll_data) if poll_data else None
            cur.execute(
                "INSERT INTO altseason_questions(question_order, poll_id, poll_chat_id, poll_message_id, title, display_timing, poll_data) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (order, poll_id, poll_chat_id, poll_message_id, title or f"سؤال {order}", display_timing, poll_data_json),
            )
            db.conn.commit()
            return cur.lastrowid
        finally:
            db.close()

    def set_display_timing(self, q_id: int, display_timing: str):
        db = Database()
        if not db.connect():
            return False
        try:
            db.conn.execute("UPDATE altseason_questions SET display_timing = ? WHERE id = ?", (display_timing, q_id))
            db.conn.commit()
            return True
        finally:
            db.close()

    def move_question(self, q_id: int, direction: str):
        """Move question up or down. direction in {'up','down'}"""
        if direction not in ("up", "down"):
            return False
        db = Database()
        if not db.connect():
            return False
        try:
            cur = db.conn.cursor()
            cur.execute("SELECT id, question_order FROM altseason_questions WHERE id=?", (q_id,))
            row = cur.fetchone()
            if not row:
                return False
            current_order = row[1]
            new_order = current_order - 1 if direction == "up" else current_order + 1
            # Find question with new_order to swap
            cur.execute("SELECT id FROM altseason_questions WHERE question_order=?", (new_order,))
            swap_row = cur.fetchone()
            if swap_row:
                swap_id = swap_row[0]
                cur.execute("UPDATE altseason_questions SET question_order=? WHERE id=?", (current_order, swap_id))
            cur.execute("UPDATE altseason_questions SET question_order=? WHERE id=?", (new_order, q_id))
            db.conn.commit()
            return True
        finally:
            db.close()

    def delete_question(self, q_id: int):
        db = Database()
        if not db.connect():
            return False
        try:
            db.conn.execute("DELETE FROM altseason_questions WHERE id = ?", (q_id,))
            db.conn.commit()
            return True
        finally:
            db.close()

    # videos
    def list_videos(self):
        db = Database()
        if not db.connect():
            return []
        try:
            cur = db.conn.cursor()
            cur.execute("SELECT * FROM altseason_videos ORDER BY video_order")
            return [dict(r) for r in cur.fetchall()]
        finally:
            db.close()
    
    def get_all_items_ordered(self):
        """Get all questions and videos in a unified list with global order"""
        db = Database()
        if not db.connect():
            return []
        try:
            cur = db.conn.cursor()
            # Get questions with type marker
            cur.execute("""
                SELECT id, question_order as item_order, title, 'question' as item_type, 
                       display_timing, poll_id, poll_chat_id, poll_message_id, poll_data
                FROM altseason_questions WHERE is_active = 1
            """)
            questions = [dict(r) for r in cur.fetchall()]
            
            # Get videos with type marker
            cur.execute("""
                SELECT id, video_order as item_order, title, 'video' as item_type,
                       NULL as display_timing, telegram_file_id, caption, origin_chat_id, origin_message_id
                FROM altseason_videos
            """)
            videos = [dict(r) for r in cur.fetchall()]
            
            # Combine and sort by item_order
            all_items = questions + videos
            all_items.sort(key=lambda x: x['item_order'])
            return all_items
        finally:
            db.close()
    
    def update_item_order(self, item_id: int, item_type: str, new_order: int):
        """Update order of a question or video"""
        db = Database()
        if not db.connect():
            return False
        try:
            if item_type == 'question':
                db.conn.execute("UPDATE altseason_questions SET question_order = ? WHERE id = ?", (new_order, item_id))
            elif item_type == 'video':
                db.conn.execute("UPDATE altseason_videos SET video_order = ? WHERE id = ?", (new_order, item_id))
            else:
                return False
            db.conn.commit()
            return True
        finally:
            db.close()

    def add_video(self, order: int, file_id: str, caption: str | None = None, title: str = None,
                  origin_chat_id: int | None = None, origin_message_id: int | None = None):
        db = Database()
        if not db.connect():
            return None
        try:
            cur = db.conn.cursor()
            cur.execute(
                "INSERT INTO altseason_videos(video_order, telegram_file_id, origin_chat_id, origin_message_id, caption, title) VALUES (?, ?, ?, ?, ?, ?)",
                (order, file_id, origin_chat_id, origin_message_id, caption, title or f"ویدیو {order}"),
            )
            db.conn.commit()
            return cur.lastrowid
        finally:
            db.close()

    def delete_video(self, v_id: int):
        db = Database()
        if not db.connect():
            return False
        try:
            db.conn.execute("DELETE FROM altseason_videos WHERE id = ?", (v_id,))
            db.conn.commit()
            return True
        finally:
            db.close()

    def update_video_sent(self, v_id: int, file_id: str, origin_chat_id: int, origin_message_id: int):
        """Update stored telegram_file_id and origin info after video successfully sent by main bot."""
        db = Database()
        if not db.connect():
            return False
        try:
            db.conn.execute(
                "UPDATE altseason_videos SET telegram_file_id = ?, origin_chat_id = ?, origin_message_id = ? WHERE id = ?",
                (file_id, origin_chat_id, origin_message_id, v_id),
            )
            db.conn.commit()
            return True
        finally:
            db.close()

    # ------------------------------------------------------------------
    # User flow helpers
    # ------------------------------------------------------------------
    def ensure_user(self, user_id: int, first_name: str = None, last_name: str = None, phone: str = None):
        db = Database()
        if not db.connect():
            return
        try:
            # Try to get phone from main users table if not provided
            if not phone:
                cur = db.conn.cursor()
                cur.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,))
                result = cur.fetchone()
                if result and result[0]:
                    phone = result[0]
            
            now_str = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
            db.conn.execute(
                "INSERT OR IGNORE INTO altseason_users(user_id, first_name, last_name, phone, started_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, first_name, last_name, phone, now_str),
            )
            db.conn.commit()
        finally:
            db.close()

    def save_answer(self, user_id: int, question_id: int, option_id: int):
        db = Database()
        if not db.connect():
            return
        try:
            db.conn.execute(
                "INSERT INTO altseason_answers(user_id, question_id, option_id, answered_at) VALUES (?, ?, ?, ?)",
                (user_id, question_id, option_id, datetime.utcnow().isoformat(sep=" ", timespec="seconds")),
            )
            db.conn.commit()
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------
    def export_answers_dataframe(self):
        """Return a pandas.DataFrame with user info and answers ready for Excel export."""
        import pandas as pd
        db = Database()
        if not db.connect():
            return pd.DataFrame()
        try:
            # Join with main users table to get phone and full user info
            query = (
                "SELECT "
                "    COALESCE(mu.user_id, au.user_id) as user_id, "
                "    COALESCE(mu.full_name, au.first_name || ' ' || COALESCE(au.last_name, '')) as full_name, "
                "    COALESCE(mu.username, '') as username, "
                "    COALESCE(mu.phone, au.phone, '') as phone, "
                "    q.title as question_title, "
                "    a.option_id, "
                "    a.answered_at "
                "FROM altseason_users au "
                "LEFT JOIN users mu ON au.user_id = mu.user_id "
                "LEFT JOIN altseason_answers a ON au.user_id = a.user_id "
                "LEFT JOIN altseason_questions q ON a.question_id = q.id "
                "ORDER BY au.user_id, a.question_id"
            )
            df = pd.read_sql_query(query, db.conn)
            
            if df.empty:
                return df
            
            # Pivot the data to show each question as a separate column
            # First, get unique users
            user_cols = ['user_id', 'full_name', 'username', 'phone']
            users_df = df[user_cols].drop_duplicates().reset_index(drop=True)
            
            # Create pivot table for answers
            if 'question_title' in df.columns and not df['question_title'].isna().all():
                answers_pivot = df.pivot_table(
                    index='user_id',
                    columns='question_title',
                    values='option_id',
                    aggfunc='first'  # Take first answer if multiple
                ).reset_index()
                
                # Merge user info with pivoted answers
                result_df = users_df.merge(answers_pivot, on='user_id', how='left')
                
                # Add answered_at timestamp for each user (latest answer)
                if 'answered_at' in df.columns:
                    latest_answer = df.groupby('user_id')['answered_at'].max().reset_index()
                    result_df = result_df.merge(latest_answer, on='user_id', how='left')
                    result_df.rename(columns={'answered_at': 'latest_answer_time'}, inplace=True)
                
                return result_df
            else:
                return users_df
        finally:
            db.close()
