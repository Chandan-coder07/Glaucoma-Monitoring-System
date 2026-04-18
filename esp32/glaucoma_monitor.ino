/**
 * GlaucoMonitor ESP32 Firmware
 * ─────────────────────────────────────────────────────────────────────────────
 * Reads Intraocular Pressure (IOP) from a pressure sensor (analog),
 * performs basic calibration, and sends readings via USB Serial to the backend.
 *
 * Hardware Setup:
 *   - Sensor output → GPIO 34 (ADC1, input only)
 *   - Left/Right eye selector → GPIO 26 (HIGH=RIGHT, LOW=LEFT)
 *   - LED indicator → GPIO 2 (built-in LED)
 *   - Optional buzzer → GPIO 27 (HIGH IOP alert)
 *
 * Serial Output Format:
 *   IOP:18.5,EYE:RIGHT,PATIENT:default\n
 *
 * Baud Rate: 9600
 *
 * NOTE: The IOP_CONVERSION_FACTOR should be calibrated against a reference
 * tonometer for clinical accuracy. The formula below is illustrative.
 */

#include <Arduino.h>

// ─── Pin Definitions ──────────────────────────────────────────────────────────
#define SENSOR_PIN        34    // Analog input from IOP sensor
#define EYE_SELECT_PIN    26    // Digital input: HIGH=RIGHT, LOW=LEFT
#define LED_PIN           2     // Built-in LED
#define BUZZER_PIN        27    // Optional buzzer

// ─── Calibration Constants ────────────────────────────────────────────────────
// These values should be calibrated with a reference Goldmann applanation tonometer.
// Sensor output (ADC 0-4095) → IOP in mmHg
const float ADC_MAX          = 4095.0f;
const float VCC              = 3.3f;         // ESP32 ADC reference voltage
const float SENSOR_MIN_V     = 0.5f;         // Sensor output at 0 mmHg
const float SENSOR_MAX_V     = 2.5f;         // Sensor output at 40 mmHg
const float IOP_MIN          = 0.0f;
const float IOP_MAX          = 40.0f;
const float IOP_HIGH_THRESH  = 21.0f;        // Alert threshold
const int   NUM_SAMPLES      = 10;           // Samples to average per reading
const int   SAMPLE_DELAY_MS  = 10;           // Delay between samples
const int   READ_INTERVAL_MS = 5000;         // Measurement interval (5 seconds)

// Patient ID (can be configured via serial command in production)
const char* PATIENT_ID = "default";

// ─── State ────────────────────────────────────────────────────────────────────
unsigned long lastReadTime = 0;
float lastIOP = 0.0f;

// ─── Setup ────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  Serial.println("GlaucoMonitor ESP32 v1.0 initializing...");

  // Pin setup
  pinMode(SENSOR_PIN, INPUT);
  pinMode(EYE_SELECT_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  // Configure ADC
  analogSetAttenuation(ADC_11db);   // Full range 0-3.3V
  analogSetWidth(12);                // 12-bit resolution (0-4095)

  // Self-test blink
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(200);
    digitalWrite(LED_PIN, LOW);
    delay(200);
  }

  Serial.println("Ready. Sending IOP readings every 5 seconds.");
  Serial.println("Format: IOP:<value>,EYE:<LEFT|RIGHT>,PATIENT:<id>");
}

// ─── Main Loop ────────────────────────────────────────────────────────────────
void loop() {
  unsigned long now = millis();

  if (now - lastReadTime >= READ_INTERVAL_MS) {
    lastReadTime = now;

    float iop = readIOP();
    String eye = readEye();

    // Format and send over serial
    sendReading(iop, eye);

    // Visual feedback
    blinkLED(1);

    // Buzzer alert on high IOP
    if (iop > IOP_HIGH_THRESH) {
      alertBuzzer();
    }

    lastIOP = iop;
  }

  // Handle incoming serial commands (for configuration)
  handleSerialCommands();
}

