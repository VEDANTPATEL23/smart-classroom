"""Phase 4 tests - needs the YOLO weights (downloaded automatically)."""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config                       # noqa: E402
from detection import Detector      # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "person_sample.jpg")
fails = []


def ok(cond, label, detail=""):
    print(("OK   " if cond else "FAIL ") + label + ("  -- " + detail if detail else ""))
    if not cond:
        fails.append(label)


def main():
    print("=== Phase 4: detection ===\n")
    det = Detector()
    if not det.load():
        print("SKIP model unavailable: %s" % det.last_error)
        return 0

    ok(True, "model loads", det.model_path)
    ok("person" in det.supported_classes, "person class supported")
    ok("cell phone" in det.supported_classes, "cell phone class supported")

    if os.path.exists(SAMPLE):
        img = cv2.imread(SAMPLE)
        dets = det.detect(img)
        people = [d for d in dets if d["class_name"] == "person"]
        ok(len(people) >= 1, "finds a person in a real photograph",
           "%d found, best %.2f" % (len(people),
                                    max([d["confidence"] for d in people], default=0)))
        consistent = all(d["center_x"] == (d["x1"] + d["x2"]) // 2
                         and d["center_y"] == (d["y1"] + d["y2"]) // 2 for d in dets)
        ok(consistent, "centre matches the reported box")
        h, w = img.shape[:2]
        inside = all(0 <= d["x1"] <= w and 0 <= d["y2"] <= h for d in dets)
        ok(inside, "boxes lie inside the frame")
        required = {"class_name", "confidence", "x1", "y1", "x2", "y2",
                    "center_x", "center_y"}
        ok(all(required.issubset(d.keys()) for d in dets), "dict shape matches the spec")
        canvas = det.draw(img, dets)
        ok(canvas is not None and canvas.shape == img.shape, "draw() annotates a copy")
        ok(not np.array_equal(canvas, img), "draw() changed pixels")
    else:
        print("SKIP  no tests/person_sample.jpg to detect against")

    blank = np.full((480, 640, 3), 127, dtype=np.uint8)
    ok(det.detect(blank) == [], "blank frame finds nothing")
    ok(det.detect(None) == [], "None frame handled, not crashed")

    det.reset_cache()
    before = det.inference_count
    for _ in range(9):
        det.detect_cached(blank, every_n=3)
    ok(det.inference_count - before == 3, "detect_cached runs every 3rd frame",
       "%d inferences for 9 frames" % (det.inference_count - before))

    ok(det.average_inference_ms < 500, "inference is fast enough for live video",
       "%.0f ms/frame" % det.average_inference_ms)

    print("\nFAILURES:", fails if fails else "none")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
