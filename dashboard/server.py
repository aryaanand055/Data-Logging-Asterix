#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from flask import Flask, jsonify, render_template, request

# When run as a script (`python3 dashboard/server.py`) the CWD and
# `sys.path[0]` are the `dashboard/` directory which prevents importing
# top-level modules like `project_paths`. Ensure the repository root is
# on `sys.path` so both module mode and script mode work.
APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from project_paths import SHARED_DB_PATH

TEMPLATE_DIR = APP_DIR / 'templates'
DB_PATH = Path(SHARED_DB_PATH)

app = Flask(__name__, template_folder=str(TEMPLATE_DIR))

PREFERRED_FIELDS: dict[str, list[str]] = {
    'imu': ['roll_deg', 'yaw_deg', 'pitch_deg', 'temperature_c'],
    'radar': ['distance_m', 'range_m', 'speed_mps', 'velocity_mps'],
    'hall_effect_speed': ['speed_kph', 'speed_mps', 'velocity_kph'],
    'hall_effect_steering': ['angle_deg', 'steering_angle_deg', 'position_deg'],
    'actuator': ['position_mm', 'position_pct', 'current_a'],
    'brake': ['brake_pct', 'position_pct', 'pressure_bar', 'force_n', 'voltage_v'],
    'stm': ['value'],
}


