#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import os
import signal
import time
from datetime import datetime, timezone

import serial

# Ensure local imports resolve when running as scripts
import sys
SCRIPT_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, SCRIPT_DIR)

from project_paths import SHARED_DB_PATH
from sensor_sqlite_logger import SensorSQLiteLogger

RUNNING = True


def handle_signal(signum, frame):
    global RUNNING
    RUNNING = False


def i16(lo: int, hi: int) -> int:
    v = (hi << 8) | lo
    return v - 65536 if v > 32767 else v


def choose_port(explicit_port: str | None = None) -> str | None:
    if explicit_port:
        return explicit_port

    candidates: list[str] = []
    candidates.extend(sorted(glob.glob('/dev/ttyUSB*')))
    candidates.extend(sorted(glob.glob('/dev/ttyACM*')))
    candidates.extend(['/dev/ttyTHS1', '/dev/ttyTHS2', '/dev/ttyS1', '/dev/ttyS2', '/dev/ttyS3'])

    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def has_hwt605_frames(port: str, baud: int, probe_seconds: float = 1.5) -> bool:
    """Return True if this port appears to emit valid HWT605 frames."""
    try:
        ser = serial.Serial(port, baud, timeout=0.05)
    except Exception:
        return False

    buf = bytearray()
    good = 0
    end_t = time.time() + probe_seconds
    try:
        while time.time() < end_t:
            chunk = ser.read(256)
            if not chunk:
                continue
            buf.extend(chunk)

            while len(buf) >= 11:
                if buf[0] != 0x55:
                    del buf[0]
                    continue

                frame = buf[:11]
                del buf[:11]

                if (sum(frame[:10]) & 0xFF) != frame[10]:
                    continue
                if frame[1] in (0x51, 0x52, 0x53):
                    good += 1
                    if good >= 3:
                        return True
    finally:
        try:
            ser.close()
        except Exception:
            pass

    return False


def detect_port_with_frames(baud: int, explicit_port: str | None = None) -> str | None:
    """Find a serial port that emits valid HWT605 packets."""
    if explicit_port:
        return explicit_port if has_hwt605_frames(explicit_port, baud) else None

    candidates: list[str] = []
    candidates.extend(sorted(glob.glob('/dev/ttyUSB*')))
    candidates.extend(sorted(glob.glob('/dev/ttyACM*')))
    candidates.extend(['/dev/ttyTHS1', '/dev/ttyTHS2', '/dev/ttyS1', '/dev/ttyS2', '/dev/ttyS3'])

    for p in candidates:
        if not os.path.exists(p):
            continue
        if has_hwt605_frames(p, baud):
            return p
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description='WIT HWT605 IMU -> SQLite logger')
    parser.add_argument('--port', default=None, help='Serial port, e.g. /dev/ttyUSB0')
    parser.add_argument('--baud', type=int, default=115200, help='Serial baud rate')
    parser.add_argument('--db-path', default=str(SHARED_DB_PATH), help='SQLite database file path')
    parser.add_argument('--sensor-name', default='imu', help='Sensor table name prefix (default: imu)')
    parser.add_argument('--source-id', default='hwt605_01', help='Source ID written with each sample')
    parser.add_argument('--auto-port', action='store_true', help='Auto-detect a port that emits valid HWT605 frames')
    parser.add_argument('--quiet', action='store_true', help='Disable per-sample console output')
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    os.system('pkill -9 brltty >/dev/null 2>&1 || true')

    db_logger = SensorSQLiteLogger(args.db_path)
    print(f'Logging IMU data to SQLite: {args.db_path}')

    while RUNNING:
        if args.auto_port:
            port = detect_port_with_frames(args.baud, args.port)
        else:
            port = choose_port(args.port)

        if not port:
            if args.auto_port:
                print('No port with valid HWT605 frames found. Retrying in 2s...')
            else:
                print('No serial port found. Retrying in 2s...')
            time.sleep(2)
            continue

        try:
            ser = serial.Serial(port, args.baud, timeout=0.5)
            print(f'Connected to {port} @ {args.baud}')
        except Exception as e:
            print(f'Failed opening {port}: {e}. Retrying in 2s...')
            time.sleep(2)
            continue

        buf = bytearray()
        acc = None
        gyro = None
        ang = None

        while RUNNING:
            try:
                chunk = ser.read(128)
                if not chunk:
                    continue
                buf.extend(chunk)

                while len(buf) >= 11:
                    if buf[0] != 0x55:
                        del buf[0]
                        continue

                    frame = buf[:11]
                    del buf[:11]

                    if (sum(frame[:10]) & 0xFF) != frame[10]:
                        continue

                    frame_type = frame[1]
                    d = frame[2:10]

                    if frame_type == 0x51:
                        acc = (
                            i16(d[0], d[1]) / 32768 * 16,
                            i16(d[2], d[3]) / 32768 * 16,
                            i16(d[4], d[5]) / 32768 * 16,
                            i16(d[6], d[7]) / 100,
                        )
                    elif frame_type == 0x52:
                        gyro = (
                            i16(d[0], d[1]) / 32768 * 2000,
                            i16(d[2], d[3]) / 32768 * 2000,
                            i16(d[4], d[5]) / 32768 * 2000,
                            i16(d[6], d[7]) / 100,
                        )
                    elif frame_type == 0x53:
                        ang = (
                            i16(d[0], d[1]) / 32768 * 180,
                            i16(d[2], d[3]) / 32768 * 180,
                            i16(d[4], d[5]) / 32768 * 180,
                            i16(d[6], d[7]) / 100,
                        )

                    if acc and gyro and ang:
                        ts = datetime.now(timezone.utc)
                        sample = {
                            'roll_deg': round(ang[0], 6),
                            'pitch_deg': round(ang[1], 6),
                            'yaw_deg': round(ang[2], 6),
                            'ax_g': round(acc[0], 8),
                            'ay_g': round(acc[1], 8),
                            'az_g': round(acc[2], 8),
                            'gx_dps': round(gyro[0], 6),
                            'gy_dps': round(gyro[1], 6),
                            'gz_dps': round(gyro[2], 6),
                            'temperature_c': round(ang[3], 4),
                        }

                        db_logger.log_reading(
                            sensor_name=args.sensor_name,
                            data=sample,
                            source_id=args.source_id,
                            timestamp=ts,
                        )

                        if not args.quiet:
                            stamp = ts.isoformat(timespec='milliseconds')
                            print(
                                f"{stamp} roll={sample['roll_deg']:.3f} pitch={sample['pitch_deg']:.3f} "
                                f"yaw={sample['yaw_deg']:.3f} temp={sample['temperature_c']:.2f}C"
                            )

                        acc = None
                        gyro = None
                        ang = None

            except Exception as e:
                print(f'Serial read error on {port}: {e}. Reconnecting...')
                break

        try:
            ser.close()
        except Exception:
            pass
        time.sleep(1)

    print('SQLite IMU logger stopped.')


if __name__ == '__main__':
    main()
