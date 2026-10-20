/*
 * Smart Classroom Assistant Robot - Arduino Uno node
 * --------------------------------------------------
 * Drives a 4-DOF arm (base / shoulder / elbow / gripper) from newline-terminated
 * text commands arriving over USB serial, and answers every command so the Python
 * side can tell success from silence.
 *
 * Protocol (9600 baud, "\n" terminated, case-insensitive):
 *   PING              -> PONG
 *   STATUS            -> STATUS base,shoulder,elbow,gripper
 *   HOME LEFT CENTER RIGHT WARNING OPEN CLOSE PICK
 *                     -> OK <NAME>
 *   ASSIST            -> runs the pick-and-place sequence, then OK ASSIST
 *   NORMAL WARN_LED ALERT
 *                     -> OK <NAME>          (indicator only, arm does not move)
 *   SET <joint> <deg> -> OK SET <joint> <deg>   calibration jog, e.g. SET SHOULDER 95
 *   SPEED <ms>        -> OK SPEED <ms>          step delay, 5..60
 *   anything else     -> ERR UNKNOWN <text>
 *
 * On reset the arm moves to HOME before accepting commands, and prints READY.
 *
 * SAFETY
 *   Every joint has a hard min/max below; angles are clamped to them, so a bad
 *   command cannot drive a horn into the frame. Set these to YOUR arm before
 *   powering the servos - the defaults are conservative guesses, not measurements.
 *   Power four SG90s from a separate 5V supply (they can pull ~2A stalled) and
 *   tie its ground to the Arduino ground. USB alone will brown the board out.
 */

#include <Servo.h>

// ------------------------------------------------------------------ wiring
const uint8_t PIN_BASE     = 9;
const uint8_t PIN_SHOULDER = 10;
const uint8_t PIN_ELBOW    = 11;
const uint8_t PIN_GRIPPER  = 6;

// Phase 9 indicators - leave unconnected if you have none
const uint8_t PIN_LED_GREEN  = 2;
const uint8_t PIN_LED_YELLOW = 3;
const uint8_t PIN_LED_RED    = 4;
const uint8_t PIN_BUZZER     = 5;

// --------------------------------------------------------------- joint model
enum JointId { BASE = 0, SHOULDER = 1, ELBOW = 2, GRIPPER = 3, JOINT_COUNT = 4 };

struct Joint {
  Servo   servo;
  uint8_t pin;
  uint8_t minAngle;   // hard mechanical limit - tune to your build
  uint8_t maxAngle;
  uint8_t current;
  const char *name;
};

Joint joints[JOINT_COUNT] = {
  { Servo(), PIN_BASE,      10, 170,  90, "BASE"     },
  { Servo(), PIN_SHOULDER,  30, 150,  90, "SHOULDER" },
  { Servo(), PIN_ELBOW,     20, 160,  90, "ELBOW"    },
  { Servo(), PIN_GRIPPER,   35, 110,  35, "GRIPPER"  }
};

// -------------------------------------------------------------- preset poses
// order: base, shoulder, elbow, gripper   (255 = "leave this joint alone")
const uint8_t KEEP = 255;

struct NamedPose { const char *name; uint8_t a[JOINT_COUNT]; };

const NamedPose PRESETS[] = {
  { "HOME",    {  90,  90,  90,  35 } },   // upright, gripper open
  { "LEFT",    { 150,  80, 100,  35 } },   // point at the left third of the room
  { "CENTER",  {  90,  75, 105,  35 } },
  { "RIGHT",   {  30,  80, 100,  35 } },
  { "WARNING", {  90,  50, 140,  35 } },   // raised "attention" pose
  { "OPEN",    { KEEP, KEEP, KEEP,  35 } },
  { "CLOSE",   { KEEP, KEEP, KEEP, 100 } },
  { "PICK",    {  90, 130,  60,  35 } }    // reach down to the table
};
const uint8_t PRESET_COUNT = sizeof(PRESETS) / sizeof(PRESETS[0]);

// ----------------------------------------------------------------- movement
uint8_t stepDelayMs = 15;          // larger = slower, gentler
const uint8_t STEP_SIZE = 1;       // degrees per step

uint8_t clampAngle(const Joint &j, int angle) {
  if (angle < j.minAngle) return j.minAngle;
  if (angle > j.maxAngle) return j.maxAngle;
  return (uint8_t)angle;
}

/* Move every joint toward its target one degree at a time so the arm eases into
 * the pose instead of slamming. KEEP leaves a joint where it is. */
void moveTo(const uint8_t target[JOINT_COUNT]) {
  uint8_t goal[JOINT_COUNT];
  for (uint8_t i = 0; i < JOINT_COUNT; i++) {
    goal[i] = (target[i] == KEEP) ? joints[i].current
                                  : clampAngle(joints[i], target[i]);
  }

  bool moving = true;
  while (moving) {
    moving = false;
    for (uint8_t i = 0; i < JOINT_COUNT; i++) {
      Joint &j = joints[i];
      int diff = (int)goal[i] - (int)j.current;
      if (diff == 0) continue;
      if (abs(diff) <= STEP_SIZE) {
        j.current = goal[i];                     // last step lands exactly
      } else {
        j.current = (uint8_t)((int)j.current + (diff > 0 ? STEP_SIZE : -STEP_SIZE));
      }
      j.servo.write(j.current);
      moving = true;
    }
    delay(stepDelayMs);
  }
}

int findPreset(const String &name) {
  for (uint8_t i = 0; i < PRESET_COUNT; i++) {
    if (name.equals(PRESETS[i].name)) return i;
  }
  return -1;
}

