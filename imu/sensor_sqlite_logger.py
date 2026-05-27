#!/usr/bin/env python3
"""Generic SQLite logger for multiple sensor types.

Each sensor type is stored in a separate table. Readings are saved with:
- auto-increment ID
- UTC timestamp
- optional source/device ID
- JSON payload for flexible sensor fields
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


class SensorSQLiteLogger:
    """Log arbitrary sensor data into SQLite with one table per sensor."""

    def __init__(self, db_path: str = "sensor_data.db") -> None:
        self.db_path = str(Path(db_path))
        self._lock = threading.Lock()
        self._ensure_db_file()

    def _ensure_db_file(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")

    @contextmanager
    def _connect(self) -> Iterable[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _sanitize_table_name(sensor_name: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", sensor_name.strip().lower())
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        if not cleaned:
            raise ValueError("sensor_name must contain at least one alphanumeric character")
        return f"sensor_{cleaned}"

    def _create_sensor_table_if_missing(self, table_name: str) -> None:
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT NOT NULL,
            source_id TEXT,
            payload_json TEXT NOT NULL
        );
        """
        index_sql = f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_recorded_at
        ON {table_name}(recorded_at);
        """
        with self._connect() as conn:
            conn.execute(create_sql)
            conn.execute(index_sql)

    def log_reading(
        self,
        sensor_name: str,
        data: Dict[str, Any],
        source_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Log a single sensor reading.

        Args:
            sensor_name: Logical sensor name (e.g. "imu", "temperature", "gps").
            data: Arbitrary sensor payload dictionary.
            source_id: Optional sensor device identifier.
            timestamp: Optional datetime; defaults to current UTC time.
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        table_name = self._sanitize_table_name(sensor_name)
        recorded_at = (timestamp or datetime.now(timezone.utc)).isoformat()
        payload_json = json.dumps(data, separators=(",", ":"), ensure_ascii=True)

        with self._lock:
            self._create_sensor_table_if_missing(table_name)
            with self._connect() as conn:
                conn.execute(
                    f"INSERT INTO {table_name} (recorded_at, source_id, payload_json) VALUES (?, ?, ?)",
                    (recorded_at, source_id, payload_json),
                )

    def log_many(
        self,
        sensor_name: str,
        readings: Iterable[Dict[str, Any]],
        source_id: Optional[str] = None,
    ) -> None:
        """Log multiple readings for one sensor in a batch."""
        table_name = self._sanitize_table_name(sensor_name)
        with self._lock:
            self._create_sensor_table_if_missing(table_name)
            with self._connect() as conn:
                for data in readings:
                    if not isinstance(data, dict):
                        raise TypeError("each reading must be a dictionary")
                    recorded_at = datetime.now(timezone.utc).isoformat()
                    payload_json = json.dumps(data, separators=(",", ":"), ensure_ascii=True)
                    conn.execute(
                        f"INSERT INTO {table_name} (recorded_at, source_id, payload_json) VALUES (?, ?, ?)",
                        (recorded_at, source_id, payload_json),
                    )

    def fetch_recent(self, sensor_name: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch recent readings for a sensor table."""
        table_name = self._sanitize_table_name(sensor_name)
        self._create_sensor_table_if_missing(table_name)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, recorded_at, source_id, payload_json
                FROM {table_name}
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(
                {
                    "id": row[0],
                    "recorded_at": row[1],
                    "source_id": row[2],
                    "data": json.loads(row[3]),
                }
            )
        return result


if __name__ == "__main__":
    logger = SensorSQLiteLogger("sensor_data.db")

    logger.log_reading(
        sensor_name="imu",
        source_id="imu_01",
        data={"ax": 0.12, "ay": -0.09, "az": 9.81, "gx": 0.01, "gy": 0.02, "gz": 0.03},
    )

    logger.log_reading(
        sensor_name="temperature",
        source_id="temp_01",
        data={"celsius": 24.7, "humidity": 52.1},
    )

    logger.log_reading(
        sensor_name="gps",
        source_id="gps_01",
        data={"lat": -1.2921, "lon": 36.8219, "alt_m": 1795.4},
    )

    print("Recent IMU readings:")
    for item in logger.fetch_recent("imu", limit=5):
        print(item)
