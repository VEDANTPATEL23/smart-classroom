#!/usr/bin/env python3
"""Run this on WINDOWS (not in ROS): streams the webcam to net_camera_node.py.

WSL cannot open the webcam itself, so this captures it on Windows and sends
JPEG frames to the ROS node over TCP. Needs only opencv-python:

    python windows_webcam_sender.py                  # camera 0 -> localhost:5600
    python windows_webcam_sender.py --camera 1 --fps 10

Keeps retrying until the ROS side is up, and reconnects if it restarts.
"""
import argparse
import os
import socket
import struct
import time

import cv2


def open_camera(index, width, height):
    # CAP_DSHOW avoids the very slow MSMF start-up path on Windows.
    backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
    capture = cv2.VideoCapture(index, backend)
    if not capture.isOpened():
        raise SystemExit("could not open camera index %d - try --camera 1, and close "
                         "any app already using the webcam" % index)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return capture


def connect(host, port):
    announced = False
    while True:
        try:
            return socket.create_connection((host, port), timeout=3)
        except OSError:
            if not announced:
                print("waiting for the ROS camera node on %s:%d ..." % (host, port))
                announced = True
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5600)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--quality", type=int, default=80, help="JPEG quality 1-100")
    args = parser.parse_args()

    capture = open_camera(args.camera, args.width, args.height)
    period = 1.0 / args.fps
    encode_options = [cv2.IMWRITE_JPEG_QUALITY, args.quality]
    try:
        while True:
            conn = connect(args.host, args.port)
            print("connected - streaming camera %d (Ctrl+C to stop)" % args.camera)
            try:
                while True:
                    started = time.time()
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        continue
                    ok, jpeg = cv2.imencode(".jpg", frame, encode_options)
                    if not ok:
                        continue
                    data = jpeg.tobytes()
                    conn.sendall(struct.pack(">I", len(data)) + data)
                    time.sleep(max(0.0, period - (time.time() - started)))
            except OSError:
                print("connection lost - reconnecting")
            finally:
                conn.close()
    except KeyboardInterrupt:
        pass
    finally:
        capture.release()


if __name__ == "__main__":
    main()
