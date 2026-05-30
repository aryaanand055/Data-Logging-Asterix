# Adding a new sensor

Every sensor in this project follows the same pattern: a **source** emits one
JSON sample per line on stdout, and an **uploader** reads stdin and writes rows
with `SensorSQLiteLogger`. You can either reuse that pipe pattern or write
directly to the database. This guide shows both.

The dashboard requires **nothing extra** — it auto-discovers any `sensor_*`
table and plots its numeric fields. (To give a sensor a preferred default field
on the charts, add it to `PREFERRED_FIELDS` in `dashboard/server.py`.)

## Option A — direct logger (simplest)

Good for a sensor you read inside one Python process (CAN bus, I²C, a file…).

```python
#!/usr/bin/env python3
import sys
from pathlib import Path
from datetime import datetime, timezone

# make repo-root modules importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from project_paths import SHARED_DB_PATH
from sensor_sqlite_logger import SensorSQLiteLogger

def main():
    db = SensorSQLiteLogger(str(SHARED_DB_PATH))
    while True:
        sample = read_my_sensor()                 # -> {'distance_m': 12.3, 'speed_mps': 1.2}
        db.log_reading(
            sensor_name='radar',                   # → table sensor_radar
            data=sample,
            source_id='radar_01',
            timestamp=datetime.now(timezone.utc),
        )

if __name__ == '__main__':
    main()
```

## Option B — source + uploader pipe (matches the existing sensors)

This is how `hall_effect_speed`, `hall_effect_steering`, and `vehicle_controls`
work. It lets you swap a real reader for a simulator without touching the
uploader.

**`mysensor/mysensor_simulator.py`** — print JSON to stdout:

```python
import json, time
from datetime import datetime, timezone

seq = 0
while True:
    seq += 1
    print(json.dumps({
        'sequence': seq,
        'recorded_at': datetime.now(timezone.utc).isoformat(),
        'distance_m': read_distance(),
    }), flush=True)
    time.sleep(0.2)
```

**`mysensor/mysensor_db_uploader.py`** — read stdin, write rows. Copy
`hall_effect_speed/speed_db_uploader.py` and change the defaults; it already:

- adds the repo root to `sys.path`,
- parses each line as JSON (falling back to `{'raw': text}`),
- stamps `ingested_at` and writes with `SensorSQLiteLogger.log_reading`,
- handles `SIGINT`/`SIGTERM` for clean shutdown.

Run it:

```bash
python3 mysensor_simulator.py | python3 mysensor_db_uploader.py --sensor-name mysensor --source-id mysensor_01
```

## Checklist

1. Pick a `sensor_name` → it becomes `sensor_<name>` (lower-cased, non-alnum → `_`).
2. Keep payload values **JSON-serializable** (numbers/strings/bools/lists/dicts).
   Only **numeric** fields are plottable.
3. Accept the standard CLI flags: `--db-path`, `--sensor-name`, `--source-id`,
   `--quiet` (and `--port`/`--baud` for serial).
4. Add a `README.md` in the sensor folder describing the wiring/protocol.
5. (Optional) add the sensor to `launch_all.sh` so it starts with everything else.
6. (Optional) add a `PREFERRED_FIELDS` entry and, for `/dbw`, a series in
   `build_dbw_dashboard_data()`.

## Conventions worth following

- Emit a per-sample `sequence` counter and an in-payload `recorded_at` — handy
  for debugging dropped samples.
- Express units in the field name (`speed_kph`, `distance_m`, `voltage_v`) so
  the dashboard axis labels and conversions stay unambiguous.
- Use a stable `source_id` per physical device so multiple identical sensors can
  share one table.
