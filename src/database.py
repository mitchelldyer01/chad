import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Tuple
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = "data/pr_tracker.db"):
        self.db_path = db_path
        self.init_db()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        """Initialize the database with required tables."""
        with self.get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS processed_prs (
                    pr_number INTEGER PRIMARY KEY,
                    processed_at TIMESTAMP,
                    status TEXT,
                    review_url TEXT
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS review_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pr_number INTEGER,
                    reviewed_at TIMESTAMP,
                    feedback TEXT,
                    status TEXT,
                    FOREIGN KEY (pr_number) REFERENCES processed_prs (pr_number)
                )
            ''')

    def is_pr_processed(self, pr_number: int) -> bool:
        """Check if a PR has been processed."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                'SELECT 1 FROM processed_prs WHERE pr_number = ?', 
                (pr_number,)
            )
            return cursor.fetchone() is not None

    def mark_pr_processed(self, pr_number: int, status: str = "completed", review_url: Optional[str] = None):
        """Mark a PR as processed."""
        with self.get_connection() as conn:
            conn.execute(
                '''INSERT INTO processed_prs (pr_number, processed_at, status, review_url) 
                   VALUES (?, ?, ?, ?)''',
                (pr_number, datetime.now(timezone.utc), status, review_url)
            )
            conn.commit()

    def add_review_history(self, pr_number: int, feedback: str, status: str = "completed"):
        """Add a review to the history."""
        with self.get_connection() as conn:
            conn.execute(
                '''INSERT INTO review_history (pr_number, reviewed_at, feedback, status)
                   VALUES (?, ?, ?, ?)''',
                (pr_number, datetime.now(timezone.utc), feedback, status)
            )
            conn.commit()

    def get_review_history(self, pr_number: int) -> List[Tuple]:
        """Get review history for a PR."""
        with self.get_connection() as conn:
            cursor = conn.execute(
                '''SELECT reviewed_at, feedback, status 
                   FROM review_history 
                   WHERE pr_number = ?
                   ORDER BY reviewed_at DESC''',
                (pr_number,)
            )
            return cursor.fetchall()
