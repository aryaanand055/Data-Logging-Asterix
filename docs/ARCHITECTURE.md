# Architecture

## Overview

The system is a collection of small, independent processes that all share one
SQLite database. There is no central broker — each sensor pipeline writes
directly to `sensor_data.db`, and the dashboard reads from it. This keeps every
piece runnable and testable on its own.

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │                              SOURCES                                      │
 │                                                                           │
 │  HWT605 IMU ──┐   STM board ──┐   Arduino ──┐    simulators ──┐           │
 │  (binary       │   (text        │   (speed/    │  (speed/steer/ │          │
 │   WIT frames)  │    serial)     │   steer/     │   brake/...)   │          │
 │                │                │   brake)     │                │          │
 └────────┬───────┴───────┬────────┴──────┬───────┴───────┬────────┘          │
          │ stdin/serial   │ serial         │ JSON lines    │ JSON lines       │
          ▼                ▼                ▼               ▼                  │
 ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────────────┐      │
 │ hwt605_      │  │ stm_serial_  │  │ *_db_uploader.py /              │      │
 │ sqlite_      │  │ sqlite_      │  │ vehicle_db_uploader.py          │      │
 │ logger.py    │  │ logger.py    │  │ (stdin JSON → rows)             │      │
 └──────┬───────┘  └──────┬───────┘  └───────────────┬─────────────────┘      │
        │                 │                          │                        │
        └─────────────────┴───────────┬──────────────┘                        │
                                       ▼                                       │
                          ┌─────────────────────────┐                         │
                          │   SensorSQLiteLogger     │  one table per sensor   │
                          │   (imu/sensor_sqlite_    │  WAL journal mode       │
                          │    logger.py)            │  thread-locked writes   │
                          └────────────┬─────────────┘                         │
                                       ▼                                       │
                          ┌─────────────────────────┐                         │
                          │     sensor_data.db       │                         │
                          └────────────┬─────────────┘                         │
                                       ▼                                       │
                          ┌─────────────────────────┐                         │
                          │  dashboard/server.py     │  Flask, port 5050       │
                          │  ── / and /dbw + JSON API│                         │
                          └─────────────────────────┘                         │
 └─────────────────────────────────────────────────────────────────────────┘
```

## Why this shape

- **Decoupled processes.** A crash in one logger never takes down the others or
  the dashboard. Each can be started, stopped, and debugged independently.
- **Pipe-friendly sources.** Most sources just print JSON to stdout, so a real
  reader and a simulator are interchangeable — `reader | uploader` or
  `simulator | uploader`. This is what makes the whole stack demoable with no
  hardware.
- **Schema-less payloads.** Every reading is a JSON blob, so a sensor can add or
  change fields without a database migration. The dashboard adapts by
  discovering numeric fields at read time.

## The shared logger

`imu/sensor_sqlite_logger.py` defines `SensorSQLiteLogger`, the single helper
every pipeline uses to write. (`sensor_sqlite_logger.py` at the repo root just
re-exports it so scripts can `from sensor_sqlite_logger import SensorSQLiteLogger`.)

Key behaviours:

- **WAL journal mode** is enabled on open, so the dashboard can read while
  loggers write.
- Writes are **serialized with a thread lock** within a process.
- **Table names are sanitized**: `sensor_name` is lower-cased, non-alphanumerics
  become `_`, and the result is prefixed with `sensor_`. So `hall_effect_speed`
  → `sensor_hall_effect_speed`.
- Tables and their `recorded_at` index are **created on demand** the first time
  a sensor is logged.

Primary API:

```python
logger = SensorSQLiteLogger(db_path)          # defaults to sensor_data.db
logger.log_reading(sensor_name, data, source_id=None, timestamp=None)
logger.log_many(sensor_name, readings, source_id=None)
logger.fetch_recent(sensor_name, limit=10)
```

`project_paths.SHARED_DB_PATH` resolves to `<repo>/sensor_data.db` and is the
default DB path for every script.

## Database schema

Every sensor table has the same four columns:

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER PK AUTOINCREMENT | insertion order |
| `recorded_at` | TEXT NOT NULL | ISO-8601 UTC, e.g. `2026-05-30T07:00:00.123456+00:00` |
| `source_id` | TEXT | device identifier, may be NULL |
| `payload_json` | TEXT NOT NULL | compact JSON of the reading |

Plus an index `idx_sensor_<name>_recorded_at` on `recorded_at` for range queries.

### Tables and payload fields

| Table | source_id | Payload fields |
| --- | --- | --- |
| `sensor_imu` | `hwt605_01` | `roll_deg`, `pitch_deg`, `yaw_deg`, `ax_g`, `ay_g`, `az_g`, `gx_dps`, `gy_dps`, `gz_dps`, `temperature_c` |
| `sensor_hall_effect_speed` | `hall_effect_speed_01` | `sequence`, `recorded_at`, `speed_kph`, `ingested_at` |
| `sensor_hall_effect_steering` | `steering_pot_01` | `sequence`, `recorded_at`, `angle_deg`, `ingested_at` |
| `sensor_brake` | `brake_pot_01` | `sequence`, `recorded_at`, `brake_pct`, `position_pct`, `voltage_v`, `ingested_at` |
| `sensor_stm` | `stm_01` | `raw`, `format` (`json`/`csv`/`key_value`/`text`), optional parsed `data`, `received_at` |
| `sensor_gps`, `sensor_temperature`, `sensor_test_launcher` | various | legacy demo/seed rows |
| `sensor_throttle` | — | **deprecated** — superseded by the per-channel tables |

> Note the distinction between `recorded_at` **inside the payload** (when the
> source produced the sample) and the **column** `recorded_at` (the timestamp
> the uploader stamped at write time). The dashboard plots against the column.

## Field selection in the dashboard

`dashboard/server.py` holds a `PREFERRED_FIELDS` map that picks the "primary"
field to plot per sensor when the client doesn't specify one:

```python
'imu':                  ['roll_deg', 'yaw_deg', 'pitch_deg', 'temperature_c']
'hall_effect_speed':    ['speed_kph', 'speed_mps', 'velocity_kph']
'hall_effect_steering': ['angle_deg', 'steering_angle_deg', 'position_deg']
'brake':                ['brake_pct', 'position_pct', 'pressure_bar', 'force_n', 'voltage_v']
'radar':                ['distance_m', 'range_m', 'speed_mps', 'velocity_mps']
'actuator':             ['position_mm', 'position_pct', 'current_a']
```

If none of the preferred fields are present, the first numeric field found is
used.

## Derived series

The `/dbw` dashboard computes several series that aren't stored directly:

- **Distance** — trapezoidal integration of speed over time (km/h is converted
  to m/s first). Computed server-side in `derive_distance_points`, with an
  identical client-side fallback.
- **Acceleration / lateral / heading** — pulled straight from the IMU fields
  `ax_g`, `ay_g`, and `yaw_deg`.

See [docs/DASHBOARD.md](DASHBOARD.md) for the full list and the API that serves
them.