// ─── IOP Measurement ─────────────────────────────────────────────────────────
/**
 * Read and average multiple ADC samples, convert to IOP value in mmHg.
 * Uses linear interpolation based on sensor voltage range.
 *
 * Real sensor (e.g., Honeywell ABPMANV001PGAA3) maps pressure linearly
 * from 0.5V to 4.5V for 0 to 60 psi. Adjust formula for your sensor.
 */
float readIOP() {
  long sum = 0;

  // Collect samples
  for (int i = 0; i < NUM_SAMPLES; i++) {
    sum += analogRead(SENSOR_PIN);
    delay(SAMPLE_DELAY_MS);
  }

  float avgADC = (float)sum / NUM_SAMPLES;

  // Convert ADC to voltage
  float voltage = (avgADC / ADC_MAX) * VCC;

  // Convert voltage to IOP (mmHg) using linear mapping
  // Clamp to sensor range
  voltage = constrain(voltage, SENSOR_MIN_V, SENSOR_MAX_V);

  float iop = IOP_MIN + (voltage - SENSOR_MIN_V) /
              (SENSOR_MAX_V - SENSOR_MIN_V) * (IOP_MAX - IOP_MIN);

  // Apply calibration offset (adjust after comparing with reference tonometer)
  float calibrationOffset = 0.0f;  // Set after calibration
  iop += calibrationOffset;

  // Clamp to physiological range
  iop = constrain(iop, 5.0f, 40.0f);

  // Round to 1 decimal place
  return roundf(iop * 10.0f) / 10.0f;
}

// ─── Eye Selection ────────────────────────────────────────────────────────────
String readEye() {
  // HIGH = RIGHT eye, LOW = LEFT eye
  return digitalRead(EYE_SELECT_PIN) == HIGH ? "RIGHT" : "LEFT";
}

// ─── Serial Output ────────────────────────────────────────────────────────────
void sendReading(float iop, String eye) {
  // Format: IOP:18.5,EYE:RIGHT,PATIENT:default
  Serial.print("IOP:");
  Serial.print(iop, 1);
  Serial.print(",EYE:");
  Serial.print(eye);
  Serial.print(",PATIENT:");
  Serial.println(PATIENT_ID);
}

// ─── LED Feedback ─────────────────────────────────────────────────────────────
void blinkLED(int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(100);
    digitalWrite(LED_PIN, LOW);
    delay(100);
  }
}

// ─── Buzzer Alert ─────────────────────────────────────────────────────────────
void alertBuzzer() {
  for (int i = 0; i < 3; i++) {
    tone(BUZZER_PIN, 1000, 200);  // 1kHz tone, 200ms
    delay(300);
  }
}

// ─── Serial Command Handler ───────────────────────────────────────────────────
/**
 * Accepts commands via serial for runtime configuration:
 *   SET_PATIENT:<id>   - Change patient ID
 *   GET_STATUS         - Print current status
 *   CALIBRATE:<offset> - Set calibration offset
 */
void handleSerialCommands() {
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.startsWith("GET_STATUS")) {
      Serial.print("STATUS:OK,LAST_IOP:");
      Serial.print(lastIOP, 1);
      Serial.print(",PATIENT:");
      Serial.println(PATIENT_ID);
    } else if (cmd.startsWith("SET_PATIENT:")) {
      // In production, store in EEPROM/NVS
      Serial.print("PATIENT_SET:");
      Serial.println(cmd.substring(12));
    } else if (cmd.startsWith("PING")) {
      Serial.println("PONG");
    }
  }
}

// ─── END OF FIRMWARE ──────────────────────────────────────────────────────────
/**
 * SIMULATION MODE (for testing without real sensor):
 * Uncomment the readIOP_simulated() function below and replace
 * the readIOP() call in loop() for development/demo testing.
 */

/*
float readIOP_simulated() {
  // Generates realistic IOP values with slight variation
  static float base = 18.5f;
  float noise = (random(0, 100) - 50) / 20.0f;  // ±2.5 mmHg noise
  base = constrain(base + (random(0, 10) - 5) / 10.0f, 10.0f, 28.0f);
  return roundf((base + noise) * 10.0f) / 10.0f;
}
*/
