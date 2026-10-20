"""Phase 3 - webcam access.

One small class so the rest of the app never touches cv2.VideoCapture directly,
and every caller gets the same warm-up and error handling.

    from camera import Camera
    with Camera() as cam:
        ok, frame = cam.read()
"""
import logging
import os
import time

import cv2

from . import config

log = logging.getLogger("camera")


class CameraError(Exception):
    """Raised when the webcam cannot be opened or stops delivering frames."""


class Camera:
    """A webcam that opens cleanly, warms up, and always releases itself."""

    def __init__(self, index=None, width=None, height=None, warmup=None):
        self.index = config.CAMERA_INDEX if index is None else index
        self.width = config.CAMERA_WIDTH if width is None else width
        self.height = config.CAMERA_HEIGHT if height is None else height
        self.warmup = config.CAMERA_WARMUP_FRAMES if warmup is None else warmup

        self.capture = None
        self.opened = False
        self.last_error = ""
        self.frame_count = 0
        self.failed_reads = 0
        self._started_at = None

    # ------------------------------------------------------------- lifecycle
    def start(self):
        """Open the camera. Returns True on success, False with last_error set."""
        if self.opened:
            return True

        # CAP_DSHOW avoids the very slow MSMF start-up path on Windows.
        backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
        self.capture = cv2.VideoCapture(self.index, backend)
        if not self.capture.isOpened():
            self.capture.release()
            self.capture = None
            self.last_error = (
                "could not open camera index %d - try another index, close any app "
                "already using the webcam, and check Windows camera privacy settings"
                % self.index)
            log.error(self.last_error)
            return False

        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        # Discard the first frames: they are underexposed while auto-exposure settles.
        frame = None
        for _ in range(max(1, self.warmup)):
            ok, f = self.capture.read()
            if ok and f is not None:
                frame = f
        if frame is None:
            self.release()
            self.last_error = "camera opened but never delivered a frame"
            log.error(self.last_error)
            return False

        self.opened = True
        self.last_error = ""
        self.frame_count = 0
        self.failed_reads = 0
        self._started_at = time.time()
        h, w = frame.shape[:2]
        log.info("camera %d open at %dx%d", self.index, w, h)
        return True

    def read(self):
        """Return (ok, frame). A failed read is counted, not raised."""
        if not self.opened or self.capture is None:
            self.last_error = "camera is not started"
            return False, None
        ok, frame = self.capture.read()
        if not ok or frame is None:
            self.failed_reads += 1
            self.last_error = "dropped frame (%d so far)" % self.failed_reads
            return False, None
        self.frame_count += 1
        return True, frame

    def release(self):
        """Always safe to call, even twice."""
        if self.capture is not None:
            try:
                self.capture.release()
            except Exception:
                pass
        self.capture = None
        self.opened = False

    # ---------------------------------------------------------------- extras
    @property
    def resolution(self):
        if not self.opened or self.capture is None:
            return (0, 0)
        return (int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    @property
    def measured_fps(self):
        """Frames per second we are actually achieving, not what the driver claims."""
        if not self._started_at or self.frame_count < 2:
            return 0.0
        elapsed = time.time() - self._started_at
        return self.frame_count / elapsed if elapsed > 0 else 0.0

    def __enter__(self):
        if not self.start():
            raise CameraError(self.last_error)
        return self

    def __exit__(self, *exc):
        self.release()
        return False
