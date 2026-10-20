"""Phase 2 - Python side of the arm.

Nothing in this file knows about cameras or YOLO; it only turns method calls into
serial text and reads the board's replies. That separation is deliberate - the
vision code can be rewritten without touching hardware control, and vice versa.

    from controller import ArduinoController
    arm = ArduinoController()
    arm.connect()
    arm.move_left()
    arm.disconnect()

With no board plugged in, a built-in SimulatedArduino answers exactly like the
sketch does, so every other phase can be built and tested today.
"""
import logging
import threading
import time

import config

log = logging.getLogger("controller")

# Commands the sketch understands. Keeping the list here means a typo raises in
# Python rather than silently becoming "ERR UNKNOWN" on the board.
PRESETS = ("HOME", "LEFT", "CENTER", "RIGHT", "WARNING", "OPEN", "CLOSE", "PICK")
INDICATORS = ("NORMAL", "WARN_LED", "ALERT")
OTHER = ("PING", "STATUS", "ASSIST")

# USB vendor ids that mean "probably an Arduino"
ARDUINO_VIDS = {
    0x2341: "Arduino",
    0x2A03: "Arduino (.org)",
    0x1A86: "CH340 clone",
    0x0403: "FTDI",
    0x10C4: "CP210x",
    0x1B4F: "SparkFun",
}


def find_arduino_port():
    """Return the device name of the first port that looks like an Arduino."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return None
    for port in list_ports.comports():
        if port.vid in ARDUINO_VIDS:
            return port.device
    return None


def list_serial_ports():
    """All ports, as (device, description, is_likely_arduino) tuples."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return [(p.device, p.description, p.vid in ARDUINO_VIDS)
            for p in list_ports.comports()]


class ArduinoError(Exception):
    """Raised when a command cannot be delivered or the board rejects it."""


class SimulatedArduino:
    """A stand-in for the board that speaks the sketch's protocol exactly.

    It mirrors classroom_robot.ino: the same joint limits, the same preset
    angles, the same OK/ERR replies. Swapping in the real Uno later changes
    nothing above this class.
    """

    # name -> (min, max), matching the sketch's Joint table
    LIMITS = {"BASE": (10, 170), "SHOULDER": (30, 150),
              "ELBOW": (20, 160), "GRIPPER": (35, 110)}
    ORDER = ("BASE", "SHOULDER", "ELBOW", "GRIPPER")
    KEEP = None

    PRESETS = {
        "HOME":    (90, 90, 90, 35),
        "LEFT":    (150, 80, 100, 35),
        "CENTER":  (90, 75, 105, 35),
        "RIGHT":   (30, 80, 100, 35),
        "WARNING": (90, 50, 140, 35),
        "OPEN":    (KEEP, KEEP, KEEP, 35),
        "CLOSE":   (KEEP, KEEP, KEEP, 100),
        "PICK":    (90, 130, 60, 35),
    }

    def __init__(self, move_time=0.0):
        self.angles = dict(zip(self.ORDER, self.PRESETS["HOME"]))
        self.leds = {"green": True, "yellow": False, "red": False}
        self.move_time = move_time          # set >0 to imitate servo travel time
        self.history = []                   # every command received
        self.is_open = True
        self._out = [b"READY classroom_robot v1 (simulated)\n", self._status_line()]

    # -- serial-like surface -------------------------------------------------
    def write(self, data):
        text = data.decode("utf-8", "replace").strip()
        for line in text.splitlines():
            if line.strip():
                self._out.append(self._handle(line.strip()).encode() + b"\n")
        return len(data)

    def readline(self):
        return self._out.pop(0) if self._out else b""

    def reset_input_buffer(self):
        self._out.clear()

    def close(self):
        self.is_open = False

    @property
    def in_waiting(self):
        return sum(len(x) for x in self._out)

    # -- board behaviour -----------------------------------------------------
    def _status_line(self):
        return ("STATUS " + ",".join(str(self.angles[j]) for j in self.ORDER)).encode() + b"\n"

    def _clamp(self, joint, angle):
        lo, hi = self.LIMITS[joint]
        return max(lo, min(hi, int(angle)))

    def _apply(self, pose):
        for joint, target in zip(self.ORDER, pose):
            if target is not self.KEEP:
                self.angles[joint] = self._clamp(joint, target)
        if self.move_time:
            time.sleep(self.move_time)

    def _handle(self, line):
        self.history.append(line)
        parts = line.upper().split()
        verb, args = parts[0], parts[1:]

        if verb == "PING":
            return "PONG"
        if verb == "STATUS":
            return self._status_line().decode().strip()
        if verb == "SPEED":
            if not args or not args[0].lstrip("-").isdigit():
                return "ERR SPEED 5..60"
            ms = int(args[0])
            return "OK SPEED %d" % ms if 5 <= ms <= 60 else "ERR SPEED 5..60"
        if verb == "SET":
            if len(args) < 2:
                return "ERR SET <JOINT> <ANGLE>"
            joint = args[0]
            if joint not in self.LIMITS:
                return "ERR SET UNKNOWN JOINT %s" % joint
            try:
                angle = int(args[1])
            except ValueError:
                return "ERR SET <JOINT> <ANGLE>"
            self.angles[joint] = self._clamp(joint, angle)
            return "OK SET %s %d" % (joint, self.angles[joint])
        if verb == "ASSIST":
            for step in ("HOME", "OPEN", "PICK", "CLOSE", "HOME", "CENTER", "OPEN", "HOME"):
                self._apply(self.PRESETS[step])
            return "OK ASSIST"
        if verb in ("NORMAL", "WARN_LED", "ALERT"):
            self.leds = {"green": verb == "NORMAL",
                         "yellow": verb == "WARN_LED",
                         "red": verb == "ALERT"}
            return "OK %s" % verb
        if verb in self.PRESETS:
            self._apply(self.PRESETS[verb])
            if verb == "WARNING":
                self.leds = {"green": False, "yellow": True, "red": False}
            return "OK %s" % verb
        return "ERR UNKNOWN %s" % verb


