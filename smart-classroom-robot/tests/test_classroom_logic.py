"""Phase 5 tests - pure logic, no camera and no serial port needed."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from classroom_logic import (ClassroomMonitor, STATUS_ALERT, STATUS_NORMAL,  # noqa: E402
                             STATUS_WARNING, ZONE_CENTER, ZONE_LEFT, ZONE_NONE,
                             ZONE_RIGHT)

W = 640
fails = []


def ok(cond, label, detail=""):
    print(("OK   " if cond else "FAIL ") + label + ("  -- " + detail if detail else ""))
    if not cond:
        fails.append(label)


def person(cx):
    return {"class_name": "person", "confidence": 0.9, "x1": cx - 20, "y1": 0,
            "x2": cx + 20, "y2": 100, "center_x": cx, "center_y": 50}


def phone(cx, conf=0.8):
    return {"class_name": "cell phone", "confidence": conf, "x1": cx - 10, "y1": 0,
            "x2": cx + 10, "y2": 40, "center_x": cx, "center_y": 20}


print("=== Phase 5: classroom logic ===\n")
print("-- zone boundaries (spec: <33% LEFT, 33-66% CENTER, >66% RIGHT) --")
z = ClassroomMonitor.zone_for
ok(z(0, W) == ZONE_LEFT, "x=0 -> LEFT")
ok(z(210, W) == ZONE_LEFT, "x=210 (32.8%) -> LEFT")
ok(z(212, W) == ZONE_CENTER, "x=212 (33.1%) -> CENTER")
ok(z(320, W) == ZONE_CENTER, "x=320 (50%) -> CENTER")
ok(z(422, W) == ZONE_CENTER, "x=422 (65.9%) -> CENTER")
ok(z(424, W) == ZONE_RIGHT, "x=424 (66.3%) -> RIGHT")
ok(z(639, W) == ZONE_RIGHT, "x=639 -> RIGHT")
ok(z(100, 0) == ZONE_NONE, "zero width -> NONE, no divide-by-zero")

print("\n-- counting --")
m = ClassroomMonitor()
s = m.update([person(100), person(320), person(500), phone(500)], W)
ok(s.students_present == 3, "counts 3 students", str(s.students_present))
ok(s.phones_detected == 1, "counts 1 phone", str(s.phones_detected))
ok(s.zone_counts == {ZONE_LEFT: 1, ZONE_CENTER: 1, ZONE_RIGHT: 1},
   "spreads students across zones", str(s.zone_counts))
s = m.update([person(100), person(110), person(500)], W)
ok(s.busiest_zone == ZONE_LEFT, "busiest zone is LEFT with 2 of 3", str(s.zone_counts))
s = m.update([], W)
ok(s.students_present == 0 and s.busiest_zone == ZONE_NONE, "empty frame -> zero, NONE")

print("\n-- WARNING needs confirmation (no single-frame flapping) --")
m = ClassroomMonitor(warning_frames=3, normal_frames=4, alert_events=3, alert_window=60)
s = m.update([phone(500)], W)
ok(s.classroom_status == STATUS_NORMAL, "1 phone frame is not enough", s.classroom_status)
s = m.update([phone(500)], W)
ok(s.classroom_status == STATUS_NORMAL, "2 phone frames is not enough", s.classroom_status)
s = m.update([phone(500)], W)
ok(s.classroom_status == STATUS_WARNING, "3rd consecutive frame confirms WARNING",
   s.classroom_status)
ok(s.detected_zone == ZONE_RIGHT, "zone is where the phone was", s.detected_zone)
ok(s.status_changed is True, "status_changed flags the transition")

print("\n-- clearing back to NORMAL is slower still --")
for i in range(3):
    s = m.update([], W)
    ok(s.classroom_status == STATUS_WARNING, "still WARNING after %d clean frame(s)" % (i + 1))
s = m.update([], W)
ok(s.classroom_status == STATUS_NORMAL, "4th clean frame clears to NORMAL", s.classroom_status)
ok(s.detected_zone == ZONE_NONE, "zone cleared with the status")

print("\n-- one bad frame cannot trigger anything --")
m2 = ClassroomMonitor(warning_frames=3, normal_frames=4)
for pattern in ([phone(100)], [], [phone(100)], [], [phone(100)], []):
    s = m2.update(pattern, W)
ok(s.classroom_status == STATUS_NORMAL, "alternating noise never reaches WARNING",
   s.classroom_status)

print("\n-- ALERT after repeated events inside the window --")
m3 = ClassroomMonitor(warning_frames=2, normal_frames=2, alert_events=3, alert_window=60)
t = 1000.0
statuses = []
for burst in range(3):
    for _ in range(2):
        s = m3.update([phone(320)], W, now=t); t += 1
    statuses.append(s.classroom_status)
    for _ in range(2):
        s = m3.update([], W, now=t); t += 1
ok(statuses == [STATUS_WARNING, STATUS_WARNING, STATUS_ALERT],
   "3rd event inside the window escalates to ALERT", str(statuses))

print("\n-- old events expire, so ALERT is not permanent --")
m4 = ClassroomMonitor(warning_frames=2, normal_frames=2, alert_events=3, alert_window=10)
t = 0.0
for burst in range(3):
    for _ in range(2):
        s = m4.update([phone(320)], W, now=t); t += 1
    for _ in range(2):
        s = m4.update([], W, now=t); t += 1
    t += 30                      # wait longer than the window between bursts
ok(s.classroom_status != STATUS_ALERT,
   "events spaced beyond the window never stack into ALERT", s.classroom_status)
ok(s.event_count <= 1, "expired events were dropped", "event_count=%d" % s.event_count)

print("\n-- the phone with the highest confidence wins the zone --")
m5 = ClassroomMonitor(warning_frames=1)
s = m5.update([phone(100, conf=0.5), phone(600, conf=0.95)], W)
ok(s.detected_zone == ZONE_RIGHT, "follows the 0.95 phone on the right, not the 0.5 one",
   s.detected_zone)

print("\n-- misc --")
ok("students_present" in ClassroomMonitor().update([], W).as_dict(), "as_dict() exports state")
m6 = ClassroomMonitor(warning_frames=1)
m6.update([phone(320)], W)
m6.reset()
ok(m6.status == STATUS_NORMAL and m6.zone == ZONE_NONE, "reset() clears the machine")

print()
print("FAILURES:", fails if fails else "none")
sys.exit(1 if fails else 0)
