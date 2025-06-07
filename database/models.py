"""
Database models for the Daraei Academy Telegram bot
"""

import sqlite3
import os
from datetime import datetime, timedelta
import config

class Database:
    """SQLite database connection and initialization"""
    
    def __init__(self, db_name=config.DATABASE_NAME):
        self.db_name = db_name
        self.conn = None
        self.cursor = None
        
    def connect(self):
        """Connect to the SQLite database"""
        try:
            self.conn = sqlite3.connect(self.db_name)
            self.conn.row_factory = sqlite3.Row  # Return rows as dictionary-like objects
            self.cursor = self.conn.cursor()
            return True
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")
            return False
            
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            
    def commit(self):
        """Commit changes to the database"""
        if self.conn:
            self.conn.commit()
            
    def execute(self, query, params=()):
        """Execute a database query with parameters"""
        try:
            self.cursor.execute(query, params)
            return True
        except sqlite3.Error as e:
            print(f"Query execution error: {e}")
            print(f"Query: {query}")
            print(f"Params: {params}")
            return False
            
    def executemany(self, query, params_list):
        """Execute a database query with multiple parameter sets"""
        try:
            self.cursor.executemany(query, params_list)
            return True
        except sqlite3.Error as e:
            print(f"Query execution error: {e}")
            return False
            
    def fetchone(self):
        """Fetch a single row from the result set"""
        return self.cursor.fetchone()
        
    def fetchall(self):
        """Fetch all rows from the result set"""
        return self.cursor.fetchall()
        
    def create_tables(self, tables):
        """Create database tables if they don't exist"""
        for table_query in tables:
            if not self.execute(table_query):
                return False
        return True
