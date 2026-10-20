cmake_minimum_required(VERSION 3.0.2)
project(smart_classroom)

find_package(catkin REQUIRED COMPONENTS
  rospy
  std_msgs
  sensor_msgs
  message_generation
)

catkin_python_setup()

add_message_files(FILES
  Detection.msg
  DetectionArray.msg
  ClassroomState.msg
)

add_service_files(FILES
  ArmCommand.srv
)

generate_messages(DEPENDENCIES std_msgs)

catkin_package(CATKIN_DEPENDS rospy std_msgs sensor_msgs message_runtime)

catkin_install_python(PROGRAMS
  scripts/camera_node.py
  scripts/net_camera_node.py
  scripts/detector_node.py
  scripts/classroom_monitor_node.py
  scripts/arm_driver_node.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY launch config models firmware
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)