def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def is_numeric(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def as_float(value: object) -> float | None:
    if is_numeric(value):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def table_name(sensor_name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", sensor_name.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        raise ValueError('sensor_name must contain at least one alphanumeric character')
    return f"sensor_{cleaned}"


def sensor_name_from_table(name: str) -> str:
    return name.removeprefix('sensor_')


def list_sensor_tables() -> list[str]:
    if not DB_PATH.exists():
        return []
    with open_db() as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name LIKE 'sensor_%'
            ORDER BY name
            """
        ).fetchall()
    return [row['name'] for row in rows]


def load_recent_rows(sensor_name: str, limit: int) -> list[dict[str, object]]:
    table = table_name(sensor_name)
    if not DB_PATH.exists():
        return []
    with open_db() as conn:
        try:
            rows = conn.execute(
                f"""
                SELECT recorded_at, source_id, payload_json
                FROM {table}
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    result: list[dict[str, object]] = []
    for row in reversed(rows):
        try:
            payload = json.loads(row['payload_json'])
        except json.JSONDecodeError:
            payload = {'raw': row['payload_json']}
        result.append(
            {
                'timestamp': row['recorded_at'],
                'source_id': row['source_id'],
                'payload': payload,
            }
        )
    return result


def load_rows_since(sensor_name: str, seconds: int) -> list[dict[str, object]]:
    table = table_name(sensor_name)
    if not DB_PATH.exists():
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec='seconds').replace('+00:00', 'Z')
    with open_db() as conn:
        try:
            rows = conn.execute(
                f"""
                SELECT recorded_at, source_id, payload_json
                FROM {table}
                WHERE recorded_at >= ?
                ORDER BY id ASC
                """,
                (cutoff,),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    result: list[dict[str, object]] = []
    for row in rows:
        try:
            payload = json.loads(row['payload_json'])
        except json.JSONDecodeError:
            payload = {'raw': row['payload_json']}
        result.append(
            {
                'timestamp': row['recorded_at'],
                'source_id': row['source_id'],
                'payload': payload,
            }
        )
    return result


def load_rows_between(sensor_name: str, start: datetime, end: datetime) -> list[dict[str, object]]:
    table = table_name(sensor_name)
    if not DB_PATH.exists():
        return []

    with open_db() as conn:
        try:
            rows = conn.execute(
                f"""
                SELECT recorded_at, source_id, payload_json
                FROM {table}
                WHERE recorded_at >= ? AND recorded_at <= ?
                ORDER BY id ASC
                """,
                (
                    start.isoformat(timespec='seconds').replace('+00:00', 'Z'),
                    end.isoformat(timespec='seconds').replace('+00:00', 'Z'),
                ),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    result: list[dict[str, object]] = []
    for row in rows:
        try:
            payload = json.loads(row['payload_json'])
        except json.JSONDecodeError:
            payload = {'raw': row['payload_json']}
        result.append(
            {
                'timestamp': row['recorded_at'],
                'source_id': row['source_id'],
                'payload': payload,
            }
        )
    return result


def load_all_rows(sensor_name: str) -> list[dict[str, object]]:
    table = table_name(sensor_name)
    if not DB_PATH.exists():
        return []

    with open_db() as conn:
        try:
            rows = conn.execute(
                f"""
                SELECT recorded_at, source_id, payload_json
                FROM {table}
                ORDER BY id ASC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    result: list[dict[str, object]] = []
    for row in rows:
        try:
            payload = json.loads(row['payload_json'])
        except json.JSONDecodeError:
            payload = {'raw': row['payload_json']}
        result.append(
            {
                'timestamp': row['recorded_at'],
                'source_id': row['source_id'],
                'payload': payload,
            }
        )
    return result


def collect_numeric_fields(rows: Iterable[dict[str, object]]) -> list[str]:
    fields: set[str] = set()
    for row in rows:
        payload = row.get('payload', {})
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if as_float(value) is not None:
                fields.add(str(key))
    return sorted(fields)


def choose_primary_field(sensor_name: str, fields: list[str]) -> str | None:
    preferred = PREFERRED_FIELDS.get(sensor_name.lower(), [])
    for candidate in preferred:
        if candidate in fields:
            return candidate
    return fields[0] if fields else None


def choose_field_from_candidates(fields: list[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in fields:
            return candidate
    return None


def parse_timestamp(timestamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    except ValueError:
        return None


def parse_request_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return parse_timestamp(value)


def resolve_dbw_range(start_param: str | None, end_param: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    end = parse_request_timestamp(end_param) or now
    start = parse_request_timestamp(start_param) or (end - timedelta(minutes=5))
    if start > end:
        start, end = end, start
    return start, end


def speed_value_in_mps(value: float, field_name: str) -> float:
    if field_name.lower().endswith('_kph'):
        return value * (1000.0 / 3600.0)
    return value


def build_numeric_points(rows: list[dict[str, object]], field_name: str) -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    for row in rows:
        payload = row.get('payload', {})
        if not isinstance(payload, dict):
            continue
        value = as_float(payload.get(field_name))
        if value is None:
            continue
        points.append({'timestamp': row['timestamp'], 'value': value})
    return points


def derive_acceleration_points(speed_points: list[dict[str, object]], speed_field: str) -> list[dict[str, object]]:
    timed_samples: list[tuple[datetime, str, float]] = []
    for point in speed_points:
        timestamp = point.get('timestamp')
        value = as_float(point.get('value'))
        if not isinstance(timestamp, str) or value is None:
            continue
        parsed_timestamp = parse_timestamp(timestamp)
        if parsed_timestamp is None:
            continue
        timed_samples.append((parsed_timestamp, timestamp, speed_value_in_mps(value, speed_field)))

    timed_samples.sort(key=lambda sample: sample[0])
    acceleration_points: list[dict[str, object]] = []
    previous_sample: tuple[datetime, str, float] | None = None

    for sample in timed_samples:
        if previous_sample is None:
            previous_sample = sample
            continue
        delta_seconds = (sample[0] - previous_sample[0]).total_seconds()
        if delta_seconds <= 0:
            previous_sample = sample
            continue
        acceleration_points.append(
            {
                'timestamp': sample[1],
                'value': (sample[2] - previous_sample[2]) / delta_seconds,
            }
        )
        previous_sample = sample

    return acceleration_points


def derive_distance_points(speed_points: list[dict[str, object]], speed_field: str) -> list[dict[str, object]]:
    timed_samples: list[tuple[datetime, str, float]] = []
    for point in speed_points:
        timestamp = point.get('timestamp')
        value = as_float(point.get('value'))
        if not isinstance(timestamp, str) or value is None:
            continue
        parsed_timestamp = parse_timestamp(timestamp)
        if parsed_timestamp is None:
            continue
        timed_samples.append((parsed_timestamp, timestamp, speed_value_in_mps(value, speed_field)))

    timed_samples.sort(key=lambda sample: sample[0])
    distance_points: list[dict[str, object]] = []
    previous_sample: tuple[datetime, str, float] | None = None
    cumulative_distance = 0.0

    for sample in timed_samples:
        if previous_sample is not None:
            delta_seconds = (sample[0] - previous_sample[0]).total_seconds()
            if delta_seconds > 0:
                cumulative_distance += ((sample[2] + previous_sample[2]) / 2.0) * delta_seconds
        distance_points.append({'timestamp': sample[1], 'value': cumulative_distance})
        previous_sample = sample

    return distance_points


def build_scatter_points(
    rows: list[dict[str, object]],
    x_field: str,
    y_field: str,
    convert_y_to_mps: bool = False,
) -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    for row in rows:
        payload = row.get('payload', {})
        if not isinstance(payload, dict):
            continue
        x_value = as_float(payload.get(x_field))
        y_value = as_float(payload.get(y_field))
        if x_value is None or y_value is None:
            continue
        if convert_y_to_mps:
            y_value = speed_value_in_mps(y_value, y_field)
        points.append({'timestamp': row['timestamp'], 'x': x_value, 'y': y_value})
    return points


def build_dbw_dashboard_data() -> dict[str, object]:
    start_param = request.args.get('start')
    end_param = request.args.get('end')
    start, end = resolve_dbw_range(start_param, end_param)

    speed_rows = load_rows_between('hall_effect_speed', start, end)
    speed_fields = collect_numeric_fields(speed_rows)
    speed_field = choose_primary_field('hall_effect_speed', speed_fields)
    speed_points = build_numeric_points(speed_rows, speed_field) if speed_field else []

    steering_rows = load_rows_between('hall_effect_steering', start, end)
    steering_fields = collect_numeric_fields(steering_rows)
    steering_field = choose_primary_field('hall_effect_steering', steering_fields)
    steering_points = build_numeric_points(steering_rows, steering_field) if steering_field else []

    distance_points = derive_distance_points(speed_points, speed_field) if speed_field else []

    radar_rows = load_rows_between('radar', start, end)
    radar_fields = collect_numeric_fields(radar_rows)
    radar_distance_field = choose_field_from_candidates(radar_fields, ['distance_m', 'range_m'])
    radar_speed_field = choose_field_from_candidates(radar_fields, ['speed_mps', 'velocity_mps', 'speed_kph', 'velocity_kph'])
    radar_scatter_points: list[dict[str, object]] = []
    if radar_distance_field and radar_speed_field:
        radar_scatter_points = build_scatter_points(
            radar_rows,
            radar_distance_field,
            radar_speed_field,
            convert_y_to_mps=True,
        )

    imu_rows = load_rows_between('imu', start, end)
    imu_fields = collect_numeric_fields(imu_rows)
    acceleration_field = choose_field_from_candidates(imu_fields, ['ax_g', 'ax', 'accel_g', 'acceleration_g'])
    acceleration_points = build_numeric_points(imu_rows, acceleration_field) if acceleration_field else []

    lateral_field = choose_field_from_candidates(imu_fields, ['ay_g', 'ay', 'lateral_g'])
    lateral_points = build_numeric_points(imu_rows, lateral_field) if lateral_field else []

    heading_field = choose_field_from_candidates(imu_fields, ['yaw_deg', 'heading_deg', 'yaw'])
    heading_points = build_numeric_points(imu_rows, heading_field) if heading_field else []

    brake_rows = load_rows_between('brake', start, end)
    brake_fields = collect_numeric_fields(brake_rows)
    brake_field = choose_primary_field('brake', brake_fields)
    brake_points = build_numeric_points(brake_rows, brake_field) if brake_field else []

    return {
        'db_path': str(DB_PATH),
        'range': {
            'start': start.isoformat(timespec='seconds').replace('+00:00', 'Z'),
            'end': end.isoformat(timespec='seconds').replace('+00:00', 'Z'),
            'default_minutes': 5,
        },
        'speed': {
            'sensor_name': 'hall_effect_speed',
            'field': speed_field,
            'rows': len(speed_rows),
            'points': speed_points,
        },
        'acceleration': {
            'sensor_name': 'imu',
            'field': acceleration_field,
            'rows': len(imu_rows),
            'points': acceleration_points,
        },
        'distance': {
            'sensor_name': 'hall_effect_speed',
            'field': speed_field,
            'rows': len(speed_rows),
            'points': distance_points,
        },
        'speed_distance': {
            'sensor_name': 'radar',
            'distance_field': radar_distance_field,
            'speed_field': radar_speed_field,
            'rows': len(radar_rows),
            'points': radar_scatter_points,
        },
        'steering': {
            'sensor_name': 'hall_effect_steering',
            'field': steering_field,
            'rows': len(steering_rows),
            'points': steering_points,
        },
        'brake': {
            'sensor_name': 'brake',
            'field': brake_field,
            'rows': len(brake_rows),
            'points': brake_points,
        },
        'lateral': {
            'sensor_name': 'imu',
            'field': lateral_field,
            'rows': len(imu_rows),
            'points': lateral_points,
        },
        'heading': {
            'sensor_name': 'imu',
            'field': heading_field,
            'rows': len(imu_rows),
            'points': heading_points,
        },
    }


def latest_payload(sensor_name: str) -> dict[str, object] | None:
    rows = load_recent_rows(sensor_name, 1)
    return rows[-1] if rows else None


@app.get('/api/latest/<sensor_name>')
def api_latest_sensor(sensor_name: str):
    latest = latest_payload(sensor_name)
    if not latest:
        resp = jsonify({'ok': False, 'error': 'sensor not found or no data'})
        resp.status_code = 404
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    resp = jsonify({'ok': True, 'sensor_name': sensor_name, 'latest': latest})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.get('/api/latest')
def api_latest():
    # Compatibility endpoint for legacy UIs that hit `/api/latest`.
    sensor_name = request.args.get('sensor')
    if sensor_name:
        return api_latest_sensor(sensor_name)

    tables = list_sensor_tables()
    if not tables:
        resp = jsonify({'ok': False, 'error': 'no data'})
        resp.status_code = 404
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    # Prefer a sensor named `imu` if available, then fallback to first.
    preferred = 'imu'
    chosen = None
    for t in tables:
        if sensor_name_from_table(t) == preferred:
            chosen = preferred
            break
    if not chosen:
        chosen = sensor_name_from_table(tables[0])

    latest = latest_payload(chosen)
    if not latest:
        resp = jsonify({'ok': False, 'error': 'no data'})
        resp.status_code = 404
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    resp = jsonify({'ok': True, 'sensor': chosen, 'latest': latest})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.get('/')
def index() -> str:
    return render_template('dashboard.html')


@app.get('/dbw')
def dbw_index() -> str:
    return render_template('dbw_dashboard.html')


@app.get('/api/sensors')
def api_sensors():
    try:
        limit = int(request.args.get('limit', '50'))
    except ValueError:
        limit = 50
    limit = max(5, min(limit, 500))
    sensors: list[dict[str, object]] = []
    for table in list_sensor_tables():
        sensor = sensor_name_from_table(table)
        rows = load_recent_rows(sensor, limit)
        latest = rows[-1] if rows else None
        fields = collect_numeric_fields(rows)
        sensors.append(
            {
                'sensor_name': sensor,
                'table_name': table,
                'row_count': len(rows),
                'fields': fields,
                'primary_field': choose_primary_field(sensor, fields),
                'latest': latest,
            }
        )
    resp = jsonify({'ok': True, 'db_path': str(DB_PATH), 'sensors': sensors})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.get('/api/dbw')
def api_dbw():
    data = build_dbw_dashboard_data()
    resp = jsonify({'ok': True, **data})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.get('/api/series/<sensor_name>')
def api_series(sensor_name: str):
    field = request.args.get('field')
    seconds_param = request.args.get('seconds')
    rows: list[dict[str, object]]
    if seconds_param is not None:
      try:
          seconds = int(seconds_param)
      except ValueError:
          seconds = 30
      seconds = max(1, min(seconds, 86400))
      rows = load_rows_since(sensor_name, seconds)
    else:
      try:
          limit = int(request.args.get('limit', '200'))
      except ValueError:
          limit = 200
      limit = max(5, min(limit, 2000))
      rows = load_recent_rows(sensor_name, limit)
    if not rows:
        resp = jsonify({'ok': True, 'sensor_name': sensor_name, 'field': field, 'seconds': int(seconds_param) if seconds_param and seconds_param.isdigit() else None, 'points': []})
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    fields = collect_numeric_fields(rows)
    field = field or choose_primary_field(sensor_name, fields)
    if not field:
        resp = jsonify({'ok': False, 'error': 'no numeric fields available'})
        resp.status_code = 400
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    points: list[dict[str, object]] = []
    for row in rows:
        payload = row['payload']
        if not isinstance(payload, dict):
            continue
        value = as_float(payload.get(field))
        if value is None:
            continue
        points.append({'timestamp': row['timestamp'], 'value': value})

    resp = jsonify(
        {
            'ok': True,
            'sensor_name': sensor_name,
            'field': field,
            'seconds': int(seconds_param) if seconds_param and seconds_param.isdigit() else None,
            'points': points,
        }
    )
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.get('/api/all/<sensor_name>')
def api_all(sensor_name: str):
    """Return all recent rows for a sensor.

    Query params:
      - limit: number of rows to return (default 1000)
        Use `limit=all` to return the full table.
      - format: 'json' (default) or 'csv'
    """
    seconds_param = request.args.get('seconds')
    limit_param = (request.args.get('limit') or '1000').strip().lower()
    return_all = limit_param in {'all', '*'}
    if seconds_param is None and not return_all:
        try:
            limit = int(limit_param)
        except ValueError:
            limit = 1000
        limit = max(1, limit)
    fmt = (request.args.get('format') or 'json').lower()

    table = table_name(sensor_name)
    if not DB_PATH.exists():
        db_rows = []
    else:
        with open_db() as conn:
            try:
                if seconds_param is not None:
                    try:
                        seconds = int(seconds_param)
                    except ValueError:
                        seconds = 30
                    seconds = max(1, min(seconds, 86400))
                    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat(timespec='seconds').replace('+00:00', 'Z')
                    query = f"""
                        SELECT recorded_at, source_id, payload_json
                        FROM {table}
                        WHERE recorded_at >= ?
                        ORDER BY id ASC
                    """
                    db_rows = conn.execute(query, (cutoff,)).fetchall()
                else:
                    query = f"""
                        SELECT recorded_at, source_id, payload_json
                        FROM {table}
                        ORDER BY id DESC
                    """
                    params: tuple[object, ...] = ()
                    if not return_all:
                        query += "\n                    LIMIT ?"
                        params = (limit,)
                    db_rows = conn.execute(query, params).fetchall()
            except sqlite3.OperationalError:
                db_rows = []

    rows: list[dict[str, object]] = []
    iterable_rows = db_rows if seconds_param is not None else reversed(db_rows)
    for row in iterable_rows:
        try:
            payload = json.loads(row['payload_json'])
        except json.JSONDecodeError:
            payload = {'raw': row['payload_json']}
        rows.append(
            {
                'timestamp': row['recorded_at'],
                'source_id': row['source_id'],
                'payload': payload,
            }
        )

    if not rows:
        resp = jsonify({'ok': True, 'sensor_name': sensor_name, 'rows': []})
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    if fmt == 'csv':
        # produce CSV with timestamp, source_id, payload_json
        import io, csv

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['timestamp', 'source_id', 'payload_json'])
        for r in rows:
            writer.writerow([r['timestamp'], r['source_id'], json.dumps(r['payload'], ensure_ascii=False)])
        resp = app.response_class(buf.getvalue(), mimetype='text/csv')
        resp.headers['Content-Disposition'] = f'attachment; filename="{sensor_name}_data.csv"'
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    # default JSON
    resp = jsonify({'ok': True, 'sensor_name': sensor_name, 'rows': rows})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=False)
