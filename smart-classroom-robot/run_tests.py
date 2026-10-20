r"""Phase 10 - run every test suite and print one verdict.

    venv\Scripts\python.exe run_tests.py
    venv\Scripts\python.exe run_tests.py --quick     # skip camera and YOLO

Suites, in dependency order:

    sketch      compiles classroom_robot.ino with g++ and runs it on this PC
    protocol    diffs the Python simulated Arduino against that compiled sketch
    logic       zones, counting and the NORMAL/WARNING/ALERT machine
    camera      the real webcam (skipped automatically if none is attached)
    detection   YOLO on a real photograph
    dashboard   the real Tk window driven with fake hardware
"""
import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(HERE, "tests")
PYTHON = sys.executable

SUITES = [
    ("protocol", "test_simulator_matches_sketch.py", False),
    ("logic", "test_classroom_logic.py", False),
    ("camera", "test_camera.py", True),
    ("detection", "test_detection.py", True),
    ("dashboard", "test_dashboard.py", False),
]


def build_sketch():
    """Compile the .ino against the Arduino stubs and run its own assertions."""
    gpp = shutil.which("g++")
    if not gpp:
        return None, "g++ not found - install MSYS2/MinGW to run the sketch tests"
    exe = os.path.join(TESTS, "test_sketch.exe")
    cmd = [gpp, "-std=c++17", "-Wall", "-Wextra", "-Wno-unused-parameter",
           "-I" + os.path.join(TESTS, "arduino_stub"),
           "-o", exe, os.path.join(TESTS, "test_sketch.cpp")]
    built = subprocess.run(cmd, capture_output=True, text=True)
    if built.returncode != 0:
        return None, "compile failed:\n" + built.stderr[:800]
    return exe, None


def run(label, cmd, verbose):
    started = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
    elapsed = time.time() - started
    output = result.stdout + result.stderr

    passed = output.count("OK   ")
    failed = output.count("FAIL ")
    skipped = "SKIP" in output

    if verbose or result.returncode != 0:
        print(output.rstrip())

    if result.returncode != 0:
        verdict = "FAILED"
    elif skipped and passed == 0:
        verdict = "skipped"
    else:
        verdict = "passed"

    print("  %-11s %-8s %3d checks%s  %5.1fs"
          % (label, verdict, passed,
             ("  (%d failed)" % failed) if failed else "", elapsed))
    return result.returncode == 0, passed, failed


def main():
    parser = argparse.ArgumentParser(description="Run every test suite.")
    parser.add_argument("--quick", action="store_true",
                        help="skip the camera and YOLO suites")
    parser.add_argument("--verbose", action="store_true", help="print all output")
    args = parser.parse_args()

    print("=" * 66)
    print(" Smart Classroom Assistant Robot - full test run")
    print("=" * 66 + "\n")

    total_pass = total_fail = 0
    failures = []

    print("building the Arduino sketch ...")
    exe, error = build_sketch()
    if error:
        print("  sketch      SKIPPED  %s\n" % error)
    else:
        okay, passed, failed = run("sketch", [exe], args.verbose)
        total_pass += passed
        total_fail += failed
        if not okay:
            failures.append("sketch")
        print()

    for label, script, slow in SUITES:
        if args.quick and slow:
            print("  %-11s skipped  (--quick)" % label)
            continue
        if label == "protocol" and error:
            print("  %-11s skipped  (needs the compiled sketch)" % label)
            continue
        okay, passed, failed = run(label, [PYTHON, os.path.join(TESTS, script)],
                                   args.verbose)
        total_pass += passed
        total_fail += failed
        if not okay:
            failures.append(label)

    print("\n" + "=" * 66)
    if failures:
        print(" %d check(s) FAILED in: %s" % (total_fail, ", ".join(failures)))
        print(" %d passed" % total_pass)
        return 1
    print(" all %d checks passed" % total_pass)
    return 0


if __name__ == "__main__":
    sys.exit(main())
