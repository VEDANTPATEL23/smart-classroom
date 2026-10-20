"""Every tunable value for the Smart Classroom Assistant Robot.

Edit this file rather than hunting through the code. Anything you change here is
picked up the next time you start the app.
"""

# ----------------------------------------------------------------- Phase 2: serial
# Leave SERIAL_PORT as "" to auto-detect the Arduino by its USB vendor id.
# Set it explicitly (e.g. "COM5") if auto-detection picks the wrong device.
SERIAL_PORT = ""
BAUD_RATE = 9600

# Seconds to wait for the board to finish its reset and print READY after the
# port opens. An Uno reboots when the serial port is opened; talking to it before
# the bootloader hands over just loses the first command.
ARDUINO_BOOT_WAIT = 2.5

# Seconds to wait for a reply line before giving up on a command.
SERIAL_TIMEOUT = 1.0
# ASSIST drives a whole pick-and-place sequence, so it needs far longer.
ASSIST_TIMEOUT = 25.0

# With no board attached the controller runs a built-in simulated Arduino that
# speaks the identical protocol, so the dashboard and integration still work.
# True  = always simulate, never touch a real port
# False = always use a real port, fail loudly if it is missing
# "auto" = use a real board when one is found, otherwise simulate
SIMULATE_ARDUINO = "auto"

# ----------------------------------------------------------------- Phase 3: camera
CAMERA_INDEX = 1
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
# Frames to read and throw away when opening, so auto-exposure can settle.
CAMERA_WARMUP_FRAMES = 15

# -------------------------------------------------------------- Phase 4: detection
# yolov8n is the smallest COCO model - the right choice on a CPU-only laptop.
YOLO_MODEL = "yolov8n.pt"
YOLO_CONFIDENCE = 0.45
# Inference resolution. Smaller = faster and blinder. 320 or 416 suit a CPU.
YOLO_IMAGE_SIZE = 416
# COCO class names this project reacts to.
CLASS_PERSON = "person"
CLASS_PHONE = "cell phone"
DETECT_CLASSES = (CLASS_PERSON, CLASS_PHONE)
# Run YOLO on every Nth frame; the frames in between still display, they just
# reuse the previous boxes. 1 = detect on every frame.
# Measured on this machine: 29 ms/inference (~35/sec) against a 16.7 fps camera,
# so every frame keeps up comfortably. Raise to 2 or 3 on a slower laptop.
DETECT_EVERY_N_FRAMES = 1

# ------------------------------------------------------------------ Phase 5: logic
# Zone boundaries as a fraction of frame width.
ZONE_LEFT_EDGE = 0.33
ZONE_RIGHT_EDGE = 0.66

# A phone must be seen in this many consecutive detection passes before the
# status changes, so one bad frame does not flap the arm.
WARNING_CONFIRM_FRAMES = 3
# Consecutive clean passes needed to fall back to NORMAL.
NORMAL_CONFIRM_FRAMES = 12
# Separate WARNING events within ALERT_WINDOW_SECONDS to reach ALERT.
ALERT_EVENT_COUNT = 3
ALERT_WINDOW_SECONDS = 60.0

# ------------------------------------------------------------- Phase 7: integration
# Never send the arm two commands closer together than this (seconds). Servos
# need time to arrive, and a command queue that outruns them looks like chaos.
COMMAND_COOLDOWN_SECONDS = 4.0
# Automatically point the arm at the zone where a phone was seen.
AUTO_POINT_AT_ZONE = True

# ------------------------------------------------------------------ Phase 6: UI
WINDOW_TITLE = "Smart Classroom Assistant Robot"
UI_REFRESH_MS = 30
VIDEO_DISPLAY_WIDTH = 640
