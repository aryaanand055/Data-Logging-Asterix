# Multi-sensor logging and dashboard

This repository collects sensor data from multiple sources (IMU, STM serial, radar, hall-effect steering, actuator, brake, throttle) into one shared SQLite database and exposes a Python-served dashboard for visualization.

This documentation covers the repository layout, quick start, how to add new sensors, the shared database schema, and troubleshooting notes.

## Quick start

Prerequisites: Python 3.10+, install dependencies:

```bash
cd /home/abaja/Documents/imu_sqlite
python3 -m pip install -r requirements.txt
```

Start everything (dashboard + IMU + STM logger):

```bash
cd /home/abaja/Documents/imu_sqlite
./launch_all.sh --start
```

Check status:

```bash
./launch_all.sh --status
```

Stop services:

```bash
./launch_all.sh --stop
```

Or run only the dashboard for local browsing:

```bash
cd /home/abaja/Documents/imu_sqlite
python3 dashboard/server.py
# then open http://<host>:5050
```

## Repository layout

- `sensor_data.db` — the shared SQLite database at the repository root.
- `launch_all.sh` — helper to start/stop/dashboard and sensor loggers.
- `dashboard/` — Flask app and templates for the multi-sensor dashboard.
- `imu/` — IMU logger, UI, and watchdog.
- `stm_serial_sqlite_logger.py` — STM serial logger (root-level helper).
- `radar/`, `hall_effect_steering/`, `actuator/`, `brake/`, `throttle/` — sensor scaffolds.

## Shared database and schema

All sensors write to a single SQLite database file at the repository root. The `SensorSQLiteLogger` helper (see `imu/sensor_sqlite_logger.py`) provides a consistent API. Key points:

- One table per sensor: `sensor_<sanitized_name>` (e.g. `sensor_imu`, `sensor_radar`).
- Table columns:
  - `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - `recorded_at TEXT NOT NULL` (ISO 8601 UTC)
  - `source_id TEXT` (optional device identifier)
  - `payload_json TEXT NOT NULL` (JSON-encoded payload)

Use `SensorSQLiteLogger.log_reading(sensor_name, data, source_id, timestamp)` to insert a reading. The dashboard reads these tables and extracts numeric fields for plotting.

## Adding a new sensor

1. Create a folder under the repository root (e.g. `radar/`).
2. Add a Python entrypoint (e.g. `radar/logger.py`) that:
   - Instantiates `SensorSQLiteLogger` pointing at the shared DB (defaults to `sensor_data.db`).
   - Normalizes the incoming payload into a simple dict of fields and calls `log_reading()`.
3. Make the logger accept command-line options `--db-path`, `--sensor-name`, `--source-id`, and transport-specific options.
4. Add a README in the folder describing the transport/protocol and any wiring.
5. Optionally add the logger to `launch_all.sh`.

A minimal logger example is provided in `docs/SENSOR_GUIDE.md`.

## Dashboard

The dashboard is a Flask app at `dashboard/server.py` serving a Chart.js-based UI (`dashboard/templates/dashboard.html`). It exposes two APIs:

- `GET /api/sensors` — lists available sensor tables and numeric fields.
- `GET /api/series/<sensor_name>?field=...&limit=...` — returns recent numeric series for a sensor field.

The dashboard pulls numeric fields from each sensor's `payload_json` and allows toggling multiple series onto a single graph.

## Troubleshooting

- If you see the CH340 USB device in `lsusb` but no `/dev/ttyUSB*` node, the host kernel may lack the `ch341` driver. The IMU runbook (`imu/README.md`) includes recovery steps for the Jetson image used here.
- The IMU watchdog previously hardcoded `/dev/ttyUSB0`; some machines require `--auto-port` or `--port` with the correct device path.

## Next steps

- Implement the radar logger (CAN) and the other sensors' loggers according to their transports.
- Add unit tests and CI to validate DB writes and dashboard APIs.
