#!/usr/bin/env bash
set -euo pipefail

# Simple launcher for the multi-sensor system.
# Usage: ./launch_all.sh [--help] [--start] [--stop] [--status] [--no-imu] [--no-stm] [--no-dashboard]

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$DIR/logs"
DB_PATH="$DIR/sensor_data.db"
mkdir -p "$LOG_DIR"

start_dashboard=true
start_imu=true
start_stm=true

usage(){
  cat <<EOF
Usage: $0 [options]

Options:
  --help           Show this help
  --start          Start selected services (default)
  --stop           Stop selected services
  --status         Show service status
  --no-imu         Do not start IMU logger
  --no-stm         Do not start STM logger
  --no-dashboard   Do not start dashboard
  --foreground     Run processes in foreground (for debugging)

Examples:
  $0 --start            # start dashboard, IMU, and STM in background
  $0 --stop             # stop the started services
  $0 --status           # show status
EOF
}

foreground=false
action="start"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help) usage; exit 0;;
    --start) action="start"; shift;;
    --stop) action="stop"; shift;;
    --status) action="status"; shift;;
    --no-imu) start_imu=false; shift;;
    --no-stm) start_stm=false; shift;;
    --no-dashboard) start_dashboard=false; shift;;
    --foreground) foreground=true; shift;;
    *) echo "Unknown option: $1"; usage; exit 1;;
  esac
done

pidfile() { echo "$LOG_DIR/$1.pid"; }
outfile() { echo "$LOG_DIR/$1.out"; }

start_service() {
  local name="$1"; shift
  local cmd=("$@")
  local pidf
  pidf=$(pidfile "$name")
  if [[ -f "$pidf" ]]; then
    local pid; pid=$(cat "$pidf" 2>/dev/null || true)
    if [[ -n "$pid" && -d "/proc/$pid" ]]; then
      echo "$name already running (pid $pid)"
      return
    else
      rm -f "$pidf" || true
    fi
  fi

  if $foreground; then
    echo "Starting $name in foreground: ${cmd[*]}"
    exec "${cmd[@]}"
  else
    echo "Starting $name: ${cmd[*]}"
    nohup "${cmd[@]}" > "$(outfile "$name")" 2>&1 &
    echo $! > "$pidf"
    echo "$name started (pid $(cat "$pidf"))"
  fi
}

stop_service() {
  local name="$1"
  local pidf
  pidf=$(pidfile "$name")
  if [[ ! -f "$pidf" ]]; then
    echo "$name not running (no pidfile)"
    return
  fi
  local pid; pid=$(cat "$pidf" 2>/dev/null || true)
  if [[ -n "$pid" ]]; then
    echo "Stopping $name (pid $pid)"
    kill "$pid" 2>/dev/null || true
    sleep 1
    if [[ -d "/proc/$pid" ]]; then
      echo "$name did not exit; killing..."
      kill -9 "$pid" 2>/dev/null || true
    fi
  fi
  rm -f "$pidf" || true
}

status_service() {
  local name="$1"
  local pidf
  pidf=$(pidfile "$name")
  if [[ -f "$pidf" ]]; then
    local pid; pid=$(cat "$pidf" 2>/dev/null || true)
    if [[ -n "$pid" && -d "/proc/$pid" ]]; then
      echo "$name running (pid $pid)"
      return
    fi
  fi
  echo "$name stopped"
}

case "$action" in
  start)
    if $start_dashboard; then
      start_service dashboard python3 "$DIR/dashboard/server.py"
    fi
    if $start_imu; then
      start_service imu bash -lc "cd '$DIR/imu' && python3 hwt605_sqlite_logger.py --auto-port --baud 115200 --db-path '$DB_PATH' --sensor-name imu --source-id hwt605_01 --quiet"
    fi
    if $start_stm; then
      start_service stm python3 "$DIR/stm_serial_sqlite_logger.py" --db-path "$DB_PATH" --sensor-name stm --source-id stm_01 --quiet
    fi
    ;;
  stop)
    stop_service dashboard || true
    stop_service imu || true
    stop_service stm || true
    ;;
  status)
    status_service dashboard
    status_service imu
    status_service stm
    ;;
  *) echo "Unknown action: $action"; exit 1;;
esac

exit 0
