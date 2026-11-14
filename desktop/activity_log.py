"""
Patient progression log.

Stores WHEN actions happen and HOW (for example how long a blink was held),
never WHAT was typed or clicked on. Doctors can use the daily totals to see
how motor control changes over time. For example:
- blink hold time getting longer or less consistent
- zoom being needed more often
- fewer actions per day

Libraries: sqlite3 (part of Python): https://docs.python.org/3/library/sqlite3.html
Written with the assistance of Claude Code (Anthropic).
"""

import sqlite3
import time
from pathlib import Path

LOG_FILE = Path(__file__).parent / "activity_log.db"


class ActivityLog:
    def __init__(self, path: Path = LOG_FILE):
        self.database = sqlite3.connect(path)
        self.database.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            " time REAL, kind TEXT, value REAL, note TEXT)"
        )

    def record(self, kind: str, value: float = 0.0, note: str = "") -> dict:
        """Save one event, e.g. record("click", 0.72) for a 0.72 s blink."""
        event = {"time": time.time(), "kind": kind, "value": value, "note": note}
        self.database.execute(
            "INSERT INTO events VALUES (:time, :kind, :value, :note)", event)
        self.database.commit()
        return event

    def daily_summary(self) -> list[dict]:
        """One row per day and kind of action: how many and the average value."""
        rows = self.database.execute(
            "SELECT date(time, 'unixepoch', 'localtime') AS day, kind,"
            " COUNT(*), ROUND(AVG(value), 3)"
            " FROM events GROUP BY day, kind ORDER BY day, kind"
        )
        return [
            {"day": day, "kind": kind, "count": count, "average_value": average}
            for day, kind, count, average in rows
        ]


if __name__ == "__main__":
    # Print the summary: python activity_log.py
    for row in ActivityLog().daily_summary():
        print(row)
