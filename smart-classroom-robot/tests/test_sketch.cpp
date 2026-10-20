/* Phase 1 test harness: compiles classroom_robot.ino against the stubs and
 * drives it with the same commands you would type into the Serial Monitor. */
#include "arduino_stub/Arduino.h"
#include "arduino_stub/Servo.h"

SerialClass Serial;
unsigned long g_millis = 0;
int g_pins[64] = {0};

#include "../arduino/classroom_robot/classroom_robot.ino"

#include <iostream>
#include <vector>
#include <string>

static int failures = 0;

static void check(bool cond, const std::string &label, const std::string &detail = "") {
    std::cout << (cond ? "OK   " : "FAIL ") << label;
    if (!detail.empty()) std::cout << "  -- " << detail;
    std::cout << "\n";
    if (!cond) failures++;
}

static std::string sendCommand(const std::string &cmd) {
    Serial.tx.clear();
    Serial.feed(cmd + "\n");
    loop();
    std::string out = Serial.tx;
    while (!out.empty() && (out.back() == '\n' || out.back() == '\r')) out.pop_back();
    return out;
}

static std::string anglesNow() {
    std::string s;
    for (int i = 0; i < JOINT_COUNT; i++) {
        s += std::to_string((int)joints[i].current);
        if (i < JOINT_COUNT - 1) s += ",";
    }
    return s;
}

int main(int argc, char **argv) {
    // --repl: read commands on stdin, print "reply|base,shoulder,elbow,gripper"
    // so the Python simulator can be diffed against the real sketch logic.
    if (argc > 1 && std::string(argv[1]) == "--repl") {
        Serial.echo = false;
        setup();
        std::string line;
        while (std::getline(std::cin, line)) {
            if (line.empty()) continue;
            std::string reply = sendCommand(line);
            std::cout << reply << "|" << anglesNow() << std::endl;
        }
        return 0;
    }

    std::cout << "=== Phase 1: Arduino sketch, executed on the PC ===\n\n";

    std::cout << "-- startup --\n";
    Serial.tx.clear();
    setup();
    std::string boot = Serial.tx;
    check(boot.find("READY") != std::string::npos, "prints READY on boot");
    check(anglesNow() == "90,90,90,35", "moves to HOME at startup", anglesNow());
    for (int i = 0; i < JOINT_COUNT; i++) {
        check(joints[i].servo.pin == joints[i].pin,
              std::string("servo attached: ") + joints[i].name,
              "pin " + std::to_string((int)joints[i].servo.pin));
    }
    check(g_pins[PIN_LED_GREEN] == HIGH, "green LED on after boot (status NORMAL)");

    std::cout << "\n-- preset poses --\n";
    struct Case { const char *cmd; const char *expectAngles; };
    std::vector<Case> cases = {
        {"LEFT",    "150,80,100,35"},
        {"CENTER",  "90,75,105,35"},
        {"RIGHT",   "30,80,100,35"},
        {"WARNING", "90,50,140,35"},
        {"CLOSE",   "90,50,140,100"},   // gripper only, arm stays put
        {"OPEN",    "90,50,140,35"},
        {"PICK",    "90,130,60,35"},
        {"HOME",    "90,90,90,35"},
    };
    for (auto &c : cases) {
        std::string reply = sendCommand(c.cmd);
        bool okReply = reply.find(std::string("OK ") + c.cmd) != std::string::npos;
        bool okPose  = anglesNow() == c.expectAngles;
        check(okReply && okPose, std::string("command ") + c.cmd,
              "reply=\"" + reply + "\" angles=" + anglesNow());
    }

    std::cout << "\n-- protocol --\n";
    check(sendCommand("PING") == "PONG", "PING replies PONG");
    check(sendCommand("STATUS").rfind("STATUS ", 0) == 0, "STATUS reports joint angles",
          sendCommand("STATUS"));
    check(sendCommand("home").find("OK HOME") != std::string::npos,
          "commands are case-insensitive");
    check(sendCommand("FLY").find("ERR UNKNOWN") != std::string::npos,
          "unknown command returns ERR", sendCommand("FLY"));
    check(sendCommand("SPEED 25").find("OK SPEED 25") != std::string::npos,
          "SPEED accepted in range");
    check(sendCommand("SPEED 999").find("ERR SPEED") != std::string::npos,
          "SPEED rejected out of range");

    std::cout << "\n-- safety limits --\n";
    sendCommand("SET SHOULDER 999");
    check(joints[SHOULDER].current == joints[SHOULDER].maxAngle,
          "over-limit angle clamps to max",
          std::to_string((int)joints[SHOULDER].current) + " == " +
          std::to_string((int)joints[SHOULDER].maxAngle));
    sendCommand("SET SHOULDER 0");
    check(joints[SHOULDER].current == joints[SHOULDER].minAngle,
          "under-limit angle clamps to min",
          std::to_string((int)joints[SHOULDER].current) + " == " +
          std::to_string((int)joints[SHOULDER].minAngle));
    check(sendCommand("SET WRIST 90").find("ERR SET UNKNOWN JOINT") != std::string::npos,
          "unknown joint rejected");

    bool everySafe = true;
    for (int i = 0; i < JOINT_COUNT; i++) {
        for (int a : joints[i].servo.history) {
            if (a < joints[i].minAngle || a > joints[i].maxAngle) everySafe = false;
        }
    }
    check(everySafe, "EVERY angle ever written stayed inside its joint limits");

    std::cout << "\n-- assist sequence (Phase 8) --\n";
    sendCommand("HOME");
    size_t before = joints[GRIPPER].servo.history.size();
    std::string reply = sendCommand("ASSIST");
    check(reply.find("OK ASSIST") != std::string::npos, "ASSIST completes and acknowledges");
    check(joints[GRIPPER].servo.history.size() > before, "gripper actuated during ASSIST");
    check(anglesNow() == "90,90,90,35", "ASSIST returns the arm to HOME", anglesNow());

    std::cout << "\n-- indicators (Phase 9) --\n";
    sendCommand("NORMAL");
    check(g_pins[PIN_LED_GREEN] == HIGH && g_pins[PIN_LED_RED] == LOW, "NORMAL -> green only");
    sendCommand("WARN_LED");
    check(g_pins[PIN_LED_YELLOW] == HIGH && g_pins[PIN_LED_GREEN] == LOW, "WARN_LED -> yellow only");
    sendCommand("ALERT");
    check(g_pins[PIN_LED_RED] == HIGH && g_pins[PIN_LED_YELLOW] == LOW, "ALERT -> red only");

    std::cout << "\n=== " << (failures ? std::to_string(failures) + " FAILURE(S)" : "all checks passed")
              << " ===\n";
    return failures ? 1 : 0;
}
