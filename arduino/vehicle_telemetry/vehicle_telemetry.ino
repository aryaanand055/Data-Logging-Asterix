/*
 * vehicle_telemetry.ino — Team Asterix drive-by-wire telemetry source
 * -------------------------------------------------------------------
 * Reads three vehicle-control inputs and streams them over USB serial:
 *
 *   - Wheel speed   from a hall-effect sensor (pulse counting)   -> km/h
 *   - Steering angle from a potentiometer                        -> degrees
 *   - Brake          from a potentiometer                        -> percent + volts
 *
 * Each sample is printed on its own line at SAMPLE_MS intervals, in the
 * key=value format that vehicle_controls/arduino_serial_reader.py parses
 * (it is also easy to read in the Arduino Serial Monitor), e.g.:
 *
 *     speed=12.34 steering=-4.10 brake=20.0 voltage=1.00
 *
 * On the host:
 *     cd vehicle_controls
 *     python3 arduino_serial_reader.py | python3 vehicle_db_uploader.py
 *
 * Board: Arduino Uno / Nano (ATmega328). The hall sensor must be on a pin
 * that supports external interrupts (D2 = INT0 or D3 = INT1 on the Uno).
 */

// ----------------------------- Pin map --------------------------------------
const uint8_t PIN_HALL      = 2;   // hall-effect speed sensor (interrupt pin)
const uint8_t PIN_STEERING  = A0;  // steering potentiometer wiper
const uint8_t PIN_BRAKE     = A1;  // brake potentiometer wiper

// --------------------------- Calibration ------------------------------------
// Speed: how the wheel/encoder relates to distance.
const float   WHEEL_CIRCUMFERENCE_M = 1.595;  // metres travelled per wheel revolution
const uint8_t PULSES_PER_REV        = 4;      // hall pulses per wheel revolution

// Steering: maps the 10-bit ADC reading to a physical angle.
const int   STEER_ADC_MIN  = 0;      // ADC value at full-left lock
const int   STEER_ADC_MAX  = 1023;   // ADC value at full-right lock
const float STEER_DEG_MIN  = -45.0;  // angle at STEER_ADC_MIN
const float STEER_DEG_MAX  =  45.0;  // angle at STEER_ADC_MAX

// Brake: maps the 10-bit ADC reading to 0..100 %.
const int   BRAKE_ADC_REST    = 0;     // ADC value with the pedal released
const int   BRAKE_ADC_PRESSED = 1023;  // ADC value fully pressed
const float ADC_REF_VOLTS     = 5.0;   // analog reference voltage

// Output rate.
const unsigned long SAMPLE_MS = 100;   // 10 Hz

// --------------------------- Internal state ---------------------------------
volatile unsigned long pulseCount = 0;  // incremented in the ISR
unsigned long          lastSampleMs = 0;

void onHallPulse() {
  pulseCount++;
}

float readSteeringDeg() {
  int raw = analogRead(PIN_STEERING);
  float t = (float)(raw - STEER_ADC_MIN) / (float)(STEER_ADC_MAX - STEER_ADC_MIN);
  if (t < 0) t = 0; else if (t > 1) t = 1;
  return STEER_DEG_MIN + t * (STEER_DEG_MAX - STEER_DEG_MIN);
}

float readBrakePct(int *rawOut) {
  int raw = analogRead(PIN_BRAKE);
  if (rawOut) *rawOut = raw;
  float t = (float)(raw - BRAKE_ADC_REST) / (float)(BRAKE_ADC_PRESSED - BRAKE_ADC_REST);
  if (t < 0) t = 0; else if (t > 1) t = 1;
  return t * 100.0;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_HALL, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_HALL), onHallPulse, RISING);
  lastSampleMs = millis();
}

void loop() {
  unsigned long now = millis();
  unsigned long elapsed = now - lastSampleMs;
  if (elapsed < SAMPLE_MS) {
    return;
  }
  lastSampleMs = now;

  // Atomically snapshot and reset the pulse counter.
  noInterrupts();
  unsigned long pulses = pulseCount;
  pulseCount = 0;
  interrupts();

  // Speed: revolutions in this window -> distance -> km/h.
  float revs       = (float)pulses / (float)PULSES_PER_REV;
  float distance_m = revs * WHEEL_CIRCUMFERENCE_M;
  float speed_mps  = distance_m / (elapsed / 1000.0);
  float speed_kph  = speed_mps * 3.6;

  float steering_deg = readSteeringDeg();

  int brakeRaw;
  float brake_pct = readBrakePct(&brakeRaw);
  float brake_v   = (float)brakeRaw / 1023.0 * ADC_REF_VOLTS;

  // key=value line — parsed by arduino_serial_reader.py and human-readable.
  Serial.print("speed=");    Serial.print(speed_kph, 3);
  Serial.print(" steering="); Serial.print(steering_deg, 3);
  Serial.print(" brake=");    Serial.print(brake_pct, 1);
  Serial.print(" voltage=");  Serial.println(brake_v, 3);
}
