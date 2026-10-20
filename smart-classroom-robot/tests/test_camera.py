"""Phase 3 tests - needs a real webcam attached."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from camera import Camera, CameraError  # noqa: E402

fails = []


def ok(cond, label, detail=""):
    print(("OK   " if cond else "FAIL ") + label + ("  -- " + detail if detail else ""))
    if not cond:
        fails.append(label)


def main():
    print("=== Phase 3: camera ===\n")
    cam = Camera()
    if not cam.start():
        print("SKIP no webcam available: %s" % cam.last_error)
        return 0

    ok(True, "camera opens", "index %d" % cam.index)
    ok(cam.resolution[0] > 0, "reports a resolution", "%dx%d" % cam.resolution)

    good, frame = 0, None
    for _ in range(60):
        got, f = cam.read()
        if got:
            good += 1
            frame = f
    ok(good >= 55, "reads 60 frames reliably", "%d/60" % good)
    ok(cam.measured_fps > 5, "usable frame rate", "%.1f fps" % cam.measured_fps)
    ok(frame is not None and frame.shape[2] == 3, "frames are 3-channel BGR",
       str(frame.shape) if frame is not None else "none")

    cam.release()
    ok(not cam.opened, "release() closes it")
    cam.release()
    ok(True, "release() is safe twice")
    got, f = cam.read()
    ok(got is False and f is None, "read() after release fails cleanly", cam.last_error)

    bad = Camera(index=97)
    ok(bad.start() is False and bad.last_error, "bad index fails gracefully",
       bad.last_error[:60])
    bad.release()

    try:
        with Camera(index=97):
            pass
        ok(False, "context manager raises CameraError on a bad index")
    except CameraError:
        ok(True, "context manager raises CameraError on a bad index")

    print("\nFAILURES:", fails if fails else "none")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
