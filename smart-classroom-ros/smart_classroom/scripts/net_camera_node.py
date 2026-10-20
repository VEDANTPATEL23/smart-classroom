#!/usr/bin/env python3
"""Network webcam -> sensor_msgs/Image.

For ROS running in WSL, whose kernel has no webcam driver: the camera stays on
Windows, scripts/windows_webcam_sender.py captures it there and streams JPEG
frames to this node over TCP.

Publishes:
    ~image_raw   sensor_msgs/Image (bgr8)

Wire format: each frame is a 4-byte big-endian length followed by that many
bytes of JPEG.
"""
import socket
import struct

import cv2
import numpy as np
import rospy
from sensor_msgs.msg import Image

from smart_classroom.image_utils import bgr_to_imgmsg

MAX_FRAME_BYTES = 8 * 1024 * 1024


def read_exactly(conn, count):
    """Return count bytes, or None when the sender has gone away."""
    chunks = []
    while count > 0 and not rospy.is_shutdown():
        try:
            chunk = conn.recv(count)
        except socket.timeout:
            continue
        if not chunk:
            return None
        chunks.append(chunk)
        count -= len(chunk)
    return b"".join(chunks) if count == 0 else None


def serve(conn, pub, frame_id):
    while not rospy.is_shutdown():
        header = read_exactly(conn, 4)
        if header is None:
            return
        size = struct.unpack(">I", header)[0]
        if size == 0 or size > MAX_FRAME_BYTES:
            rospy.logwarn("camera: bad frame size %d, dropping the sender", size)
            return
        payload = read_exactly(conn, size)
        if payload is None:
            return
        frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            continue
        msg = bgr_to_imgmsg(frame)
        msg.header.stamp = rospy.Time.now()
        msg.header.frame_id = frame_id
        pub.publish(msg)


def main():
    rospy.init_node("camera")
    port = rospy.get_param("~net_port", 5600)
    frame_id = rospy.get_param("~frame_id", "camera")
    pub = rospy.Publisher("~image_raw", Image, queue_size=1)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(1)
    server.settimeout(1.0)
    rospy.on_shutdown(server.close)
    rospy.loginfo("camera: waiting for windows_webcam_sender.py on port %d", port)

    while not rospy.is_shutdown():
        try:
            conn, address = server.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        rospy.loginfo("camera: sender connected from %s", address[0])
        conn.settimeout(1.0)
        try:
            serve(conn, pub, frame_id)
        except OSError as error:
            rospy.logwarn("camera: %s", error)
        finally:
            conn.close()
        rospy.loginfo("camera: sender disconnected, waiting again")


if __name__ == "__main__":
    try:
        main()
    except rospy.ROSInterruptException:
        pass
