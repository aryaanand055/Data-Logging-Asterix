#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import os
import subprocess
import sqlite3
import json
from collections import deque
from datetime import datetime, timezone
import sys

from flask import Flask, jsonify, render_template_string

SCRIPT_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, SCRIPT_DIR)

from project_paths import SHARED_DB_PATH

LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
DB_PATH = str(SHARED_DB_PATH)
MAX_POINTS = 1200

app = Flask(__name__)

history = {'t': deque(maxlen=MAX_POINTS), 'roll': deque(maxlen=MAX_POINTS), 'pitch': deque(maxlen=MAX_POINTS), 'yaw': deque(maxlen=MAX_POINTS)}
last_timestamp = None


def parse_csv_line(line: str):
    if not line or line.startswith('timestamp_utc'):
        return None
    row = next(csv.reader(io.StringIO(line)))
    if len(row) < 11:
        return None
    return {
        'timestamp_utc': row[0],
        'roll_deg': float(row[1]),
        'pitch_deg': float(row[2]),
        'yaw_deg': float(row[3]),
        'ax_g': float(row[4]),
        'ay_g': float(row[5]),
        'az_g': float(row[6]),
        'gx_dps': float(row[7]),
        'gy_dps': float(row[8]),
        'gz_dps': float(row[9]),
        'temperature_c': float(row[10]),
    }


def latest_line():
    day = datetime.now(timezone.utc).strftime('%Y%m%d')
    path = f"{LOG_DIR}/hwt605_{day}.csv"
    if not os.path.exists(path):
        return ''
    try:
        return subprocess.check_output(['tail', '-n', '1', path], text=True).strip()
    except Exception:
        return ''


