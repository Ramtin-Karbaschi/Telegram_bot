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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    full_name TEXT,
                    username TEXT,
                    phone TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id)
                )
                """
            )
            
            # keyboard settings table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS altseason_keyboard_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_key TEXT UNIQUE NOT NULL,
                setting_value TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            
            # Initialize default keyboard settings if not exist
            cur.execute("SELECT COUNT(*) FROM altseason_keyboard_settings")
            if cur.fetchone()[0] == 0:
                default_settings = [
                    ('show_free_package', '1'),
                    ('show_products_menu', '1')
                ]
                cur.executemany(
                    "INSERT INTO altseason_keyboard_settings (setting_key, setting_value) VALUES (?, ?)",
                    default_settings
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
        """Export answers with user info as a DataFrame for Excel."""
        db = Database()
        if not db.connect():
            return None
        try:
            # Join altseason_users with main users table to get phone numbers
            # and pivot answers so each question is a separate column
            query = """
            WITH user_answers AS (
                SELECT 
                    au.user_id,
                    COALESCE(u.full_name, TRIM(au.first_name || ' ' || IFNULL(au.last_name, ''))) AS full_name,
                    u.username AS username,
                    COALESCE(u.phone, au.phone) AS phone,
                    aa.question_id,
                    aq.title as question_title,
                    aa.option_id as selected_option,
                    aa.answered_at
                FROM altseason_users au
                LEFT JOIN users u ON au.user_id = u.user_id
                LEFT JOIN altseason_answers aa ON au.user_id = aa.user_id
                LEFT JOIN altseason_questions aq ON aa.question_id = aq.id
                WHERE aa.question_id IS NOT NULL
            ),
            latest_answers AS (
                SELECT 
                    user_id,
                    full_name,
                    username,
                    phone,
                    MAX(answered_at) as latest_answer_time
                FROM user_answers
                GROUP BY user_id, full_name, username, phone
            )
            SELECT 
                ua.user_id,
                ua.full_name,
                ua.username,
                ua.phone,
                ua.question_id,
                ua.question_title,
                ua.selected_option,
                la.latest_answer_time
            FROM user_answers ua
            JOIN latest_answers la ON ua.user_id = la.user_id
            ORDER BY ua.user_id, ua.question_id
            """
            
            import pandas as pd
            df = pd.read_sql_query(query, db.conn)
            
            if df.empty:
                return pd.DataFrame()
            
            # ------------------------------------------------------------------
            # Group answers by user and session (based on answered_at timestamps)
            # Each complete set of answers represents one attempt/session
            # ------------------------------------------------------------------
            
            # Get total number of questions
            cur = db.conn.cursor()
            cur.execute('SELECT COUNT(*) FROM altseason_questions')
            total_questions = cur.fetchone()[0] or 1
            
            # Get all questions in order
            cur.execute('SELECT id, title FROM altseason_questions ORDER BY question_order, id')
            all_questions = cur.fetchall()
            
            # Group by user and create sessions based on complete answer sets
            result_rows = []
            
            for user_id in df['user_id'].unique():
                user_df = df[df['user_id'] == user_id].copy()
                user_df = user_df.sort_values('latest_answer_time')
                
                # Get user info (take first row)
                user_info = user_df.iloc[0]
                full_name = user_info['full_name']
                username = user_info['username']
                phone = user_info['phone']
                
                # Group answers into sessions (every total_questions answers = 1 session)
                answers_list = user_df.to_dict('records')
                
                session_num = 1
                for i in range(0, len(answers_list), total_questions):
                    session_answers = answers_list[i:i + total_questions]
                    
                    # Create row for this session
                    row = {
                        'user_id': user_id,
                        'full_name': full_name,
                        'username': username,
                        'phone': phone,
                        'attempt_number': session_num,
                        'session_date': session_answers[0]['latest_answer_time'] if session_answers else None
                    }
                    
                    # Add question and answer columns
                    for q_idx, (q_id, q_title) in enumerate(all_questions, 1):
                        row[f'question_{q_idx}'] = q_title
                        
                        # Find answer for this question in this session
                        answer = None
                        for ans in session_answers:
                            if ans['question_id'] == q_id:
                                answer = ans['selected_option']
                                break
                        row[f'answer_{q_idx}'] = answer
                    
                    result_rows.append(row)
                    session_num += 1
            
            # Convert to DataFrame
            if not result_rows:
                return pd.DataFrame()
                
            result_df = pd.DataFrame(result_rows)
            return result_df
            
        except Exception as e:
            logger.error(f"Error exporting answers dataframe: {e}")
            return None
        finally:
            db.close()
    
    # ------------------------------------------------------------------
    # Keyboard Settings Management
    # ------------------------------------------------------------------
    def get_keyboard_setting(self, key):
        """Get a keyboard setting value by key."""
        db = Database()
        if not db.connect():
            return None
        try:
            cur = db.conn.cursor()
            cur.execute("SELECT setting_value FROM altseason_keyboard_settings WHERE setting_key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.error(f"Error getting keyboard setting {key}: {e}")
            return None
        finally:
            db.close()
    
    def update_keyboard_setting(self, key, value):
        """Update a keyboard setting."""
        db = Database()
        if not db.connect():
            return False
        try:
            cur = db.conn.cursor()
            cur.execute(
                """INSERT OR REPLACE INTO altseason_keyboard_settings 
                   (setting_key, setting_value, updated_at) 
                   VALUES (?, ?, CURRENT_TIMESTAMP)""",
                (key, value)
            )
            db.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating keyboard setting {key}: {e}")
            return False
        finally:
            db.close()
    
    def get_keyboard_setting(self, key: str):
        """Get single keyboard setting value; returns '1' by default if missing."""
        db = Database()
        if not db.connect():
            return '1'
        try:
            cur = db.conn.cursor()
            cur.execute("SELECT setting_value FROM altseason_keyboard_settings WHERE setting_key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else '1'
        except Exception as e:
            logger.error(f"Error getting keyboard setting {key}: {e}")
            return '1'
        finally:
            db.close()

    def get_all_keyboard_settings(self):
        """Get all keyboard settings as a dictionary."""
        db = Database()
        if not db.connect():
            return {}
        try:
            cur = db.conn.cursor()
            cur.execute("SELECT setting_key, setting_value FROM altseason_keyboard_settings")
            rows = cur.fetchall()
            return {row[0]: row[1] for row in rows}
        except Exception as e:
            logger.error(f"Error getting all keyboard settings: {e}")
            return {}
        finally:
            db.close()
