#!/usr/bin/env python3
"""Log unified vehicle-control JSON lines into SQLite.

Reads the JSON stream produced by ``arduino_serial_reader.py`` (or the bundled
``vehicle_simulator.py``) on ``stdin`` and writes each reading into the shared
SQLite database. A single Arduino sample carries speed, steering, and brake at
once, so it is fanned out into the three canonical sensor tables that the
dashboard already understands:

    speed_kph           -> sensor_hall_effect_speed   (field: speed_kph)
    steering_angle_deg  -> sensor_hall_effect_steering (field: angle_deg)
    brake_pct           -> sensor_brake               (field: brake_pct)

Each table keeps its own source_id so the dashboard's per-sensor view stays
tidy. Only the channels present in a given sample are written.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from project_paths import SHARED_DB_PATH
from sensor_sqlite_logger import SensorSQLiteLogger

RUNNING = True


def handle_signal(signum, frame):
    global RUNNING
    RUNNING = False


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_channel_payloads(reading: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Split one combined reading into per-sensor payloads.

    Returns a mapping of ``sensor_name -> payload``. Each payload carries the
    sequence/recorded_at metadata plus that channel's value(s). Channels with no
    numeric value in the reading are omitted.
    """
    sequence = reading.get('sequence')
    recorded_at = reading.get('recorded_at')
    base: dict[str, Any] = {}
    if sequence is not None:
        base['sequence'] = sequence
    if recorded_at is not None:
        base['recorded_at'] = recorded_at

    channels: dict[str, dict[str, Any]] = {}

    speed = _as_float(reading.get('speed_kph'))
    if speed is not None:
        channels['hall_effect_speed'] = {**base, 'speed_kph': round(speed, 3)}

    steering = _as_float(reading.get('steering_angle_deg'))
    if steering is None:
        steering = _as_float(reading.get('angle_deg'))
    if steering is not None:
        channels['hall_effect_steering'] = {**base, 'angle_deg': round(steering, 3)}

    brake = _as_float(reading.get('brake_pct'))
    if brake is not None:
        brake_payload: dict[str, Any] = {**base, 'brake_pct': round(brake, 3), 'position_pct': round(brake, 3)}
        brake_voltage = _as_float(reading.get('brake_voltage_v'))
        if brake_voltage is not None:
            brake_payload['voltage_v'] = round(brake_voltage, 4)
        channels['brake'] = brake_payload

    return channels


def main() -> None:
    parser = argparse.ArgumentParser(description='Vehicle-controls JSONL -> SQLite uploader')
    parser.add_argument('--db-path', default=str(SHARED_DB_PATH), help='SQLite database file path')
    parser.add_argument('--speed-source-id', default='hall_effect_speed_01', help='Source ID for speed rows')
    parser.add_argument('--steering-source-id', default='steering_pot_01', help='Source ID for steering rows')
    parser.add_argument('--brake-source-id', default='brake_pot_01', help='Source ID for brake rows')
    parser.add_argument('--quiet', action='store_true', help='Disable progress messages')
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    source_ids = {
        'hall_effect_speed': args.speed_source_id,
        'hall_effect_steering': args.steering_source_id,
        'brake': args.brake_source_id,
    }

    db_logger = SensorSQLiteLogger(args.db_path)
    if not args.quiet:
        print(f'Logging vehicle-control data to SQLite: {args.db_path}', file=sys.stderr)

    while RUNNING:
        line = sys.stdin.readline()
        if not line:
            break

        text = line.strip()
        if not text:
            continue

        try:
            reading = json.loads(text)
        except json.JSONDecodeError:
            if not args.quiet:
                print(f'skipping non-JSON line: {text[:80]}', file=sys.stderr)
            continue

        if not isinstance(reading, dict):
            continue

        timestamp = datetime.now(timezone.utc)
        channels = build_channel_payloads(reading)
        for sensor_name, payload in channels.items():
            payload['ingested_at'] = timestamp.isoformat()
            db_logger.log_reading(
                sensor_name=sensor_name,
                data=payload,
                source_id=source_ids[sensor_name],
                timestamp=timestamp,
            )

        if not args.quiet:
            print(f'logged sample {reading.get("sequence", "?")} -> {", ".join(channels) or "nothing"}', file=sys.stderr)

    if not args.quiet:
        print('Vehicle-controls uploader stopped.', file=sys.stderr)


if __name__ == '__main__':
    main()
