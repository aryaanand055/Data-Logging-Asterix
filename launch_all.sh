#!/usr/bin/env bash
set -euo pipefail

# Simple launcher for the multi-sensor system.
# Usage: ./launch_all.sh [--help] [--start] [--stop] [--status] [--no-dashboard]

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$DIR/logs"
DB_PATH="$DIR/sensor_data.db"
mkdir -p "$LOG_DIR"

start_dashboard=true
start_imu=true
start_stm=true
start_vehicle=true
use_arduino=false

usage(){
  cat <<EOF
Usage: $0 [options]

One command to start every sensor and the dashboard. By default the vehicle
controls (speed + steering + brake) are simulated; pass --arduino to read them
from a real Arduino over serial instead.

Options:
  --help           Show this help
  --start          Start selected services (default)
  --stop           Stop selected services
  --status         Show service status
  --no-dashboard   Do not start the dashboard
  --no-imu         Do not start the IMU logger
  --no-stm         Do not start the STM serial logger
  --no-vehicle     Do not start the speed/steering/brake pipeline
  --arduino        Read speed/steering/brake from a real Arduino (default: simulated)
  --foreground     Run processes in foreground (for debugging)

Examples:
  $0 --start            # dashboard + IMU + STM + simulated speed/steering/brake
  $0 --start --arduino  # same, but vehicle controls come from a real Arduino
  $0 --stop             # stop everything it started
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
    --no-dashboard) start_dashboard=false; shift;;
    --no-imu) start_imu=false; shift;;
    --no-stm) start_stm=false; shift;;
    --no-vehicle) start_vehicle=false; shift;;
    --arduino) use_arduino=true; shift;;
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

kill_orphan_processes() {
  local pattern="$1"
  local label="$2"
  local pids
  pids=$(pgrep -f "$pattern" || true)
  if [[ -z "$pids" ]]; then
    return
  fi

  while read -r pid; do
    [[ -z "$pid" ]] && continue
    if [[ "$pid" == "$$" ]]; then
      continue
    fi
    if [[ -d "/proc/$pid" ]]; then
      echo "Killing stale $label process (pid $pid)"
      kill "$pid" 2>/dev/null || true
    fi
  done <<< "$pids"

  sleep 1
  while read -r pid; do
    [[ -z "$pid" ]] && continue
    if [[ "$pid" == "$$" ]]; then
      continue
    fi
    if [[ -d "/proc/$pid" ]]; then
      echo "Force killing stale $label process (pid $pid)"
      kill -9 "$pid" 2>/dev/null || true
    fi
  done <<< "$(pgrep -f "$pattern" || true)"
}

stop_all_services() {
  stop_service dashboard || true
  stop_service imu || true
  stop_service stm || true
  stop_service vehicle_controls || true
  # Legacy services (kept so older pipelines are also cleaned up).
  stop_service hall_effect_speed || true
  stop_service hall_effect_steering || true

  kill_orphan_processes 'dashboard/server.py' 'dashboard'
  kill_orphan_processes 'hwt605_sqlite_logger.py' 'imu'
  kill_orphan_processes 'stm_serial_sqlite_logger.py' 'stm'
  kill_orphan_processes 'vehicle_db_uploader.py' 'vehicle controls uploader'
  kill_orphan_processes 'arduino_serial_reader.py' 'vehicle controls arduino reader'
  kill_orphan_processes 'vehicle_simulator.py' 'vehicle controls simulator'
  kill_orphan_processes 'speed_db_uploader.py --db-path' 'hall-effect speed'
  kill_orphan_processes 'speed_simulator.py --source-id' 'hall-effect speed simulator'
  kill_orphan_processes 'steering_db_uploader.py --db-path' 'hall-effect steering'
  kill_orphan_processes 'steering_simulator.py --source-id' 'hall-effect steering simulator'
}

start_all_services() {
  if $start_dashboard; then
    start_service dashboard python3 "$DIR/dashboard/server.py"
  fi
  if $start_imu; then
    start_service imu bash -lc "cd '$DIR/imu' && python3 hwt605_sqlite_logger.py --auto-port --baud 115200 --db-path '$DB_PATH' --sensor-name imu --source-id hwt605_01 --quiet"
  fi
  if $start_stm; then
    start_service stm python3 "$DIR/stm_serial_sqlite_logger.py" --db-path "$DB_PATH" --sensor-name stm --source-id stm_01 --quiet
  fi
  if $start_vehicle; then
    if $use_arduino; then
      vehicle_source="python3 arduino_serial_reader.py --source-id vehicle_controls_01 --quiet"
    else
      vehicle_source="python3 vehicle_simulator.py --source-id vehicle_controls_01"
    fi
    start_service vehicle_controls bash -lc "cd '$DIR/vehicle_controls' && $vehicle_source | python3 vehicle_db_uploader.py --db-path '$DB_PATH' --quiet"
  fi
}

case "$action" in
  start)
    stop_all_services
    start_all_services
    ;;
  stop)
    stop_all_services
    ;;
  status)
    status_service dashboard
    status_service imu
    status_service stm
    status_service vehicle_controls
    ;;
  *) echo "Unknown action: $action"; exit 1;;
esac

exit 0
