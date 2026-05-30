#!/usr/bin/env python3
"""Read vehicle-control telemetry from an Arduino and emit unified JSON lines.

The Arduino streams speed, steering, and brake-potentiometer data over its USB
serial port. This script reads that stream, normalises it into a single JSON
object per sample, and prints one object per line to ``stdout`` so it can be
piped straight into ``vehicle_db_uploader.py`` for logging, e.g.::

    python3 arduino_serial_reader.py | python3 vehicle_db_uploader.py

The reader is deliberately tolerant of however the firmware chooses to print a
sample. Each incoming line is parsed with the first format that matches:

1. JSON object:    {"speed_kph": 12.3, "steering_deg": -4.1, "brake_pct": 20}
2. key=value:      speed=12.3 steering=-4.1 brake=20
3. CSV (ordered):  12.3,-4.1,20            # order set by --csv-order

Field names are matched case-insensitively against a list of common aliases, so
``speed``/``speed_kph``/``velocity_kph`` all map to the canonical ``speed_kph``.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any

import serial

RUNNING = True

# Canonical field -> accepted aliases (all compared lower-case).
SPEED_ALIASES = ('speed_kph', 'speed', 'speed_kmh', 'velocity_kph', 'kph', 'v', 'vel')
STEERING_ALIASES = (
    'steering_angle_deg', 'steering_deg', 'angle_deg', 'steering', 'steer', 'angle', 'wheel_deg',
)
BRAKE_ALIASES = (
    'brake_pct', 'brake', 'brake_pot', 'brake_position_pct', 'pedal_pct', 'position_pct', 'pot',
)
BRAKE_VOLTAGE_ALIASES = ('brake_voltage_v', 'brake_v', 'voltage_v', 'volts', 'voltage')


def handle_signal(signum, frame):
    global RUNNING
    RUNNING = False


def choose_port(explicit_port: str | None = None) -> str | None:
    """Pick a serial port, preferring Arduino-style USB CDC devices."""
    if explicit_port:
        return explicit_port

    candidates: list[str] = []
    # Arduinos usually enumerate as ttyACM* (Uno R3/R4, Leonardo) or ttyUSB*
    # (boards with an FTDI/CH340 USB-serial bridge).
    candidates.extend(sorted(glob.glob('/dev/ttyACM*')))
    candidates.extend(sorted(glob.glob('/dev/ttyUSB*')))
    candidates.extend(['/dev/ttyTHS1', '/dev/ttyTHS2', '/dev/ttyS1', '/dev/ttyS2', '/dev/ttyS3'])

    for port in candidates:
        if os.path.exists(port):
            return port
    return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _match_alias(fields: dict[str, Any], aliases: tuple[str, ...]) -> float | None:
    for alias in aliases:
        if alias in fields:
            number = _to_float(fields[alias])
            if number is not None:
                return number
    return None


def parse_line(line: str, csv_order: list[str]) -> dict[str, float] | None:
    """Parse a single firmware line into canonical numeric fields.

    Returns a dict that may contain ``speed_kph``, ``steering_angle_deg``,
    ``brake_pct`` and ``brake_voltage_v``. Returns ``None`` when nothing
    numeric could be extracted.
    """
    text = line.strip()
    if not text:
        return None

    fields: dict[str, Any] = {}

    # 1) JSON object.
    if text.startswith('{') and text.endswith('}'):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                fields = {str(key).lower(): val for key, val in parsed.items()}
        except json.JSONDecodeError:
            fields = {}

    # 2) key=value pairs (space/comma/semicolon separated).
    if not fields and '=' in text:
        for chunk in text.replace(',', ' ').replace(';', ' ').split():
            if '=' not in chunk:
                continue
            key, _, val = chunk.partition('=')
            key = key.strip().lower()
            if key:
                fields[key] = val.strip()

    # 3) Positional CSV mapped onto --csv-order.
    if not fields and (',' in text or ' ' in text):
        parts = [p.strip() for p in text.replace(';', ',').replace(' ', ',').split(',') if p.strip()]
        for name, raw in zip(csv_order, parts):
            fields[name.lower()] = raw

    if not fields:
        return None

    sample: dict[str, float] = {}
    speed = _match_alias(fields, SPEED_ALIASES)
    if speed is not None:
        sample['speed_kph'] = round(speed, 3)
    steering = _match_alias(fields, STEERING_ALIASES)
    if steering is not None:
        sample['steering_angle_deg'] = round(steering, 3)
    brake = _match_alias(fields, BRAKE_ALIASES)
    if brake is not None:
        sample['brake_pct'] = round(brake, 3)
    brake_v = _match_alias(fields, BRAKE_VOLTAGE_ALIASES)
    if brake_v is not None:
        sample['brake_voltage_v'] = round(brake_v, 4)

    return sample or None


def main() -> None:
    parser = argparse.ArgumentParser(description='Arduino vehicle-controls serial reader -> unified JSON lines')
    parser.add_argument('--port', default=None, help='Serial port, e.g. /dev/ttyACM0 (auto-detected if omitted)')
    parser.add_argument('--baud', type=int, default=115200, help='Serial baud rate (default: 115200)')
    parser.add_argument('--source-id', default='vehicle_controls_01', help='Source ID included with each sample')
    parser.add_argument(
        '--csv-order',
        default='speed_kph,steering_angle_deg,brake_pct',
        help='Comma-separated column order used when the firmware prints bare CSV values',
    )
    parser.add_argument('--quiet', action='store_true', help='Disable status messages on stderr')
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # brltty can grab USB serial adapters on some Linux systems and block reads.
    os.system('pkill -9 brltty >/dev/null 2>&1 || true')

    csv_order = [c.strip() for c in args.csv_order.split(',') if c.strip()]
    sequence = 0

    while RUNNING:
        port = choose_port(args.port)
        if not port:
            if not args.quiet:
                print('No serial port found. Retrying in 2s...', file=sys.stderr)
            time.sleep(2)
            continue

        try:
            ser = serial.Serial(port, args.baud, timeout=1.0)
            if not args.quiet:
                print(f'Connected to {port} @ {args.baud}', file=sys.stderr)
        except Exception as exc:  # noqa: BLE001 - report and retry on any open failure
            if not args.quiet:
                print(f'Failed opening {port}: {exc}. Retrying in 2s...', file=sys.stderr)
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

                    sample = parse_line(raw_line, csv_order)
                    if sample is None:
                        continue

                    sequence += 1
                    sample['sequence'] = sequence
                    sample['recorded_at'] = datetime.now(timezone.utc).isoformat()
                    sample['source_id'] = args.source_id

                    print(json.dumps(sample, separators=(',', ':'), ensure_ascii=True), flush=True)

                    if not args.quiet:
                        print(f'sample {sequence}: {raw_line}', file=sys.stderr)

            except Exception as exc:  # noqa: BLE001 - reconnect on transient serial errors
                if not args.quiet:
                    print(f'Serial read error on {port}: {exc}. Reconnecting...', file=sys.stderr)
                break

        try:
            ser.close()
        except Exception:
            pass
        time.sleep(1)

    if not args.quiet:
        print('Arduino serial reader stopped.', file=sys.stderr)


if __name__ == '__main__':
    main()
