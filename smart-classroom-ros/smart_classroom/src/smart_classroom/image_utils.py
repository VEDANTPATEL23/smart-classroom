"""sensor_msgs/Image <-> OpenCV BGR frames, without cv_bridge.

cv_bridge is compiled against the system numpy/OpenCV, and `pip install
ultralytics` pulls in newer copies of both that it can clash with. These two
functions cover the 8-bit encodings a webcam or a Gazebo camera produces, which
is all this package needs.
"""
import cv2
import numpy as np
from sensor_msgs.msg import Image

# encoding -> (channels, cv2 conversion to BGR or None)
_ENCODINGS = {
    "bgr8": (3, None),
    "rgb8": (3, cv2.COLOR_RGB2BGR),
    "bgra8": (4, cv2.COLOR_BGRA2BGR),
    "rgba8": (4, cv2.COLOR_RGBA2BGR),
    "mono8": (1, cv2.COLOR_GRAY2BGR),
}


def imgmsg_to_bgr(msg):
    """Return the image as an HxWx3 BGR uint8 array. Raises ValueError on an
    encoding this module does not handle."""
    encoding = msg.encoding.lower()
    if encoding not in _ENCODINGS:
        raise ValueError("unsupported image encoding '%s'" % msg.encoding)
    channels, conversion = _ENCODINGS[encoding]

    # step can be wider than width*channels when rows are padded
    rows = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
    frame = rows[:, :msg.width * channels].reshape(msg.height, msg.width, channels)
    if conversion is None:
        return np.ascontiguousarray(frame)
    return cv2.cvtColor(frame, conversion)


def bgr_to_imgmsg(frame, header=None):
    """Wrap an HxWx3 BGR uint8 array as a bgr8 sensor_msgs/Image."""
    msg = Image()
    if header is not None:
        msg.header = header
    msg.height, msg.width = frame.shape[:2]
    msg.encoding = "bgr8"
    msg.is_bigendian = 0
    msg.step = msg.width * 3
    msg.data = np.ascontiguousarray(frame, dtype=np.uint8).tobytes()
    return msg
