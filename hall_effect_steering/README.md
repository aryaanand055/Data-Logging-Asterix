# Hall Effect Steering

This folder contains the steering potentiometer pipeline.

- `steering_simulator.py` generates JSONL samples that mimic steering-angle readings.
- `steering_db_uploader.py` reads those samples from stdin and writes them to the shared SQLite database.

Shared settings:

- Shared database: `sensor_data.db` at the repo root
- Target table: `sensor_hall_effect_steering`
- Dashboard: `dashboard/server.py`

Run the pipeline from the repository root:

```bash
python3 hall_effect_steering/steering_simulator.py | python3 hall_effect_steering/steering_db_uploader.py
```

For a short test run:

```bash
python3 hall_effect_steering/steering_simulator.py --count 5 | python3 hall_effect_steering/steering_db_uploader.py --quiet
```
