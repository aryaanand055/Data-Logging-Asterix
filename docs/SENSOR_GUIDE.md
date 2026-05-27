# Sensor integration guide

This guide shows how to add a new sensor logger that writes to the shared `sensor_data.db` using the existing `SensorSQLiteLogger` helper.

1. Create a new folder: `mkdir radar` and add `radar/logger.py`.

2. Example minimal `logger.py`:

```python
#!/usr/bin/env python3
from datetime import datetime, timezone
from sensor_sqlite_logger import SensorSQLiteLogger

def main():
    db = SensorSQLiteLogger('sensor_data.db')
    # read sensor, convert to dict
    sample = {'distance_m': 12.3, 'speed_mps': 1.2}
    db.log_reading(sensor_name='radar', data=sample, source_id='radar_01', timestamp=datetime.now(timezone.utc))

if __name__ == '__main__':
    main()
```

3. Command-line options: accept `--db-path`, `--sensor-name`, `--source-id`, `--quiet`.

4. Make sure the payload values are simple JSON-serializable types (strings, numbers, booleans, lists, dicts). The dashboard will only plot numeric fields.

5. Add the logger to `launch_all.sh` if you want it started automatically.
