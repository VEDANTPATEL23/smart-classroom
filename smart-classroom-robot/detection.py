"""Phase 4 - object detection with a pretrained YOLO model.

No custom training and no hardware knowledge lives here. The detector turns a
frame into a list of plain dictionaries; deciding what those mean is Phase 5's
job, and moving the arm is the controller's.

    from detection import Detector
    det = Detector(); det.load()
    for d in det.detect(frame):
        print(d["class_name"], d["confidence"], d["center_x"])

HONEST SCOPE: this is the COCO-pretrained yolov8n model. It detects `person` and
`cell phone`. It does NOT detect raised hands, attention, emotion or discipline,
and nothing in this project claims otherwise.
"""
import logging
import os
import shutil
import time

import cv2

import config

log = logging.getLogger("detection")

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

# box colours per class, BGR
COLOURS = {
    config.CLASS_PERSON: (80, 220, 120),
    config.CLASS_PHONE: (60, 90, 240),
}
DEFAULT_COLOUR = (200, 200, 200)


class DetectorError(Exception):
    """Raised when the model cannot be loaded."""


class Detector:
    """Thin wrapper over Ultralytics YOLO returning structured detections."""

    def __init__(self, model_path=None, confidence=None, imgsz=None, classes=None):
        self.model_path = model_path or config.YOLO_MODEL
        self.confidence = config.YOLO_CONFIDENCE if confidence is None else confidence
        self.imgsz = config.YOLO_IMAGE_SIZE if imgsz is None else imgsz
        self.wanted = tuple(classes) if classes is not None else tuple(config.DETECT_CLASSES)

        self.model = None
        self.ready = False
        self.last_error = ""
        self.class_names = {}

        self.inference_count = 0
        self.total_inference_time = 0.0

        # frame-skipping state for detect_cached()
        self._frame_index = 0
        self._cached = []

    # ------------------------------------------------------------------ load
    def _resolve_weights(self):
        """Prefer models/<name>.pt; let Ultralytics fetch it there on first run."""
        if os.path.dirname(self.model_path):
            return self.model_path
        local = os.path.join(MODELS_DIR, self.model_path)
        if os.path.exists(local):
            return local
        return self.model_path            # ultralytics downloads it

    def load(self):
        """Import torch/ultralytics and load the weights. Slow - call once."""
        if self.ready:
            return True
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            self.last_error = "ultralytics is not installed: %s" % exc
            log.error(self.last_error)
            return False

        weights = self._resolve_weights()
        try:
            log.info("loading %s ...", weights)
            self.model = YOLO(weights)
        except Exception as exc:
            self.last_error = "could not load %s: %s" % (weights, exc)
            log.error(self.last_error)
            return False

        # If Ultralytics downloaded into the working directory, tuck it away.
        if not os.path.dirname(weights) and os.path.exists(weights):
            os.makedirs(MODELS_DIR, exist_ok=True)
            target = os.path.join(MODELS_DIR, os.path.basename(weights))
            if not os.path.exists(target):
                try:
                    shutil.move(weights, target)
                    log.info("moved weights into %s", target)
                except Exception:
                    pass

        self.class_names = dict(self.model.names)
        missing = [c for c in self.wanted if c not in self.class_names.values()]
        if missing:
            log.warning("model cannot detect %s - those will never be reported",
                        ", ".join(missing))

        self.ready = True
        self.last_error = ""

        # The very first inference pays for lazy kernel/graph setup - about 1.2s
        # against ~30ms steady state. Spend it here, at load time, so the first
        # live frame is not the one that stalls.
        try:
            import numpy as np
            warm = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
            started = time.time()
            self.model.predict(warm, imgsz=self.imgsz, conf=self.confidence,
                               verbose=False, device="cpu")
            log.info("warm-up inference took %.0f ms", (time.time() - started) * 1000)
        except Exception as exc:
            log.debug("warm-up skipped: %s", exc)

        return True

    @property
    def supported_classes(self):
        """Which of the classes we care about this model can actually detect."""
        available = set(self.class_names.values())
        return tuple(c for c in self.wanted if c in available)

    # --------------------------------------------------------------- detect
    def detect(self, frame):
        """Run YOLO on one frame. Returns a list of detection dicts (never None)."""
        if not self.ready or frame is None:
            return []

        started = time.time()
        try:
            results = self.model.predict(
                frame, imgsz=self.imgsz, conf=self.confidence,
                verbose=False, device="cpu",
            )
        except Exception as exc:
            self.last_error = "inference failed: %s" % exc
            log.error(self.last_error)
            return []

        self.inference_count += 1
        self.total_inference_time += time.time() - started

        detections = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls[0])
                name = self.class_names.get(cls_id, str(cls_id))
                if self.wanted and name not in self.wanted:
                    continue
                # Round the corners FIRST, then derive the centre from them, so
                # the dict is self-consistent: a caller that recomputes the centre
                # from x1/x2 gets the same number this reports.
                x1, y1, x2, y2 = (int(round(float(v))) for v in box.xyxy[0])
                detections.append({
                    "class_name": name,
                    "confidence": round(float(box.conf[0]), 3),
                    "x1": x1, "y1": y1,
                    "x2": x2, "y2": y2,
                    "center_x": (x1 + x2) // 2,
                    "center_y": (y1 + y2) // 2,
                })
        return detections

    def detect_cached(self, frame, every_n=None):
        """Detect on every Nth frame, reusing the previous boxes in between.

        On a CPU-only laptop yolov8n costs far more than a frame interval, so
        detecting on every frame would stall the video. The boxes go slightly
        stale between passes; that is the trade being made, deliberately.
        """
        every_n = config.DETECT_EVERY_N_FRAMES if every_n is None else every_n
        every_n = max(1, int(every_n))
        run_now = (self._frame_index % every_n == 0)
        self._frame_index += 1
        if run_now:
            self._cached = self.detect(frame)
        return self._cached

    def reset_cache(self):
        self._frame_index = 0
        self._cached = []

    @property
    def average_inference_ms(self):
        if not self.inference_count:
            return 0.0
        return (self.total_inference_time / self.inference_count) * 1000.0

    # ----------------------------------------------------------------- draw
    @staticmethod
    def draw(frame, detections, zone_lines=True):
        """Annotate a copy of the frame with boxes, labels and zone dividers."""
        if frame is None:
            return None
        canvas = frame.copy()
        h, w = canvas.shape[:2]

        if zone_lines:
            for fraction, label in ((config.ZONE_LEFT_EDGE, "LEFT|CENTER"),
                                    (config.ZONE_RIGHT_EDGE, "CENTER|RIGHT")):
                x = int(w * fraction)
                cv2.line(canvas, (x, 0), (x, h), (70, 70, 70), 1)
            third = w // 6
            for name, cx in (("LEFT", third), ("CENTER", w // 2), ("RIGHT", w - third)):
                cv2.putText(canvas, name, (cx - 22, h - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (140, 140, 140), 1, cv2.LINE_AA)

        for det in detections:
            colour = COLOURS.get(det["class_name"], DEFAULT_COLOUR)
            cv2.rectangle(canvas, (det["x1"], det["y1"]), (det["x2"], det["y2"]), colour, 2)
            label = "%s %.0f%%" % (det["class_name"], det["confidence"] * 100)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            top = max(det["y1"] - th - 8, 0)
            cv2.rectangle(canvas, (det["x1"], top),
                          (det["x1"] + tw + 8, top + th + 8), colour, -1)
            cv2.putText(canvas, label, (det["x1"] + 4, top + th + 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (20, 20, 20), 1, cv2.LINE_AA)
            cv2.circle(canvas, (det["center_x"], det["center_y"]), 3, colour, -1)

        return canvas
