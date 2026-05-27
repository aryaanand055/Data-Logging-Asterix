# IMU Runbook

This folder contains the IMU logger, live UI, and watchdog for the HWT605 sensor.

The IMU now writes to the shared repository-level database at `/home/abaja/Documents/imu_sqlite/sensor_data.db`, which is also the target database for the other sensor folders and the shared dashboard.

Use this runbook when you want to start data collection, view the live display, or recover from a missing `/dev/ttyUSB0` device.

## What Runs What

- `hwt605_sqlite_logger.py` reads the IMU and writes each sample into the shared `sensor_data.db` at the repository root.
- `hwt605_ui.py` reads the latest sample from that database and serves the legacy IMU-only dashboard on port `5050`.
- `dashboard/server.py` serves the new shared multi-sensor dashboard.
- `imu_watchdog.sh` keeps the logger running and retries recovery if the USB serial device disappears.

## Start Data Collection

Run the logger from this directory on the IMU host:

```sh
cd /home/abaja/Documents/imu_sqlite/imu
python3 hwt605_sqlite_logger.py --port /dev/ttyUSB0 --baud 115200 --sensor-name imu --source-id hwt605_01 --quiet
```

If the port name is not stable, use auto-detection instead:

```sh
python3 hwt605_sqlite_logger.py --auto-port --baud 115200 --sensor-name imu --source-id hwt605_01 --quiet
```

What the logger does:

- Reads HWT605 frames from the serial port.
- Converts roll, pitch, yaw, acceleration, gyro, and temperature into samples.
- Stores each sample in SQLite under the shared `sensor_imu` table in the root database.
- Retries every 2 seconds if the port is missing or the device cannot be opened.

## Start the Live UI

In a second terminal on the same machine:

```sh
cd /home/abaja/Documents/imu_sqlite/imu
python3 hwt605_ui.py
```

Open the dashboard in a browser at:

```text
http://<imu-host>:5050/
```

The UI shows the latest IMU sample from SQLite and updates the plotted roll, pitch, and yaw values.

For the shared dashboard, run:

```sh
cd /home/abaja/Documents/imu_sqlite
python3 dashboard/server.py
```

Then open:

```text
http://<imu-host>:5050/
```

Alternatively, use the provided launcher to start dashboard and loggers together from the repository root:

```sh
cd /home/abaja/Documents/imu_sqlite
./launch_all.sh --start
# check status
./launch_all.sh --status
# stop
./launch_all.sh --stop
```

## Optional Watchdog

If you want the logger to be restarted automatically, run the watchdog from this folder:

```sh
cd /home/abaja/Documents/imu_sqlite/imu
./imu_watchdog.sh
```

The watchdog checks for `/dev/ttyUSB0`, starts the logger if it is missing, and repeats the same recovery steps below when needed.

## Local Recovery Steps

Use these steps when the IMU is not detected, `/dev/ttyUSB0` does not appear, or the logger cannot read valid data.

This matches the current recovery behavior in the IMU scripts:

- `pkill -9 brltty` is used to stop `brltty` from grabbing the CH340 adapter.
- `make load` loads the CH34x kernel module on this Jetson image.
- USB unbind/bind forces re-enumeration so `/dev/ttyUSB0` can be recreated.

Run the recovery sequence on the IMU host shell:

```sh
echo abaja | sudo -S pkill -9 brltty >/dev/null 2>&1 || true
cd /home/abaja/ch341-driver && echo abaja | sudo -S make load >/dev/null 2>&1 || true
echo abaja | sudo -S sh -c 'echo 1-2.3 > /sys/bus/usb/drivers/usb/unbind; sleep 1; echo 1-2.3 > /sys/bus/usb/drivers/usb/bind' || true
sleep 2
ls -l /dev/ttyUSB0
```

If your USB path is not `1-2.3`, find the correct device path first and replace it in the unbind/bind commands above.

What each step does:

- `pkill -9 brltty`: prevents `brltty` from claiming the USB serial adapter.
- `make load`: inserts the CH34x kernel module needed for this Jetson image.
- `unbind` and `bind`: forces USB re-enumeration and usually recreates `/dev/ttyUSB0`.
- `ls -l /dev/ttyUSB0`: confirms the device node appeared after recovery.

## After Recovery

If the IMU still does not work, check the attached USB device information directly:

```sh
lsusb
ls /sys/bus/usb/devices
```

If those commands show the device but the logger still fails, restart the logger and watch for connection or frame errors in the terminal output.

## Related Scripts

- `hwt605_sqlite_logger.py` retries when the port is missing and stops `brltty` as a best-effort workaround.
- `hwt605_logger.py` uses the same port-selection fallback and `brltty` workaround.
- `imu_watchdog.sh` keeps the logger running and performs the same `/dev/ttyUSB0` recovery flow.