"""
Database connection pooling for improved performance and reliability
"""

import sqlite3
import threading
import queue
import logging
from contextlib import contextmanager
import config
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabasePool:
    """SQLite connection pool manager"""
    
    def __init__(self, db_path: str = None, pool_size: int = 5, timeout: float = 10.0):
        """
        Initialize the database connection pool.
        
        Args:
            db_path: Path to the database file
            pool_size: Number of connections to maintain in the pool
            timeout: Connection timeout in seconds
        """
        if db_path is None:
            if hasattr(config, 'DATABASE_NAME') and config.DATABASE_NAME:
                db_path = config.DATABASE_NAME
            else:
                db_path = os.path.join(os.getcwd(), 'database', 'data', 'bot_database.db')
        
        self.db_path = db_path
        self.pool_size = pool_size
        self.timeout = timeout
        self._pool = queue.Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._connections_created = 0
        
        # Pre-create connections
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Pre-create database connections for the pool"""
        try:
            for _ in range(self.pool_size):
                conn = self._create_connection()
                self._pool.put(conn)
            logger.info(f"Database pool initialized with {self.pool_size} connections")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection with optimized settings"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            check_same_thread=False,
            isolation_level=None  # Autocommit mode
        )
        
        # Enable row factory for dict-like access
        conn.row_factory = sqlite3.Row
        
        # Optimize SQLite settings for better performance
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode = WAL")  # Write-Ahead Logging
        cursor.execute("PRAGMA synchronous = NORMAL")  # Faster writes
        cursor.execute("PRAGMA cache_size = 10000")  # Larger cache
        cursor.execute("PRAGMA temp_store = MEMORY")  # Use memory for temp tables
        cursor.execute("PRAGMA busy_timeout = 10000")  # 10 second busy timeout
        cursor.close()
        
        self._connections_created += 1
        return conn
    
    @contextmanager
    def get_connection(self):
        """
        Get a connection from the pool.
        
        Usage:
            with pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users")
                ...
        """
        conn = None
        try:
            # Try to get a connection from the pool
            try:
                conn = self._pool.get(timeout=self.timeout)
            except queue.Empty:
                logger.warning("Connection pool exhausted, creating new connection")
                conn = self._create_connection()
            
            # Test if connection is still alive
            try:
                conn.execute("SELECT 1")
            except sqlite3.Error:
                logger.warning("Dead connection detected, creating new one")
                try:
                    conn.close()
                except:
                    pass
                conn = self._create_connection()
            
            yield conn
            
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            # Return connection to pool if possible
            if conn:
                try:
                    if not self._pool.full():
                        self._pool.put(conn)
                    else:
                        conn.close()
                except:
                    try:
                        conn.close()
                    except:
                        pass
    
    def close_all(self):
        """Close all connections in the pool"""
        closed = 0
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
                closed += 1
            except:
                break
        logger.info(f"Closed {closed} database connections")
    
    def get_stats(self):
        """Get pool statistics"""
        return {
            'pool_size': self.pool_size,
            'available_connections': self._pool.qsize(),
            'total_created': self._connections_created,
            'timestamp': datetime.now().isoformat()
        }

# Global pool instance
_pool_instance = None
_pool_lock = threading.Lock()

def get_pool() -> DatabasePool:
    """Get the global database pool instance"""
    global _pool_instance
    if _pool_instance is None:
        with _pool_lock:
            if _pool_instance is None:
                _pool_instance = DatabasePool()
    return _pool_instance

def close_pool():
    """Close the global database pool"""
    global _pool_instance
    if _pool_instance:
        _pool_instance.close_all()
        _pool_instance = None
