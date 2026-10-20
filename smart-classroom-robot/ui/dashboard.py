"""Phase 6 - the Tkinter dashboard.

Threading model, which is the whole difficulty of a GUI like this:

    capture thread   camera.read -> detector -> monitor  -> latest frame slot
    arm thread       drains a queue of serial commands (ASSIST takes ~20s)
    Tk main thread   every UI_REFRESH_MS, paints the newest frame and labels

Tk widgets are touched from the main thread only. The worker threads never call
into Tk; they publish into a lock-guarded slot and a queue, and the UI polls.
That is what keeps the window responsive while YOLO and the servos take their time.
"""
import logging
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

import cv2
from PIL import Image, ImageTk

import config
from classroom_logic import (ClassroomMonitor, STATUS_ALERT, STATUS_NORMAL,
                             STATUS_WARNING, ZONE_NONE)

log = logging.getLogger("dashboard")

BG = "#10141c"
PANEL = "#182031"
FG = "#e8eef8"
MUTED = "#8fa0bd"
ACCENT = "#4a9eff"

MIN_FRAME_INTERVAL = 1.0 / 60.0   # never loop faster than 60 fps

STATUS_COLOURS = {
    STATUS_NORMAL: "#3ddc84",
    STATUS_WARNING: "#ffb020",
    STATUS_ALERT: "#ff5252",
}


