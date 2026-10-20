"""Phase 5 - turning detections into a classroom picture.

Pure decision logic: it takes the dictionaries Phase 4 produces and works out how
many students are present, whether a phone is out, which third of the room the
event happened in, and what the overall status is. It touches no camera and no
serial port, which is what makes it easy to test.

WHAT THIS CANNOT DO
    The detector recognises `person` and `cell phone` and nothing more. This
    module therefore says nothing about attention, emotion, engagement or
    discipline, because a COCO object detector has no basis for any of that.
"""
import logging
import time
from collections import deque

import config

log = logging.getLogger("logic")

ZONE_LEFT = "LEFT"
ZONE_CENTER = "CENTER"
ZONE_RIGHT = "RIGHT"
ZONE_NONE = "NONE"

STATUS_NORMAL = "NORMAL"
STATUS_WARNING = "WARNING"
STATUS_ALERT = "ALERT"


class ClassroomState:
    """A snapshot of what the monitor believes right now."""

    __slots__ = ("students_present", "phones_detected", "classroom_status",
                 "detected_zone", "busiest_zone", "zone_counts",
                 "status_changed", "zone_changed", "event_count")

    def __init__(self):
        self.students_present = 0
        self.phones_detected = 0
        self.classroom_status = STATUS_NORMAL
        self.detected_zone = ZONE_NONE
        self.busiest_zone = ZONE_NONE
        self.zone_counts = {ZONE_LEFT: 0, ZONE_CENTER: 0, ZONE_RIGHT: 0}
        self.status_changed = False
        self.zone_changed = False
        self.event_count = 0

    def as_dict(self):
        return {
            "students_present": self.students_present,
            "phones_detected": self.phones_detected,
            "classroom_status": self.classroom_status,
            "detected_zone": self.detected_zone,
            "busiest_zone": self.busiest_zone,
            "zone_counts": dict(self.zone_counts),
            "status_changed": self.status_changed,
            "zone_changed": self.zone_changed,
            "event_count": self.event_count,
        }

    def __repr__(self):
        return ("<ClassroomState students=%d phones=%d status=%s zone=%s>"
                % (self.students_present, self.phones_detected,
                   self.classroom_status, self.detected_zone))


class ClassroomMonitor:
    """Counts people, spots phones, assigns zones and holds the status machine.

    The status is deliberately sluggish. A single frame where YOLO thinks a hand
    is a phone should not swing the arm around, so a WARNING needs several
    consecutive confirmations and clearing it needs more still.
    """

    def __init__(self, warning_frames=None, normal_frames=None,
                 alert_events=None, alert_window=None):
        self.warning_frames = (config.WARNING_CONFIRM_FRAMES
                               if warning_frames is None else warning_frames)
        self.normal_frames = (config.NORMAL_CONFIRM_FRAMES
                              if normal_frames is None else normal_frames)
        self.alert_events = (config.ALERT_EVENT_COUNT
                             if alert_events is None else alert_events)
        self.alert_window = (config.ALERT_WINDOW_SECONDS
                             if alert_window is None else alert_window)
        self.reset()

    def reset(self):
        self.status = STATUS_NORMAL
        self.zone = ZONE_NONE
        self._phone_streak = 0
        self._clean_streak = 0
        self._events = deque()          # timestamps of confirmed WARNING events
        self.state = ClassroomState()

    # --------------------------------------------------------------- zones
    @staticmethod
    def zone_for(center_x, frame_width):
        """Which third of the frame a point falls in.

        x < 33% -> LEFT, 33-66% -> CENTER, x > 66% -> RIGHT.
        """
        if not frame_width:
            return ZONE_NONE
        fraction = float(center_x) / float(frame_width)
        if fraction < config.ZONE_LEFT_EDGE:
            return ZONE_LEFT
        if fraction <= config.ZONE_RIGHT_EDGE:
            return ZONE_CENTER
        return ZONE_RIGHT

    # -------------------------------------------------------------- update
    def update(self, detections, frame_width, now=None):
        """Fold one frame of detections into the running picture."""
        now = time.time() if now is None else now
        detections = detections or []

        people = [d for d in detections if d["class_name"] == config.CLASS_PERSON]
        phones = [d for d in detections if d["class_name"] == config.CLASS_PHONE]

        state = ClassroomState()
        state.students_present = len(people)
        state.phones_detected = len(phones)

        for person in people:
            zone = self.zone_for(person["center_x"], frame_width)
            if zone in state.zone_counts:
                state.zone_counts[zone] += 1

        busiest = max(state.zone_counts.items(), key=lambda kv: kv[1])
        state.busiest_zone = busiest[0] if busiest[1] > 0 else ZONE_NONE

        # The zone we would point at is the zone of the most confident phone;
        # with no phone there is no event to point at.
        if phones:
            best = max(phones, key=lambda d: d["confidence"])
            event_zone = self.zone_for(best["center_x"], frame_width)
        else:
            event_zone = ZONE_NONE

        previous_status = self.status
        previous_zone = self.zone

        # ---- status machine
        if phones:
            self._phone_streak += 1
            self._clean_streak = 0
            if self._phone_streak == self.warning_frames:
                self._events.append(now)
                self._trim_events(now)
                if len(self._events) >= self.alert_events:
                    self.status = STATUS_ALERT
                    log.info("ALERT - %d phone events inside %.0fs",
                             len(self._events), self.alert_window)
                else:
                    self.status = STATUS_WARNING
                    log.info("WARNING - phone confirmed in %s", event_zone)
                self.zone = event_zone
            elif self._phone_streak > self.warning_frames and event_zone != ZONE_NONE:
                self.zone = event_zone          # follow the phone while it is out
        else:
            self._phone_streak = 0
            self._clean_streak += 1
            if self.status != STATUS_NORMAL and self._clean_streak >= self.normal_frames:
                self.status = STATUS_NORMAL
                self.zone = ZONE_NONE
                log.info("back to NORMAL after %d clean frames", self._clean_streak)

        self._trim_events(now)

        state.classroom_status = self.status
        state.detected_zone = self.zone
        state.event_count = len(self._events)
        state.status_changed = (self.status != previous_status)
        state.zone_changed = (self.zone != previous_zone)

        self.state = state
        return state

    def _trim_events(self, now):
        """Forget WARNING events older than the alert window."""
        while self._events and (now - self._events[0]) > self.alert_window:
            self._events.popleft()

    # ------------------------------------------------------------- helpers
    @property
    def summary(self):
        s = self.state
        return ("Students %d | Phones %d | %s | zone %s"
                % (s.students_present, s.phones_detected,
                   s.classroom_status, s.detected_zone))
