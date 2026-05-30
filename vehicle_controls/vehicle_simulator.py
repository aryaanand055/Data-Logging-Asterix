#!/usr/bin/env python3
"""Simulate an Arduino streaming speed, steering, and brake telemetry.

Emits the exact same unified JSON lines that ``arduino_serial_reader.py``
produces, so the full logging chain can be exercised without hardware::

    python3 vehicle_simulator.py | python3 vehicle_db_uploader.py

Speed, steering, and brake are loosely coupled to look like a plausible drive:
braking bleeds off speed, and steering wanders as if tracking a course.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import signal
import time
from datetime import datetime, timezone

RUNNING = True

speed_kph = 0.0
angle_deg = 0.0
brake_pct = 0.0


def handle_signal(signum, frame):
    global RUNNING
    RUNNING = False


def build_sample(sequence: int, rng: random.Random) -> dict[str, float | int | str]:
    global speed_kph, angle_deg, brake_pct

    # Brake comes and goes in gentle pulses.
    target_brake = max(0.0, 35.0 * math.sin(sequence / 33.0) + rng.uniform(-6.0, 6.0))
    target_brake = min(100.0, target_brake)
    brake_pct += (target_brake - brake_pct) * 0.15

    # Speed climbs toward a cruising target but is pulled down by braking.
    cruise = 22.0 + 6.0 * math.sin(sequence / 25.0)
    target_speed = max(0.0, cruise - brake_pct * 0.25 + rng.uniform(-0.8, 0.8))
    target_speed = min(40.0, target_speed)
    speed_kph += (target_speed - speed_kph) * 0.12
    speed_kph = max(0.0, min(40.0, speed_kph))

    # Steering wanders within a believable lock range.
    target_angle = 14.0 * math.sin(sequence / 40.0) + 6.0 * rng.uniform(-1.0, 1.0)
    target_angle = max(-35.0, min(35.0, target_angle))
    step = max(-1.2, min(1.2, target_angle - angle_deg))
    angle_deg = max(-45.0, min(45.0, angle_deg + step))

    # Map brake percentage to a 0-5 V potentiometer reading.
    brake_voltage_v = round(brake_pct / 100.0 * 5.0, 4)

    return {
        'sequence': sequence,
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'speed_kph': round(speed_kph, 3),
        'steering_angle_deg': round(angle_deg, 3),
        'brake_pct': round(brake_pct, 3),
        'brake_voltage_v': brake_voltage_v,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Vehicle-controls (speed/steering/brake) simulator')
    parser.add_argument('--interval', type=float, default=0.2, help='Seconds between samples')
    parser.add_argument('--count', type=int, default=0, help='Number of samples to emit; 0 runs forever')
    parser.add_argument('--seed', type=int, default=29, help='Random seed for repeatable output')
    parser.add_argument('--source-id', default='vehicle_controls_01', help='Source ID to include in each sample')
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    rng = random.Random(args.seed)
    sequence = 0

    while RUNNING and (args.count <= 0 or sequence < args.count):
        sequence += 1
        sample = build_sample(sequence, rng)
        sample['source_id'] = args.source_id
        print(json.dumps(sample, separators=(',', ':'), ensure_ascii=True), flush=True)

        if args.count <= 0 or sequence < args.count:
            time.sleep(max(0.0, args.interval))


if __name__ == '__main__':
    main()
