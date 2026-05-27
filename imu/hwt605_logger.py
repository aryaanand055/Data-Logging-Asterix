#!/usr/bin/env python3
import argparse
import datetime as dt
import glob
import os
import signal
import sys
import time

import serial

SCRIPT_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, SCRIPT_DIR)

RUNNING = True


def handle_signal(signum, frame):
    global RUNNING
    RUNNING = False


def i16(lo, hi):
    v = (hi << 8) | lo
    return v - 65536 if v > 32767 else v


def choose_port(explicit_port=None):
    if explicit_port:
        return explicit_port

    candidates = []
    candidates.extend(sorted(glob.glob('/dev/ttyUSB*')))
    candidates.extend(sorted(glob.glob('/dev/ttyACM*')))
    # Fallback candidates if IMU is wired to UART
    candidates.extend(['/dev/ttyTHS1', '/dev/ttyTHS2', '/dev/ttyS1', '/dev/ttyS2', '/dev/ttyS3'])

    for p in candidates:
        if os.path.exists(p):
            return p
    return None


# CSV logging removed: this logger now only listens to IMU and prints samples.


def main():
    parser = argparse.ArgumentParser(description='WIT HWT605 IMU listener (no CSV)')
    parser.add_argument('--port', default=None, help='Serial port, e.g. /dev/ttyUSB0')
    parser.add_argument('--baud', type=int, default=115200, help='Serial baud rate (default: 9600)')
    parser.add_argument('--quiet', action='store_true', help='Disable console print for each sample')
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Best-effort workaround: stop user-space brltty process if it is present.
    os.system('pkill -9 brltty >/dev/null 2>&1 || true')
    print('Listening for IMU samples; CSV logging disabled.')

    while RUNNING:
        port = choose_port(args.port)
        if not port:
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
        acc = gyro = ang = None

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
                        ts = dt.datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
                        row = [
                            ts,
                            f'{ang[0]:.3f}', f'{ang[1]:.3f}', f'{ang[2]:.3f}',
                            f'{acc[0]:.5f}', f'{acc[1]:.5f}', f'{acc[2]:.5f}',
                            f'{gyro[0]:.3f}', f'{gyro[1]:.3f}', f'{gyro[2]:.3f}',
                            f'{ang[3]:.2f}',
                        ]

                        if not args.quiet:
                            print(','.join(row))

                        acc = gyro = ang = None

            except Exception as e:
                print(f'Serial read error on {port}: {e}. Reconnecting...')
                break

        try:
            ser.close()
        except Exception:
            pass
        time.sleep(1)

    print('Listener stopped.')


if __name__ == '__main__':
    main()
