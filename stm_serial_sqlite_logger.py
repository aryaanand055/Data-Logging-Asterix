#!/usr/bin/env python3
"""Read STM serial output and store each record in SQLite.

This script is intentionally flexible because STM firmware often prints either
plain text status lines, CSV rows, JSON snippets, or key=value telemetry.
It stores the original line in SQLite and also attempts to parse useful fields.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import signal
import time
from datetime import datetime, timezone
from typing import Any

import serial

from project_paths import SHARED_DB_PATH
from sensor_sqlite_logger import SensorSQLiteLogger

RUNNING = True


def handle_signal(signum, frame):
    global RUNNING
    RUNNING = False


def choose_port(explicit_port: str | None = None) -> str | None:
    if explicit_port:
        return explicit_port

    candidates: list[str] = []
    candidates.extend(sorted(glob.glob('/dev/ttyUSB*')))
    candidates.extend(sorted(glob.glob('/dev/ttyACM*')))
    candidates.extend(['/dev/ttyTHS1', '/dev/ttyTHS2', '/dev/ttyS1', '/dev/ttyS2', '/dev/ttyS3'])

    for port in candidates:
        if os.path.exists(port):
            return port
    return None


def parse_payload(line: str) -> dict[str, Any]:
    text = line.strip()
    if not text:
        return {'raw': line, 'format': 'empty'}

    if text.startswith('{') and text.endswith('}'):
        try:
            parsed = json.loads(text)
            return {'raw': line, 'format': 'json', 'data': parsed}
        except json.JSONDecodeError:
            pass

    if '=' in text and any(sep in text for sep in (' ', ',', ';')):
        fields: dict[str, str] = {}
        for chunk in text.replace(',', ' ').replace(';', ' ').split():
            if '=' not in chunk:
                continue
            key, value = chunk.split('=', 1)
            key = key.strip()
            value = value.strip()
            if key:
                fields[key] = value
        if fields:
            return {'raw': line, 'format': 'key_value', 'data': fields}

    if ',' in text:
        parts = [part.strip() for part in text.split(',') if part.strip()]
        if len(parts) > 1:
            return {'raw': line, 'format': 'csv', 'data': parts}

    return {'raw': line, 'format': 'text'}


def open_serial(port: str, baud: int) -> serial.Serial:
    return serial.Serial(port, baud, timeout=1.0)


def main() -> None:
    parser = argparse.ArgumentParser(description='STM serial -> SQLite logger')
    parser.add_argument('--port', default=None, help='Serial port, e.g. /dev/ttyUSB0')
    parser.add_argument('--baud', type=int, default=115200, help='Serial baud rate')
    parser.add_argument('--db-path', default=str(SHARED_DB_PATH), help='SQLite database file path')
    parser.add_argument('--sensor-name', default='stm', help='Sensor table name prefix')
    parser.add_argument('--source-id', default='stm_01', help='Source ID written with each sample')
    parser.add_argument('--quiet', action='store_true', help='Disable per-line console output')
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    os.system('pkill -9 brltty >/dev/null 2>&1 || true')

    db_logger = SensorSQLiteLogger(args.db_path)
    print(f'Logging STM serial data to SQLite: {args.db_path}')

    while RUNNING:
        port = choose_port(args.port)
        if not port:
            print('No serial port found. Retrying in 2s...')
            time.sleep(2)
            continue

        try:
            ser = open_serial(port, args.baud)
            print(f'Connected to {port} @ {args.baud}')
        except Exception as exc:
            print(f'Failed opening {port}: {exc}. Retrying in 2s...')
            time.sleep(2)
            continue

        buffer = bytearray()

        while RUNNING:
            try:
                chunk = ser.read(256)
                if not chunk:
                    continue
                buffer.extend(chunk)

                while b'\n' in buffer:
                    line_bytes, _, remainder = buffer.partition(b'\n')
                    buffer = bytearray(remainder)

                    raw_line = line_bytes.decode('utf-8', errors='replace').rstrip('\r')
                    if not raw_line.strip():
                        continue

                    payload = parse_payload(raw_line)
                    timestamp = datetime.now(timezone.utc)
                    payload['received_at'] = timestamp.isoformat()

                    db_logger.log_reading(
                        sensor_name=args.sensor_name,
                        data=payload,
                        source_id=args.source_id,
                        timestamp=timestamp,
                    )

                    if not args.quiet:
                        print(raw_line)

            except Exception as exc:
                print(f'Serial read error on {port}: {exc}. Reconnecting...')
                break

        try:
            ser.close()
        except Exception:
            pass
        time.sleep(1)

    print('STM serial logger stopped.')


if __name__ == '__main__':
    main()