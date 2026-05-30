/*
 * vehicle_telemetry_simulator.ino — Team Asterix telemetry SIMULATOR
 * ------------------------------------------------------------------
 * Streams FAKE speed / steering / brake data over USB serial, in the same
 * format as vehicle_telemetry.ino — but with NO sensors wired. Flash it to any
 * Arduino to exercise the host pipeline (arduino_serial_reader.py) and the
 * dashboard without real hardware.
 *
 * Output (one line per sample, 10 Hz, 115200 baud):
 *
 *     speed=21.83 steering=9.56 brake=19.5 voltage=0.98
 *
 * On the host:
 *     cd vehicle_controls
 *     python3 arduino_serial_reader.py | python3 vehicle_db_uploader.py
 *   or simply:
 *     ./launch_all.sh --arduino
 *
 * The motion is loosely coupled to look like a plausible drive: braking bleeds
 * off speed, and steering wanders as if tracking a course. No pins are used.
 */

const unsigned long SAMPLE_MS = 100;   // 10 Hz output

unsigned long lastSampleMs = 0;
unsigned long sequence     = 0;

// Smoothed state, mirrors the Python simulator (vehicle_controls/vehicle_simulator.py).
float speed_kph = 0.0;
float angle_deg = 0.0;
float brake_pct = 0.0;

// Small helper: a pseudo-random float in [-1, 1] (random() needs no hardware).
float jitter() {
  return (random(-1000, 1001)) / 1000.0;
}

void setup() {
  Serial.begin(115200);
  // A0 is left floating, so its noise gives a different seed on each power-up.
  randomSeed(analogRead(A0));
}

void loop() {
  unsigned long now = millis();
  if (now - lastSampleMs < SAMPLE_MS) {
    return;
  }
  lastSampleMs = now;
  sequence++;

  float t = sequence;

  // Brake comes and goes in gentle pulses (0..100 %).
  float targetBrake = 35.0 * sin(t / 33.0) + 6.0 * jitter();
  if (targetBrake < 0)   targetBrake = 0;
  if (targetBrake > 100) targetBrake = 100;
  brake_pct += (targetBrake - brake_pct) * 0.15;

  // Speed climbs toward a cruising target but is pulled down by braking.
  float cruise      = 22.0 + 6.0 * sin(t / 25.0);
  float targetSpeed = cruise - brake_pct * 0.25 + 0.8 * jitter();
  if (targetSpeed < 0)  targetSpeed = 0;
  if (targetSpeed > 40) targetSpeed = 40;
  speed_kph += (targetSpeed - speed_kph) * 0.12;
  if (speed_kph < 0)  speed_kph = 0;
  if (speed_kph > 40) speed_kph = 40;

  // Steering wanders within a believable lock range, rate-limited.
  float targetAngle = 14.0 * sin(t / 40.0) + 6.0 * jitter();
  if (targetAngle < -35) targetAngle = -35;
  if (targetAngle >  35) targetAngle =  35;
  float step = targetAngle - angle_deg;
  if (step < -1.2) step = -1.2;
  if (step >  1.2) step =  1.2;
  angle_deg += step;
  if (angle_deg < -45) angle_deg = -45;
  if (angle_deg >  45) angle_deg =  45;

  // Brake potentiometer voltage equivalent (0..5 V).
  float brake_v = brake_pct / 100.0 * 5.0;

  // Same key=value line the real firmware emits.
  Serial.print("speed=");     Serial.print(speed_kph, 2);
  Serial.print(" steering="); Serial.print(angle_deg, 2);
  Serial.print(" brake=");    Serial.print(brake_pct, 1);
  Serial.print(" voltage=");  Serial.println(brake_v, 2);
}