class Dashboard(tk.Tk):
    """The operator window. Everything it shows reflects real state, including
    failures - a disconnected Arduino says DISCONNECTED rather than pretending."""

    def __init__(self, camera, detector, controller, monitor=None):
        super().__init__()
        self.camera = camera
        self.detector = detector
        self.controller = controller
        self.monitor = monitor or ClassroomMonitor()

        self.title(config.WINDOW_TITLE)
        self.configure(bg=BG)
        self.minsize(1040, 700)
        self.geometry("1120x760")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # shared state between threads
        self._frame_lock = threading.Lock()
        self._latest = None                 # (annotated_frame, ClassroomState)
        self._commands = queue.Queue()
        self._status_queue = queue.Queue(maxsize=200)
        self._monitoring = False
        self._shutdown = threading.Event()
        self._capture_thread = None
        self._arm_thread = None

        self._photo = None                  # keep a reference or Tk drops the image
        self._last_command_at = 0.0
        self.status_message = "Idle. Press START MONITORING."
        self.fps = 0.0
        self._fps_samples = []

        self._build_ui()
        self._start_arm_worker()
        self.after(config.UI_REFRESH_MS, self._tick)

    # ------------------------------------------------------------------- UI
    def _build_ui(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=18, pady=(14, 6))
        tk.Label(header, text="SMART CLASSROOM ASSISTANT ROBOT", bg=BG, fg=FG,
                 font=("Segoe UI", 14, "bold")).pack(side="left")
        self.fps_label = tk.Label(header, text="", bg=BG, fg=MUTED,
                                  font=("Consolas", 9))
        self.fps_label.pack(side="right")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=6)

        # ---- left: live video
        video_panel = tk.Frame(body, bg=PANEL, highlightbackground="#26314a",
                               highlightthickness=1)
        video_panel.pack(side="left", fill="both", expand=True)
        tk.Label(video_panel, text="LIVE CAMERA FEED", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(10, 4))
        # A Label's width/height are CHARACTERS and LINES while it shows text,
        # so sizing it 640x480 directly made a monstrous placeholder that wrecked
        # the layout until the first frame arrived. Size a Frame instead - Frame
        # width/height really are pixels - and let the label fill it.
        holder = tk.Frame(video_panel, bg="#05070b",
                          width=config.VIDEO_DISPLAY_WIDTH,
                          height=int(config.VIDEO_DISPLAY_WIDTH * 3 / 4))
        holder.pack(padx=12, pady=(0, 12))
        holder.pack_propagate(False)
        self.video_label = tk.Label(holder, bg="#05070b", text="camera off", fg=MUTED)
        self.video_label.pack(fill="both", expand=True)

        # ---- right: readouts and controls
        side = tk.Frame(body, bg=BG, width=330)
        side.pack(side="right", fill="y", padx=(16, 0))
        side.pack_propagate(False)

        # Buttons are packed against the BOTTOM first, so they keep their space
        # no matter how tall the readout stack grows or how short the window is.
        button_area = tk.Frame(side, bg=BG)
        button_area.pack(side="bottom", fill="x", pady=(10, 0))
        card_area = tk.Frame(side, bg=BG)
        card_area.pack(side="top", fill="both", expand=True)

        self.value_labels = {}
        for key, caption in (("students_present", "Students Present"),
                             ("phones_detected", "Phones Detected"),
                             ("classroom_status", "Class Status"),
                             ("detected_zone", "Detected Zone"),
                             ("arduino", "Arduino")):
            # One line per readout: caption left, value right. Two-line cards
            # overflowed the column on a 150%-scaled display.
            card = tk.Frame(card_area, bg=PANEL, highlightbackground="#26314a",
                            highlightthickness=1)
            card.pack(fill="x", pady=2)
            tk.Label(card, text=caption.upper(), bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 8, "bold")).pack(side="left", padx=10, pady=3)
            value = tk.Label(card, text="-", bg=PANEL, fg=FG,
                             font=("Segoe UI", 11, "bold"))
            value.pack(side="right", padx=10, pady=3)
            self.value_labels[key] = value

        self.buttons = {}
        specs = (("start", "START MONITORING", self.start_monitoring, ACCENT),
                 ("stop", "STOP", self.stop_monitoring, "#40506e"),
                 ("home", "HOME", self.cmd_home, "#40506e"),
                 ("assist", "ASSIST", self.cmd_assist, "#2f8f5b"),
                 ("warning", "WARNING", self.cmd_warning, "#b8791c"))
        for key, caption, handler, colour in specs:
            btn = tk.Button(button_area, text=caption, command=handler, bg=colour, fg="white",
                            activebackground=colour, activeforeground="white",
                            relief="flat", font=("Segoe UI", 9, "bold"),
                            cursor="hand2", pady=3, borderwidth=0)
            btn.pack(fill="x", pady=2)
            self.buttons[key] = btn
        self.buttons["stop"].configure(state="disabled")

        self.status_bar = tk.Label(self, text=self.status_message, bg="#0b0f16",
                                   fg=MUTED, anchor="w", font=("Segoe UI", 9),
                                   padx=18, pady=7)
        self.status_bar.pack(fill="x", side="bottom")

    def set_status(self, message):
        """Safe to call from ANY thread.

        Tk is not thread-safe: configuring a widget from the capture or arm
        thread raises "main thread is not in main loop" and kills that thread.
        So the message is queued here and painted by _tick() on the main thread.
        """
        self.status_message = message
        log.info(message)
        try:
            self._status_queue.put_nowait(message)
        except queue.Full:
            pass

    # ------------------------------------------------------- arm command lane
    def _start_arm_worker(self):
        """Serial commands run on their own thread; ASSIST alone takes ~20s and
        would otherwise freeze the window solid."""
        def worker():
            while not self._shutdown.is_set():
                try:
                    label, action = self._commands.get(timeout=0.2)
                except queue.Empty:
                    continue
                try:
                    ok = action()
                    if ok:
                        self.set_status("%s done" % label)
                    else:
                        self.set_status("%s FAILED: %s" % (label, self.controller.last_error))
                except Exception as exc:                     # never kill the thread
                    log.exception("arm command failed")
                    self.set_status("%s raised %s" % (label, exc))
                finally:
                    self._commands.task_done()

        self._arm_thread = threading.Thread(target=worker, name="arm", daemon=True)
        self._arm_thread.start()

    def queue_command(self, label, action):
        if not self.controller.connected:
            self.set_status("%s ignored - Arduino is disconnected" % label)
            return False
        self.set_status("%s ..." % label)
        self._commands.put((label, action))
        return True

    # ---- button handlers
    def cmd_home(self):
        self.queue_command("HOME", self.controller.home)

    def cmd_assist(self):
        self.queue_command("ASSIST (pick and place)", self.controller.assist)

    def cmd_warning(self):
        self.queue_command("WARNING", self.controller.warning)

    # ------------------------------------------------------- capture pipeline
    def start_monitoring(self):
        if self._monitoring:
            return
        if not self.camera.opened and not self.camera.start():
            self.set_status("CAMERA ERROR: %s" % self.camera.last_error)
            return
        if not self.detector.ready and not self.detector.load():
            self.set_status("MODEL ERROR: %s" % self.detector.last_error)
            return

        self._monitoring = True
        self.monitor.reset()
        self.detector.reset_cache()
        self._fps_samples = []
        self.buttons["start"].configure(state="disabled")
        self.buttons["stop"].configure(state="normal")
        self._capture_thread = threading.Thread(target=self._capture_loop,
                                                name="capture", daemon=True)
        self._capture_thread.start()
        self.set_status("Monitoring. Detecting %s."
                        % ", ".join(self.detector.supported_classes))

    def stop_monitoring(self):
        if not self._monitoring:
            return
        self._monitoring = False
        if self._capture_thread is not None:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None
        self.buttons["start"].configure(state="normal")
        self.buttons["stop"].configure(state="disabled")
        self.set_status("Stopped. Camera still open - press START to resume.")

    def _capture_loop(self):
        """Runs off the UI thread. Publishes the newest annotated frame only;
        if the UI falls behind, older frames are dropped rather than queued."""
        consecutive_failures = 0
        while self._monitoring and not self._shutdown.is_set():
            got, frame = self.camera.read()
            if not got:
                consecutive_failures += 1
                if consecutive_failures >= 30:
                    self._monitoring = False
                    self.set_status("CAMERA ERROR: %s" % self.camera.last_error)
                    break
                time.sleep(0.02)
                continue
            consecutive_failures = 0

            started = time.time()
            detections = self.detector.detect_cached(frame)
            state = self.monitor.update(detections, frame.shape[1])
            annotated = self.detector.draw(frame, detections)

            with self._frame_lock:
                self._latest = (annotated, state)
                self._fps_samples.append(time.time() - started)
                if len(self._fps_samples) > 30:
                    self._fps_samples.pop(0)

            self._react(state)

            # A blocking camera paces this loop naturally, but a fast or fake
            # source would spin the CPU flat out. Cap the rate.
            spent = time.time() - started
            if spent < MIN_FRAME_INTERVAL:
                time.sleep(MIN_FRAME_INTERVAL - spent)

    # --------------------------------------------- Phase 7: detection -> arm
    def _react(self, state):
        """Decide whether this frame deserves a command to the arm.

        Rate-limited: servos need time to arrive, and a command stream that
        outruns them just looks like thrashing. Only genuine transitions fire.
        """
        if not self.controller.connected:
            return
        if not (state.status_changed or state.zone_changed):
            return
        if time.time() - self._last_command_at < config.COMMAND_COOLDOWN_SECONDS:
            return

        if state.status_changed and state.classroom_status in (STATUS_WARNING, STATUS_ALERT):
            self._last_command_at = time.time()
            self.queue_command("auto WARNING (%s)" % state.classroom_status,
                               self.controller.warning)
            self._commands.put(("indicator",
                                lambda s=state.classroom_status:
                                self.controller.set_indicator(s)))
            return

        if state.status_changed and state.classroom_status == STATUS_NORMAL:
            self._last_command_at = time.time()
            self._commands.put(("indicator", lambda: self.controller.set_indicator("NORMAL")))
            self.queue_command("auto HOME (back to normal)", self.controller.home)
            return

        if (config.AUTO_POINT_AT_ZONE and state.zone_changed
                and state.detected_zone != ZONE_NONE
                and state.classroom_status != STATUS_NORMAL):
            zone = state.detected_zone
            self._last_command_at = time.time()
            self.queue_command("auto point %s" % zone,
                               lambda z=zone: self.controller.point_at_zone(z))

    # -------------------------------------------------------- UI refresh loop
    def _tick(self):
        """Main-thread repaint. The only place Tk widgets are touched."""
        try:
            with self._frame_lock:
                latest = self._latest
                samples = list(self._fps_samples)

            if latest is not None:
                frame, state = latest
                self._show_frame(frame)
                self._show_state(state)

            latest_message = None
            while True:
                try:
                    latest_message = self._status_queue.get_nowait()
                except queue.Empty:
                    break
            if latest_message is not None:
                self.status_bar.configure(text=latest_message)

            if samples:
                mean = sum(samples) / len(samples)
                self.fps = (1.0 / mean) if mean > 0 else 0.0
                self.fps_label.configure(
                    text="%.1f fps  |  %.0f ms/frame" % (self.fps, mean * 1000))

            self.value_labels["arduino"].configure(
                text=self.controller.status_text,
                fg="#3ddc84" if self.controller.connected else "#ff5252")

            if not self.controller.connected:
                for key in ("home", "assist", "warning"):
                    self.buttons[key].configure(state="disabled")
            else:
                for key in ("home", "assist", "warning"):
                    self.buttons[key].configure(state="normal")
        except tk.TclError:
            return                                   # window is closing
        except Exception:
            log.exception("UI refresh failed")

        if not self._shutdown.is_set():
            self.after(config.UI_REFRESH_MS, self._tick)

    def _show_frame(self, frame):
        width = config.VIDEO_DISPLAY_WIDTH
        h, w = frame.shape[:2]
        if w != width:
            frame = cv2.resize(frame, (width, int(h * width / w)))
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        self._photo = ImageTk.PhotoImage(image)      # keep the reference alive
        self.video_label.configure(image=self._photo, text="")

    def _show_state(self, state):
        self.value_labels["students_present"].configure(text=str(state.students_present))
        self.value_labels["phones_detected"].configure(text=str(state.phones_detected))
        self.value_labels["classroom_status"].configure(
            text=state.classroom_status,
            fg=STATUS_COLOURS.get(state.classroom_status, FG))
        self.value_labels["detected_zone"].configure(text=state.detected_zone)

    # ------------------------------------------------------------- shutdown
    def on_close(self):
        """Release the camera, the serial port and the threads, in that order."""
        self.set_status("shutting down ...")
        self._monitoring = False
        self._shutdown.set()

        for thread in (self._capture_thread, self._arm_thread):
            if thread is not None and thread.is_alive():
                thread.join(timeout=2.0)

        try:
            self.camera.release()
        except Exception:
            log.exception("camera release failed")
        try:
            self.controller.disconnect()
        except Exception:
            log.exception("controller disconnect failed")

        log.info("clean shutdown")
        try:
            self.destroy()
        except tk.TclError:
            pass
