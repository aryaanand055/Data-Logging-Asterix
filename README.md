# Asterix — Multi-Sensor Logging & Drive-by-Wire Dashboard

A vehicle telemetry stack for **Team Asterix**. It collects data from several
sensors — IMU, an STM microcontroller, and an Arduino streaming speed, steering,
and brake — into a single shared SQLite database, and serves a live Chart.js
dashboard for visualising it.

Every sensor follows the same shape: a **source** (real hardware reader or a
simulator) emits one JSON sample per line, which is piped into an **uploader**
that writes it to `sensor_data.db`. The Flask **dashboard** reads that database
and plots it.

```
   sources (hardware / simulators)        uploaders            store            UI
 ┌──────────────────────────────┐   ┌────────────────────┐  ┌──────────┐  ┌──────────────┐
 │ HWT605 IMU  (binary serial)  │──▶│ (built-in logger)  │─▶│          │  │  /     multi │
 │ STM        (text serial)     │──▶│ (built-in logger)  │─▶│ sensor_  │─▶│        sensor│
 │ Arduino    (speed/steer/brake)──▶│ vehicle_db_uploader│─▶│ data.db  │─▶│  /dbw  Asterix│
 │ simulators (no hardware)     │──▶│ *_db_uploader.py   │─▶│ (SQLite) │  │        DBW    │
 └──────────────────────────────┘   └────────────────────┘  └──────────┘  └──────────────┘
```

---

## Quick start

Requires **Python 3.10+**.

```bash
cd /home/abaja/Documents/imu_sqlite
python3 -m pip install -r requirements.txt   # Flask + pyserial

# Start everything with one command (dashboard + IMU + STM + speed/steering/brake)
./launch_all.sh

# Open the dashboards
#   http://localhost:5050/        multi-sensor explorer
#   http://localhost:5050/dbw     Asterix drive-by-wire telemetry

./launch_all.sh --status          # what's running
./launch_all.sh --stop            # stop everything it started
```

By default the speed/steering/brake channels are **simulated** so the dashboard
fills with data even without hardware attached. To read them from a real
Arduino instead:

```bash
./launch_all.sh --arduino
```

---

## What's in the box

| Sensor | Source script | Table | Key fields |
| --- | --- | --- | --- |
| IMU (WIT HWT605) | `imu/hwt605_sqlite_logger.py` | `sensor_imu` | `roll_deg`, `pitch_deg`, `yaw_deg`, `ax_g`, `ay_g`, `az_g`, `gx_dps`…, `temperature_c` |
| STM board | `stm_serial_sqlite_logger.py` | `sensor_stm` | flexible (`raw`, parsed `data`) |
| Wheel speed | `hall_effect_speed/` + `vehicle_controls/` | `sensor_hall_effect_speed` | `speed_kph` |
| Steering | `hall_effect_steering/` + `vehicle_controls/` | `sensor_hall_effect_steering` | `angle_deg` |
| Brake pot | `vehicle_controls/` | `sensor_brake` | `brake_pct`, `position_pct`, `voltage_v` |

The **Arduino** path (`vehicle_controls/`) streams speed, steering, and brake
from one device and fans them into the three tables above. See
[vehicle_controls/README.md](vehicle_controls/README.md).

---

## Documentation

| Guide | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System design, data flow, the shared database schema, table/field reference. |
| [docs/RUNNING.md](docs/RUNNING.md) | Every launch command and flag, the individual pipelines, and how to run pieces by hand. |
| [docs/DASHBOARD.md](docs/DASHBOARD.md) | The two dashboards, the KPI/graph catalogue, and the full HTTP API reference. |
| [docs/SENSOR_GUIDE.md](docs/SENSOR_GUIDE.md) | Step-by-step: add a brand-new sensor to the stack. |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Serial-port contention, empty charts, dashboard issues, and recovery steps. |
| [vehicle_controls/README.md](vehicle_controls/README.md) | The host-side Arduino speed/steering/brake reader, uploader, and simulator. |
| [arduino/README.md](arduino/README.md) | The Arduino firmware: wiring, calibration, output format, and flashing. |

---

## Repository layout

```
imu_sqlite/
├── launch_all.sh              # one command to start/stop/status everything
├── launch_vehicle_sensors.sh  # speed/steering/brake pipelines only
├── project_paths.py           # SHARED_DB_PATH = <repo>/sensor_data.db
├── sensor_sqlite_logger.py    # re-exports imu.sensor_sqlite_logger
├── stm_serial_sqlite_logger.py
├── sensor_data.db             # the shared SQLite store (git-ignored content)
├── requirements.txt           # Flask, pyserial
│
├── dashboard/
│   ├── server.py              # Flask app + JSON API (port 5050)
│   └── templates/
│       ├── dashboard.html     # "/"    multi-sensor explorer
│       └── dbw_dashboard.html # "/dbw" Asterix drive-by-wire dashboard
│
├── imu/
│   ├── sensor_sqlite_logger.py  # SensorSQLiteLogger (the real implementation)
│   ├── hwt605_sqlite_logger.py  # HWT605 binary-serial → SQLite
│   ├── hwt605_logger.py, hwt605_ui.py
│   └── imu_watchdog.sh          # re-binds the USB tty and respawns the logger
│
├── hall_effect_speed/         # speed_simulator.py + speed_db_uploader.py
├── hall_effect_steering/      # steering_simulator.py + steering_db_uploader.py
├── vehicle_controls/          # host: arduino_serial_reader.py, vehicle_db_uploader.py, vehicle_simulator.py
├── arduino/                   # device: vehicle_telemetry.ino firmware
│
├── radar/  actuator/  brake/  throttle/   # scaffolds / notes
└── docs/                      # this documentation set
```

---

## Conventions

- **One table per sensor**, named `sensor_<sanitized_name>`.
- Every reading stores `recorded_at` (ISO-8601 UTC), an optional `source_id`,
  and a JSON `payload_json` blob — so sensors can add fields freely without
  schema migrations.
- The dashboard auto-discovers tables and plots any **numeric** payload field.
- All timestamps are **UTC**; the dashboard converts to local time for display.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full schema and rationale.
