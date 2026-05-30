#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import signal
import time
from datetime import datetime, timezone


RUNNING = True
CURRENT_ANGLE_DEG = 0.0


def handle_signal(signum, frame):
    global RUNNING
    RUNNING = False


def build_sample(sequence: int, rng: random.Random) -> dict[str, float | int | str]:
    global CURRENT_ANGLE_DEG

    target_angle = 12.0 * rng.uniform(-1.0, 1.0) + 8.0 * ((sequence % 240) / 240.0 - 0.5)
    target_angle += 6.0 * rng.uniform(-0.25, 0.25)
    target_angle = max(-35.0, min(35.0, target_angle))

    angle_step = target_angle - CURRENT_ANGLE_DEG
    angle_step = max(-0.9, min(0.9, angle_step))
    angle_deg = max(-45.0, min(45.0, CURRENT_ANGLE_DEG + angle_step))
    CURRENT_ANGLE_DEG = angle_deg

    return {
        'sequence': sequence,
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'angle_deg': round(angle_deg, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Steering potentiometer simulator')
    parser.add_argument('--interval', type=float, default=0.2, help='Seconds between samples')
    parser.add_argument('--count', type=int, default=0, help='Number of samples to emit; 0 runs forever')
    parser.add_argument('--seed', type=int, default=23, help='Random seed for repeatable output')
    parser.add_argument('--source-id', default='steering_pot_01', help='Source ID to include in each sample')
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    rng = random.Random(args.seed)
    sequence = 0
    global CURRENT_ANGLE_DEG
    CURRENT_ANGLE_DEG = 0.0

    while RUNNING and (args.count <= 0 or sequence < args.count):
        sequence += 1
        sample = build_sample(sequence, rng)
        sample['source_id'] = args.source_id
        print(json.dumps(sample, separators=(',', ':'), ensure_ascii=True), flush=True)

        if args.count <= 0 or sequence < args.count:
            time.sleep(max(0.0, args.interval))


if __name__ == '__main__':
    main()