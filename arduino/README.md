# Arduino firmware

Sample firmware for the Arduino that streams **speed, steering, and brake** to
the host, where `vehicle_controls/arduino_serial_reader.py` reads it and
`vehicle_db_uploader.py` logs it into `sensor_data.db`.

```
arduino/
├── vehicle_telemetry/
│   └── vehicle_telemetry.ino             # REAL sensors (hall + 2 pots)
└── vehicle_telemetry_simulator/
    └── vehicle_telemetry_simulator.ino   # FAKE data, no sensors wired
```

> The Arduino IDE requires a sketch's `.ino` to live in a folder of the **same
> name** — that's why each sketch is in its own subfolder, not directly in
> `arduino/`.

## Which sketch?

| Sketch | Use when |
| --- | --- |
| `vehicle_telemetry/` | You have the real hall-effect speed sensor and two potentiometers wired up. |
| `vehicle_telemetry_simulator/` | You want to test the host pipeline/dashboard with **any** Arduino and **no sensors** — it streams plausible fake data. |

Both print the **identical line format**, so the host side
(`arduino_serial_reader.py`, `./launch_all.sh --arduino`) works the same with
either. The simulator is the firmware equivalent of the host-side
`vehicle_controls/vehicle_simulator.py`.

## What it does

Every 100 ms (10 Hz) it reads the three inputs and prints one line:

```
speed=12.340 steering=-4.100 brake=20.0 voltage=1.000
```

- **speed** — km/h, derived by counting hall-effect pulses per sample window.
- **steering** — degrees, mapped from a potentiometer (default ±45°).
- **brake** — percent pressed, mapped from a potentiometer.
- **voltage** — the raw brake-pot voltage (handy for calibration).

This `key=value` format is both machine-parseable and easy to read in the
Arduino IDE **Serial Monitor** (set it to **115200 baud**).

## Wiring (Arduino Uno / Nano)

| Signal | Pin | Notes |
| --- | --- | --- |
| Hall-effect speed | **D2** | Interrupt pin (INT0). `INPUT_PULLUP`; sensor pulls to GND. |
| Steering pot wiper | **A0** | Pot ends to 5 V and GND. |
| Brake pot wiper | **A1** | Pot ends to 5 V and GND. |
| Power / ground | 5V, GND | Shared with the sensors. |

If you use D3 instead of D2 for the hall sensor, it also supports interrupts
(INT1) — just change `PIN_HALL`.

## Calibration

Edit the constants at the top of `vehicle_telemetry.ino`:

| Constant | Meaning |
| --- | --- |
| `WHEEL_CIRCUMFERENCE_M` | Metres travelled per wheel revolution. |
| `PULSES_PER_REV` | Hall pulses per wheel revolution. |
| `STEER_ADC_MIN/MAX`, `STEER_DEG_MIN/MAX` | Map raw ADC to steering degrees. |
| `BRAKE_ADC_REST/PRESSED` | Raw ADC at released / fully-pressed pedal. |
| `SAMPLE_MS` | Output period in milliseconds. |

To calibrate the pots: open the Serial Monitor, move the input to each extreme,
note the `voltage`/raw behaviour, and set the ADC endpoints accordingly.

## Flashing & connecting

1. Open `arduino/vehicle_telemetry/` in the Arduino IDE.
2. Select your board and port, then **Upload**.
3. Confirm output in the Serial Monitor (115200 baud).
4. Close the Serial Monitor (only one program can own the port), then on the host:

   ```bash
   cd ../vehicle_controls
   python3 arduino_serial_reader.py | python3 vehicle_db_uploader.py
   ```

   …or let the launcher do it:

   ```bash
   ./launch_all.sh --arduino
   ```

The reader auto-detects the Arduino on `/dev/ttyACM*` or `/dev/ttyUSB*`; pass
`--port /dev/ttyACM0` to force one.

## Output format options

`arduino_serial_reader.py` accepts three line formats — pick whichever is
easiest for your firmware. All three carry the same data:

```text
key=value :  speed=12.3 steering=-4.1 brake=20 voltage=1.0     (this sketch)
JSON      :  {"speed_kph":12.3,"steering_deg":-4.1,"brake_pct":20}
CSV       :  12.3,-4.1,20        (column order set by --csv-order)
```

Field names are matched case-insensitively against common aliases (`speed` /
`speed_kph`, `steering` / `angle_deg` / `steering_deg`, `brake` / `brake_pct`,
`voltage`). To emit JSON instead, replace the `Serial.print(...)` block with:

```cpp
Serial.print("{\"speed_kph\":");   Serial.print(speed_kph, 3);
Serial.print(",\"steering_deg\":"); Serial.print(steering_deg, 3);
Serial.print(",\"brake_pct\":");    Serial.print(brake_pct, 1);
Serial.println("}");
```