int findJoint(const String &name) {
  for (uint8_t i = 0; i < JOINT_COUNT; i++) {
    if (name.equals(joints[i].name)) return i;
  }
  return -1;
}

// --------------------------------------------------------------- indicators
void setIndicators(bool green, bool yellow, bool red) {
  digitalWrite(PIN_LED_GREEN,  green  ? HIGH : LOW);
  digitalWrite(PIN_LED_YELLOW, yellow ? HIGH : LOW);
  digitalWrite(PIN_LED_RED,    red    ? HIGH : LOW);
}

void beep(uint16_t ms, uint8_t times) {
  for (uint8_t i = 0; i < times; i++) {
    tone(PIN_BUZZER, 2000, ms);
    delay(ms + 60);
  }
  noTone(PIN_BUZZER);
}

// ----------------------------------------------------------- assist routine
/* Phase 8: fixed-position marker/eraser fetch. No inverse kinematics - every
 * waypoint is a preset, so the arm can only ever visit angles we vetted. */
void runAssist() {
  moveTo(PRESETS[findPreset("HOME")].a);
  moveTo(PRESETS[findPreset("OPEN")].a);
  moveTo(PRESETS[findPreset("PICK")].a);      // reach down to the marker
  delay(300);
  moveTo(PRESETS[findPreset("CLOSE")].a);     // grip it
  delay(300);
  moveTo(PRESETS[findPreset("HOME")].a);      // lift clear of the table
  moveTo(PRESETS[findPreset("CENTER")].a);    // present it to the teacher
  delay(500);
  moveTo(PRESETS[findPreset("OPEN")].a);      // release
  delay(300);
  moveTo(PRESETS[findPreset("HOME")].a);
}

// ------------------------------------------------------------ command parser
void reportStatus() {
  Serial.print(F("STATUS "));
  for (uint8_t i = 0; i < JOINT_COUNT; i++) {
    Serial.print(joints[i].current);
    if (i < JOINT_COUNT - 1) Serial.print(',');
  }
  Serial.println();
}

void handleCommand(String line) {
  line.trim();
  if (line.length() == 0) return;
  line.toUpperCase();

  // split off the first word
  int sp = line.indexOf(' ');
  String verb = (sp < 0) ? line : line.substring(0, sp);
  String rest = (sp < 0) ? ""   : line.substring(sp + 1);
  rest.trim();

  if (verb == "PING")   { Serial.println(F("PONG")); return; }
  if (verb == "STATUS") { reportStatus(); return; }

  if (verb == "SPEED") {
    int ms = rest.toInt();
    if (ms < 5 || ms > 60) { Serial.println(F("ERR SPEED 5..60")); return; }
    stepDelayMs = (uint8_t)ms;
    Serial.print(F("OK SPEED ")); Serial.println(ms);
    return;
  }

  if (verb == "SET") {                       // calibration jog: SET ELBOW 120
    int sp2 = rest.indexOf(' ');
    if (sp2 < 0) { Serial.println(F("ERR SET <JOINT> <ANGLE>")); return; }
    String jname = rest.substring(0, sp2);
    int angle = rest.substring(sp2 + 1).toInt();
    int idx = findJoint(jname);
    if (idx < 0) { Serial.print(F("ERR SET UNKNOWN JOINT ")); Serial.println(jname); return; }
    uint8_t safe = clampAngle(joints[idx], angle);
    uint8_t target[JOINT_COUNT] = { KEEP, KEEP, KEEP, KEEP };
    target[idx] = safe;
    moveTo(target);
    Serial.print(F("OK SET ")); Serial.print(joints[idx].name);
    Serial.print(' '); Serial.println(safe);
    return;
  }

  if (verb == "ASSIST") { runAssist(); Serial.println(F("OK ASSIST")); return; }

  // ---- indicator-only commands (Phase 9). The arm does not move for these.
  if (verb == "NORMAL")  { setIndicators(true, false, false); Serial.println(F("OK NORMAL")); return; }
  if (verb == "WARN_LED"){ setIndicators(false, true, false); beep(80, 1); Serial.println(F("OK WARN_LED")); return; }
  if (verb == "ALERT")   { setIndicators(false, false, true); beep(160, 2); Serial.println(F("OK ALERT")); return; }

  // ---- preset poses
  int p = findPreset(verb);
  if (p >= 0) {
    moveTo(PRESETS[p].a);
    if (verb == "WARNING") { setIndicators(false, true, false); beep(80, 1); }
    Serial.print(F("OK ")); Serial.println(PRESETS[p].name);
    return;
  }

  Serial.print(F("ERR UNKNOWN ")); Serial.println(verb);
}

// ------------------------------------------------------------------- sketch
void setup() {
  Serial.begin(9600);

  pinMode(PIN_LED_GREEN,  OUTPUT);
  pinMode(PIN_LED_YELLOW, OUTPUT);
  pinMode(PIN_LED_RED,    OUTPUT);
  pinMode(PIN_BUZZER,     OUTPUT);
  setIndicators(false, false, false);

  for (uint8_t i = 0; i < JOINT_COUNT; i++) {
    joints[i].servo.attach(joints[i].pin);
    joints[i].servo.write(joints[i].current);   // hold the declared start angle
  }
  delay(500);                                   // let the horns settle

  moveTo(PRESETS[findPreset("HOME")].a);
  setIndicators(true, false, false);

  Serial.println(F("READY classroom_robot v1"));
  reportStatus();
}

void loop() {
  static String buffer = "";
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (buffer.length() > 0) { handleCommand(buffer); buffer = ""; }
    } else if (buffer.length() < 40) {
      buffer += c;
    }
  }
}
