"""Phase 0 - verify the environment before any real code is written.

    python check_setup.py                 # run every check
    python check_setup.py --camera 1      # try a different webcam index
    python check_setup.py --show          # also open a live preview window
    python check_setup.py --skip-yolo     # skip the slow model import

Exit code is 0 only when Python, the packages and the webcam are all working.
A missing Arduino is reported but does NOT fail the run - you may not have it
plugged in yet.
"""
import argparse
import os
import platform
import sys

WARMUP_FRAMES = 15

PASS = "  [ OK ]  "
FAIL = "  [FAIL]  "
WARN = "  [WARN]  "

results = []


def record(name, good, detail=""):
    tag = PASS if good else FAIL
    print(tag + name + (("  - " + detail) if detail else ""))
    results.append((name, good))
    return good


def note(name, detail=""):
    print(WARN + name + (("  - " + detail) if detail else ""))


def section(title):
    print("\n" + title)
    print("-" * len(title))


# ------------------------------------------------------------------ 1. python

def check_python():
    section("1. Python")
    v = sys.version_info
    record("Python %d.%d.%d" % (v.major, v.minor, v.micro), v >= (3, 9),
           platform.platform())
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if in_venv:
        record("running inside the virtual environment", True, sys.prefix)
    else:
        note("not running inside venv",
             r"use venv\Scripts\python.exe so packages stay isolated")


# ---------------------------------------------------------------- 2. packages

def check_packages(skip_yolo):
    section("2. Packages")

    try:
        import numpy
        record("numpy", True, numpy.__version__)
    except Exception as exc:
        record("numpy", False, str(exc))

    try:
        import cv2
        record("opencv-python", True, cv2.__version__)
    except Exception as exc:
        record("opencv-python", False, str(exc))

    try:
        import serial
        import serial.tools.list_ports  # noqa: F401
        record("pyserial", True, serial.__version__)
    except Exception as exc:
        record("pyserial", False, str(exc))

    if skip_yolo:
        note("ultralytics", "skipped with --skip-yolo")
        return
    try:
        import ultralytics
        record("ultralytics", True, ultralytics.__version__)
        import torch
        record("torch", True, torch.__version__ +
               ("  (CUDA available)" if torch.cuda.is_available() else "  (CPU)"))
    except Exception as exc:
        record("ultralytics / torch", False, str(exc))


# ------------------------------------------------------------------ 3. camera

def check_camera(index, show):
    section("3. Webcam")
    try:
        import cv2
    except Exception:
        record("webcam", False, "opencv is not importable, cannot test")
        return

    # CAP_DSHOW avoids the very slow MSMF backend start-up on Windows
    backend = cv2.CAP_DSHOW if os.name == "nt" else 0
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        record("webcam opens at index %d" % index, False,
               "try --camera 1, close Teams/Zoom, and check Windows camera privacy settings")
        return

    # The first frames after opening are usually underexposed because auto-exposure
    # and auto-white-balance have not settled. Throw a few away before judging.
    frame = None
    for _ in range(WARMUP_FRAMES):
        ok, f = cap.read()
        if ok and f is not None:
            frame = f
    if frame is None:
        cap.release()
        record("webcam returns a frame", False, "device opened but delivered no image")
        return

    h, w = frame.shape[:2]
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    fps_text = "%.0f fps" % fps if fps > 0 else "fps not reported by the driver"
    record("webcam opens at index %d" % index, True, "%dx%d, %s" % (w, h, fps_text))

    # A frame this dark will cost you detections in Phase 4, so say so plainly.
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    if brightness < 40:
        note("the picture is very dark (mean %.0f/255)" % brightness,
             "turn a light on or open the blinds - YOLO loses people in the dark")
    elif brightness > 215:
        note("the picture is blown out (mean %.0f/255)" % brightness,
             "point the camera away from a window or bright lamp")
    else:
        record("exposure looks usable", True, "mean brightness %.0f/255" % brightness)

    # a still proves the pipeline end to end and gives you a Phase 0 screenshot
    os.makedirs("screenshots", exist_ok=True)
    out = os.path.join("screenshots", "phase0_camera.png")
    cv2.imwrite(out, frame)
    record("saved a test still", os.path.exists(out), out)

    if show:
        print("       preview open - press q to close")
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            cv2.imshow("Phase 0 - webcam test (press q)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        cv2.destroyAllWindows()

    cap.release()


# ----------------------------------------------------------------- 4. arduino

# USB vendor ids that mean "probably an Arduino"
KNOWN_VIDS = {
    0x2341: "Arduino",
    0x2A03: "Arduino (.org)",
    0x1A86: "CH340 clone",
    0x0403: "FTDI",
    0x10C4: "CP210x",
    0x1B4F: "SparkFun",
}


def check_arduino():
    section("4. Arduino / serial ports")
    try:
        from serial.tools import list_ports
    except Exception:
        record("serial ports", False, "pyserial is not importable")
        return

    ports = list(list_ports.comports())
    if not ports:
        note("no serial ports found",
             "plug the Arduino in over USB, or install the CH340/CP210x driver for a clone")
        print("       (Phase 0 still passes - the Arduino is only needed from Phase 1)")
        return

    print("       %d port(s):" % len(ports))
    likely = []
    for p in ports:
        vid = p.vid
        tag = KNOWN_VIDS.get(vid)
        marker = "  <-- likely Arduino (%s)" % tag if tag else ""
        if tag:
            likely.append(p.device)
        print("         %-8s %s%s" % (p.device, p.description, marker))

    if likely:
        record("Arduino detected", True, ", ".join(likely))
        print("\n       Put this in config.py in Phase 2:  SERIAL_PORT = \"%s\"" % likely[0])
    else:
        note("no obviously-Arduino port",
             "if one of the ports above is your board, use it anyway in Phase 2")


# --------------------------------------------------------------------- runner

def main():
    ap = argparse.ArgumentParser(description="Phase 0 environment check.")
    ap.add_argument("--camera", type=int, default=0, help="webcam index (default 0)")
    ap.add_argument("--show", action="store_true", help="open a live preview window")
    ap.add_argument("--skip-yolo", action="store_true", help="skip the slow ultralytics import")
    args = ap.parse_args()

    print("=" * 62)
    print(" Smart Classroom Assistant Robot - Phase 0 environment check")
    print("=" * 62)

    check_python()
    check_packages(args.skip_yolo)
    check_camera(args.camera, args.show)
    check_arduino()

    section("Summary")
    failed = [n for n, good in results if not good]
    for name, good in results:
        print(("  PASS  " if good else "  FAIL  ") + name)
    if failed:
        print("\n%d check(s) failed. Fix these before Phase 1:" % len(failed))
        for name in failed:
            print("  - " + name)
        return 1
    print("\nEnvironment is ready. Phase 0 complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
