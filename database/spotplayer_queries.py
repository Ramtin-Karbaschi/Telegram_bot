"""
Database queries for SpotPlayer functionality
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class SpotPlayerQueries:
    """Database queries for SpotPlayer management"""
    
    def __init__(self, connection):
        """Initialize with database connection"""
        self.connection = connection
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Ensure SpotPlayer tables exist"""
        try:
            cursor = self.connection.cursor()
            
            # Create tables if not exists
            with open('database/migrations/add_spotplayer_tables.sql', 'r', encoding='utf-8') as f:
                migration_sql = f.read()
                cursor.executescript(migration_sql)
            
            self.connection.commit()
            logger.info("SpotPlayer tables ensured")
            
        except Exception as e:
            logger.error(f"Error ensuring SpotPlayer tables: {e}")
    
    def get_config(self, key: str) -> Optional[str]:
        """Get SpotPlayer configuration value"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT config_value FROM spotplayer_config WHERE config_key = ?",
                (key,)
            )
            result = cursor.fetchone()
            return result[0] if result else None
            
        except Exception as e:
            logger.error(f"Error getting SpotPlayer config: {e}")
            return None
    
    def update_config(self, key: str, value: str) -> bool:
        """Update SpotPlayer configuration value"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """UPDATE spotplayer_config 
                SET config_value = ?, updated_at = datetime('now')
                WHERE config_key = ?""",
                (value, key)
            )
            self.connection.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error updating SpotPlayer config: {e}")
            return False
    
    def add_purchase(
        self,
        user_id: int,
        tracking_code: str,
        amount: int,
        spotplayer_key: str,
        payment_data: Dict = None,
        notes: str = None
    ) -> Optional[int]:
        """Add a new SpotPlayer purchase"""
        try:
            cursor = self.connection.cursor()
            
            payment_json = json.dumps(payment_data, ensure_ascii=False) if payment_data else None
            
            cursor.execute(
                """INSERT INTO spotplayer_purchases 
                (user_id, tracking_code, amount, spotplayer_key, payment_data, notes)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, tracking_code, amount, spotplayer_key, payment_json, notes)
            )
            
            self.connection.commit()
            purchase_id = cursor.lastrowid
            
            # Log the action
            self.add_access_log(
                purchase_id=purchase_id,
                user_id=user_id,
                action='purchase_created',
                details=f'Amount: {amount}, Key: {spotplayer_key}'
            )
            
            return purchase_id
            
        except Exception as e:
            logger.error(f"Error adding SpotPlayer purchase: {e}")
            return None
    
    def get_purchase_by_tracking_code(self, tracking_code: str) -> Optional[Dict]:
        """Get purchase by tracking code"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT p.*, u.full_name, u.telegram_id
                FROM spotplayer_purchases p
                LEFT JOIN users u ON p.user_id = u.user_id
                WHERE p.tracking_code = ?""",
                (tracking_code,)
            )
            
            result = cursor.fetchone()
            if not result:
                return None
            
            columns = [desc[0] for desc in cursor.description]
            purchase = dict(zip(columns, result))
            
            # Parse payment data if exists
            if purchase.get('payment_data'):
                try:
                    purchase['payment_data'] = json.loads(purchase['payment_data'])
                except:
                    pass
            
            return purchase
            
        except Exception as e:
            logger.error(f"Error getting purchase by tracking code: {e}")
            return None
    
    def get_purchase_by_key(self, spotplayer_key: str) -> Optional[Dict]:
        """Get purchase by SpotPlayer key"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT p.*, u.full_name, u.telegram_id
                FROM spotplayer_purchases p
                LEFT JOIN users u ON p.user_id = u.user_id
                WHERE p.spotplayer_key = ?""",
                (spotplayer_key,)
            )
            
            result = cursor.fetchone()
            if not result:
                return None
            
            columns = [desc[0] for desc in cursor.description]
            purchase = dict(zip(columns, result))
            
            # Parse payment data if exists
            if purchase.get('payment_data'):
                try:
                    purchase['payment_data'] = json.loads(purchase['payment_data'])
                except:
                    pass
            
            return purchase
            
        except Exception as e:
            logger.error(f"Error getting purchase by key: {e}")
            return None
    
    def get_user_purchases(self, user_id: int) -> List[Dict]:
        """Get all purchases for a user"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT * FROM spotplayer_purchases
                WHERE user_id = ?
                ORDER BY created_at DESC""",
                (user_id,)
            )
            
            columns = [desc[0] for desc in cursor.description]
            purchases = []
            
            for row in cursor.fetchall():
                purchase = dict(zip(columns, row))
                
                # Parse payment data if exists
                if purchase.get('payment_data'):
                    try:
                        purchase['payment_data'] = json.loads(purchase['payment_data'])
                    except:
                        pass
                
                purchases.append(purchase)
            
            return purchases
            
        except Exception as e:
            logger.error(f"Error getting user purchases: {e}")
            return []
    
    def check_tracking_code_exists(self, tracking_code: str) -> bool:
        """Check if tracking code already exists"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM spotplayer_purchases WHERE tracking_code = ?",
                (tracking_code,)
            )
            count = cursor.fetchone()[0]
            return count > 0
            
        except Exception as e:
            logger.error(f"Error checking tracking code: {e}")
            return True  # Return True for safety
    
    def get_recent_purchases(self, limit: int = 10, offset: int = 0) -> List[Dict]:
        """Get recent SpotPlayer purchases"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """SELECT p.*, u.full_name, u.telegram_id
                FROM spotplayer_purchases p
                LEFT JOIN users u ON p.user_id = u.user_id
                ORDER BY p.created_at DESC
                LIMIT ? OFFSET ?""",
                (limit, offset)
            )
            
            columns = [desc[0] for desc in cursor.description]
            purchases = []
            
            for row in cursor.fetchall():
                purchase = dict(zip(columns, row))
                
                # Parse payment data if exists
                if purchase.get('payment_data'):
                    try:
                        purchase['payment_data'] = json.loads(purchase['payment_data'])
                    except:
                        pass
                
                purchases.append(purchase)
            
            return purchases
            
        except Exception as e:
            logger.error(f"Error getting recent purchases: {e}")
            return []
    
    def get_purchase_stats(self) -> Dict:
        """Get SpotPlayer purchase statistics"""
        try:
            cursor = self.connection.cursor()
            
            # Total stats
            cursor.execute(
                """SELECT 
                    COUNT(*) as total_count,
                    SUM(amount) as total_revenue,
                    COUNT(DISTINCT user_id) as unique_users
                FROM spotplayer_purchases"""
            )
            
            result = cursor.fetchone()
            total_stats = {
                'total_count': result[0] or 0,
                'total_revenue': result[1] or 0,
                'unique_users': result[2] or 0
            }
            
            # Today's stats
            cursor.execute(
                """SELECT 
                    COUNT(*) as today_count,
                    SUM(amount) as today_revenue
                FROM spotplayer_purchases
                WHERE DATE(created_at) = DATE('now')"""
            )
            
            result = cursor.fetchone()
            today_stats = {
                'today_count': result[0] or 0,
                'today_revenue': result[1] or 0
            }
            
            # This month's stats
            cursor.execute(
                """SELECT 
                    COUNT(*) as month_count,
                    SUM(amount) as month_revenue
                FROM spotplayer_purchases
                WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"""
            )
            
            result = cursor.fetchone()
            month_stats = {
                'month_count': result[0] or 0,
                'month_revenue': result[1] or 0
            }
            
            return {
                'total': total_stats,
                'today': today_stats,
                'month': month_stats
            }
            
        except Exception as e:
            logger.error(f"Error getting purchase stats: {e}")
            return {
                'total': {'total_count': 0, 'total_revenue': 0, 'unique_users': 0},
                'today': {'today_count': 0, 'today_revenue': 0},
                'month': {'month_count': 0, 'month_revenue': 0}
            }
    
    def search_purchases(
        self,
        query: str = None,
        user_id: int = None,
        date_from: str = None,
        date_to: str = None,
        limit: int = 50
    ) -> List[Dict]:
        """Search SpotPlayer purchases"""
        try:
            cursor = self.connection.cursor()
            
            sql = """SELECT p.*, u.full_name, u.telegram_id
                    FROM spotplayer_purchases p
                    LEFT JOIN users u ON p.user_id = u.user_id
                    WHERE 1=1"""
            
            params = []
            
            if query:
                sql += """ AND (p.tracking_code LIKE ? OR p.spotplayer_key LIKE ? 
                          OR u.full_name LIKE ?)"""
                query_param = f"%{query}%"
                params.extend([query_param, query_param, query_param])
            
            if user_id:
                sql += " AND p.user_id = ?"
                params.append(user_id)
            
            if date_from:
                sql += " AND DATE(p.created_at) >= ?"
                params.append(date_from)
            
            if date_to:
                sql += " AND DATE(p.created_at) <= ?"
                params.append(date_to)
            
            sql += " ORDER BY p.created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(sql, params)
            
            columns = [desc[0] for desc in cursor.description]
            purchases = []
            
            for row in cursor.fetchall():
                purchase = dict(zip(columns, row))
                
                # Parse payment data if exists
                if purchase.get('payment_data'):
                    try:
                        purchase['payment_data'] = json.loads(purchase['payment_data'])
                    except:
                        pass
                
                purchases.append(purchase)
            
            return purchases
            
        except Exception as e:
            logger.error(f"Error searching purchases: {e}")
            return []
    
    def add_access_log(
        self,
        user_id: int,
        action: str,
        details: str = None,
        purchase_id: int = None,
        ip_address: str = None
    ):
        """Add SpotPlayer access log entry"""
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """INSERT INTO spotplayer_access_log 
                (purchase_id, user_id, action, details, ip_address)
                VALUES (?, ?, ?, ?, ?)""",
                (purchase_id, user_id, action, details, ip_address)
            )
            self.connection.commit()
            
        except Exception as e:
            logger.error(f"Error adding access log: {e}")
    
    def update_purchase_status(
        self,
        purchase_id: int,
        status: str,
        notes: str = None
    ) -> bool:
        """Update purchase status"""
        try:
            cursor = self.connection.cursor()
            
            if notes:
                cursor.execute(
                    """UPDATE spotplayer_purchases 
                    SET status = ?, notes = ?
                    WHERE purchase_id = ?""",
                    (status, notes, purchase_id)
                )
            else:
                cursor.execute(
                    """UPDATE spotplayer_purchases 
                    SET status = ?
                    WHERE purchase_id = ?""",
                    (status, purchase_id)
                )
            
            self.connection.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"Error updating purchase status: {e}")
            return False
    
    def get_duplicate_prevention_key(self, user_id: int, amount: int) -> str:
        """Generate a key for duplicate prevention"""
        from datetime import datetime
        
        # Create a time window key (5 minutes)
        time_window = datetime.now().strftime('%Y%m%d%H') + str((datetime.now().minute // 5) * 5)
        
        return f"{user_id}_{amount}_{time_window}"
    
    def is_duplicate_purchase(
        self,
        user_id: int,
        amount: int,
        tracking_code: str
    ) -> bool:
        """Check if this might be a duplicate purchase"""
        try:
            cursor = self.connection.cursor()
            
            # Check for same tracking code
            if self.check_tracking_code_exists(tracking_code):
                return True
            
            # Check for recent similar purchase (within 5 minutes)
            cursor.execute(
                """SELECT COUNT(*) FROM spotplayer_purchases
                WHERE user_id = ? 
                AND amount = ?
                AND datetime(created_at) > datetime('now', '-5 minutes')""",
                (user_id, amount)
            )
            
            count = cursor.fetchone()[0]
            return count > 0
            
        except Exception as e:
            logger.error(f"Error checking duplicate purchase: {e}")
            return False
