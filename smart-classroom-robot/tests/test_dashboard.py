"""Phase 6 tests - drive the real Tkinter window with fake hardware.

The window is withdrawn (never shown) and pumped by hand with update(), so this
runs unattended while still exercising the genuine widgets, the capture thread,
the arm queue and the shutdown path.
"""
import os
import sys
import threading
import time

import numpy as np

if os.name == "nt":                       # app.py does this too; layout depends on it
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config                                              # noqa: E402
from classroom_logic import ClassroomMonitor, STATUS_WARNING  # noqa: E402
from controller import ArduinoController                   # noqa: E402
from ui.dashboard import Dashboard                         # noqa: E402

fails = []


def ok(cond, label, detail=""):
    print(("OK   " if cond else "FAIL ") + label + ("  -- " + detail if detail else ""))
    if not cond:
        fails.append(label)


class FakeCamera:
    """Same surface as camera.Camera, but generates frames instantly."""

    def __init__(self):
        self.opened = False
        self.last_error = ""
        self.released = False
        self.reads = 0

    def start(self):
        self.opened = True
        return True

    def read(self):
        self.reads += 1
        frame = np.full((480, 640, 3), 60, dtype=np.uint8)
        return True, frame

    def release(self):
        self.opened = False
        self.released = True


class FakeDetector:
    """Returns whatever detections the test scripts, with no model involved."""

    def __init__(self):
        self.ready = True
        self.last_error = ""
        self.supported_classes = ("person", "cell phone")
        self.scripted = []
        self.calls = 0

    def load(self):
        return True

    def reset_cache(self):
        self.calls = 0

    def detect_cached(self, frame, every_n=None):
        self.calls += 1
        return list(self.scripted)

    @staticmethod
    def draw(frame, detections, zone_lines=True):
        return frame


def person(cx):
    return {"class_name": "person", "confidence": 0.9, "x1": cx - 20, "y1": 0,
            "x2": cx + 20, "y2": 100, "center_x": cx, "center_y": 50}


def phone(cx):
    return {"class_name": "cell phone", "confidence": 0.9, "x1": cx - 10, "y1": 0,
            "x2": cx + 10, "y2": 40, "center_x": cx, "center_y": 20}


def pump(app, seconds=1.0):
    """Run the Tk event loop by hand for a while."""
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.01)


def main():
    print("=== Phase 6/7: dashboard with fake hardware ===\n")

    cam = FakeCamera()
    det = FakeDetector()
    arm = ArduinoController(simulate=True)
    ok(arm.connect(), "simulated arm connects", arm.status_text)
    monitor = ClassroomMonitor(warning_frames=2, normal_frames=3)

    app = Dashboard(cam, det, arm, monitor)
    ok(True, "dashboard constructs without error")

    # The window has to be mapped for a moment to check that nothing overflows
    # the default geometry. At 150% display scaling the side column previously
    # pushed two readouts and all five buttons off the bottom.
    pump(app, 0.5)                                   # let Windows actually map it
    app.update_idletasks()
    ok(all(b.winfo_ismapped() for b in app.buttons.values()),
       "all 5 buttons fit inside the default window",
       str({k: bool(v.winfo_ismapped()) for k, v in app.buttons.items()}))
    ok(all(v.winfo_ismapped() for v in app.value_labels.values()),
       "all 5 readouts fit inside the default window",
       str({k: bool(v.winfo_ismapped()) for k, v in app.value_labels.items()}))
    app.withdraw()                                   # hide it for the rest of the run

    for key in ("students_present", "phones_detected", "classroom_status",
                "detected_zone", "arduino"):
        ok(key in app.value_labels, "readout present: %s" % key)
    for key in ("start", "stop", "home", "assist", "warning"):
        ok(key in app.buttons, "button present: %s" % key.upper())

    ok(str(app.buttons["stop"]["state"]) == "disabled", "STOP starts disabled")
    pump(app, 0.2)
    ok(app.value_labels["arduino"]["text"] == "SIMULATED",
       "Arduino readout reflects reality", app.value_labels["arduino"]["text"])

    # ---- monitoring with three people in shot
    det.scripted = [person(100), person(320), person(500)]
    threads_before = threading.active_count()
    app.start_monitoring()
    pump(app, 1.2)
    ok(app._monitoring, "monitoring started")
    ok(str(app.buttons["start"]["state"]) == "disabled", "START disables while running")
    ok(str(app.buttons["stop"]["state"]) == "normal", "STOP enables while running")
    ok(cam.reads > 5, "capture thread is reading frames", "%d reads" % cam.reads)
    ok(app.value_labels["students_present"]["text"] == "3",
       "student count reaches the UI", app.value_labels["students_present"]["text"])
    ok(app._photo is not None, "a video frame was painted into the window")
    ok(threading.active_count() > threads_before, "capture thread is alive")

    # ---- a phone appears: status must escalate and the arm must be commanded
    sent_before = len(arm._link.history)
    det.scripted = [person(100), phone(560)]
    pump(app, 1.5)
    ok(app.value_labels["phones_detected"]["text"] == "1",
       "phone count reaches the UI", app.value_labels["phones_detected"]["text"])
    ok(app.value_labels["classroom_status"]["text"] in ("WARNING", "ALERT"),
       "status escalates on a confirmed phone",
       app.value_labels["classroom_status"]["text"])
    ok(app.value_labels["detected_zone"]["text"] == "RIGHT",
       "zone points at the phone's third of the room",
       app.value_labels["detected_zone"]["text"])
    time.sleep(0.4)
    sent = arm._link.history[sent_before:]
    ok(any(c.startswith("WARNING") or c.startswith("WARN_LED") for c in sent),
       "detection actually reached the arm over the wire", str(sent))

    # ---- manual buttons
    before = len(arm._link.history)
    app.cmd_home()
    pump(app, 0.6)
    ok(any(c == "HOME" for c in arm._link.history[before:]),
       "HOME button sends HOME", str(arm._link.history[before:]))

    before = len(arm._link.history)
    app.cmd_assist()
    pump(app, 1.0)
    ok("ASSIST" in arm._link.history[before:], "ASSIST button sends ASSIST")
    ok(app._monitoring, "the window stayed responsive during ASSIST")

    # ---- stop and shut down
    app.stop_monitoring()
    ok(not app._monitoring, "STOP halts the capture loop")
    ok(str(app.buttons["start"]["state"]) == "normal", "START re-enables after STOP")

    app.on_close()
    time.sleep(0.4)
    ok(cam.released, "camera released on close")
    ok(not arm.connected, "serial link closed on close")
    ok(app._shutdown.is_set(), "worker threads told to stop")
    alive = [t.name for t in threading.enumerate() if t.name in ("capture", "arm")]
    ok(not alive, "no worker thread left running", str(alive) if alive else "none")

    print()
    print("FAILURES:", fails if fails else "none")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
