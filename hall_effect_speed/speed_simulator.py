#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import random
import signal
import time
from datetime import datetime, timezone


RUNNING = True
CURRENT_SPEED_KPH = 0.0


def handle_signal(signum, frame):
    global RUNNING
    RUNNING = False


def build_sample(sequence: int, rng: random.Random) -> dict[str, float | int | str]:
    global CURRENT_SPEED_KPH
    target_speed = 18.0 + 8.0 * math.sin(sequence / 22.0) + 2.0 * math.sin(sequence / 7.0)
    target_speed += rng.uniform(-0.8, 0.8)
    target_speed = max(0.0, min(30.0, target_speed))

    speed_kph = CURRENT_SPEED_KPH + (target_speed - CURRENT_SPEED_KPH) * 0.12
    speed_kph = max(0.0, min(30.0, speed_kph))
    CURRENT_SPEED_KPH = speed_kph

    return {
        'sequence': sequence,
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'speed_kph': round(speed_kph, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Hall-effect speed simulator')
    parser.add_argument('--interval', type=float, default=0.2, help='Seconds between samples')
    parser.add_argument('--count', type=int, default=0, help='Number of samples to emit; 0 runs forever')
    parser.add_argument('--seed', type=int, default=11, help='Random seed for repeatable output')
    parser.add_argument('--source-id', default='hall_effect_speed_01', help='Source ID to include in each sample')
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    rng = random.Random(args.seed)
    sequence = 0
    global CURRENT_SPEED_KPH
    CURRENT_SPEED_KPH = 0.0

    while RUNNING and (args.count <= 0 or sequence < args.count):
        sequence += 1
        sample = build_sample(sequence, rng)
        sample['source_id'] = args.source_id
        print(json.dumps(sample, separators=(',', ':'), ensure_ascii=True), flush=True)

        if args.count <= 0 or sequence < args.count:
            time.sleep(max(0.0, args.interval))


if __name__ == '__main__':
    main()