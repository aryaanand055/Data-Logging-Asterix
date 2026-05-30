#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$DIR/logs"
DB_PATH="$DIR/sensor_data.db"
mkdir -p "$LOG_DIR"

start_speed=true
start_steering=true
start_vehicle=false
vehicle_simulate=false

usage(){
  cat <<EOF
Usage: $0 [options]

Options:
  --help             Show this help
  --start            Start selected services (default)
  --stop             Stop selected services
  --status           Show service status
  --no-speed         Do not start hall-effect speed pipeline
  --no-steering      Do not start steering pipeline
  --vehicle          Stream combined speed/steering/brake from an Arduino
                     (vehicle_controls/arduino_serial_reader.py). Implies
                     --no-speed and --no-steering to avoid duplicate rows.
  --vehicle-sim      Same as --vehicle but feeds from the bundled simulator
                     instead of real hardware (useful for demos/testing).
  --foreground       Run processes in foreground (for debugging)

Examples:
  $0 --start                 # speed + steering simulators
  $0 --start --vehicle       # real Arduino: speed + steering + brake
  $0 --start --vehicle-sim   # simulated speed + steering + brake
  $0 --stop
  $0 --status
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
    --no-speed) start_speed=false; shift;;
    --no-steering) start_steering=false; shift;;
    --vehicle) start_vehicle=true; start_speed=false; start_steering=false; shift;;
    --vehicle-sim) start_vehicle=true; vehicle_simulate=true; start_speed=false; start_steering=false; shift;;
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
    if $start_speed; then
      start_service hall_effect_speed bash -lc "cd '$DIR/hall_effect_speed' && python3 speed_simulator.py --source-id hall_effect_speed_01 | python3 speed_db_uploader.py --db-path '$DB_PATH' --sensor-name hall_effect_speed --source-id hall_effect_speed_01 --quiet"
    fi
    if $start_steering; then
      start_service hall_effect_steering bash -lc "cd '$DIR/hall_effect_steering' && python3 steering_simulator.py --source-id steering_pot_01 | python3 steering_db_uploader.py --db-path '$DB_PATH' --sensor-name hall_effect_steering --source-id steering_pot_01 --quiet"
    fi
    if $start_vehicle; then
      if $vehicle_simulate; then
        source_cmd="python3 vehicle_simulator.py --source-id vehicle_controls_01"
      else
        source_cmd="python3 arduino_serial_reader.py --source-id vehicle_controls_01 --quiet"
      fi
      start_service vehicle_controls bash -lc "cd '$DIR/vehicle_controls' && $source_cmd | python3 vehicle_db_uploader.py --db-path '$DB_PATH' --quiet"
    fi
    ;;
  stop)
    stop_service hall_effect_speed || true
    stop_service hall_effect_steering || true
    stop_service vehicle_controls || true
    ;;
  status)
    status_service hall_effect_speed
    status_service hall_effect_steering
    status_service vehicle_controls
    ;;
  *) echo "Unknown action: $action"; exit 1;;
esac

exit 0