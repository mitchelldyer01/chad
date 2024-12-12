from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, DataTable, Line, Label
from textual.reactive import reactive
from rich.console import Console
from rich.layout import Layout
import asciichartpy
import sqlite3
import asyncio
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

class Graph(Static):
    """A widget for displaying ASCII graphs."""
    def __init__(self, title: str, graph_type: str = "line", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = title
        self.graph_type = graph_type
        self.data = []

    def create_line_graph(self, data, width=60, height=10):
        """Create a line graph using asciichartpy."""
        config = {
            'height': height,
            'width': width,
            'format': '{:8.0f}',
            'colors': [
                asciichartpy.blue,
                asciichartpy.green,
                asciichartpy.red
            ]
        }
        return asciichartpy.plot(data, config)

    def create_bar_graph(self, data, width=60, height=10):
        """Create a bar graph using Unicode block characters."""
        if not data:
            return ""
            
        max_val = max(data)
        ratio = height / max_val if max_val > 0 else 0
        bars = []
        
        blocks = " ▁▂▃▄▅▆▇█"
        for val in data:
            bar_height = val * ratio
            full_blocks = int(bar_height)
            remainder = bar_height - full_blocks
            partial_block_idx = int(remainder * len(blocks))
            
            bar = "█" * full_blocks
            if partial_block_idx > 0:
                bar += blocks[partial_block_idx]
            bar = bar.ljust(height)
            bars.append(bar)
        
        # Rotate the graph
        return "\n".join("".join(row) for row in zip(*reversed(bars)))

    def update_data(self, new_data):
        """Update the graph data."""
        self.data = new_data
        self.refresh()

    def render(self):
        """Render the graph."""
        if self.graph_type == "line":
            graph = self.create_line_graph(self.data)
        else:  # bar
            graph = self.create_bar_graph(self.data)
        
        return f"{self.title}\n{graph}"

class MetricsPanel(Static):
    """A panel displaying a specific metric with title and graph."""
    def __init__(self, title: str, graph_type: str = "line", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = title
        self.graph_type = graph_type

    def compose(self) -> ComposeResult:
        yield Label(self.title, classes="panel-title")
        yield Line()
        yield Static("", classes="panel-content", id=f"{self.title.lower().replace(' ', '-')}-content")
        yield Graph("", self.graph_type, classes="panel-graph", id=f"{self.title.lower().replace(' ', '-')}-graph")

class PRMetricsDashboard(App):
    """A TUI dashboard for PR review metrics with graphs."""
    CSS = """
    Screen {
        background: $surface;
    }

    Header {
        dock: top;
        background: $accent;
        color: $text;
        padding: 1;
    }

    Footer {
        background: $accent;
        color: $text;
        padding: 1;
    }

    MetricsPanel {
        height: auto;
        border: solid $accent;
        margin: 1;
        padding: 1;
    }

    .panel-title {
        text-align: center;
        text-style: bold;
    }

    .panel-content {
        margin: 1;
    }

    .panel-graph {
        margin-top: 1;
        min-height: 12;
    }

    DataTable {
        height: auto;
        margin: 1;
    }

    #metrics-container {
        layout: grid;
        grid-size: 2 2;
        grid-gutter: 1;
    }

    #table-container {
        height: 30%;
    }
    """

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header(show_clock=True)
        yield Container(
            Container(
                MetricsPanel("PR Processing", "line"),
                MetricsPanel("Success Rate", "bar"),
                MetricsPanel("Processing Times", "line"),
                MetricsPanel("Token Usage", "bar"),
                id="metrics-container"
            ),
            Container(
                DataTable(id="recent-prs"),
                id="table-container"
            )
        )
        yield Footer()

    async def on_mount(self) -> None:
        """Set up the dashboard when the app starts."""
        table = self.query_one("#recent-prs", DataTable)
        table.add_columns(
            "PR #", "Status", "Processing Time", "Tokens Used", "Timestamp"
        )
        
        self.update_task = asyncio.create_task(self.periodic_update())

    def get_historical_data(self, days=7):
        """Get historical data for graphs."""
        conn = sqlite3.connect(self.db_path)
        
        # PR Processing history
        pr_history = pd.read_sql_query('''
            SELECT 
                date(processing_start) as date,
                COUNT(*) as count
            FROM pr_metrics
            WHERE date(processing_start) >= date('now', ?)
            GROUP BY date(processing_start)
            ORDER BY date
        ''', conn, params=(f'-{days} days',))
        
        # Success rate history
        success_history = pd.read_sql_query('''
            SELECT 
                date(processing_start) as date,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as rate
            FROM pr_metrics
            WHERE date(processing_start) >= date('now', ?)
            GROUP BY date(processing_start)
            ORDER BY date
        ''', conn, params=(f'-{days} days',))
        
        # Processing times history
        times_history = pd.read_sql_query('''
            SELECT 
                date(processing_start) as date,
                AVG(processing_duration_seconds) as avg_time
            FROM pr_metrics
            WHERE date(processing_start) >= date('now', ?)
            GROUP BY date(processing_start)
            ORDER BY date
        ''', conn, params=(f'-{days} days',))
        
        # Token usage history
        token_history = pd.read_sql_query('''
            SELECT 
                date(timestamp) as date,
                SUM(input_tokens + output_tokens) as total_tokens
            FROM llm_metrics
            WHERE date(timestamp) >= date('now', ?)
            GROUP BY date(timestamp)
            ORDER BY date
        ''', conn, params=(f'-{days} days',))
        
        conn.close()
        
        return {
            'pr_processing': pr_history['count'].tolist(),
            'success_rate': success_history['rate'].tolist(),
            'processing_times': times_history['avg_time'].tolist(),
            'token_usage': token_history['total_tokens'].tolist()
        }

    async def update_metrics(self) -> None:
        """Update all metrics and graphs."""
        try:
            # Get historical data for graphs
            historical_data = self.get_historical_data()
            
            # Update graphs
            self.query_one("#pr-processing-graph", Graph).update_data(historical_data['pr_processing'])
            self.query_one("#success-rate-graph", Graph).update_data(historical_data['success_rate'])
            self.query_one("#processing-times-graph", Graph).update_data(historical_data['processing_times'])
            self.query_one("#token-usage-graph", Graph).update_data(historical_data['token_usage'])
            
            # Update rest of the metrics as before...
            # [Previous metrics update code remains the same]

        except Exception as e:
            self.query_one(Footer).highlight = f"Error updating metrics: {str(e)}"

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Real-time PR Metrics Dashboard')
    parser.add_argument('--db-path', type=str, default='data/pr_tracker.db',
                       help='Path to SQLite database')
    parser.add_argument('--interval', type=int, default=5,
                       help='Update interval in seconds')
    
    args = parser.parse_args()
    
    app = PRMetricsDashboard(db_path=args.db_path)
    app.update_interval = args.interval
    app.run()

if __name__ == "__main__":
    main()
