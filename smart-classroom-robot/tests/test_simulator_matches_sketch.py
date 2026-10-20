r"""Prove the Python SimulatedArduino behaves exactly like the real sketch.

The C++ harness compiles arduino/classroom_robot/classroom_robot.ino and runs it
on this PC. This script feeds the same command script to both the sketch and the
Python simulator and diffs every reply and every joint angle. If they ever drift
apart, developing against the simulator would be building on a lie.

    venv\Scripts\python.exe tests\test_simulator_matches_sketch.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from controller import SimulatedArduino  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SKETCH_EXE = os.path.join(HERE, "test_sketch.exe")

COMMANDS = [
    "PING", "STATUS",
    "HOME", "LEFT", "CENTER", "RIGHT", "WARNING",
    "OPEN", "CLOSE", "OPEN", "PICK", "HOME",
    "home", "LeFt",                       # case-insensitivity
    "SET SHOULDER 999", "SET SHOULDER 0", "SET BASE 45",
    "SET ELBOW 200", "SET GRIPPER 5",
    "SET WRIST 90", "SET",                # bad joint / bad arity
    "SPEED 25", "SPEED 999", "SPEED abc",
    "NORMAL", "WARN_LED", "ALERT",
    "FLY", "", "   ",
    "ASSIST",
    "STATUS",
]


def run_sketch(commands):
    if not os.path.exists(SKETCH_EXE):
        raise SystemExit("build the harness first:\n"
                         "  g++ -std=c++17 -Itests/arduino_stub "
                         "-o tests/test_sketch.exe tests/test_sketch.cpp")
    payload = "\n".join(c for c in commands if c.strip()) + "\n"
    out = subprocess.run([SKETCH_EXE, "--repl"], input=payload, text=True,
                         capture_output=True, timeout=120)
    if out.returncode != 0:
        raise SystemExit("sketch harness failed:\n" + out.stderr)
    rows = []
    for line in out.stdout.splitlines():
        if "|" in line:
            reply, angles = line.rsplit("|", 1)
            rows.append((reply.strip(), angles.strip()))
    return rows


def run_simulator(commands):
    board = SimulatedArduino()
    while board.readline():                     # discard READY + STATUS banner
        pass
    rows = []
    for cmd in commands:
        if not cmd.strip():
            continue
        board.write((cmd + "\n").encode())
        reply = board.readline().decode().strip()
        angles = ",".join(str(board.angles[j]) for j in board.ORDER)
        rows.append((reply, angles))
    return rows


def main():
    live = [c for c in COMMANDS if c.strip()]
    sketch = run_sketch(COMMANDS)
    sim = run_simulator(COMMANDS)

    print("comparing %d commands against the compiled sketch\n" % len(live))
    if len(sketch) != len(sim):
        print("FAIL  reply count differs: sketch=%d simulator=%d" % (len(sketch), len(sim)))
        return 1

    bad = 0
    for cmd, (s_reply, s_ang), (p_reply, p_ang) in zip(live, sketch, sim):
        same = (s_reply == p_reply) and (s_ang == p_ang)
        if not same:
            bad += 1
            print("FAIL mismatch %-20s sketch: %-28s %s" % (cmd, s_reply, s_ang))
            print("               %-20s python: %-28s %s" % ("", p_reply, p_ang))
        else:
            print("OK   match %-20s -> %-28s %s" % (cmd, s_reply, s_ang))

    print()
    if bad:
        print("%d MISMATCH(ES) - the simulator does not match the sketch" % bad)
        return 1
    print("simulator matches the compiled sketch on all %d commands" % len(live))
    return 0


if __name__ == "__main__":
    sys.exit(main())
