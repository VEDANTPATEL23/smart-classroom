# Smart classroom robot - ROS 1 packages

Two catkin packages, converted from the Arduino + Python projects:

| Package | Converted from | What it does |
|---|---|---|
| `arm_teleop` | `trailass.ino` + `joystick_test.py` | drive the 4-servo arm with a joystick |
| `smart_classroom` | `smart-classroom-robot/` | webcam + YOLO watch the room, the arm points at a phone |

Written for ROS Noetic (Python 3) and a catkin workspace.

**The Arduino sketches are unchanged.** Each package has a driver node that owns
the serial port and speaks the protocol the sketch already understood, so the
boards are flashed exactly as before (`firmware/` in each package).

## Install

Copy this whole folder into the `src` of your workspace, then inside the VM:

```bash
cd ~/catkin_ws/24BRS1339/src/smart-classroom-ros
chmod +x arm_teleop/scripts/*.py smart_classroom/scripts/*.py

sudo apt install ros-noetic-joy ros-noetic-rqt-image-view python3-serial python3-pip
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip3 install ultralytics

sudo usermod -aG dialout $USER      # serial port access - log out and back in

cd ~/catkin_ws/24BRS1339
catkin_make
source devel/setup.bash
```

`chmod +x` matters: files copied from Windows lose the executable bit and
`rosrun` / `roslaunch` will not find the nodes without it.

In VirtualBox, pass the hardware through with **Devices > USB** (Arduino,
joystick) and **Devices > Webcams**. The Arduino then shows up as `/dev/ttyACM0`
(or `/dev/ttyUSB0` for a CH340 clone) and the joystick as `/dev/input/js0`.

## arm_teleop

```bash
roslaunch arm_teleop arm_teleop.launch port:=/dev/ttyACM0
```

```
joy_node --/arm/joy--> arm_teleop --/arm/joint_command--> arm_driver --serial--> trailass.ino
                                                              |
                                                              +--/arm/joint_states
```

| Node | Replaces | Role |
|---|---|---|
| `joy` (standard `joy` package) | pygame | reads the controller |
| `arm_teleop_node.py` | the main loop of `joystick_test.py` | stick -> speed -> angle, deadzone, limits |
| `arm_serial_driver.py` | `arduino.write(bytes([...]))` | sends the 4 angle bytes at 115200 baud |

Left X -> base, left Y -> pivot, right Y -> elbow, right X -> end effector, as
before. Limits, speeds, deadzone and axis numbers are in `config/arm.yaml`.

Because the driver listens on a topic, anything can move the arm, not only the
joystick:

```bash
rostopic pub -1 /arm/joint_command sensor_msgs/JointState \
  "{name: [base, pivot, elbow, end_effector], position: [1.57, 2.53, 2.53, 2.06]}"
```

Positions are in radians (the ROS convention); the driver converts to degrees
and clamps to the joint limits.

If a stick moves the wrong joint, run `rostopic echo /arm/joy`, see which axis
changes, and edit `axes` in `arm.yaml`. Flip a direction with `scale`.

## smart_classroom

```bash
roslaunch smart_classroom classroom.launch                    # webcam, arm auto-detected
roslaunch smart_classroom classroom.launch simulate:=true     # no Arduino needed
roslaunch smart_classroom classroom.launch port:=/dev/ttyACM0 simulate:=false
```

```
camera --image_raw--> detector --detections--> monitor --arm/command--> arm_driver --serial--> classroom_robot.ino
                         |                        |                        |
                         +--image_annotated       +--classroom_state       +--arm/joint_states, arm/status, arm/result
```

Everything lives under the `/classroom` namespace.

| Node | Replaces | Role |
|---|---|---|
| `camera_node.py` | `camera.py` in the app loop | webcam -> `camera/image_raw` |
| `detector_node.py` | `detection.py` | YOLOv8n -> `detections`, `image_annotated` |
| `classroom_monitor_node.py` | `classroom_logic.py` + the dashboard's `_react()` | NORMAL / WARNING / ALERT, decides arm commands |
| `arm_driver_node.py` | `controller.py` | serial link to the Uno, or the simulated board |
| `rqt_image_view` | the Tkinter video panel | shows the annotated feed |

`camera.py`, `detection.py`, `classroom_logic.py` and `controller.py` are the
original files, used as a library in `src/smart_classroom/`. Settings moved from
`config.py` to `config/classroom.yaml`.

### Watching and commanding it

```bash
rostopic echo /classroom/classroom_state     # students, phones, status, zone
rostopic echo /classroom/arm/result          # what the arm did
rostopic echo -n1 /classroom/arm/status      # CONNECTED (...) / SIMULATED / DISCONNECTED

# the dashboard's HOME / ASSIST / WARNING buttons
rostopic pub -1 /classroom/arm/command std_msgs/String "data: 'ASSIST'"
rosservice call /classroom/arm/send_command "command: 'SET ELBOW 120'"
```

The topic queues commands; the service waits for the board's answer and returns
it. Both accept any line of the sketch's protocol: `HOME LEFT CENTER RIGHT
WARNING OPEN CLOSE PICK ASSIST NORMAL WARN_LED ALERT`, `SET <JOINT> <ANGLE>`,
`SPEED <ms>`, `PING`, `STATUS`.

### Using the rover's camera in Gazebo

The detector takes any `sensor_msgs/Image` topic, so it can watch through the
simulated rover instead of a webcam:

```bash
roslaunch smart_classroom classroom.launch use_webcam:=false image_topic:=/rover/camera/image_raw
```

### Running in WSL (webcam on Windows)

The WSL kernel has no webcam driver, so there the camera stays on Windows and
is streamed in. Start the ROS side with `net_camera:=true`:

```bash
roslaunch smart_classroom classroom.launch net_camera:=true simulate:=true
```

and on Windows run the sender (needs only `opencv-python`):

```
python smart_classroom\scripts\windows_webcam_sender.py
```

It sends JPEG frames to `localhost:5600`, where `net_camera_node.py` publishes
them as `camera/image_raw`. The Arduino does work in WSL through USB
passthrough: install usbipd-win, then from an administrator PowerShell
`usbipd list`, `usbipd bind --busid <id>` and `usbipd attach --wsl --busid <id>`.

## What has and has not been tested

Checked on Windows against a stand-in for `rospy` (35 checks): the monitor's
status machine and the commands it sends, the arm driver against the simulated
board, teleop integration / limits / stale-joystick stop, the 4-byte serial
packets, image conversion, and real YOLO inference on the sample photo.

Checked in ROS Noetic on WSL 2 (Ubuntu 20.04): `catkin_make` builds both
packages; `classroom.launch` with the simulated arm runs the whole chain from a
still image and from the live Windows webcam through `net_camera:=true`; the
`arm/send_command` service answers.

Not run: `arm_teleop.launch`, and anything on real hardware. As in the original
project, the preset angles and joint limits in `classroom_robot.ino` are
guesses until they are calibrated on the arm.

## Differences from the originals

- The Tkinter dashboard is not ported; `rqt_image_view` and `rostopic echo`
  cover what it showed.
- Arm moves wait up to 10 s for the board's `OK` (`move_timeout`) instead of
  1 s. The sketch only replies once the arm has arrived, and a long sweep takes
  more than a second.
- Teleop stops the arm if the joystick goes silent for 0.5 s.
- Teleop rounds angles to the nearest degree; `joystick_test.py` truncated.
