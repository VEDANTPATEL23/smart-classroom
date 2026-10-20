cmake_minimum_required(VERSION 3.0.2)
project(arm_teleop)

find_package(catkin REQUIRED COMPONENTS
  rospy
  sensor_msgs
)

catkin_package(CATKIN_DEPENDS rospy sensor_msgs)

catkin_install_python(PROGRAMS
  scripts/arm_teleop_node.py
  scripts/arm_serial_driver.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

install(DIRECTORY launch config firmware
  DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION}
)
