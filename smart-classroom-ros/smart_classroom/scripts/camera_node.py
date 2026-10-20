#!/usr/bin/env python3
"""Webcam -> sensor_msgs/Image.

Publishes:
    ~image_raw   sensor_msgs/Image (bgr8)

Not needed when the images come from somewhere else (a Gazebo camera, usb_cam):
launch with use_webcam:=false and point image_topic at that source instead.
"""
import rospy
from sensor_msgs.msg import Image

from smart_classroom.camera import Camera
from smart_classroom.image_utils import bgr_to_imgmsg


def main():
    rospy.init_node("camera")

    camera = Camera(index=rospy.get_param("~index", 0),
                    width=rospy.get_param("~width", 640),
                    height=rospy.get_param("~height", 480),
                    warmup=rospy.get_param("~warmup_frames", 15))
    frame_id = rospy.get_param("~frame_id", "camera")
    rate = rospy.Rate(rospy.get_param("~fps", 15.0))

    if not camera.start():
        rospy.logfatal("camera: %s", camera.last_error)
        return
    rospy.on_shutdown(camera.release)
    rospy.loginfo("camera %d open at %dx%d", camera.index, *camera.resolution)

    pub = rospy.Publisher("~image_raw", Image, queue_size=1)
    failures = 0
    while not rospy.is_shutdown():
        got, frame = camera.read()
        if not got:
            failures += 1
            if failures >= 30:
                rospy.logfatal("camera: %s", camera.last_error)
                return
        else:
            failures = 0
            msg = bgr_to_imgmsg(frame)
            msg.header.stamp = rospy.Time.now()
            msg.header.frame_id = frame_id
            pub.publish(msg)
        rate.sleep()


if __name__ == "__main__":
    try:
        main()
    except rospy.ROSInterruptException:
        pass
