from datetime import datetime, timezone
import sqlite3
from contextlib import contextmanager
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class MetricsManager:
    def __init__(self, db_path: str = "data/pr_tracker.db"):
        self.db_path = db_path
        self.init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        """Initialize metrics tables."""
        with self.get_connection() as conn:
            # PR Processing Metrics
            conn.execute('''
                CREATE TABLE IF NOT EXISTS pr_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pr_number INTEGER,
                    processing_start TIMESTAMP,
                    processing_end TIMESTAMP,
                    status TEXT,
                    diff_size INTEGER,
                    processing_duration_seconds FLOAT,
                    error_message TEXT
                )
            ''')

            # LLM Metrics
            conn.execute('''
                CREATE TABLE IF NOT EXISTS llm_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pr_number INTEGER,
                    timestamp TIMESTAMP,
                    input_tokens INTEGER,
                    output_tokens INTEGER,
                    processing_time_seconds FLOAT,
                    error_message TEXT
                )
            ''')

            # Daily Summary Metrics
            conn.execute('''
                CREATE TABLE IF NOT EXISTS daily_metrics (
                    date DATE PRIMARY KEY,
                    prs_processed INTEGER,
                    successful_reviews INTEGER,
                    failed_reviews INTEGER,
                    avg_processing_time FLOAT,
                    total_tokens_used INTEGER
                )
            ''')

    def start_pr_processing(self, pr_number: int) -> int:
        """Record the start of PR processing."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                INSERT INTO pr_metrics (pr_number, processing_start, status)
                VALUES (?, ?, ?)
            ''', (pr_number, datetime.now(timezone.utc), 'processing'))
            return cursor.lastrowid

    def end_pr_processing(self, metric_id: int, status: str, diff_size: Optional[int] = None, 
                         error_message: Optional[str] = None):
        """Record the end of PR processing."""
        end_time = datetime.now(timezone.utc)
        
        with self.get_connection() as conn:
            # Get start time
            cursor = conn.execute('SELECT processing_start FROM pr_metrics WHERE id = ?', (metric_id,))
            result = cursor.fetchone()
            if not result:
                return
            
            start_time = datetime.fromisoformat(result[0])
            duration = (end_time - start_time).total_seconds()
            
            conn.execute('''
                UPDATE pr_metrics 
                SET processing_end = ?,
                    status = ?,
                    diff_size = ?,
                    processing_duration_seconds = ?,
                    error_message = ?
                WHERE id = ?
            ''', (end_time, status, diff_size, duration, error_message, metric_id))

    def record_llm_metrics(self, pr_number: int, input_tokens: int, output_tokens: int, 
                          processing_time: float, error_message: Optional[str] = None):
        """Record metrics for an LLM operation."""
        with self.get_connection() as conn:
            conn.execute('''
                INSERT INTO llm_metrics 
                (pr_number, timestamp, input_tokens, output_tokens, 
                 processing_time_seconds, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (pr_number, datetime.now(timezone.utc), input_tokens, output_tokens,
                 processing_time, error_message))

    def update_daily_metrics(self):
        """Update the daily metrics summary."""
        today = datetime.now(timezone.utc).date()
        
        with self.get_connection() as conn:
            # Calculate metrics for today
            cursor = conn.execute('''
                SELECT 
                    COUNT(*) as total_prs,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN status != 'completed' THEN 1 ELSE 0 END) as failed,
                    AVG(processing_duration_seconds) as avg_time
                FROM pr_metrics
                WHERE date(processing_start) = ?
            ''', (today,))
            pr_stats = cursor.fetchone()

            cursor = conn.execute('''
                SELECT SUM(input_tokens + output_tokens) as total_tokens
                FROM llm_metrics
                WHERE date(timestamp) = ?
            ''', (today,))
            token_stats = cursor.fetchone()

            # Update daily metrics
            conn.execute('''
                INSERT OR REPLACE INTO daily_metrics 
                (date, prs_processed, successful_reviews, failed_reviews, 
                 avg_processing_time, total_tokens_used)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (today, pr_stats[0], pr_stats[1], pr_stats[2], 
                 pr_stats[3], token_stats[0] or 0))

    def get_daily_metrics(self, days: int = 7) -> list:
        """Get metrics for the last N days."""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM daily_metrics
                ORDER BY date DESC
                LIMIT ?
            ''', (days,))
            return cursor.fetchall()
