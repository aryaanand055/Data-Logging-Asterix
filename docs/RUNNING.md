# Running the stack

Everything is launched through two shell scripts, or by running individual
Python pipelines by hand. All services log to `logs/<name>.out` and track their
PID in `logs/<name>.pid`.

## `launch_all.sh` — one command for everything

Starts the dashboard, the IMU logger, the STM logger, and the combined
speed/steering/brake pipeline.

```bash
./launch_all.sh                # --start is the default action
./launch_all.sh --start
./launch_all.sh --status
./launch_all.sh --stop
```

### Options

| Flag | Effect |
| --- | --- |
| `--start` | Start selected services (default). Stops stale instances first. |
| `--stop` | Stop everything it started, plus any orphaned loggers. |
| `--status` | Print the running/stopped state of each service. |
| `--arduino` | Read speed/steering/brake from a real Arduino instead of the simulator. |
| `--no-dashboard` | Don't start the Flask dashboard. |
| `--no-imu` | Don't start the IMU logger. |
| `--no-stm` | Don't start the STM logger. |
| `--no-vehicle` | Don't start the speed/steering/brake pipeline. |
| `--foreground` | Run in the foreground (single service, for debugging). |

### Services it manages

| Name | Command (simplified) |
| --- | --- |
| `dashboard` | `python3 dashboard/server.py` |
| `imu` | `hwt605_sqlite_logger.py --auto-port --baud 115200 …` |
| `stm` | `stm_serial_sqlite_logger.py …` |
| `vehicle_controls` | `vehicle_simulator.py \| vehicle_db_uploader.py` (or `arduino_serial_reader.py \| …` with `--arduino`) |

Before starting, `--start` kills stale instances by PID file **and** sweeps for
orphaned processes (e.g. an IMU logger left holding the serial port), so
re-running the command is always safe.

## `launch_vehicle_sensors.sh` — vehicle channels only

Useful when the dashboard/IMU/STM are managed elsewhere and you only want the
drive-by-wire channels.

```bash
./launch_vehicle_sensors.sh --start                 # speed + steering simulators
./launch_vehicle_sensors.sh --start --vehicle       # real Arduino: speed + steering + brake
./launch_vehicle_sensors.sh --start --vehicle-sim   # simulated speed + steering + brake
./launch_vehicle_sensors.sh --status
./launch_vehicle_sensors.sh --stop
```

| Flag | Effect |
| --- | --- |
| `--no-speed` / `--no-steering` | Skip the individual simulator pipelines. |
| `--vehicle` | Run the combined Arduino pipeline (implies `--no-speed --no-steering`). |
| `--vehicle-sim` | Same, but feed from the bundled simulator. |
| `--foreground` | Run in the foreground. |

> Run **either** the individual speed/steering simulators **or** the combined
> vehicle pipeline — not both — or speed/steering rows are written twice.

## Running pieces by hand

The dashboard alone:

```bash
python3 dashboard/server.py          # serves http://0.0.0.0:5050
```

The vehicle pipeline (no hardware):

```bash
cd vehicle_controls
python3 vehicle_simulator.py | python3 vehicle_db_uploader.py
```

The vehicle pipeline (real Arduino):

```bash
cd vehicle_controls
python3 arduino_serial_reader.py | python3 vehicle_db_uploader.py
```

A single channel simulator:

```bash
cd hall_effect_speed
python3 speed_simulator.py | python3 speed_db_uploader.py --sensor-name hall_effect_speed
```

The IMU logger directly:

```bash
cd imu
python3 hwt605_sqlite_logger.py --auto-port --baud 115200    # auto-detect the port
python3 hwt605_sqlite_logger.py --port /dev/ttyUSB0          # explicit port
```

The STM logger:

```bash
python3 stm_serial_sqlite_logger.py --port /dev/ttyACM0 --baud 115200
```

## Common arguments

Most loggers/uploaders accept:

| Flag | Meaning |
| --- | --- |
| `--db-path PATH` | SQLite file (defaults to the shared `sensor_data.db`). |
| `--sensor-name NAME` | Logical sensor name → `sensor_<name>` table. |
| `--source-id ID` | Device identifier stored with each row. |
| `--quiet` | Silence per-sample status messages. |

Serial readers additionally accept `--port` and `--baud`; the IMU logger accepts
`--auto-port` to probe for a port that emits valid HWT605 frames.

## Ports & hosts

- Dashboard listens on **`0.0.0.0:5050`** (reachable as `http://localhost:5050`
  locally, or `http://<host-ip>:5050` on the network).
- Serial devices are auto-detected from `/dev/ttyACM*`, `/dev/ttyUSB*`, then a
  few Jetson UART fallbacks (`/dev/ttyTHS*`, `/dev/ttyS*`).
