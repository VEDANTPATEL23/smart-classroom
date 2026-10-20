# Smart Classroom Assistant Robot 🤖

An integrated robotics and computer vision project combining real-time YOLOv8 object detection, classroom activity monitoring, a 4-DOF robotic arm with safety-constrained Arduino firmware, a Tkinter desktop GUI, and ROS 1 packages.

![Dashboard Preview](smart-classroom-robot/screenshots/phase6_dashboard.png)

---

## 📂 Repository Structure

```text
smart-classroom/
├── smart-classroom-robot/     # Standalone Python + Tkinter + Arduino implementation
│   ├── arduino/               # Arduino firmware (classroom_robot.ino)
│   ├── tests/                 # 150 automated tests (including native C++ sketch tests)
│   ├── ui/                    # Tkinter multi-threaded dashboard
│   ├── app.py                 # Main entrypoint
│   ├── camera.py              # Camera capture & warmup
│   ├── classroom_logic.py     # Classroom state machine (NORMAL / WARNING / ALERT)
│   ├── controller.py          # Serial communication & simulated Arduino fallback
│   ├── detection.py           # YOLOv8 nano inference engine
│   └── requirements.txt       # Python dependencies
│
├── smart-classroom-ros/       # ROS 1 (Noetic) catkin packages
│   ├── arm_teleop/            # Teleoperation package (joystick to 4-DOF arm)
│   └── smart_classroom/       # Full ROS pipeline (camera, detector, monitor, arm driver)
│
└── trailass/                  # Standalone 4-DOF Arduino arm sketch (trailass.ino)
```

---

## 🚀 Features

- **Real-Time Detection:** Uses YOLOv8n to identify persons and cell phones from a live webcam or IP camera feed.
- **Classroom State Engine:** Monitors zones, head counts, and unauthorized phone usage, triggering `NORMAL`, `WARNING`, or `ALERT` states.
- **Physical 4-DOF Robotic Arm:**
  - Base, pivot, elbow, and end-effector servos.
  - Hard constraint limits on every joint to prevent mechanical stall or self-collision.
  - Automated pointing towards detected alert zones.
  - Built-in assist routine (marker/pen pick-and-place).
- **Interactive Tkinter Dashboard:** Multi-threaded desktop interface displaying the annotated camera feed, detection telemetry, arm status, and manual overrides.
- **ROS 1 Noetic Workspace:**
  - Distributed architecture with dedicated nodes for camera, detection, decision logic, and serial driver.
  - Custom ROS messages (`Detection`, `DetectionArray`, `ClassroomState`) and service (`ArmCommand`).
  - Joystick-driven arm teleoperation package.
- **Comprehensive Test Suite:** 150 automated unit and integration tests, including a compiled C++ harness that executes the Arduino sketch logic natively on the host CPU.

---

## 🛠️ Quick Start

### 1. Standalone Python Application (`smart-classroom-robot`)

```bash
cd smart-classroom-robot

# Create virtual environment and install dependencies
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt

# Run setup diagnostic
python check_setup.py

# Launch application
python app.py
```

### 2. ROS 1 Packages (`smart-classroom-ros`)

Copy `smart-classroom-ros` into your catkin workspace's `src` folder:

```bash
cd ~/catkin_ws/src
cp -r /path/to/smart-classroom-ros .

# Install dependencies
sudo apt update
sudo apt install ros-noetic-joy ros-noetic-rqt-image-view python3-serial python3-pip
pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip3 install ultralytics

# Build the workspace
cd ~/catkin_ws
catkin_make
source devel/setup.bash

# Run Classroom Monitor pipeline
roslaunch smart_classroom classroom.launch
```

### 3. Arduino Firmware

- Open `smart-classroom-robot/arduino/classroom_robot/classroom_robot.ino` or `trailass/trailass.ino` in the Arduino IDE.
- Connect your Arduino Uno with the 4-servo shield.
- Select your board and port, then click **Upload**.

---

## 🧪 Testing

Run the test suite inside `smart-classroom-robot`:

```bash
cd smart-classroom-robot
python run_tests.py
```

---

## 📄 License

This project is licensed under the MIT License - see the repository files for details.
