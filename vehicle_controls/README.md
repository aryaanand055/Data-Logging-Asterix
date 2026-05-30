# Vehicle controls (Arduino: speed + steering + brake)

Reads combined drive-by-wire telemetry from an Arduino over the serial monitor
and logs it into the shared SQLite database.

## Pipeline

```
Arduino (USB serial)
        │  speed / steering / brake-pot
        ▼
arduino_serial_reader.py   ──►   vehicle_db_uploader.py   ──►   sensor_data.db
   (reads serial,                  (fans one sample out
    emits unified JSON)             into three tables)
```

The reader and uploader are deliberately separate so the reader's stdout can be
piped into the uploader (or inspected / redirected on its own):

```bash
cd vehicle_controls
python3 arduino_serial_reader.py | python3 vehicle_db_uploader.py
```

No hardware? Swap the reader for the bundled simulator (identical output):

```bash
python3 vehicle_simulator.py | python3 vehicle_db_uploader.py
```

Or use the launcher from the repo root:

```bash
./launch_vehicle_sensors.sh --start --vehicle        # real Arduino
./launch_vehicle_sensors.sh --start --vehicle-sim    # simulated
./launch_vehicle_sensors.sh --status
./launch_vehicle_sensors.sh --stop
```

## Files

| File | Role |
| --- | --- |
| `arduino_serial_reader.py` | Reads the Arduino serial port, normalises each line, prints one JSON object per sample to stdout. |
| `vehicle_db_uploader.py` | Reads those JSON lines from stdin and writes them to SQLite. |
| `vehicle_simulator.py` | Emits the same JSON as the reader, for testing without hardware. |

## Expected Arduino serial format

Each sample should be printed on its own line. The reader accepts whichever of
these the firmware emits (matched in this order):

1. **JSON** — `{"speed_kph": 12.3, "steering_deg": -4.1, "brake_pct": 20}`
2. **key=value** — `speed=12.3 steering=-4.1 brake=20 voltage=2.75`
3. **CSV** — `12.3,-4.1,20` (column order set by `--csv-order`,
   default `speed_kph,steering_angle_deg,brake_pct`)

Field names are matched case-insensitively against common aliases
(`speed`/`speed_kph`/`velocity_kph`, `steering`/`angle_deg`/`steering_deg`,
`brake`/`brake_pct`/`pedal_pct`, plus an optional brake `voltage`).

Ready-to-flash firmware lives in [`../arduino/`](../arduino/README.md)
(`vehicle_telemetry.ino`). A minimal example of what it prints (`Serial.println`
at 115200 baud):

```cpp
void loop() {
  float speed_kph = readWheelSpeed();
  float steering  = readSteeringAngle();
  float brake_pct = map(analogRead(A0), 0, 1023, 0, 100);
  Serial.print("speed="); Serial.print(speed_kph);
  Serial.print(" steering="); Serial.print(steering);
  Serial.print(" brake="); Serial.println(brake_pct);
  delay(50);
}
```

## Where the data lands

A single combined sample is fanned out into the three canonical sensor tables
that the dashboard already plots:

| Channel | Table | Field(s) |
| --- | --- | --- |
| Speed | `sensor_hall_effect_speed` | `speed_kph` |
| Steering | `sensor_hall_effect_steering` | `angle_deg` |
| Brake | `sensor_brake` | `brake_pct`, `position_pct`, `voltage_v` |

Open the dashboard at `http://localhost:5050/dbw` to see them live.

## Options

`arduino_serial_reader.py`

```
--port PORT          Serial port (auto-detected from /dev/ttyACM*, /dev/ttyUSB* if omitted)
--baud BAUD          Baud rate (default 115200)
--source-id ID       Source ID stamped on each sample (default vehicle_controls_01)
--csv-order COLS     Column order for bare CSV (default speed_kph,steering_angle_deg,brake_pct)
--quiet              Silence stderr status messages
```

`vehicle_db_uploader.py`

```
--db-path PATH               SQLite file (default: shared sensor_data.db)
--speed-source-id ID         Source ID for speed rows   (default hall_effect_speed_01)
--steering-source-id ID      Source ID for steering rows (default steering_pot_01)
--brake-source-id ID         Source ID for brake rows    (default brake_pot_01)
--quiet                      Silence stderr status messages
```
