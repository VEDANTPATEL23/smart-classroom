#!/usr/bin/env python3
"""Detections -> classroom status -> arm commands.

Subscribes:
    detections        smart_classroom/DetectionArray
Publishes:
    classroom_state   smart_classroom/ClassroomState
    arm/command       std_msgs/String   (HOME, WARNING, LEFT, WARN_LED, ...)

The status machine is ClassroomMonitor from the original project, unchanged.
The arm reactions are the dashboard's _react(): only real transitions fire, and
never closer together than command_cooldown seconds.
"""
import time

import rospy
from std_msgs.msg import String

from smart_classroom import config
from smart_classroom.classroom_logic import (ClassroomMonitor, STATUS_ALERT,
                                             STATUS_NORMAL, STATUS_WARNING,
                                             ZONE_CENTER, ZONE_LEFT, ZONE_NONE,
                                             ZONE_RIGHT)
from smart_classroom.msg import ClassroomState, DetectionArray


class ClassroomMonitorNode:
    def __init__(self):
        config.ZONE_LEFT_EDGE = rospy.get_param("~zone_left_edge", config.ZONE_LEFT_EDGE)
        config.ZONE_RIGHT_EDGE = rospy.get_param("~zone_right_edge", config.ZONE_RIGHT_EDGE)
        config.CLASS_PERSON = rospy.get_param("~class_person", config.CLASS_PERSON)
        config.CLASS_PHONE = rospy.get_param("~class_phone", config.CLASS_PHONE)

        self.monitor = ClassroomMonitor(
            warning_frames=rospy.get_param("~warning_confirm_frames", config.WARNING_CONFIRM_FRAMES),
            normal_frames=rospy.get_param("~normal_confirm_frames", config.NORMAL_CONFIRM_FRAMES),
            alert_events=rospy.get_param("~alert_event_count", config.ALERT_EVENT_COUNT),
            alert_window=rospy.get_param("~alert_window_seconds", config.ALERT_WINDOW_SECONDS))

        self.cooldown = rospy.get_param("~command_cooldown", config.COMMAND_COOLDOWN_SECONDS)
        self.auto_point = rospy.get_param("~auto_point_at_zone", config.AUTO_POINT_AT_ZONE)
        self.drive_arm = rospy.get_param("~drive_arm", True)
        self._last_command_at = 0.0

        self.pub_state = rospy.Publisher("classroom_state", ClassroomState, queue_size=10)
        self.pub_command = rospy.Publisher("arm/command", String, queue_size=10)
        rospy.Subscriber("detections", DetectionArray, self.on_detections, queue_size=10)

    def on_detections(self, msg):
        detections = [{"class_name": d.class_name, "confidence": d.confidence,
                       "center_x": d.center_x} for d in msg.detections]
        state = self.monitor.update(detections, msg.image_width)

        out = ClassroomState()
        out.header = msg.header
        out.students_present = state.students_present
        out.phones_detected = state.phones_detected
        out.classroom_status = state.classroom_status
        out.detected_zone = state.detected_zone
        out.busiest_zone = state.busiest_zone
        out.left_count = state.zone_counts[ZONE_LEFT]
        out.center_count = state.zone_counts[ZONE_CENTER]
        out.right_count = state.zone_counts[ZONE_RIGHT]
        out.status_changed = state.status_changed
        out.zone_changed = state.zone_changed
        out.event_count = state.event_count
        self.pub_state.publish(out)

        if state.status_changed:
            rospy.loginfo(self.monitor.summary)
        if self.drive_arm:
            self.react(state)

    def send(self, command):
        self.pub_command.publish(String(data=command))

    def react(self, state):
        """Decide whether this frame deserves a command to the arm."""
        if not (state.status_changed or state.zone_changed):
            return
        # Wall-clock on purpose: the servos are real even when Gazebo's clock is not.
        if time.time() - self._last_command_at < self.cooldown:
            return

        if state.status_changed and state.classroom_status in (STATUS_WARNING, STATUS_ALERT):
            self._last_command_at = time.time()
            self.send("WARNING")
            self.send("WARN_LED" if state.classroom_status == STATUS_WARNING else "ALERT")
            return

        if state.status_changed and state.classroom_status == STATUS_NORMAL:
            self._last_command_at = time.time()
            self.send("NORMAL")
            self.send("HOME")
            return

        if (self.auto_point and state.zone_changed
                and state.detected_zone != ZONE_NONE
                and state.classroom_status != STATUS_NORMAL):
            self._last_command_at = time.time()
            self.send(state.detected_zone)


if __name__ == "__main__":
    rospy.init_node("monitor")
    try:
        ClassroomMonitorNode()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
