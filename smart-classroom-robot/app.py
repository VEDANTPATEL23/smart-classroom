r"""Smart Classroom Assistant Robot - entry point.

    venv\Scripts\python.exe app.py                 # normal run
    venv\Scripts\python.exe app.py --simulate      # force the simulated arm
    venv\Scripts\python.exe app.py --port COM5     # pin the serial port
    venv\Scripts\python.exe app.py --camera 1      # second webcam
    venv\Scripts\python.exe app.py --list-ports    # just show serial ports

Wiring:

    Camera -> Detector -> ClassroomMonitor -> Dashboard -> ArduinoController -> arm
"""
import argparse
import logging
import os
import sys

import config
from camera import Camera
from classroom_logic import ClassroomMonitor
from controller import ArduinoController, list_serial_ports
from detection import Detector
from ui.dashboard import Dashboard


def enable_dpi_awareness():
    """Tell Windows we scale ourselves.

    Without this, Tk is stretched by the compositor on a 125%/150% display and
    every label and video frame comes out soft. Harmless everywhere else.
    """
    if os.name != "nt":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)      # per-monitor aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()        # older Windows
        except Exception:
            pass


def setup_logging(verbose=False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)-10s %(message)s",
        datefmt="%H:%M:%S",
    )
    # ultralytics is chatty on every predict call
    logging.getLogger("ultralytics").setLevel(logging.WARNING)


def show_ports():
    ports = list_serial_ports()
    if not ports:
        print("No serial ports found. Plug the Arduino in over USB.")
        print("A clone board may need the CH340 or CP210x driver installed.")
        return
    print("Serial ports:")
    for device, description, likely in ports:
        print("  %-8s %s%s" % (device, description, "   <-- likely Arduino" if likely else ""))
    print("\nPut the right one in config.py as SERIAL_PORT, or pass --port.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Smart Classroom Assistant Robot")
    parser.add_argument("--port", help="serial port, e.g. COM5 (default: auto-detect)")
    parser.add_argument("--camera", type=int, help="webcam index (default: %d)"
                        % config.CAMERA_INDEX)
    parser.add_argument("--simulate", action="store_true",
                        help="always use the simulated arm, never a real port")
    parser.add_argument("--require-arduino", action="store_true",
                        help="refuse to start unless a real board answers")
    parser.add_argument("--list-ports", action="store_true", help="list serial ports and exit")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    log = logging.getLogger("app")

    if args.list_ports:
        show_ports()
        return 0

    simulate = True if args.simulate else (False if args.require_arduino else None)
    controller = ArduinoController(port=args.port, simulate=simulate)
    if not controller.connect():
        log.error("could not reach the arm: %s", controller.last_error)
        if args.require_arduino:
            print("\n--require-arduino was given but no board answered.")
            show_ports()
            return 2
    log.info("arm: %s", controller.status_text)
    if controller.simulated:
        log.warning("no hardware attached - running the simulated arm. "
                    "Commands are executed against a software model of the sketch.")

    enable_dpi_awareness()

    camera = Camera(index=args.camera)
    detector = Detector()
    monitor = ClassroomMonitor()

    log.info("loading the detection model (a few seconds) ...")
    if not detector.load():
        log.error("model failed to load: %s", detector.last_error)
        print("\nThe dashboard will still open, but detection will not run.")

    app = Dashboard(camera, detector, controller, monitor)
    try:
        app.mainloop()
    except KeyboardInterrupt:
        app.on_close()
    finally:
        camera.release()
        controller.disconnect()
    log.info("bye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