def latest_db_sample():
    """Return the most recent IMU sample from the SQLite DB as a dict, or None."""
    path = DB_PATH
    if not os.path.exists(path):
        return None
    conn = None
    try:
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        # sensor_imu is the table created by SensorSQLiteLogger for sensor_name='imu'
        cur.execute("SELECT recorded_at, payload_json FROM sensor_imu ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        if not row:
            return None
        recorded_at, payload_json = row
        payload = json.loads(payload_json)
        # map payload fields to the UI's expected keys
        sample = {
            'timestamp_utc': recorded_at,
            'roll_deg': float(payload.get('roll_deg', payload.get('roll', 0.0))),
            'pitch_deg': float(payload.get('pitch_deg', payload.get('pitch', 0.0))),
            'yaw_deg': float(payload.get('yaw_deg', payload.get('yaw', 0.0))),
            'ax_g': float(payload.get('ax_g', payload.get('ax', 0.0))),
            'ay_g': float(payload.get('ay_g', payload.get('ay', 0.0))),
            'az_g': float(payload.get('az_g', payload.get('az', 0.0))),
            'gx_dps': float(payload.get('gx_dps', payload.get('gx', 0.0))),
            'gy_dps': float(payload.get('gy_dps', payload.get('gy', 0.0))),
            'gz_dps': float(payload.get('gz_dps', payload.get('gz', 0.0))),
            'temperature_c': float(payload.get('temperature_c', payload.get('temp', 0.0))),
        }
        return sample
    except Exception:
        return None
    finally:
        if conn:
            conn.close()


@app.get('/')
def index():
    return render_template_string('''
<!doctype html><html><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<title>HWT605 Live UI</title><script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{--bg:#f8fafc;--card:#fff;--ink:#0f172a;--muted:#64748b}
*{box-sizing:border-box}body{margin:0;font-family:Segoe UI,Tahoma,sans-serif;background:linear-gradient(120deg,#e0f2fe,#fff7ed);color:var(--ink)}
.wrap{max-width:1180px;margin:18px auto;padding:0 14px;display:grid;gap:12px}.head{display:flex;justify-content:space-between;align-items:center;gap:10px}.status{color:var(--muted)}
.left{display:flex;align-items:center;gap:10px}.btn{border:1px solid #cbd5e1;background:#fff;border-radius:10px;padding:8px 12px;font-weight:600;cursor:pointer}.btn:hover{background:#f1f5f9}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}.card{background:var(--card);border-radius:12px;padding:10px;border:1px solid #dbeafe;box-shadow:0 6px 16px rgba(2,6,23,.06)}
.label{font-size:.78rem;color:var(--muted)}.val{font-size:1.33rem;font-weight:700}.panel{background:#fff;border:1px solid #dbeafe;border-radius:12px;padding:10px;height:360px}
</style></head><body><div class="wrap"><div class="head"><div class="left"><h2 style="margin:0">HWT605 Live Stream</h2><button class="btn" id="calBtn">Calibrate Zero</button></div><div class="status" id="st">connecting...</div></div>
<div class="grid"><div class="card"><div class="label">Roll (cal)</div><div class="val" id="roll">-</div></div><div class="card"><div class="label">Pitch (cal)</div><div class="val" id="pitch">-</div></div><div class="card"><div class="label">Yaw (cal)</div><div class="val" id="yaw">-</div></div><div class="card"><div class="label">Temp C</div><div class="val" id="temp">-</div></div><div class="card"><div class="label">Acc XYZ</div><div class="val" id="acc">-</div></div><div class="card"><div class="label">Gyro XYZ</div><div class="val" id="gyro">-</div></div></div>
<div class="panel"><canvas id="c"></canvas></div></div>
<script>
const st=document.getElementById('st'),roll=document.getElementById('roll'),pitch=document.getElementById('pitch'),yaw=document.getElementById('yaw'),temp=document.getElementById('temp'),acc=document.getElementById('acc'),gyro=document.getElementById('gyro'),calBtn=document.getElementById('calBtn');

const MAX_POINTS=1200;
const tArr=[], rArr=[], pArr=[], yArr=[];
let lastSampleTs=null;
let latestRaw=null;
let prevRaw=null;
let prevUnwrapped=null;
let uiTickMs=[];
let sampleDtMs=[];
let lastUiNow=performance.now();
let lastSampleMs=null;

let zero={r:0,p:0,y:0};
let calibrated=false;

function pushBounded(arr,val){ arr.push(val); if(arr.length>MAX_POINTS) arr.shift(); }
function avg(arr){ if(!arr.length) return 0; return arr.reduce((a,b)=>a+b,0)/arr.length; }
function wrap180(a){ while(a>180)a-=360; while(a<-180)a+=360; return a; }
function unwrapAxis(prevU, prevR, raw){
  let d = raw - prevR;
  if(d > 180) d -= 360;
  else if(d < -180) d += 360;
  return prevU + d;
}

function calibratedAngles(raw){
  if(!calibrated){
    return {r:raw.roll_deg,p:raw.pitch_deg,y:raw.yaw_deg};
  }
  return {
    r:wrap180(raw.roll_deg-zero.r),
    p:wrap180(raw.pitch_deg-zero.p),
    y:wrap180(raw.yaw_deg-zero.y)
  };
}

calBtn.addEventListener('click',()=>{
  if(!latestRaw){ return; }
  zero={r:latestRaw.roll_deg,p:latestRaw.pitch_deg,y:latestRaw.yaw_deg};
  calibrated=true;
  prevRaw=null;
  prevUnwrapped=null;
  tArr.length=0; rArr.length=0; pArr.length=0; yArr.length=0;
  st.textContent='calibrated: current pose set to 0,0,0';
});

const ch=new Chart(document.getElementById('c').getContext('2d'),{
  type:'line',
  data:{
    labels:[],
    datasets:[
      {label:'Roll (cal, unwrapped)',data:[],borderColor:'#0ea5e9',pointRadius:0,tension:0},
      {label:'Pitch (cal, unwrapped)',data:[],borderColor:'#f97316',pointRadius:0,tension:0},
      {label:'Yaw (cal, unwrapped)',data:[],borderColor:'#10b981',pointRadius:0,tension:0}
    ]
  },
  options:{animation:false,maintainAspectRatio:false,responsive:true,normalized:true}
});

async function tick(){
  const now=performance.now();
  pushBounded(uiTickMs, now-lastUiNow);
  lastUiNow=now;

  try{
    const r=await fetch('/api/latest',{cache:'no-store'});
    const j=await r.json();
    if(!j.ok){
      const uiHz=1000/Math.max(1,avg(uiTickMs));
      st.textContent=`waiting for logger data... | UI ${uiHz.toFixed(1)} Hz | Data 0.0 Hz`;
      return;
    }

    const s=j.sample;
    latestRaw=s;
    const c=calibratedAngles(s);

    roll.textContent=c.r.toFixed(2);
    pitch.textContent=c.p.toFixed(2);
    yaw.textContent=c.y.toFixed(2);
    temp.textContent=s.temperature_c.toFixed(2);
    acc.textContent=`${s.ax_g.toFixed(3)} / ${s.ay_g.toFixed(3)} / ${s.az_g.toFixed(3)}`;
    gyro.textContent=`${s.gx_dps.toFixed(2)} / ${s.gy_dps.toFixed(2)} / ${s.gz_dps.toFixed(2)}`;

    if(s.timestamp_utc!==lastSampleTs){
      lastSampleTs=s.timestamp_utc;
      const label=s.timestamp_utc.split('T')[1].replace('Z','');

      if(prevRaw===null){
        prevRaw={r:c.r,p:c.p,y:c.y};
        prevUnwrapped={r:c.r,p:c.p,y:c.y};
      }else{
        prevUnwrapped={
          r:unwrapAxis(prevUnwrapped.r, prevRaw.r, c.r),
          p:unwrapAxis(prevUnwrapped.p, prevRaw.p, c.p),
          y:unwrapAxis(prevUnwrapped.y, prevRaw.y, c.y)
        };
        prevRaw={r:c.r,p:c.p,y:c.y};
      }

      pushBounded(tArr,label);
      pushBounded(rArr,prevUnwrapped.r);
      pushBounded(pArr,prevUnwrapped.p);
      pushBounded(yArr,prevUnwrapped.y);

      const sampleMs=Date.parse(s.timestamp_utc);
      if(lastSampleMs!==null){
        const dt=Math.max(1,sampleMs-lastSampleMs);
        pushBounded(sampleDtMs,dt);
      }
      lastSampleMs=sampleMs;

      ch.data.labels=tArr;
      ch.data.datasets[0].data=rArr;
      ch.data.datasets[1].data=pArr;
      ch.data.datasets[2].data=yArr;
      ch.update('none');
    }

    const uiHz=1000/Math.max(1,avg(uiTickMs));
    const dataHz=sampleDtMs.length?1000/Math.max(1,avg(sampleDtMs)):0;
    const calTxt=calibrated?'CAL ON':'CAL OFF';
    st.textContent=`live ${s.timestamp_utc} | ${calTxt} | UI ${uiHz.toFixed(1)} Hz | Data ${dataHz.toFixed(1)} Hz`;

  }catch(_){
    st.textContent='reconnecting...';
  }
}
setInterval(tick,10);tick();
</script></body></html>
''')


@app.get('/api/latest')
def api_latest():
    global last_timestamp
    # Prefer the SQLite DB as the live source; fall back to CSV logs if DB missing
    s = latest_db_sample()
    if s is None:
        s = parse_csv_line(latest_line())

    if s is None:
        resp = jsonify({'ok': False})
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    if s['timestamp_utc'] != last_timestamp:
        last_timestamp = s['timestamp_utc']
        history['t'].append(datetime.now(timezone.utc).strftime('%H:%M:%S'))
        history['roll'].append(s['roll_deg'])
        history['pitch'].append(s['pitch_deg'])
        history['yaw'].append(s['yaw_deg'])

    resp = jsonify({'ok': True, 'sample': s, 'history': {k: list(v) for k, v in history.items()}})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5050, debug=False)
