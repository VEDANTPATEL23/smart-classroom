#!/usr/bin/env python3
"""Joystick -> joint angles. The ROS version of joystick_test.py.

pygame is replaced by the standard `joy` node; this node keeps the same control
law: each stick axis sets a joint's speed in degrees per second, the angle is
integrated, clamped to the joint limits, and held when the stick is released.

Subscribes:
    joy             sensor_msgs/Joy
Publishes:
    joint_command   sensor_msgs/JointState   target angles in radians, every tick
"""
import math

import rospy
from sensor_msgs.msg import Joy, JointState


class ArmTeleop:
    def __init__(self):
        self.names = rospy.get_param("~joints/names")
        self.min_deg = rospy.get_param("~joints/min_deg")
        self.max_deg = rospy.get_param("~joints/max_deg")
        self.angles = [float(a) for a in rospy.get_param("~joints/home_deg")]

        self.axes = rospy.get_param("~axes")            # joy axis index per joint
        self.scale = rospy.get_param("~scale")          # +1 / -1 per joint
        self.speed = rospy.get_param("~speed_deg_s")    # degrees per second per joint
        self.deadzone = rospy.get_param("~deadzone", 0.12)
        self.joy_timeout = rospy.get_param("~joy_timeout", 0.5)
        self.rate_hz = rospy.get_param("~rate", 50.0)

        count = len(self.names)
        for key, values in (("min_deg", self.min_deg), ("max_deg", self.max_deg),
                            ("home_deg", self.angles), ("axes", self.axes),
                            ("scale", self.scale), ("speed_deg_s", self.speed)):
            if len(values) != count:
                raise ValueError("%s needs %d entries, one per joint" % (key, count))

        self.sticks = [0.0] * count
        self.last_joy = None

        self.pub = rospy.Publisher("joint_command", JointState, queue_size=1)
        rospy.Subscriber("joy", Joy, self.on_joy, queue_size=1)

    def on_joy(self, msg):
        sticks = []
        for axis, scale in zip(self.axes, self.scale):
            value = msg.axes[axis] * scale if axis < len(msg.axes) else 0.0
            sticks.append(0.0 if abs(value) < self.deadzone else value)
        self.sticks = sticks
        self.last_joy = rospy.get_time()

    def step(self, dt):
        # A joystick that went quiet (unplugged, joy node died) must not leave
        # the arm sweeping on its last reading.
        if self.last_joy is None or rospy.get_time() - self.last_joy > self.joy_timeout:
            self.sticks = [0.0] * len(self.names)

        for i, stick in enumerate(self.sticks):
            angle = self.angles[i] + stick * self.speed[i] * dt
            self.angles[i] = max(self.min_deg[i], min(self.max_deg[i], angle))

        msg = JointState()
        msg.header.stamp = rospy.Time.now()
        msg.name = list(self.names)
        msg.position = [math.radians(a) for a in self.angles]
        self.pub.publish(msg)

    def run(self):
        rate = rospy.Rate(self.rate_hz)
        last = rospy.get_time()
        while not rospy.is_shutdown():
            now = rospy.get_time()
            self.step(now - last)
            last = now
            rate.sleep()


if __name__ == "__main__":
    rospy.init_node("arm_teleop")
    try:
        ArmTeleop().run()
    except rospy.ROSInterruptException:
        pass
