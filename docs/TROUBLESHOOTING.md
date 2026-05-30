# Troubleshooting

## Serial port issues

### "device reports readiness to read but returned no data (… multiple access on port?)"

Two processes are opening the same serial device. Usually a stale logger is
still holding the port. Fix:

```bash
./launch_all.sh --stop        # sweeps orphaned loggers by process name
# or find it manually:
ps -eo pid,cmd | grep -E 'hwt605|stm_serial|arduino_serial' | grep -v grep
```

`launch_all.sh --start` already kills stale IMU/STM/vehicle loggers before
starting, so re-running it generally clears this. The HWT605 auto-port probe
also tolerates a transient read error now and simply retries the port instead of
crashing.

### No `/dev/ttyUSB*` or `/dev/ttyACM*` node

- Confirm the device enumerates: `lsusb` and `dmesg | tail`.
- A CH340/CH341 adapter needs the `ch341` kernel module; if it's missing the
  USB device shows in `lsusb` but no tty appears.
- `brltty` sometimes grabs USB-serial adapters. The loggers run
  `pkill -9 brltty` on start; you can also remove the `brltty` package.
- On the Jetson, `imu/imu_watchdog.sh` can unbind/rebind the USB device to
  recover a wedged port (it uses `sudo`).

### Wrong port chosen automatically

Pass an explicit port:

```bash
python3 imu/hwt605_sqlite_logger.py --port /dev/ttyUSB0 --baud 115200
python3 stm_serial_sqlite_logger.py --port /dev/ttyACM0
```

Auto-detection order is `/dev/ttyACM*`, `/dev/ttyUSB*`, then Jetson UARTs
(`/dev/ttyTHS*`, `/dev/ttyS*`).

## Empty or flat charts

- **No data in range.** The `/dbw` page defaults to the last 5 minutes — widen
  the start/end pickers, or confirm rows exist:
  ```bash
  sqlite3 sensor_data.db "SELECT COUNT(*), MAX(recorded_at) FROM sensor_brake;"
  ```
- **Sensor not running.** Check `./launch_all.sh --status` and the matching
  `logs/<name>.out`.
- **Brake panel empty.** Brake data only exists when the Arduino/vehicle
  pipeline is running (`--arduino` or `--vehicle-sim`). The individual
  speed/steering simulators don't produce brake.
- **Field has no numeric values.** Only numeric payload fields are plottable;
  text fields (e.g. STM `raw`) won't appear as series.

## Dashboard won't load

- **Port in use.** Something else is on 5050:
  ```bash
  fuser -k 5050/tcp        # free the port
  ```
- **`ModuleNotFoundError: project_paths`.** Run from the repo root, or use
  `launch_all.sh`. `server.py` adds the repo root to `sys.path`, but a stray
  working directory can still confuse imports.
- **Dependencies missing.** `python3 -m pip install -r requirements.txt`.

## Duplicate speed/steering rows

Running the individual `speed`/`steering` simulators **and** the combined
`vehicle_controls` pipeline at the same time writes those channels twice. Use
one or the other:

- `launch_all.sh` uses the combined pipeline (correct by default).
- With `launch_vehicle_sensors.sh`, `--vehicle`/`--vehicle-sim` automatically
  disable the individual simulators.

## Database growth

`sensor_data.db` grows continuously (the IMU alone is high-rate). To archive and
start fresh while services are stopped:

```bash
./launch_all.sh --stop
mv sensor_data.db sensor_data.$(date +%Y%m%d).db
./launch_all.sh --start        # a new DB is created automatically
```

WAL files (`sensor_data.db-wal`, `-shm`) are normal; they're checkpointed into
the main file by SQLite.
