#!/usr/bin/env bash
set -u
BASE_DIR='/home/abaja/Documents/imu_sqlite/imu'
DB_PATH='/home/abaja/Documents/imu_sqlite/sensor_data.db'
PASS='abaja'
USB_ID='1-2.3'
LOG="$BASE_DIR/watchdog.log"

recover_tty() {
  echo "$(date -u +%FT%TZ) recovering ttyUSB0" >> "$LOG"
  echo "$PASS" | sudo -S pkill -9 brltty >/dev/null 2>&1 || true
  echo "$PASS" | sudo -S sh -c "echo $USB_ID > /sys/bus/usb/drivers/usb/unbind; sleep 1; echo $USB_ID > /sys/bus/usb/drivers/usb/bind" >/dev/null 2>&1 || true
  sleep 1
}

while true; do
  if [ ! -e /dev/ttyUSB0 ]; then
    recover_tty
  fi

  if ! pgrep -f "$BASE_DIR/hwt605_logger.py --port /dev/ttyUSB0" >/dev/null 2>&1; then
    echo "$(date -u +%FT%TZ) starting logger" >> "$LOG"
    nohup python3 "$BASE_DIR/hwt605_logger.py" --port /dev/ttyUSB0 --baud 115200 --db-path "$DB_PATH" --quiet > "$BASE_DIR/logger.out" 2>&1 &
    sleep 1
  fi

  sleep 2
done
