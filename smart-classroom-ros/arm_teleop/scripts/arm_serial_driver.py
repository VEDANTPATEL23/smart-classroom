#!/usr/bin/env python3
"""ROS side of trailass.ino.

The sketch is unchanged: it still expects four raw bytes at 115200 baud, one
angle in degrees per servo, in the order base, pivot, elbow, end effector.

Subscribes:
    joint_command   sensor_msgs/JointState   target angles in radians
Publishes:
    joint_states    sensor_msgs/JointState   the angles actually sent (the servos
                                             give no feedback, so this is open loop)
"""
import math
import time

import rospy
import serial
from sensor_msgs.msg import JointState


class ArmSerialDriver:
    def __init__(self):
        self.port = rospy.get_param("~port", "/dev/ttyACM0")
        self.baud = rospy.get_param("~baud", 115200)
        self.boot_wait = rospy.get_param("~boot_wait", 2.0)
        self.names = rospy.get_param("~joints/names")
        self.min_deg = rospy.get_param("~joints/min_deg")
        self.max_deg = rospy.get_param("~joints/max_deg")

        self.link = None
        self.next_attempt = 0.0
        self.open()

        self.pub = rospy.Publisher("joint_states", JointState, queue_size=1)
        rospy.Subscriber("joint_command", JointState, self.on_command, queue_size=1)
        rospy.on_shutdown(self.close)

    def open(self):
        try:
            self.link = serial.Serial(self.port, self.baud, write_timeout=0.5)
        except serial.SerialException as exc:
            self.link = None
            rospy.logwarn_throttle(10.0, "arm: could not open %s: %s" % (self.port, exc))
            return False
        # The Arduino resets when the port opens; bytes sent before the sketch
        # is running would be lost and shift every later 4-byte packet.
        time.sleep(self.boot_wait)
        rospy.loginfo("arm connected on %s", self.port)
        return True

    def close(self):
        if self.link is not None:
            try:
                self.link.close()
            except serial.SerialException:
                pass
        self.link = None

    def on_command(self, msg):
        if self.link is None:
            if time.time() < self.next_attempt:
                return
            self.next_attempt = time.time() + 2.0
            if not self.open():
                return

        targets = dict(zip(msg.name, msg.position))
        if any(name not in targets for name in self.names):
            rospy.logwarn_throttle(5.0, "arm: joint_command must name all of %s" % self.names)
            return

        degrees = []
        for name, low, high in zip(self.names, self.min_deg, self.max_deg):
            angle = int(round(math.degrees(targets[name])))
            degrees.append(max(low, min(high, angle)))

        try:
            self.link.write(bytes(degrees))
        except (serial.SerialException, OSError) as exc:
            rospy.logwarn("arm: write failed, reconnecting: %s", exc)
            self.close()
            return

        out = JointState()
        out.header.stamp = rospy.Time.now()
        out.name = list(self.names)
        out.position = [math.radians(d) for d in degrees]
        self.pub.publish(out)


if __name__ == "__main__":
    rospy.init_node("arm_driver")
    try:
        ArmSerialDriver()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
