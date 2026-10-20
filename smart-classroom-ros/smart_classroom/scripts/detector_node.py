#!/usr/bin/env python3
"""YOLO on an image topic.

Subscribes:
    image             sensor_msgs/Image
Publishes:
    detections        smart_classroom/DetectionArray
    image_annotated   sensor_msgs/Image   (boxes and zone lines drawn on)

Same scope as the original detection.py: COCO-pretrained yolov8n, reporting
`person` and `cell phone` and nothing else.
"""
import rospy
from sensor_msgs.msg import Image

from smart_classroom import config
from smart_classroom.detection import Detector
from smart_classroom.image_utils import bgr_to_imgmsg, imgmsg_to_bgr
from smart_classroom.msg import Detection, DetectionArray


class DetectorNode:
    def __init__(self):
        # draw() reads the zone edges from config, so keep it in step with the monitor
        config.ZONE_LEFT_EDGE = rospy.get_param("~zone_left_edge", config.ZONE_LEFT_EDGE)
        config.ZONE_RIGHT_EDGE = rospy.get_param("~zone_right_edge", config.ZONE_RIGHT_EDGE)
        self.every_n = rospy.get_param("~detect_every_n_frames", config.DETECT_EVERY_N_FRAMES)

        self.detector = Detector(
            model_path=rospy.get_param("~model", config.YOLO_MODEL),
            confidence=rospy.get_param("~confidence", config.YOLO_CONFIDENCE),
            imgsz=rospy.get_param("~image_size", config.YOLO_IMAGE_SIZE),
            classes=rospy.get_param("~classes", list(config.DETECT_CLASSES)))

        rospy.loginfo("loading the detection model (a few seconds) ...")
        if not self.detector.load():
            raise RuntimeError(self.detector.last_error)
        rospy.loginfo("detecting: %s", ", ".join(self.detector.supported_classes))

        self.pub_detections = rospy.Publisher("detections", DetectionArray, queue_size=1)
        self.pub_annotated = rospy.Publisher("image_annotated", Image, queue_size=1)
        # queue_size=1 with a big buffer: always work on the newest frame instead
        # of falling further and further behind the camera.
        rospy.Subscriber("image", Image, self.on_image, queue_size=1, buff_size=2 ** 24)

    def on_image(self, msg):
        try:
            frame = imgmsg_to_bgr(msg)
        except ValueError as exc:
            rospy.logerr_throttle(5.0, "detector: %s" % exc)
            return

        detections = self.detector.detect_cached(frame, self.every_n)

        out = DetectionArray()
        out.header = msg.header
        out.image_width = msg.width
        out.image_height = msg.height
        for d in detections:
            out.detections.append(Detection(
                class_name=d["class_name"], confidence=d["confidence"],
                x1=d["x1"], y1=d["y1"], x2=d["x2"], y2=d["y2"],
                center_x=d["center_x"], center_y=d["center_y"]))
        self.pub_detections.publish(out)

        if self.pub_annotated.get_num_connections() > 0:
            annotated = self.detector.draw(frame, detections)
            self.pub_annotated.publish(bgr_to_imgmsg(annotated, msg.header))


if __name__ == "__main__":
    rospy.init_node("detector")
    try:
        DetectorNode()
        rospy.spin()
    except RuntimeError as exc:
        rospy.logfatal("detector: %s", exc)
    except rospy.ROSInterruptException:
        pass
