# Dashboard & HTTP API

The Flask app in `dashboard/server.py` serves two web pages and a JSON API on
port **5050**. It reads the shared `sensor_data.db` and never writes to it.

## Pages

### `/` — Multi-sensor explorer (`dashboard.html`)

A general-purpose viewer for **every** sensor table in the database:

- Auto-discovers all `sensor_*` tables.
- One toggle + field selector per sensor; plot any combination on one chart.
- "All data" option overlays every numeric field of a sensor.
- A rolling time window (default 30 s) refreshed once a second.
- Per-sensor online/offline dot (online = a sample within the last 10 s).
- CSV export per sensor.

### `/dbw` — Asterix drive-by-wire dashboard (`dbw_dashboard.html`)

A branded, purpose-built telemetry view for the vehicle. It queries a
**time range** (default: the last 5 minutes; adjustable with the start/end
pickers) and shows:

**Live KPI tiles** — latest value in range for speed, steering, brake, heading,
longitudinal accel, lateral accel, and total distance.

**Graphs:**

| Graph | Source | Field |
| --- | --- | --- |
| Speed vs Time | `sensor_hall_effect_speed` | `speed_kph` |
| Brake Position vs Time | `sensor_brake` | `brake_pct` |
| Steering Angle vs Time | `sensor_hall_effect_steering` | `angle_deg` |
| Longitudinal Acceleration | `sensor_imu` | `ax_g` |
| Lateral Acceleration | `sensor_imu` | `ay_g` |
| Heading (Yaw) vs Time | `sensor_imu` | `yaw_deg` |
| Distance Travelled | derived | ∫ speed dt |

A sensor-health strip and a live "Live/Idle" indicator sit under the header.

## HTTP API

All responses are JSON with a top-level `ok` boolean and carry
`Cache-Control: no-store`.

### `GET /api/sensors?limit=N`

Inventory of every sensor table. `limit` (5–500, default 50) caps the rows
scanned per sensor for field discovery.

```json
{
  "ok": true,
  "db_path": "/…/sensor_data.db",
  "sensors": [
    {
      "sensor_name": "hall_effect_speed",
      "table_name": "sensor_hall_effect_speed",
      "row_count": 50,
      "fields": ["sequence", "speed_kph"],
      "primary_field": "speed_kph",
      "latest": { "timestamp": "…", "source_id": "…", "payload": { … } }
    }
  ]
}
```

### `GET /api/latest/<sensor_name>`

The single most recent reading for one sensor. `404` if the sensor has no data.
`GET /api/latest?sensor=<name>` is an equivalent legacy form; with no `sensor`
it falls back to `imu` (or the first table).

### `GET /api/series/<sensor_name>`

A numeric series for one field, for line charts.

| Param | Meaning |
| --- | --- |
| `field` | Field to plot; defaults to the sensor's primary field. |
| `seconds` | Return rows from the last N seconds (1–86400). |
| `limit` | Or, the most recent N rows (5–2000, default 200). Ignored if `seconds` is set. |

```json
{ "ok": true, "sensor_name": "imu", "field": "yaw_deg",
  "seconds": 30, "points": [ { "timestamp": "…", "value": -89.6 } ] }
```

### `GET /api/all/<sensor_name>`

Bulk export of rows.

| Param | Meaning |
| --- | --- |
| `seconds` | Rows from the last N seconds. |
| `limit` | Most recent N rows (default 1000); `limit=all` returns the whole table. |
| `format` | `json` (default) or `csv` (downloads `<sensor>_data.csv`). |

### `GET /api/dbw?start=<iso>&end=<iso>`

Everything the `/dbw` page needs in one call, for a time range. Defaults to the
last 5 minutes if `start`/`end` are omitted. Returns these series, each as
`{ sensor_name, field, rows, points }`:

`speed`, `acceleration`, `distance`, `speed_distance` (radar scatter, if present),
`steering`, `brake`, `lateral`, `heading` — plus a `range` object echoing the
resolved `start`/`end`.

```json
{
  "ok": true,
  "db_path": "/…/sensor_data.db",
  "range": { "start": "…Z", "end": "…Z", "default_minutes": 5 },
  "speed":    { "sensor_name": "hall_effect_speed", "field": "speed_kph", "rows": 600, "points": [ … ] },
  "brake":    { "sensor_name": "brake", "field": "brake_pct", "rows": 60, "points": [ … ] },
  "heading":  { "sensor_name": "imu", "field": "yaw_deg", "rows": 9000, "points": [ … ] }
}
```

## Notes

- All timestamps are UTC ISO-8601; the UI converts to local time for axis labels.
- The IMU streams fast, so wide time ranges return many points. The default
  5-minute window keeps the page responsive; narrow the range for long sessions.
- The server is started with `debug=False`. For development you can run
  `python3 dashboard/server.py` and edit templates live (refresh the browser).
