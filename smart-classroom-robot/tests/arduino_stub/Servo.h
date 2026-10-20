#pragma once
#include <cstdint>
#include <vector>

/* Records every angle written so a test can assert what the arm actually did. */
class Servo {
 public:
  uint8_t pin = 255;
  int last = -1;
  std::vector<int> history;

  void attach(uint8_t p) { pin = p; }
  void write(int angle) { last = angle; history.push_back(angle); }
  int read() const { return last; }
};
