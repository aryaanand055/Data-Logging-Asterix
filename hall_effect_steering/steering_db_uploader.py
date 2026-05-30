#!/usr/bin/env python3
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


def normalize_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        payload = dict(raw)
        nested = payload.pop('data', None)
        if isinstance(nested, dict):
            payload.update(nested)
        payload.pop('source_id', None)
        return payload
    return {'raw': raw}


def main() -> None:
    parser = argparse.ArgumentParser(description='Steering potentiometer JSONL -> SQLite uploader')
    parser.add_argument('--db-path', default=str(SHARED_DB_PATH), help='SQLite database file path')
    parser.add_argument('--sensor-name', default='hall_effect_steering', help='Sensor table name prefix')
    parser.add_argument('--source-id', default='steering_pot_01', help='Source ID written with each sample')
    parser.add_argument('--quiet', action='store_true', help='Disable progress messages')
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    db_logger = SensorSQLiteLogger(args.db_path)
    if not args.quiet:
        print(f'Logging steering data to SQLite: {args.db_path}', file=sys.stderr)

    while RUNNING:
        line = sys.stdin.readline()
        if not line:
            break

        text = line.strip()
        if not text:
            continue

        try:
            raw_payload = json.loads(text)
        except json.JSONDecodeError:
            raw_payload = {'raw': text}

        payload = normalize_payload(raw_payload)
        timestamp = datetime.now(timezone.utc)
        payload['ingested_at'] = timestamp.isoformat()

        source_id = args.source_id
        if isinstance(raw_payload, dict) and isinstance(raw_payload.get('source_id'), str):
            source_id = raw_payload['source_id']

        db_logger.log_reading(
            sensor_name=args.sensor_name,
            data=payload,
            source_id=source_id,
            timestamp=timestamp,
        )

        if not args.quiet:
            print(f'logged steering sample {payload.get("sequence", "?")}', file=sys.stderr)

    if not args.quiet:
        print('Steering uploader stopped.', file=sys.stderr)


if __name__ == '__main__':
    main()