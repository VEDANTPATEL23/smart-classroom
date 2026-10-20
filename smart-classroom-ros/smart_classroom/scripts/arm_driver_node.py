#!/usr/bin/env python3
"""ROS side of classroom_robot.ino.

The sketch is unchanged: this node owns the serial port and speaks the same
newline-terminated text protocol the original controller.py did.

Subscribes:
    arm/command        std_msgs/String   queued and run in order
Publishes:
    arm/result         std_msgs/String   "<COMMAND>: OK" or "<COMMAND>: FAILED <why>"
    arm/status         std_msgs/String   latched: CONNECTED (<port>) / SIMULATED / DISCONNECTED
    arm/joint_states   sensor_msgs/JointState   servo angles in radians
Services:
    arm/send_command   smart_classroom/ArmCommand   blocks until the board answers

With no board attached and simulate set to auto, the SimulatedArduino from
controller.py answers instead, so the rest of the graph still runs.
"""
import math
import queue
import threading

import rospy
from sensor_msgs.msg import JointState
from std_msgs.msg import String

from smart_classroom import config
from smart_classroom.controller import ArduinoController, SimulatedArduino
from smart_classroom.srv import ArmCommand, ArmCommandResponse


def simulate_setting(value):
    """true / false / auto, whether it arrived as a bool or as text."""
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no"):
        return False
    return "auto"


class ArmDriverNode:
    def __init__(self):
        config.ARDUINO_BOOT_WAIT = rospy.get_param("~boot_wait", config.ARDUINO_BOOT_WAIT)
        config.SERIAL_TIMEOUT = rospy.get_param("~serial_timeout", config.SERIAL_TIMEOUT)
        self.assist_timeout = rospy.get_param("~assist_timeout", config.ASSIST_TIMEOUT)
        # The sketch only replies once the arm has ARRIVED, and a long sweep at
        # 15 ms per degree takes well over the 1 s the plain serial timeout allows.
        self.move_timeout = rospy.get_param("~move_timeout", 10.0)
        self.reconnect_period = rospy.get_param("~reconnect_period", 5.0)

        self.controller = ArduinoController(
            port=rospy.get_param("~port", ""),
            baud=rospy.get_param("~baud", config.BAUD_RATE),
            simulate=simulate_setting(rospy.get_param("~simulate", "auto")))

        self.pub_result = rospy.Publisher("arm/result", String, queue_size=10)
        self.pub_status = rospy.Publisher("arm/status", String, queue_size=1, latch=True)
        self.pub_joints = rospy.Publisher("arm/joint_states", JointState, queue_size=10)
        self._last_status = None

        self.connect()

        self._commands = queue.Queue()
        self._worker = threading.Thread(target=self._drain, name="arm", daemon=True)
        self._worker.start()

        rospy.Subscriber("arm/command", String, self.on_command, queue_size=20)
        rospy.Service("arm/send_command", ArmCommand, self.on_service)
        rospy.Timer(rospy.Duration(self.reconnect_period), self.on_timer)
        rospy.on_shutdown(self.controller.disconnect)

    # ---------------------------------------------------------- connection
    def connect(self):
        if self.controller.connect():
            if self.controller.simulated:
                rospy.logwarn("no board found - running the simulated arm")
            else:
                rospy.loginfo("arm %s", self.controller.banner)
            self.publish_joints()
        else:
            rospy.logwarn_throttle(30.0, "arm not reachable: %s" % self.controller.last_error)
        self.publish_status()

    def on_timer(self, _event):
        if not self.controller.connected:
            self.connect()
        self.publish_status()

    def publish_status(self):
        text = self.controller.status_text
        if text != self._last_status:
            self._last_status = text
            self.pub_status.publish(String(data=text))

    def publish_joints(self):
        angles = self.controller.get_status()
        if not angles:
            return
        msg = JointState()
        msg.header.stamp = rospy.Time.now()
        for name in SimulatedArduino.ORDER:
            msg.name.append(name.lower())
            msg.position.append(math.radians(angles[name]))
        self.pub_joints.publish(msg)

    # ------------------------------------------------------------ commands
    def execute(self, command):
        """Send one protocol line. Returns (ok, message)."""
        command = (command or "").strip().upper()
        if not command:
            return False, "empty command"
        if not self.controller.connected:
            return False, "arm is disconnected"

        verb = command.split()[0]
        if verb == "PING":
            ok = self.controller.send_command(command, expect="PONG")
        elif verb == "STATUS":
            angles = self.controller.get_status()
            if angles is None:
                return False, "no STATUS reply"
            self.publish_joints()
            return True, ",".join(str(angles[j]) for j in SimulatedArduino.ORDER)
        else:
            timeout = self.assist_timeout if verb == "ASSIST" else self.move_timeout
            ok = self.controller.send_command(command, timeout=timeout)

        if not ok:
            self.publish_status()
            return False, self.controller.last_error
        self.publish_joints()
        return True, "OK"

    def report(self, command, ok, message):
        text = "%s: %s" % (command, "OK" if ok else "FAILED " + message)
        (rospy.loginfo if ok else rospy.logwarn)("arm %s", text)
        self.pub_result.publish(String(data=text))

    def on_command(self, msg):
        self._commands.put(msg.data)

    def _drain(self):
        """Serial work stays off the subscriber thread; ASSIST alone takes ~20 s."""
        while not rospy.is_shutdown():
            try:
                command = self._commands.get(timeout=0.2)
            except queue.Empty:
                continue
            ok, message = self.execute(command)
            self.report(command.strip().upper(), ok, message)

    def on_service(self, request):
        ok, message = self.execute(request.command)
        self.report(request.command.strip().upper(), ok, message)
        return ArmCommandResponse(success=ok, message=message)


if __name__ == "__main__":
    rospy.init_node("arm_driver")
    try:
        ArmDriverNode()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