class ArduinoController:
    """Sends commands to the arm and reports whether they landed.

    Every public method returns True on success and False on failure - the
    dashboard uses that to keep its status label honest instead of pretending a
    disconnected board obeyed.
    """

    def __init__(self, port=None, baud=None, simulate=None):
        self.port = port if port is not None else config.SERIAL_PORT
        self.baud = baud if baud is not None else config.BAUD_RATE
        self.simulate_setting = config.SIMULATE_ARDUINO if simulate is None else simulate

        self._link = None                 # pyserial Serial or SimulatedArduino
        self._lock = threading.Lock()     # UI thread and worker thread both send
        self.simulated = False
        self.connected = False
        self.last_error = ""
        self.last_command = ""
        self.banner = ""

    # ---------------------------------------------------------- connection
    def connect(self):
        """Open the port, or fall back to simulation when configured to."""
        if self.connected:
            return True

        want_sim = self.simulate_setting is True
        allow_sim = self.simulate_setting in (True, "auto")

        if not want_sim:
            port = self.port or find_arduino_port()
            if port:
                if self._open_serial(port):
                    return True
                if not allow_sim:
                    return False
            else:
                self.last_error = "no Arduino found on any serial port"
                log.warning(self.last_error)
                if not allow_sim:
                    return False

        if allow_sim:
            self._link = SimulatedArduino()
            self.simulated = True
            self.connected = True
            self.banner = self._read_line()
            self._drain()
            log.info("running against the simulated Arduino")
            return True

        return False

    def _open_serial(self, port):
        try:
            import serial
        except ImportError:
            self.last_error = "pyserial is not installed"
            return False
        try:
            self._link = serial.Serial(port, self.baud, timeout=config.SERIAL_TIMEOUT)
        except Exception as exc:
            self.last_error = "could not open %s: %s" % (port, exc)
            log.warning(self.last_error)
            return False

        # An Uno resets when the port opens; wait for the sketch to boot.
        time.sleep(config.ARDUINO_BOOT_WAIT)
        self._link.reset_input_buffer()
        self.port = port
        self.simulated = False
        self.connected = True
        self.last_error = ""

        if self.send_command("PING", expect="PONG"):
            self.banner = "connected on %s" % port
            log.info(self.banner)
            return True

        self.last_error = "%s opened but did not answer PING" % port
        log.warning(self.last_error)
        self.disconnect()
        return False

    def disconnect(self):
        with self._lock:
            if self._link is not None:
                try:
                    self._link.close()
                except Exception:
                    pass
            self._link = None
            self.connected = False
            self.simulated = False

    @property
    def status_text(self):
        if not self.connected:
            return "DISCONNECTED"
        return "SIMULATED" if self.simulated else "CONNECTED (%s)" % self.port

    # ------------------------------------------------------------- plumbing
    def _read_line(self):
        try:
            raw = self._link.readline()
        except Exception as exc:
            self.last_error = "read failed: %s" % exc
            return ""
        return raw.decode("utf-8", "replace").strip() if raw else ""

    def _drain(self):
        """Throw away anything still queued, so replies line up with commands."""
        for _ in range(20):
            if not self._read_line():
                break

    def send_command(self, command, expect="OK", timeout=None):
        """Send one command and wait for the board to acknowledge it.

        Returns True when the reply starts with `expect`. Never raises - a dead
        board makes this return False and sets last_error.
        """
        command = command.strip().upper()
        if not command:
            return False
        if not self.connected or self._link is None:
            self.last_error = "not connected"
            return False

        deadline = time.time() + (timeout or config.SERIAL_TIMEOUT)
        with self._lock:
            self.last_command = command
            try:
                self._link.write((command + "\n").encode())
                if hasattr(self._link, "flush"):
                    self._link.flush()
            except Exception as exc:
                self.last_error = "write failed: %s" % exc
                self.connected = False
                return False

            while time.time() < deadline:
                reply = self._read_line()
                if not reply:
                    time.sleep(0.01)
                    continue
                if reply.startswith("ERR"):
                    self.last_error = reply
                    log.warning("board rejected %s: %s", command, reply)
                    return False
                if reply.startswith(expect):
                    self.last_error = ""
                    return True
                # STATUS/READY chatter can arrive first; keep looking
                log.debug("ignoring unsolicited line: %s", reply)

        self.last_error = "timed out waiting for '%s' after %s" % (expect, command)
        log.warning(self.last_error)
        return False

    def get_status(self):
        """Ask the board for its joint angles. Returns a dict or None."""
        if not self.connected or self._link is None:
            return None
        with self._lock:
            try:
                self._link.write(b"STATUS\n")
            except Exception as exc:
                self.last_error = "write failed: %s" % exc
                self.connected = False
                return None
            deadline = time.time() + config.SERIAL_TIMEOUT
            while time.time() < deadline:
                reply = self._read_line()
                if reply.startswith("STATUS "):
                    try:
                        values = [int(v) for v in reply.split(" ", 1)[1].split(",")]
                    except ValueError:
                        return None
                    return dict(zip(SimulatedArduino.ORDER, values))
                if not reply:
                    time.sleep(0.01)
        return None

    # -------------------------------------------------------- arm movements
    def home(self):          return self.send_command("HOME")
    def move_left(self):     return self.send_command("LEFT")
    def move_center(self):   return self.send_command("CENTER")
    def move_right(self):    return self.send_command("RIGHT")
    def warning(self):       return self.send_command("WARNING")
    def open_gripper(self):  return self.send_command("OPEN")
    def close_gripper(self): return self.send_command("CLOSE")
    def pick(self):          return self.send_command("PICK")

    def assist(self):
        """Run the full pick-and-place sequence on the board (Phase 8)."""
        return self.send_command("ASSIST", timeout=config.ASSIST_TIMEOUT)

    def point_at_zone(self, zone):
        """Point the arm at LEFT / CENTER / RIGHT. Unknown zones are ignored."""
        zone = (zone or "").upper()
        if zone == "LEFT":
            return self.move_left()
        if zone == "CENTER":
            return self.move_center()
        if zone == "RIGHT":
            return self.move_right()
        return False

    # ------------------------------------------------------- indicators
    def set_indicator(self, status):
        """NORMAL / WARNING / ALERT -> LEDs only, without moving the arm."""
        status = (status or "").upper()
        if status == "WARNING":
            return self.send_command("WARN_LED")
        if status in ("NORMAL", "ALERT"):
            return self.send_command(status)
        return False

    # ------------------------------------------------- context manager sugar
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.disconnect()
        return False
